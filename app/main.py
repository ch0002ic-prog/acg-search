from __future__ import annotations

from contextlib import asynccontextmanager
import ipaddress
import logging
import re
import time
from typing import Annotated
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import ArticleRepository
from app.schemas import FeedResponse, InteractionRequest, ProfileUpdateRequest, RefreshResponse, SearchRequest, SourceHealthResponse, SourceHealthRollupsResponse, SourceHealthRunsResponse, UserProfile
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.news import NewsService
from app.services.vector_store import VectorStore
from app.sources.registry import build_sources


NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

MAX_FEED_LIMIT = 50
REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


class CacheControlledStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code: int = 200):
        if settings.disable_http_cache:
            return FileResponse(full_path, status_code=status_code, stat_result=stat_result, headers=NO_CACHE_HEADERS)
        return super().file_response(full_path, stat_result, scope, status_code=status_code)


def build_runtime() -> tuple[ArticleRepository, NewsService, IngestionService]:
    repository = ArticleRepository(settings.db_path)
    repository.init_database()
    vector_store = VectorStore(settings=settings, repository=repository)
    duplicate_ids = repository.prune_duplicate_articles()
    if duplicate_ids:
        vector_store.delete_articles(duplicate_ids)
    orphan_interactions = repository.cleanup_orphan_user_interactions()
    updated_articles = repository.refresh_article_entities()
    if updated_articles:
        vector_store.upsert_articles(updated_articles)
    llm_service = LLMService(settings)
    ingestion_service = IngestionService(
        settings=settings,
        repository=repository,
        vector_store=vector_store,
        llm_service=llm_service,
        sources=build_sources(settings),
    )
    ingestion_service.bootstrap_if_empty()
    news_service = NewsService(repository=repository, vector_store=vector_store, llm_service=llm_service)
    logger.info("Runtime initialized with db=%s and vector backend=%s", settings.db_path, vector_store.backend)
    if orphan_interactions:
        logger.info("Removed %s orphan interaction rows during startup maintenance", orphan_interactions)
    return repository, news_service, ingestion_service


def _normalized_default_feed_limit() -> int:
    return max(1, min(settings.default_feed_limit, MAX_FEED_LIMIT))


def _is_loopback_client(request: Request) -> bool:
    host = request.client.host if request.client else None
    if not host:
        return False
    if host == "testclient" or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _resolve_request_id(request: Request) -> str:
    candidate = (request.headers.get(REQUEST_ID_HEADER) or "").strip()
    if candidate and REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _build_source_health_response(items) -> SourceHealthResponse:
    healthy_count = sum(1 for item in items if item.status == "ok" and not item.stale)
    failing_count = sum(1 for item in items if item.status == "error")
    stale_count = sum(1 for item in items if item.stale)
    return SourceHealthResponse(
        items=items,
        healthy_count=healthy_count,
        failing_count=failing_count,
        stale_count=stale_count,
    )


def _build_source_health_runs_response(items) -> SourceHealthRunsResponse:
    return SourceHealthRunsResponse(items=items)


def _build_source_health_rollups_response(items, window_hours: int) -> SourceHealthRollupsResponse:
    return SourceHealthRollupsResponse(items=items, window_hours=window_hours)


def install_request_timing_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def api_request_timing(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        start = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"
        request_id = _resolve_request_id(request)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "API request failed: request_id=%s method=%s path=%s client=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                client_host,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path in {"/api/search", "/api/refresh"}:
            logger.info(
                "API request completed: request_id=%s method=%s path=%s status=%s client=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                client_host,
                duration_ms,
            )
        if duration_ms >= settings.request_slow_log_ms:
            logger.warning(
                "Slow API request: request_id=%s method=%s path=%s status=%s client=%s duration_ms=%.1f threshold_ms=%s",
                request_id,
                request.method,
                request.url.path,
                response.status_code,
                client_host,
                duration_ms,
                settings.request_slow_log_ms,
            )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    repository, news_service, ingestion_service = build_runtime()
    app.state.repository = repository
    app.state.news_service = news_service
    app.state.ingestion_service = ingestion_service
    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)
install_request_timing_middleware(app)
app.mount("/static", CacheControlledStaticFiles(directory=str(settings.static_dir)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    headers = NO_CACHE_HEADERS if settings.disable_http_cache else None
    return FileResponse(settings.static_dir / "index.html", headers=headers)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/news", response_model=FeedResponse)
def news(
    request: Request,
    limit: Annotated[int | None, Query(ge=1, le=MAX_FEED_LIMIT)] = None,
    user_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> FeedResponse:
    news_service: NewsService = request.app.state.news_service
    return news_service.home_feed(limit=limit or _normalized_default_feed_limit(), user_id=user_id)


@app.post("/api/search", response_model=FeedResponse)
def search(request: Request, payload: SearchRequest) -> FeedResponse:
    news_service: NewsService = request.app.state.news_service
    response = news_service.search(
        query=payload.query,
        limit=payload.limit,
        rerank=payload.rerank,
        user_id=payload.user_id,
        track_profile=payload.track_profile,
    )
    logger.info(
        "Search response ready: request_id=%s query=%r limit=%s result_count=%s rerank=%s user_id_present=%s track_profile=%s",
        _request_id(request),
        payload.query,
        payload.limit,
        len(response.items),
        payload.rerank,
        bool(payload.user_id),
        payload.track_profile,
    )
    return response


@app.get("/api/profile", response_model=UserProfile)
def get_profile(request: Request, user_id: Annotated[str, Query(min_length=1, max_length=64)]) -> UserProfile:
    repository: ArticleRepository = request.app.state.repository
    return repository.get_or_create_user_profile(user_id=user_id)


@app.get("/api/source-health", response_model=SourceHealthResponse)
def source_health(
    request: Request,
    stale_after_hours: Annotated[int | None, Query(ge=1, le=168)] = None,
) -> SourceHealthResponse:
    repository: ArticleRepository = request.app.state.repository
    items = repository.list_source_health(stale_after_hours=stale_after_hours or settings.source_health_stale_hours)
    return _build_source_health_response(items)


@app.get("/api/source-health/runs", response_model=SourceHealthRunsResponse)
def source_health_runs(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    source_name: Annotated[str | None, Query(min_length=1, max_length=160)] = None,
) -> SourceHealthRunsResponse:
    repository: ArticleRepository = request.app.state.repository
    items = repository.list_source_health_runs(limit=limit, source_name=source_name)
    return _build_source_health_runs_response(items)


@app.get("/api/source-health/rollups", response_model=SourceHealthRollupsResponse)
def source_health_rollups(
    request: Request,
    window_hours: Annotated[int, Query(ge=1, le=168)] = 24,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SourceHealthRollupsResponse:
    repository: ArticleRepository = request.app.state.repository
    items = repository.list_source_health_rollups(window_hours=window_hours, limit=limit)
    return _build_source_health_rollups_response(items, window_hours=window_hours)


@app.post("/api/profile", response_model=UserProfile)
def update_profile(request: Request, payload: ProfileUpdateRequest) -> UserProfile:
    repository: ArticleRepository = request.app.state.repository
    return repository.update_user_profile(
        user_id=payload.user_id,
        display_name=payload.display_name,
        pinned_categories=payload.pinned_categories,
        pinned_tags=payload.pinned_tags,
        pinned_entities=payload.pinned_entities,
        pinned_regions=payload.pinned_regions,
    )


@app.post("/api/interactions", response_model=UserProfile)
def record_interaction(request: Request, payload: InteractionRequest) -> UserProfile:
    repository: ArticleRepository = request.app.state.repository
    try:
        return repository.record_interaction(
            user_id=payload.user_id,
            article_id=payload.article_id,
            action=payload.action,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Article not found.") from exc


@app.post("/api/refresh", response_model=RefreshResponse)
def refresh(request: Request) -> RefreshResponse:
    if not settings.allow_remote_refresh and not _is_loopback_client(request):
        host = request.client.host if request.client else "unknown"
        logger.warning("Rejected refresh request from non-local client %s request_id=%s", host, _request_id(request))
        raise HTTPException(status_code=403, detail="Refresh is limited to local requests unless ALLOW_REMOTE_REFRESH=true.")
    ingestion_service: IngestionService = request.app.state.ingestion_service
    return RefreshResponse(**ingestion_service.ingest(request_id=_request_id(request)))
