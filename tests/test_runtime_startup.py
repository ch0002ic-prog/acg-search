from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import ANY
from unittest.mock import patch

import app.main as main_module
from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord, SourceHealthEntry
from app.services.embeddings import EmbeddingRecord, SemanticEmbeddingService
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.sources.base import BaseSource, SourceArticle


class EmptySource(BaseSource):
    def fetch(self, limit: int) -> list[SourceArticle]:
        return []


class StaticSource(BaseSource):
    def __init__(self, articles: list[SourceArticle], **kwargs) -> None:
        super().__init__(**kwargs)
        self._articles = articles

    def fetch(self, limit: int) -> list[SourceArticle]:
        return self._articles[:limit]


class RuntimeStartupTests(unittest.TestCase):
    def test_start_background_llm_warmup_runs_in_daemon_thread(self) -> None:
        test_settings = replace(
            settings,
            llm_provider="ollama",
            llm_base_url="http://127.0.0.1:11434",
            llm_model="qwen2.5:3b",
        )
        llm_service = LLMService(test_settings)

        class InlineThread:
            def __init__(self, target, name: str, daemon: bool) -> None:
                self._target = target
                self.name = name
                self.daemon = daemon

            def start(self) -> None:
                self._target()

        with (
            patch("app.main.threading.Thread", side_effect=InlineThread) as thread_factory,
            patch.object(llm_service, "warmup", return_value=234.5) as llm_warmup,
        ):
            main_module._start_background_llm_warmup(llm_service)

        thread_factory.assert_called_once_with(target=ANY, name="llm-warmup", daemon=True)
        llm_warmup.assert_called_once()

    def test_build_runtime_canonicalizes_stored_google_news_wrapper_articles(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            test_settings = replace(
                settings,
                db_path=base_path / "test-runtime.db",
                vector_dir=base_path / "vector-store",
                data_dir=base_path,
                vector_backend="local",
                llm_provider="none",
                llm_model=None,
                enable_llm_enrichment=False,
            )
            repository = ArticleRepository(test_settings.db_path)
            repository.init_database()
            vector_store = VectorStore(settings=test_settings, repository=repository)
            llm_service = LLMService(test_settings)
            source = EmptySource(
                name="Google News SG Events",
                feed_url="https://example.com/google-events",
                quality=0.74,
                source_type="rss",
                category_hints=["events", "anime"],
                region_hints=["Singapore"],
            )
            ingestion_service = IngestionService(
                settings=test_settings,
                repository=repository,
                vector_store=vector_store,
                llm_service=llm_service,
                sources=[source],
            )
            wrapper_url = (
                "https://news.google.com/rss/articles/"
                "CBMikAFBVV95cUxQbW5oaUNVdTN5MkFaU3FLUGNwQzAxRWJIVFZTUUdncjdFZkE0cHNtdklkQ0ZmQUJrc2FYWjIwMG0xcVNfenFpT3A4dlgtZ2tpaloxcWpkRXJQSGhGb3JsQWtWQ0lXNDJnMUx1UU9yem1GWjFMenNIS18xRzltR3p3S0hncFFpbG9Ram1nYzVDT0g?oc=5"
            )
            canonical_url = "https://danamic.org/2025/11/29/afa-2025-highlights-from-this-years-anime-festival-asia/"
            wrapper_article = ingestion_service._to_article(
                source,
                SourceArticle(
                    title="AFA 2025: Highlights from this year’s Anime Festival Asia - DANAMIC",
                    url=wrapper_url,
                    published_at=datetime.now(timezone.utc) - timedelta(hours=2),
                    summary="AFA highlights story.",
                ),
            )
            repository.upsert_articles([wrapper_article])

            with (
                patch.object(main_module, "settings", test_settings),
                patch.object(main_module, "build_sources", return_value=[]),
                patch("app.services.ingestion.resolve_google_news_url", return_value=canonical_url),
            ):
                runtime_repository, _news_service, _ingestion_service = main_module.build_runtime()

            items = runtime_repository.latest_articles(limit=10)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].url, canonical_url)
            self.assertNotEqual(items[0].id, wrapper_article.id)

    def test_build_runtime_synchronizes_curated_source_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            test_settings = replace(
                settings,
                db_path=base_path / "test-runtime.db",
                vector_dir=base_path / "vector-store",
                data_dir=base_path,
                vector_backend="local",
                llm_provider="none",
                llm_model=None,
                enable_llm_enrichment=False,
            )
            repository = ArticleRepository(test_settings.db_path)
            repository.init_database()
            vector_store = VectorStore(settings=test_settings, repository=repository)
            llm_service = LLMService(test_settings)
            stale_source = StaticSource(
                name="SG Source Pages",
                feed_url="local://curated-sg-search-watch",
                quality=0.8,
                source_type="curated",
                category_hints=["events", "anime"],
                region_hints=["Singapore"],
                articles=[],
            )
            stale_article = IngestionService(
                settings=test_settings,
                repository=repository,
                vector_store=vector_store,
                llm_service=llm_service,
                sources=[stale_source],
            )._to_article(
                stale_source,
                SourceArticle(
                    title="Old curated artist alley fallback",
                    url="https://www.eventbrite.sg/d/singapore--singapore/artist-alley/",
                    published_at=datetime.now(timezone.utc) - timedelta(days=30),
                    summary="Old fallback row.",
                ),
            )
            repository.upsert_articles([stale_article])

            current_source = StaticSource(
                name="SG Source Pages",
                feed_url="local://curated-sg-search-watch",
                quality=0.8,
                source_type="curated",
                category_hints=["events", "anime"],
                region_hints=["Singapore"],
                articles=[
                    SourceArticle(
                        title="AFA Singapore 2026 official event page with creator and cosplay hub updates",
                        url="https://animefestival.asia/afasg26/",
                        published_at=datetime.now(timezone.utc) - timedelta(days=5),
                        summary="Current curated fallback row.",
                    )
                ],
            )

            with (
                patch.object(main_module, "settings", test_settings),
                patch.object(main_module, "build_sources", return_value=[current_source]),
            ):
                runtime_repository, _news_service, _ingestion_service = main_module.build_runtime()

            items = runtime_repository.latest_articles(limit=10)
            urls = [item.url for item in items]

            self.assertIn("https://animefestival.asia/afasg26/", urls)
            self.assertNotIn("https://www.eventbrite.sg/d/singapore--singapore/artist-alley/", urls)

    def test_build_runtime_backfills_semantic_embeddings_when_configured(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            test_settings = replace(
                settings,
                db_path=base_path / "test-runtime.db",
                vector_dir=base_path / "vector-store",
                data_dir=base_path,
                vector_backend="local",
                llm_provider="none",
                llm_model=None,
                enable_llm_enrichment=False,
                embedding_provider="openai_compatible",
                embedding_base_url="https://embeddings.example",
                embedding_model="text-embedding-3-small",
            )
            repository = ArticleRepository(test_settings.db_path)
            repository.init_database()
            vector_store = VectorStore(settings=test_settings, repository=repository)
            llm_service = LLMService(test_settings)
            source = EmptySource(
                name="Bandwagon Asia",
                feed_url="https://example.com/bandwagon",
                quality=0.78,
                source_type="rss",
                category_hints=["events", "anime"],
                region_hints=["Singapore"],
            )
            article = IngestionService(
                settings=test_settings,
                repository=repository,
                vector_store=vector_store,
                llm_service=llm_service,
                sources=[source],
            )._to_article(
                source,
                SourceArticle(
                    title="AFA Singapore creator stage schedule announced",
                    url="https://example.com/afa-stage",
                    published_at=datetime.now(timezone.utc) - timedelta(hours=3),
                    summary="AFA Singapore confirms creator stage segments and headline guests.",
                ),
            )
            repository.upsert_articles([article])
            signature = SemanticEmbeddingService(test_settings).current_signature()

            with (
                patch.object(main_module, "settings", test_settings),
                patch.object(main_module, "build_sources", return_value=[]),
                patch(
                    "app.services.embeddings.SemanticEmbeddingService.embed_documents",
                    return_value=[EmbeddingRecord(vector=[1.0, 0.0], signature=signature)],
                ),
            ):
                runtime_repository, _news_service, _ingestion_service = main_module.build_runtime()

            with runtime_repository.connect() as connection:
                row = connection.execute(
                    "SELECT semantic_embedding, semantic_embedding_signature FROM articles WHERE id = ?",
                    (article.id,),
                ).fetchone()

            self.assertIsNotNone(row)
            self.assertEqual(row["semantic_embedding_signature"], signature)
            self.assertNotEqual(row["semantic_embedding"], "[]")

    def test_build_runtime_applies_newer_deploy_snapshot_over_restored_durable_state(self) -> None:
        class FakeStateStore:
            def __init__(self, restored_db_path: Path) -> None:
                self.restored_db_path = restored_db_path
                self.persist_paths: list[str] = []

            def restore_to(self, db_path: Path) -> bool:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.write_bytes(self.restored_db_path.read_bytes())
                return True

            def persist_from(self, db_path: Path) -> bool:
                self.persist_paths.append(str(db_path))
                return True

        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            test_settings = replace(
                settings,
                db_path=base_path / "runtime.db",
                vector_dir=base_path / "vector-store",
                data_dir=base_path,
                vector_backend="local",
                llm_provider="none",
                llm_model=None,
                enable_llm_enrichment=False,
                warm_local_models_on_startup=False,
            )
            restored_db_path = base_path / "restored.db"
            restored_repository = ArticleRepository(restored_db_path)
            restored_repository.init_database()
            restored_repository.upsert_articles(
                [
                    ArticleRecord(
                        id="stale-article",
                        title="Old Eventbrite snapshot row",
                        url="https://example.com/stale-event",
                        source_name="Old Snapshot Source",
                        source_type="rss",
                        published_at=datetime(2026, 4, 6, 4, 5, tzinfo=timezone.utc),
                        summary="Stale durable-state row.",
                        categories=["events"],
                        tags=["stale"],
                        region_tags=["Singapore"],
                        sg_relevance=0.4,
                        freshness_score=0.1,
                        home_score=0.1,
                        source_quality=0.5,
                    )
                ]
            )
            restored_repository.record_source_health(
                source_name="Old Snapshot Source",
                status="ok",
                fetched_count=5,
                persisted_count=5,
                error_count=0,
                ran_at=datetime(2026, 4, 6, 4, 5, tzinfo=timezone.utc),
            )

            deploy_article = ArticleRecord(
                id="fresh-article",
                title="Fresh deploy snapshot row",
                url="https://example.com/fresh-deploy-article",
                source_name="Snapshot Source",
                source_type="rss",
                published_at=datetime(2026, 4, 13, 4, 23, tzinfo=timezone.utc),
                summary="Fresh bundled deploy snapshot row.",
                categories=["news"],
                tags=["deploy"],
                region_tags=["Singapore"],
                sg_relevance=0.9,
                freshness_score=0.95,
                home_score=0.95,
                source_quality=0.8,
            )
            deploy_source_health = SourceHealthEntry(
                source_name="Snapshot Source",
                status="ok",
                fetched_count=12,
                persisted_count=12,
                error_count=0,
                consecutive_failures=0,
                last_run_at=datetime(2026, 4, 13, 4, 23, tzinfo=timezone.utc),
                last_success_at=datetime(2026, 4, 13, 4, 23, tzinfo=timezone.utc),
                last_error=None,
                stale=False,
            )
            (base_path / "deploy_articles.json").write_text(
                json.dumps([deploy_article.model_dump(mode="json")], indent=2),
                encoding="utf-8",
            )
            (base_path / "deploy_source_health.json").write_text(
                json.dumps([deploy_source_health.model_dump(mode="json")], indent=2),
                encoding="utf-8",
            )

            current_source = EmptySource(
                name="Snapshot Source",
                feed_url="https://example.com/snapshot-source",
                quality=0.82,
                source_type="rss",
                category_hints=["news"],
                region_hints=["Singapore"],
            )
            state_store = FakeStateStore(restored_db_path)

            with (
                patch.object(main_module, "settings", test_settings),
                patch.object(main_module, "build_sources", return_value=[current_source]),
            ):
                runtime_repository, _news_service, _ingestion_service = main_module.build_runtime(state_store=state_store)

            source_health_items = runtime_repository.list_source_health(
                stale_after_hours=24,
                now=datetime(2026, 4, 13, 5, 23, tzinfo=timezone.utc),
            )
            articles = runtime_repository.latest_articles(limit=10)

            self.assertEqual([item.source_name for item in source_health_items], ["Snapshot Source"])
            self.assertEqual(source_health_items[0].last_run_at, deploy_source_health.last_run_at)
            self.assertFalse(source_health_items[0].stale)
            self.assertIn("https://example.com/fresh-deploy-article", [item.url for item in articles])
            self.assertEqual(state_store.persist_paths, [str(test_settings.db_path)])

    def test_build_runtime_warms_local_ollama_models_when_enabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir)
            test_settings = replace(
                settings,
                db_path=base_path / "test-runtime.db",
                vector_dir=base_path / "vector-store",
                data_dir=base_path,
                vector_backend="local",
                llm_provider="ollama",
                llm_base_url="http://127.0.0.1:11434",
                llm_model="qwen2.5:3b",
                enable_llm_enrichment=False,
                embedding_provider="ollama",
                embedding_base_url="http://127.0.0.1:11434",
                embedding_model="nomic-embed-text",
                warm_local_models_on_startup=True,
            )

            with (
                patch.object(main_module, "settings", test_settings),
                patch.object(main_module, "build_sources", return_value=[]),
                patch("app.main.SemanticEmbeddingService.warmup", return_value=123.4) as embedding_warmup,
                patch("app.main._start_background_llm_warmup") as llm_warmup,
            ):
                _runtime_repository, _news_service, _ingestion_service = main_module.build_runtime()

            embedding_warmup.assert_called_once()
            llm_warmup.assert_called_once()


if __name__ == "__main__":
    unittest.main()