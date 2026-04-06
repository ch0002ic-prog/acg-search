from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.dedupe import normalize_dedupe_title
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.ranking import compute_home_score, score_freshness
from app.services.vector_store import VectorStore
from app.sources.base import BaseSource, SourceArticle


class FakeSource(BaseSource):
    def __init__(self, articles: list[SourceArticle], **kwargs) -> None:
        super().__init__(**kwargs)
        self._articles = articles

    def fetch(self, limit: int) -> list[SourceArticle]:
        return self._articles[:limit]


class DeduplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = TemporaryDirectory()
        base_path = Path(cls.temp_dir.name)
        cls.test_settings = replace(
            settings,
            db_path=base_path / "test-articles.db",
            vector_dir=base_path / "vector-store",
            data_dir=base_path,
            vector_backend="local",
            llm_provider="none",
            llm_model=None,
            enable_llm_enrichment=False,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        if self.test_settings.db_path.exists():
            self.test_settings.db_path.unlink()
        if self.test_settings.vector_dir.exists():
            shutil.rmtree(self.test_settings.vector_dir)
        self.repository = ArticleRepository(self.test_settings.db_path)
        self.repository.init_database()
        self.vector_store = VectorStore(settings=self.test_settings, repository=self.repository)
        self.llm_service = LLMService(self.test_settings)

    def make_article(
        self,
        article_id: str,
        title: str,
        url: str,
        source_name: str,
        source_type: str,
        published_at: datetime,
        summary: str = "",
        content: str = "",
        source_quality: float = 0.78,
    ) -> ArticleRecord:
        freshness = score_freshness(published_at)
        return ArticleRecord(
            id=article_id,
            title=title,
            url=url,
            source_name=source_name,
            source_type=source_type,
            published_at=published_at,
            summary=summary,
            content=content or summary,
            categories=["events", "anime"],
            tags=["singapore"],
            region_tags=["Singapore"],
            sg_relevance=0.6,
            freshness_score=freshness,
            home_score=compute_home_score(
                freshness_score=freshness,
                sg_relevance=0.6,
                categories=["events", "anime"],
                source_quality=source_quality,
            ),
            source_quality=source_quality,
        )

    def test_event_listing_titles_normalize_to_same_dedupe_key(self) -> None:
        base = normalize_dedupe_title(
            "Manga Drawing - Art Workshop Experience 动漫绘画工作坊",
            source_type="event_listing",
            source_name="Eventbrite SG Anime",
        )
        variant = normalize_dedupe_title(
            "Manga Drawing - Art Workshop Experience 动漫绘画工作坊 (Fri.周五）",
            source_type="event_listing",
            source_name="Eventbrite SG Anime",
        )
        self.assertEqual(base, variant)

    def test_prune_duplicate_articles_keeps_cleanest_representative(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="plain",
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊",
                    url="https://example.com/plain",
                    source_name="Eventbrite SG Anime",
                    source_type="event_listing",
                    published_at=now + timedelta(days=1),
                    summary="Base listing for the workshop series.",
                ),
                self.make_article(
                    article_id="fri",
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊 (Fri.周五）",
                    url="https://example.com/fri",
                    source_name="Eventbrite SG Anime",
                    source_type="event_listing",
                    published_at=now + timedelta(days=2),
                    summary="Friday listing for the workshop series.",
                ),
                self.make_article(
                    article_id="wed",
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊 (Wed.周三）",
                    url="https://example.com/wed",
                    source_name="Eventbrite SG Anime",
                    source_type="event_listing",
                    published_at=now + timedelta(days=3),
                    summary="Wednesday listing for the workshop series.",
                ),
            ]
        )

        deleted_ids = self.repository.prune_duplicate_articles()
        items = self.repository.latest_articles(limit=10)

        self.assertEqual(set(deleted_ids), {"fri", "wed"})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Manga Drawing - Art Workshop Experience 动漫绘画工作坊")

    def test_prune_duplicate_articles_prefers_external_url_over_internal_relative_url(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="placeholder-curated",
                    title="HoyoFest Singapore watch for HoYoVerse merch booths and cafe drops",
                    url="https://example.com/curated/hoyofest-singapore-watch",
                    source_name="SG Source Pages",
                    source_type="curated",
                    published_at=now,
                    summary="Curated Singapore watch entry for HoyoFest coverage.",
                ),
                self.make_article(
                    article_id="internal-curated",
                    title="HoyoFest Singapore watch for HoYoVerse merch booths and cafe drops",
                    url="/?query=HoyoFest%20Singapore",
                    source_name="SG Source Pages",
                    source_type="curated",
                    published_at=now,
                    summary="Curated Singapore watch entry for HoyoFest coverage.",
                ),
            ]
        )

        deleted_ids = self.repository.prune_duplicate_articles()
        items = self.repository.latest_articles(limit=10)

        self.assertEqual(deleted_ids, ["internal-curated"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://example.com/curated/hoyofest-singapore-watch")

    def test_prune_non_external_articles_removes_internal_relative_urls(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="external-story",
                    title="Official HoyoFest Singapore story",
                    url="https://example.com/hoyofest-official",
                    source_name="Bandwagon Asia",
                    source_type="rss",
                    published_at=now,
                    summary="Official HoyoFest story.",
                ),
                self.make_article(
                    article_id="internal-story",
                    title="Internal HoyoFest watch note",
                    url="/?query=HoyoFest%20Singapore",
                    source_name="Prototype Seed",
                    source_type="seed",
                    published_at=now,
                    summary="Internal watch note.",
                ),
            ]
        )

        deleted_ids = self.repository.prune_non_external_articles()
        items = self.repository.latest_articles(limit=10)

        self.assertEqual(deleted_ids, ["internal-story"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "external-story")

    def test_prune_duplicate_articles_remaps_interactions_to_keeper(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="plain",
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊",
                    url="https://example.com/plain",
                    source_name="Eventbrite SG Anime",
                    source_type="event_listing",
                    published_at=now + timedelta(days=1),
                    summary="Base listing for the workshop series.",
                ),
                self.make_article(
                    article_id="fri",
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊 (Fri.周五）",
                    url="https://example.com/fri",
                    source_name="Eventbrite SG Anime",
                    source_type="event_listing",
                    published_at=now + timedelta(days=2),
                    summary="Friday listing for the workshop series.",
                ),
            ]
        )
        self.repository.record_interaction(user_id="fan-1", article_id="fri", action="open")

        deleted_ids = self.repository.prune_duplicate_articles()

        with self.repository.connect() as connection:
            rows = connection.execute(
                "SELECT article_id FROM user_interactions WHERE user_id = ? AND action = 'open'",
                ("fan-1",),
            ).fetchall()

        self.assertEqual(deleted_ids, ["fri"])
        self.assertEqual([str(row["article_id"]) for row in rows], ["plain"])

    def test_cleanup_orphan_user_interactions_removes_stale_rows(self) -> None:
        with self.repository.connect() as connection:
            connection.execute(
                "INSERT INTO user_interactions (user_id, article_id, action) VALUES (?, ?, ?)",
                ("fan-1", "missing-article", "open"),
            )
            connection.commit()

        deleted = self.repository.cleanup_orphan_user_interactions()

        with self.repository.connect() as connection:
            remaining = connection.execute("SELECT COUNT(*) AS count FROM user_interactions").fetchone()

        self.assertEqual(deleted, 1)
        self.assertEqual(int(remaining["count"]), 0)

    def test_ingestion_collapses_recurring_event_variants(self) -> None:
        now = datetime.now(timezone.utc)
        source = FakeSource(
            name="Eventbrite SG Anime",
            feed_url="https://example.com/anime",
            quality=0.78,
            source_type="event_listing",
            category_hints=["events", "anime"],
            region_hints=["Singapore"],
            articles=[
                SourceArticle(
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊 (Fri.周五）",
                    url="https://example.com/fri",
                    published_at=now + timedelta(days=2),
                    summary="Friday workshop listing.",
                ),
                SourceArticle(
                    title="Manga Drawing - Art Workshop Experience 动漫绘画工作坊",
                    url="https://example.com/base",
                    published_at=now + timedelta(days=1),
                    summary="Base workshop listing.",
                ),
                SourceArticle(
                    title="Otaket 2026: Jumpstart",
                    url="https://example.com/otaket",
                    published_at=now + timedelta(days=5),
                    summary="Anime community event in Singapore.",
                ),
            ],
        )
        ingestion_service = IngestionService(
            settings=self.test_settings,
            repository=self.repository,
            vector_store=self.vector_store,
            llm_service=self.llm_service,
            sources=[source],
        )

        result = ingestion_service.ingest(limit_per_source=10)
        items = self.repository.latest_articles(limit=10)
        titles = {item.title for item in items}

        self.assertEqual(result["fetched"], 2)
        self.assertEqual(len(items), 2)
        self.assertIn("Manga Drawing - Art Workshop Experience 动漫绘画工作坊", titles)
        self.assertIn("Otaket 2026: Jumpstart", titles)