from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import logging
from typing import Any

import httpx

from app.config import Settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.dedupe import article_dedupe_key, article_preference_signature
from app.services.entities import infer_entity_tags
from app.services.event_metadata import infer_event_metadata, merge_event_metadata
from app.services.llm import LLMService
from app.services.ranking import (
    compute_home_score,
    infer_categories,
    infer_region_tags,
    infer_tags,
    score_freshness,
    score_singapore_relevance,
    strip_text,
)
from app.services.sample_data import load_sample_articles, load_source_health_snapshot
from app.services.vector_store import VectorStore
from app.url_utils import is_external_http_url
from app.sources.base import BaseSource, SourceArticle
from app.sources.rss import RSS_REQUEST_HEADERS, resolve_google_news_url


logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        settings: Settings,
        repository: ArticleRepository,
        vector_store: VectorStore,
        llm_service: LLMService,
        sources: list[BaseSource],
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.vector_store = vector_store
        self.llm_service = llm_service
        self.sources = sources

    def bootstrap_if_empty(self) -> None:
        if self.repository.count_articles() == 0:
            articles = load_sample_articles(self.settings.data_dir)
            self.repository.upsert_articles(articles)
            self.vector_store.upsert_articles(articles)

        if self.repository.count_source_health() == 0:
            source_health_entries = load_source_health_snapshot(self.settings.data_dir)
            self.repository.bootstrap_source_health(source_health_entries, request_id="deploy-snapshot")

    def ingest(self, limit_per_source: int | None = None, request_id: str | None = None) -> dict[str, Any]:
        limit = limit_per_source or self.settings.source_limit_per_feed
        collected_by_key: dict[str, ArticleRecord] = {}
        errors: list[str] = []
        seen_urls: set[str] = set()
        curated_urls_by_source: dict[str, set[str]] = {}
        source_runs: dict[str, dict[str, Any]] = {}
        logger.info(
            "Refresh ingest started: request_id=%s limit_per_source=%s source_count=%s",
            request_id or "none",
            limit,
            len(self.sources),
        )

        for source in self.sources:
            source_runs[source.name] = {
                "status": "ok",
                "fetched_count": 0,
                "error_count": 0,
                "last_error": None,
                "ran_at": datetime.now(timezone.utc),
            }
            try:
                fetched_items = source.fetch(limit=limit)[:limit]
                source_runs[source.name]["fetched_count"] = len(fetched_items)
                if source.source_type == "curated":
                    curated_urls_by_source[source.name] = set()
                for item in fetched_items:
                    if not source.matches(item):
                        continue
                    if not is_external_http_url(item.url):
                        continue
                    if source.source_type == "curated":
                        curated_urls_by_source[source.name].add(item.url)
                    if item.url in seen_urls:
                        continue
                    seen_urls.add(item.url)
                    article = self._to_article(source, item)
                    dedupe_key = article_dedupe_key(article)
                    existing = collected_by_key.get(dedupe_key)
                    if existing is None or article_preference_signature(article) > article_preference_signature(existing):
                        collected_by_key[dedupe_key] = article
            except Exception as exc:
                errors.append(f"{source.name}: {exc}")
                source_runs[source.name].update(status="error", error_count=1, last_error=str(exc))
                logger.warning(
                    "Source ingestion failed for %s request_id=%s.",
                    source.name,
                    request_id or "none",
                    exc_info=exc,
                )

        collected = list(collected_by_key.values())
        seed_used = False
        if not collected and self.repository.count_articles() == 0:
            collected = load_sample_articles(self.settings.data_dir)
            seed_used = True

        self.repository.upsert_articles(collected)
        self.vector_store.upsert_articles(collected)
        stale_curated_ids = self.synchronize_curated_source_articles(curated_urls_by_source=curated_urls_by_source)
        canonicalized_articles, canonicalized_old_ids = self.canonicalize_google_news_wrapper_articles()
        duplicate_ids = self.repository.prune_duplicate_articles()
        mismatch_ids = self._prune_source_mismatches()
        self.vector_store.delete_articles(duplicate_ids + mismatch_ids)
        persisted_by_source = Counter(article.source_name for article in collected)
        self.repository.record_source_health_batch(
            [
                {
                    "source_name": source.name,
                    "status": source_runs[source.name]["status"],
                    "fetched_count": source_runs[source.name]["fetched_count"],
                    "persisted_count": persisted_by_source.get(source.name, 0) if source_runs[source.name]["status"] == "ok" else 0,
                    "error_count": source_runs[source.name]["error_count"],
                    "last_error": source_runs[source.name]["last_error"],
                    "ran_at": source_runs[source.name]["ran_at"],
                    "request_id": request_id,
                }
                for source in self.sources
            ],
            retention_days=self.settings.source_health_runs_retention_days,
        )
        result = {
            "fetched": len(collected),
            "persisted": len(collected),
            "seed_used": seed_used,
            "errors": errors,
        }
        logger.info(
            "Refresh ingest completed: request_id=%s fetched=%s persisted=%s seed_used=%s errors=%s canonicalized=%s stale_curated_pruned=%s duplicates_pruned=%s mismatches_pruned=%s",
            request_id or "none",
            result["fetched"],
            result["persisted"],
            seed_used,
            len(errors),
            len(canonicalized_old_ids),
            len(stale_curated_ids),
            len(duplicate_ids),
            len(mismatch_ids),
        )
        return result

    def synchronize_curated_source_articles(
        self,
        curated_urls_by_source: dict[str, set[str]] | None = None,
        limit_per_source: int | None = None,
    ) -> list[str]:
        authoritative_sources = [source for source in self.sources if source.source_type == "curated"]
        if not authoritative_sources:
            return []

        if curated_urls_by_source is None:
            curated_urls_by_source = {}
            current_articles: list[ArticleRecord] = []
            fetch_limit = max(limit_per_source or self.settings.source_limit_per_feed, 200)
            for source in authoritative_sources:
                current_urls: set[str] = set()
                for item in source.fetch(limit=fetch_limit)[:fetch_limit]:
                    if not source.matches(item):
                        continue
                    if not is_external_http_url(item.url):
                        continue
                    current_urls.add(item.url)
                    current_articles.append(self._to_article(source, item))
                curated_urls_by_source[source.name] = current_urls

            if current_articles:
                self.repository.upsert_articles(current_articles)
                self.vector_store.upsert_articles(current_articles)

        deleted_ids = self._prune_stale_curated_source_articles(curated_urls_by_source)
        if deleted_ids:
            self.vector_store.delete_articles(deleted_ids)
        return deleted_ids

    def canonicalize_google_news_wrapper_articles(self) -> tuple[list[ArticleRecord], list[str]]:
        canonicalized_articles, deleted_ids = self._canonicalize_google_news_wrapper_articles()
        if canonicalized_articles:
            self.vector_store.upsert_articles(canonicalized_articles)
        if deleted_ids:
            self.vector_store.delete_articles(deleted_ids)
        return canonicalized_articles, deleted_ids

    def _canonicalize_google_news_wrapper_articles(self) -> tuple[list[ArticleRecord], list[str]]:
        wrapper_articles = self.repository.list_google_news_wrapper_articles()
        if not wrapper_articles:
            return [], []

        replacements: list[tuple[str, ArticleRecord]] = []
        with httpx.Client(
            headers=RSS_REQUEST_HEADERS,
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            for article in wrapper_articles:
                resolved_url = resolve_google_news_url(article.url, client=client)
                if resolved_url == article.url or not is_external_http_url(resolved_url):
                    continue

                replacements.append(
                    (
                        article.id,
                        article.model_copy(
                            update={
                                "id": hashlib.sha1(resolved_url.encode("utf-8")).hexdigest(),
                                "url": resolved_url,
                            }
                        ),
                    )
                )

        if not replacements:
            return [], []

        deleted_ids = self.repository.replace_articles(replacements)
        return [article for _, article in replacements], deleted_ids

    def _to_article(self, source: BaseSource, item: SourceArticle) -> ArticleRecord:
        content = item.content or item.summary
        if self.settings.enable_full_text_fetch and len(content) < 180:
            content = self._fetch_article_text(item.url) or content

        summary, llm_categories, llm_tags = self.llm_service.summarize_and_tag(item.title, content)
        categories = list(dict.fromkeys(source.category_hints + item.category_hints + llm_categories + infer_categories(item.title, summary, content)))
        tags = list(dict.fromkeys(llm_tags + infer_tags(item.title, summary, content)))
        entity_tags = infer_entity_tags(item.title, summary)
        region_tags = list(dict.fromkeys(source.region_hints + item.region_hints + infer_region_tags(item.title, summary, content)))
        sg_relevance = score_singapore_relevance(item.title, summary, content, " ".join(region_tags), " ".join(tags))
        freshness_score = score_freshness(item.published_at)
        home_score = compute_home_score(
            freshness_score=freshness_score,
            sg_relevance=sg_relevance,
            categories=categories,
            source_quality=source.quality,
        )
        inferred_event_metadata = infer_event_metadata(
            title=item.title,
            summary=summary,
            content=content,
            source_type=source.source_type,
            published_at=item.published_at.astimezone(timezone.utc),
            url=item.url,
            source_name=source.name,
        )

        article_id = hashlib.sha1(item.url.encode("utf-8")).hexdigest()
        return ArticleRecord(
            id=article_id,
            title=strip_text(item.title),
            url=item.url,
            source_name=source.name,
            source_type=source.source_type,
            published_at=item.published_at.astimezone(timezone.utc),
            summary=strip_text(summary),
            content=strip_text(content),
            categories=categories,
            tags=tags,
            entity_tags=entity_tags,
            region_tags=region_tags,
            sg_relevance=sg_relevance,
            freshness_score=freshness_score,
            home_score=home_score,
            source_quality=source.quality,
            image_url=item.image_url,
            event_metadata=merge_event_metadata(item.event_metadata, inferred_event_metadata),
        )

    def _prune_source_mismatches(self) -> list[str]:
        cleanup_sources = {
            source.name: source
            for source in self.sources
            if source.cleanup_mismatches and (source.include_keywords or source.exclude_keywords)
        }
        if not cleanup_sources:
            return []

        stored_articles = self.repository.list_articles_by_source_names(list(cleanup_sources))
        delete_ids: list[str] = []
        for article in stored_articles:
            source = cleanup_sources.get(article.source_name)
            if source is None:
                continue
            source_article = SourceArticle(
                title=article.title,
                url=article.url,
                published_at=article.published_at,
                summary=article.summary,
                content=article.content,
                category_hints=list(article.categories),
                region_hints=list(article.region_tags),
                image_url=article.image_url,
                event_metadata=article.event_metadata,
            )
            if not source.matches(source_article):
                delete_ids.append(article.id)

        self.repository.delete_articles(delete_ids)
        return delete_ids

    def _prune_stale_curated_source_articles(self, curated_urls_by_source: dict[str, set[str]]) -> list[str]:
        if not curated_urls_by_source:
            return []

        stored_articles = self.repository.list_articles_by_source_names(list(curated_urls_by_source))
        delete_ids = [
            article.id
            for article in stored_articles
            if article.url not in curated_urls_by_source.get(article.source_name, set())
        ]
        self.repository.delete_articles(delete_ids)
        return delete_ids

    def _fetch_article_text(self, url: str) -> str:
        try:
            response = httpx.get(url, timeout=self.settings.request_timeout_seconds, follow_redirects=True)
            response.raise_for_status()
            html = response.text
        except Exception as exc:
            logger.debug("Full-text fetch failed for %s; keeping original summary/content.", url, exc_info=exc)
            return ""

        try:
            from bs4 import BeautifulSoup
        except Exception as exc:
            logger.debug("BeautifulSoup unavailable for full-text fetch fallback.", exc_info=exc)
            return ""

        soup = BeautifulSoup(html, "html.parser")
        paragraphs = [paragraph.get_text(" ", strip=True) for paragraph in soup.find_all("p")]
        return strip_text(" ".join(paragraphs[:10]))
