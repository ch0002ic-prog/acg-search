from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
import os


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _default_data_dir(root_dir: Path) -> Path:
    # Vercel functions can only write under /tmp; local defaults stay under the repo.
    if _as_bool(os.getenv("VERCEL"), False) or os.getenv("VERCEL_ENV"):
        return Path("/tmp/acg-search")
    return root_dir / "data"


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    data_dir: Path
    db_path: Path
    database_url: str | None
    state_snapshot_key: str
    state_store_connect_timeout_seconds: int
    vector_dir: Path
    static_dir: Path
    project_name: str
    request_timeout_seconds: float
    llm_timeout_seconds: float
    llm_max_tokens: int
    llm_cache_ttl_seconds: int
    llm_cache_max_entries: int
    embedding_timeout_seconds: float
    request_slow_log_ms: int
    source_health_stale_hours: int
    source_health_runs_retention_days: int
    source_limit_per_feed: int
    default_feed_limit: int
    local_vector_prefilter_limit: int
    vector_backend: str
    chroma_collection: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str | None
    enable_llm_enrichment: bool
    enable_full_text_fetch: bool
    disable_http_cache: bool
    allow_remote_refresh: bool
    embedding_provider: str = "none"
    embedding_base_url: str = "http://localhost:11434"
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    embedding_batch_size: int = 12

    @classmethod
    def from_env(cls) -> "Settings":
        root_dir = Path(__file__).resolve().parent.parent
        data_dir = Path(os.getenv("DATA_DIR", _default_data_dir(root_dir))).expanduser().resolve()
        db_path = Path(os.getenv("DB_PATH", data_dir / "articles.db")).expanduser().resolve()
        vector_dir = Path(os.getenv("VECTOR_DIR", data_dir / "vector-store")).expanduser().resolve()
        static_dir = Path(os.getenv("STATIC_DIR", root_dir / "app" / "static")).expanduser().resolve()

        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            db_path=db_path,
            database_url=_clean_optional(os.getenv("DATABASE_URL")),
            state_snapshot_key=os.getenv("STATE_SNAPSHOT_KEY", "acg-search-runtime").strip() or "acg-search-runtime",
            state_store_connect_timeout_seconds=int(os.getenv("STATE_STORE_CONNECT_TIMEOUT_SECONDS", "10")),
            vector_dir=vector_dir,
            static_dir=static_dir,
            project_name=os.getenv("PROJECT_NAME", "ACG Search SG"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "10")),
            llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))),
            llm_max_tokens=max(int(os.getenv("LLM_MAX_TOKENS", "256")), 32),
            llm_cache_ttl_seconds=max(int(os.getenv("LLM_CACHE_TTL_SECONDS", "900")), 0),
            llm_cache_max_entries=max(int(os.getenv("LLM_CACHE_MAX_ENTRIES", "256")), 1),
            embedding_timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", os.getenv("REQUEST_TIMEOUT_SECONDS", "45"))),
            request_slow_log_ms=int(os.getenv("REQUEST_SLOW_LOG_MS", "750")),
            source_health_stale_hours=int(os.getenv("SOURCE_HEALTH_STALE_HOURS", "24")),
            source_health_runs_retention_days=int(os.getenv("SOURCE_HEALTH_RUNS_RETENTION_DAYS", "30")),
            source_limit_per_feed=int(os.getenv("SOURCE_LIMIT_PER_FEED", "12")),
            default_feed_limit=int(os.getenv("DEFAULT_FEED_LIMIT", "12")),
            local_vector_prefilter_limit=int(os.getenv("LOCAL_VECTOR_PREFILTER_LIMIT", "400")),
            vector_backend=os.getenv("VECTOR_BACKEND", "local").strip().lower(),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "acg_news"),
            llm_provider=os.getenv("LLM_PROVIDER", "none").strip().lower(),
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_api_key=os.getenv("LLM_API_KEY"),
            llm_model=os.getenv("LLM_MODEL"),
            enable_llm_enrichment=_as_bool(os.getenv("ENABLE_LLM_ENRICHMENT"), False),
            enable_full_text_fetch=_as_bool(os.getenv("ENABLE_FULL_TEXT_FETCH"), False),
            disable_http_cache=_as_bool(os.getenv("DISABLE_HTTP_CACHE"), True),
            allow_remote_refresh=_as_bool(os.getenv("ALLOW_REMOTE_REFRESH"), False),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "none").strip().lower(),
            embedding_base_url=os.getenv("EMBEDDING_BASE_URL", os.getenv("LLM_BASE_URL", "http://localhost:11434")),
            embedding_api_key=_clean_optional(os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")),
            embedding_model=_clean_optional(os.getenv("EMBEDDING_MODEL")),
            embedding_batch_size=max(int(os.getenv("EMBEDDING_BATCH_SIZE", "12")), 1),
        )


settings = Settings.from_env()
