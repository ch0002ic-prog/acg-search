from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import app.main as main_module
from app.config import settings
from app.database import ArticleRepository
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
                        title="AFA Singapore 2025 official event page with creator and artist alley updates",
                        url="https://animefestival.asia/afasg25/",
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

            self.assertIn("https://animefestival.asia/afasg25/", urls)
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


if __name__ == "__main__":
    unittest.main()