from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.entities import build_entity_groups, infer_entity_tags
from app.services.llm import LLMService
from app.services.news import NewsService
from app.services.ranking import compute_home_score, score_freshness
from app.services.vector_store import VectorStore


class EntityNormalizationTests(unittest.TestCase):
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
        self.repository = ArticleRepository(self.test_settings.db_path)
        self.repository.init_database()
        self.vector_store = VectorStore(settings=self.test_settings, repository=self.repository)
        self.llm_service = LLMService(self.test_settings)
        self.news_service = NewsService(
            repository=self.repository,
            vector_store=self.vector_store,
            llm_service=self.llm_service,
        )

    def make_article(
        self,
        article_id: str,
        title: str,
        summary: str,
        source_name: str,
        entity_tags: list[str],
        published_at: datetime,
    ) -> ArticleRecord:
        freshness = score_freshness(published_at)
        return ArticleRecord(
            id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            source_name=source_name,
            source_type="rss",
            published_at=published_at,
            summary=summary,
            content=summary,
            categories=["events", "anime"],
            tags=["singapore"],
            entity_tags=entity_tags,
            region_tags=["Singapore"],
            sg_relevance=0.74,
            freshness_score=freshness,
            home_score=compute_home_score(
                freshness_score=freshness,
                sg_relevance=0.74,
                categories=["events", "anime"],
                source_quality=0.78,
            ),
            source_quality=0.78,
        )

    def test_infer_entity_tags_normalizes_event_aliases(self) -> None:
        from_acronym = infer_entity_tags("AFA Singapore guest lineup announced")
        from_full_name = infer_entity_tags("Anime Festival Asia Singapore 2025 Is Back")
        self.assertIn("AFA Singapore", from_acronym)
        self.assertEqual(from_acronym, from_full_name)

    def test_infer_entity_tags_normalizes_poppa_mmq_and_ani_idol_aliases(self) -> None:
        from_poppa = infer_entity_tags("POPPA by Moe Moe Q confirms a new Singapore idol live")
        from_mmq = infer_entity_tags("MMQ previews POPPA fan benefits for the next Singapore stage")
        from_ani_idol = infer_entity_tags("Ani-Idol Singapore unveils a fresh anisong stage lineup")

        self.assertEqual(from_poppa, from_mmq)
        self.assertIn("POPPA", from_poppa)
        self.assertIn("Ani-Idol", from_ani_idol)

    def test_infer_entity_tags_skips_ambiguous_poppa_without_idol_context(self) -> None:
        from_article = infer_entity_tags("Lil Poppa tribute merch rumor spreads")
        from_query = infer_entity_tags("POPPA Singapore", for_query=True)

        self.assertNotIn("POPPA", from_article)
        self.assertIn("POPPA", from_query)

    def test_infer_entity_tags_skips_ambiguous_persona_without_franchise_context(self) -> None:
        from_company = infer_entity_tags("Persona AI announces Brian Davis as head of manufacturing")
        from_diplomacy = infer_entity_tags("Argentina declares Iranian envoy persona non grata")
        from_merch = infer_entity_tags("'Persona' Funko POP! Vinyls celebrate 30 years")
        from_query = infer_entity_tags("persona 4 revival", for_query=True)

        self.assertNotIn("Persona", from_company)
        self.assertNotIn("Persona", from_diplomacy)
        self.assertIn("Persona", from_merch)
        self.assertIn("Persona", from_query)

    def test_feed_response_builds_cross_source_entity_groups(self) -> None:
        now = datetime.now(timezone.utc)
        articles = [
            self.make_article(
                article_id="afa-1",
                title="AFA Singapore guest lineup lands",
                summary="Anime Festival Asia Singapore shares new guest details.",
                source_name="Google News SG Events",
                entity_tags=["AFA Singapore"],
                published_at=now - timedelta(hours=2),
            ),
            self.make_article(
                article_id="afa-2",
                title="Bandwagon previews Anime Festival Asia Singapore",
                summary="Bandwagon maps out Anime Festival Asia highlights and queues.",
                source_name="Bandwagon Asia",
                entity_tags=["AFA Singapore"],
                published_at=now - timedelta(hours=3),
            ),
            self.make_article(
                article_id="sgcc-1",
                title="Singapore Comic Con tickets go live",
                summary="SGCC confirms a fresh ticketing update.",
                source_name="Google News SG Events",
                entity_tags=["SGCC"],
                published_at=now - timedelta(hours=1),
            ),
        ]
        self.repository.upsert_articles(articles)

        response = self.news_service.home_feed(limit=3)

        self.assertTrue(response.entity_groups)
        self.assertEqual(response.entity_groups[0].name, "AFA Singapore")
        self.assertEqual(response.entity_groups[0].count, 2)
        self.assertEqual(response.entity_groups[0].source_count, 2)

    def test_query_entity_alias_boosts_matching_story(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="ffxiv-fest",
                    title="US FFXIV Fan Festival 2026 Schedule Shared",
                    summary="Square Enix publishes the FFXIV Fan Festival schedule.",
                    source_name="Siliconera",
                    entity_tags=["FFXIV Fan Festival", "Final Fantasy"],
                    published_at=now - timedelta(hours=2),
                ),
                self.make_article(
                    article_id="generic-festival",
                    title="Singapore fan meetup weekend schedule shared",
                    summary="A community fan meetup publishes its weekend schedule.",
                    source_name="Eventbrite SG Anime",
                    entity_tags=[],
                    published_at=now - timedelta(hours=1),
                ),
            ]
        )

        response = self.news_service.search(query="ff14 fan fest", limit=3, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "US FFXIV Fan Festival 2026 Schedule Shared")

    def test_build_entity_groups_aggregates_sources(self) -> None:
        now = datetime.now(timezone.utc)
        groups = build_entity_groups(
            [
                self.make_article(
                    article_id="mlbb-1",
                    title="MLBB qualifiers update",
                    summary="Mobile Legends qualifier update.",
                    source_name="Google News SEA Esports",
                    entity_tags=["MLBB"],
                    published_at=now - timedelta(hours=3),
                ),
                self.make_article(
                    article_id="mlbb-2",
                    title="Community guide for Mobile Legends Singapore weekend",
                    summary="Another MLBB coverage angle.",
                    source_name="Bandwagon Asia",
                    entity_tags=["MLBB"],
                    published_at=now - timedelta(hours=1),
                ),
            ]
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].name, "MLBB")
        self.assertEqual(groups[0].count, 2)
        self.assertEqual(groups[0].source_count, 2)

    def test_search_query_records_learned_entity_affinity(self) -> None:
        profile = self.repository.record_search_query(user_id="fan-entity", query="AFA Singapore")

        self.assertIn("AFA Singapore", profile.top_entities)
        self.assertGreater(profile.entity_affinities.get("afa singapore", 0), 0)

    def test_like_signal_lifts_related_entity_story_across_sources(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="afa-direct",
                    title="Anime Festival Asia Singapore ticket window opens",
                    summary="AFA Singapore confirms ticket release timing.",
                    source_name="Google News SG Events",
                    entity_tags=["AFA Singapore"],
                    published_at=now - timedelta(hours=6),
                ),
                self.make_article(
                    article_id="afa-bandwagon",
                    title="Bandwagon previews Anime Festival Asia Singapore creator alley",
                    summary="Bandwagon shares Anime Festival Asia creator alley highlights.",
                    source_name="Bandwagon Asia",
                    entity_tags=["AFA Singapore"],
                    published_at=now - timedelta(hours=7),
                ),
                self.make_article(
                    article_id="sgcc-fresh",
                    title="Singapore Comic Con weekend update",
                    summary="SGCC posts a fresh logistics update.",
                    source_name="Google News SG Events",
                    entity_tags=["SGCC"],
                    published_at=now - timedelta(hours=1),
                ),
            ]
        )

        baseline_titles = [item.title for item in self.news_service.home_feed(limit=3).items]
        self.assertEqual(baseline_titles[0], "Singapore Comic Con weekend update")

        profile = self.repository.record_interaction(user_id="fan-like", article_id="afa-direct", action="like")
        personalized_titles = [item.title for item in self.news_service.home_feed(limit=3, user_id="fan-like").items]

        self.assertIn("AFA Singapore", profile.top_entities)
        self.assertEqual(personalized_titles[0], "Anime Festival Asia Singapore ticket window opens")
        self.assertEqual(personalized_titles[1], "Bandwagon previews Anime Festival Asia Singapore creator alley")

    def test_pinned_entity_promotes_related_cluster_in_home_feed(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="persona-fresh",
                    title="Persona collab cafe update",
                    summary="Persona collaboration cafe gets a fresh Singapore update.",
                    source_name="Google News Merch And Deals",
                    entity_tags=["Persona"],
                    published_at=now - timedelta(hours=1),
                ),
                self.make_article(
                    article_id="afa-steady",
                    title="Anime Festival Asia Singapore guest guide",
                    summary="AFA Singapore shares creator alley and guest planning notes.",
                    source_name="Bandwagon Asia",
                    entity_tags=["AFA Singapore"],
                    published_at=now - timedelta(hours=8),
                ),
            ]
        )

        baseline_titles = [item.title for item in self.news_service.home_feed(limit=2).items]
        self.assertEqual(baseline_titles[0], "Persona collab cafe update")

        updated_profile = self.repository.update_user_profile(
            user_id="fan-pinned-entity",
            pinned_entities=["AFA Singapore"],
        )
        personalized_titles = [item.title for item in self.news_service.home_feed(limit=2, user_id="fan-pinned-entity").items]

        self.assertIn("AFA Singapore", updated_profile.pinned_entities)
        self.assertEqual(personalized_titles[0], "Anime Festival Asia Singapore guest guide")

    def test_custom_named_pinned_entity_promotes_matching_story(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="custom-entity-story",
                    title="Blue Archive Singapore popup weekend details",
                    summary="Blue Archive Singapore popup shares its latest schedule update.",
                    source_name="Bandwagon Asia",
                    entity_tags=["Blue Archive Singapore Popup"],
                    published_at=now - timedelta(hours=8),
                ),
                self.make_article(
                    article_id="generic-fresh-story",
                    title="Persona merch drop returns to Singapore",
                    summary="A fresher merch update lands in Singapore.",
                    source_name="Google News Merch And Deals",
                    entity_tags=["Persona"],
                    published_at=now - timedelta(hours=1),
                ),
            ]
        )

        baseline_titles = [item.title for item in self.news_service.home_feed(limit=2).items]
        self.assertEqual(baseline_titles[0], "Persona merch drop returns to Singapore")

        updated_profile = self.repository.update_user_profile(
            user_id="fan-custom-pinned-entity",
            pinned_entities=["Blue Archive Singapore Popup"],
        )
        personalized_titles = [item.title for item in self.news_service.home_feed(limit=2, user_id="fan-custom-pinned-entity").items]

        self.assertIn("Blue Archive Singapore Popup", updated_profile.pinned_entities)
        self.assertEqual(personalized_titles[0], "Blue Archive Singapore popup weekend details")