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
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.vector_store import VectorStore
from app.sources.base import BaseSource, SourceArticle


class EmptySource(BaseSource):
    def fetch(self, limit: int) -> list[SourceArticle]:
        return []


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


if __name__ == "__main__":
    unittest.main()