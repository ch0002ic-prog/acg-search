from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.llm import LLMService
from app.services.news import NewsService
from app.services.ranking import compute_home_score, diversify_scored_articles, score_freshness
from app.services.vector_store import VectorStore


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


class SearchBackendTests(unittest.TestCase):
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
        cls.repository = ArticleRepository(cls.test_settings.db_path)
        cls.repository.init_database()
        cls.vector_store = VectorStore(settings=cls.test_settings, repository=cls.repository)
        cls.llm_service = LLMService(cls.test_settings)
        cls.news_service = NewsService(
            repository=cls.repository,
            vector_store=cls.vector_store,
            llm_service=cls.llm_service,
        )

        now = datetime.now(timezone.utc)
        cls.repository.upsert_articles(
            [
                cls.make_article(
                    article_id="doujin-market",
                    title="Doujin Market 2026",
                    summary="Singapore doujin market returns with artist alley booths and indie creator circles.",
                    content="Doujin Market 2026 lands at Suntec Singapore with doujin creators, fan artists, and limited goods.",
                    categories=["events", "comics", "anime"],
                    tags=["doujin", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.77,
                    published_at=now - timedelta(hours=3),
                    source_name="Eventbrite SG Anime",
                ),
                cls.make_article(
                    article_id="doki-market",
                    title="DOKI! DOKI! ANIME MARKET SINGAPORE 2026",
                    summary="Anime market with merch booths and cosplay showcase in Singapore.",
                    content="A large anime market event in Singapore featuring merchandise, cosplay, and artist booths.",
                    categories=["events", "anime", "merch"],
                    tags=["singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.55,
                    published_at=now - timedelta(hours=2),
                    source_name="Eventbrite SG Anime",
                ),
                cls.make_article(
                    article_id="demon-slayer-merch",
                    title="Inside The New Demon Slayer Exhibition In SG – Iconic Anime Scenes & SG-Exclusive Merch",
                    summary="Singapore exhibition opens with SG-exclusive merch, collectibles, and photo zones.",
                    content="Fans can browse limited Demon Slayer merchandise, collectibles, and collaboration goods in Singapore.",
                    categories=["anime", "merch", "events"],
                    tags=["singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.58,
                    published_at=now - timedelta(hours=6),
                    source_name="Google News Anime And Manga",
                ),
                cls.make_article(
                    article_id="anime-bitcoin",
                    title="ANIME to SGD: Anime Bitcoin Price in Singapore Dollar",
                    summary="Crypto price ticker for ANIME token against SGD.",
                    content="A cryptocurrency conversion page unrelated to anime merchandise, events, or fandom coverage.",
                    categories=["games"],
                    tags=["singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.83,
                    published_at=now - timedelta(hours=1),
                    source_name="Google News SG ACG",
                ),
                cls.make_article(
                    article_id="sgcc-guests",
                    title="Singapore Comic Con 2026 guest lineup revealed",
                    summary="SGCC confirms headline guests, creator signings, and major stage sessions.",
                    content="Singapore Comic Con reveals its guest lineup, signings, and showfloor plans for this year.",
                    categories=["events", "comics"],
                    tags=["sgcc", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.76,
                    published_at=now - timedelta(hours=8),
                    source_name="Google News SG Events",
                ),
                cls.make_article(
                    article_id="mlbb-qualifiers",
                    title="Mobile Legends Singapore qualifiers announced for MPL weekend",
                    summary="MLBB teams will battle through Singapore qualifier brackets ahead of playoffs.",
                    content="Mobile Legends: Bang Bang qualifier slots open in Singapore ahead of the next MPL stage.",
                    categories=["esports", "games"],
                    tags=["mlbb", "singapore"],
                    region_tags=["Singapore", "SEA"],
                    sg_relevance=0.68,
                    published_at=now - timedelta(hours=4),
                    source_name="Google News SEA Esports",
                ),
                cls.make_article(
                    article_id="hoyofest",
                    title="HoyoFest Singapore 2026 brings Genshin and Honkai merch booths",
                    summary="HoYoVerse confirms Singapore event zones for Genshin Impact, Honkai: Star Rail, and Zenless.",
                    content="HoyoFest Singapore returns with themed merch booths, collab cafes, and cosplay activities.",
                    categories=["events", "merch", "gacha"],
                    tags=["hoyofest", "hoyoverse", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.82,
                    published_at=now - timedelta(hours=5),
                    source_name="Google News Merch And Deals",
                ),
                cls.make_article(
                    article_id="boardgames",
                    title="Boardgames",
                    summary="Singapore meetup night for boardgames, social deduction, and tabletop sessions.",
                    content="Join a Singapore boardgames session featuring tabletop titles and casual group play.",
                    categories=["games", "events"],
                    tags=["boardgame", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.4,
                    published_at=now - timedelta(hours=2),
                    source_name="Eventbrite SG Gaming",
                ),
                cls.make_article(
                    article_id="mahjong",
                    title="Learn to play Singapore Mahjong Lah! (Beginners)",
                    summary="Beginner-friendly mahjong workshop in Singapore for tabletop and tile game fans.",
                    content="Learn Singapore mahjong scoring and gameplay in a guided beginner workshop.",
                    categories=["games", "events"],
                    tags=["mahjong", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.38,
                    published_at=now - timedelta(hours=7),
                    source_name="Eventbrite SG Gaming",
                ),
                cls.make_article(
                    article_id="jrpg-demo",
                    title="New JRPG demo announced by Atlus at Asia showcase",
                    summary="Atlus reveals a playable JRPG demo and release window during the latest showcase.",
                    content="A new turn-based RPG demo from Atlus is now available, with fresh footage and release details.",
                    categories=["games"],
                    tags=["jrpg", "atlus"],
                    region_tags=[],
                    sg_relevance=0.08,
                    published_at=now - timedelta(hours=10),
                    source_name="Google News JRPG",
                ),
                cls.make_article(
                    article_id="atlus-sale",
                    title="SEGA / Atlus hosting new Nintendo Switch 2 sale with low prices",
                    summary="Atlus sale discounts multiple titles but does not include any playable demo.",
                    content="A storefront promotion highlights price cuts rather than a new JRPG demo announcement.",
                    categories=["games"],
                    tags=["jrpg", "atlus"],
                    region_tags=[],
                    sg_relevance=0.0,
                    published_at=now - timedelta(hours=1),
                    source_name="Google News JRPG",
                ),
                cls.make_article(
                    article_id="manga-workshop",
                    title="Cozy Tea, Draw and Manga Inking Workshop",
                    summary="Singapore art session focused on manga inking, sketching, and guided workshop practice.",
                    content="A manga workshop in Singapore covering inking basics, panel layout, and character drawing.",
                    categories=["manga", "events"],
                    tags=["manga", "workshop", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.35,
                    published_at=now - timedelta(hours=3),
                    source_name="Eventbrite SG Anime",
                ),
                cls.make_article(
                    article_id="afa-guide",
                    title="Anime Festival Asia Singapore 2026 guest list and ticket guide",
                    summary="Bandwagon Asia previews Anime Festival Asia Singapore guests, ticketing windows, and merch lanes.",
                    content="Anime Festival Asia Singapore returns with guest announcements, early ticket sales, and creator alley planning tips.",
                    categories=["events", "anime", "merch"],
                    tags=["afa", "singapore"],
                    region_tags=["Singapore", "SEA"],
                    sg_relevance=0.88,
                    published_at=now - timedelta(hours=9),
                    source_name="Bandwagon Asia",
                ),
                cls.make_article(
                    article_id="digital-art-manga",
                    title="Introduction To Digital Art (Character Manga) Workshop - VAC Open House",
                    summary="Singapore workshop covers digital art basics for manga character illustration and colouring.",
                    content="A digital art and manga workshop in Singapore focusing on character design, colouring, and illustration fundamentals.",
                    categories=["manga", "events"],
                    tags=["manga", "workshop", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.36,
                    published_at=now - timedelta(hours=2),
                    source_name="Eventbrite SG Anime",
                ),
                cls.make_article(
                    article_id="playtest-party",
                    title="Playtest Party Indie Games in the Making",
                    summary="Singapore indie developers share in-progress games at a public playtest party.",
                    content="A Singapore playtest event gives local indie developers a venue to showcase games and gather player feedback.",
                    categories=["games", "events"],
                    tags=["indie games", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.34,
                    published_at=now - timedelta(hours=5),
                    source_name="Eventbrite SG Gaming",
                ),
                cls.make_article(
                    article_id="otaket",
                    title="Otaket 2026: Jumpstart",
                    summary="Singapore anime community event with creator booths, early-bird tickets, and fan meetups.",
                    content="Otaket returns in Singapore with anime creator booths, fan activities, and convention-style programming.",
                    categories=["events", "anime"],
                    tags=["otaket", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.41,
                    published_at=now - timedelta(hours=3),
                    source_name="Eventbrite SG Anime",
                ),
            ]
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    @classmethod
    def make_article(
        cls,
        article_id: str,
        title: str,
        summary: str,
        content: str,
        categories: list[str],
        tags: list[str],
        region_tags: list[str],
        sg_relevance: float,
        published_at: datetime,
        source_name: str,
    ) -> ArticleRecord:
        freshness = score_freshness(published_at)
        return ArticleRecord(
            id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            source_name=source_name,
            source_type="test",
            published_at=published_at,
            summary=summary,
            content=content,
            categories=categories,
            tags=tags,
            region_tags=region_tags,
            sg_relevance=sg_relevance,
            freshness_score=freshness,
            home_score=compute_home_score(
                freshness_score=freshness,
                sg_relevance=sg_relevance,
                categories=categories,
                source_quality=0.8,
            ),
            source_quality=0.8,
        )

    def assert_top_result_contains(self, query: str, expected_terms: tuple[str, ...]) -> None:
        response = self.news_service.search(query=query, limit=5, rerank=False, user_id=None)
        self.assertTrue(response.items, msg=f"Expected results for query '{query}'")
        top_text = normalize_text(response.items[0].title + " " + response.items[0].summary)
        self.assertTrue(
            any(term in top_text for term in expected_terms),
            msg=f"Unexpected top result for '{query}': {response.items[0].title}",
        )

    def test_query_suite_prefers_expected_top_results(self) -> None:
        expectations = {
            "doujin market": ("doujin market",),
            "afa singapore": ("anime festival asia", "afa"),
            "anime merch singapore": ("exclusive merch", "merch", "market"),
            "sgcc guests": ("singapore comic con", "sgcc"),
            "mlbb qualifiers": ("mobile legends", "mlbb"),
            "hoyofest singapore": ("hoyofest",),
            "board games singapore": ("boardgames", "mahjong"),
            "new jrpg demo": ("jrpg demo", "playable jrpg demo", "atlus reveals a playable jrpg demo"),
            "manga workshop singapore": ("manga", "workshop"),
            "mahjong singapore": ("mahjong",),
            "anime market singapore": ("anime market", "doki"),
            "digital art manga workshop": ("digital art", "manga", "workshop"),
            "indie games singapore": ("playtest party", "indie games"),
            "otaket singapore": ("otaket",),
        }

        for query, expected_terms in expectations.items():
            with self.subTest(query=query):
                self.assert_top_result_contains(query, expected_terms)

    def test_irrelevant_query_does_not_fallback_to_latest(self) -> None:
        response = self.news_service.search(query="zzzzqxjvtr", limit=5, rerank=False, user_id=None)
        self.assertEqual(response.items, [])
        self.assertTrue(response.digest)
        self.assertIn("No strong matches", response.digest[0])

    def test_exact_match_beats_partial_market_overlap(self) -> None:
        response = self.news_service.search(query="doujin market", limit=5, rerank=False, user_id=None)
        self.assertEqual(response.items[0].title, "Doujin Market 2026")

    def test_broad_search_surfaces_multiple_sources(self) -> None:
        response = self.news_service.search(query="anime singapore", limit=3, rerank=False, user_id=None)
        self.assertEqual(len(response.items), 3)
        self.assertGreaterEqual(len({item.source_name for item in response.items}), 2)

    def test_diversify_scored_articles_reduces_same_source_stacking(self) -> None:
        now = datetime.now(timezone.utc)
        diversified = diversify_scored_articles(
            [
                (
                    self.make_article(
                        article_id="diverse-1",
                        title="Anime Market Singapore Weekend",
                        summary="Anime market with merch and booths in Singapore.",
                        content="A broad anime market event for Singapore fans.",
                        categories=["events", "anime"],
                        tags=["anime", "singapore"],
                        region_tags=["Singapore"],
                        sg_relevance=0.7,
                        published_at=now - timedelta(hours=2),
                        source_name="Eventbrite SG Anime",
                    ),
                    0.93,
                ),
                (
                    self.make_article(
                        article_id="diverse-2",
                        title="Anime Creator Meetup Singapore",
                        summary="Creator meetup with artist tables and anime fan networking.",
                        content="Another anime-focused Singapore event from the same source.",
                        categories=["events", "anime"],
                        tags=["anime", "singapore"],
                        region_tags=["Singapore"],
                        sg_relevance=0.69,
                        published_at=now - timedelta(hours=3),
                        source_name="Eventbrite SG Anime",
                    ),
                    0.91,
                ),
                (
                    self.make_article(
                        article_id="diverse-3",
                        title="Anime Festival Asia Singapore guest guide",
                        summary="Bandwagon Asia previews AFA Singapore guests and key fan highlights.",
                        content="Anime Festival Asia coverage from a different source with Singapore relevance.",
                        categories=["events", "anime"],
                        tags=["afa", "singapore"],
                        region_tags=["Singapore", "SEA"],
                        sg_relevance=0.78,
                        published_at=now - timedelta(hours=4),
                        source_name="Bandwagon Asia",
                    ),
                    0.89,
                ),
                (
                    self.make_article(
                        article_id="diverse-4",
                        title="Anime Inking Workshop Singapore",
                        summary="Hands-on anime illustration workshop for Singapore attendees.",
                        content="A third same-source event that would otherwise dominate a broad anime query.",
                        categories=["manga", "events"],
                        tags=["anime", "singapore"],
                        region_tags=["Singapore"],
                        sg_relevance=0.66,
                        published_at=now - timedelta(hours=1),
                        source_name="Eventbrite SG Anime",
                    ),
                    0.88,
                ),
            ],
            limit=3,
        )

        self.assertEqual(diversified[0].source_name, "Eventbrite SG Anime")
        self.assertEqual(diversified[1].source_name, "Bandwagon Asia")
        self.assertGreaterEqual(len({article.source_name for article in diversified}), 2)

    def test_search_can_skip_profile_tracking_for_route_replay(self) -> None:
        profile = self.repository.get_or_create_user_profile("route-replay-fan")
        before_queries = list(profile.recent_queries)
        before_count = profile.interaction_count

        response = self.news_service.search(
            query="afa singapore",
            limit=5,
            rerank=False,
            user_id="route-replay-fan",
            track_profile=False,
        )
        updated_profile = self.repository.get_or_create_user_profile("route-replay-fan")

        self.assertTrue(response.items)
        self.assertEqual(updated_profile.recent_queries, before_queries)
        self.assertEqual(updated_profile.interaction_count, before_count)

    def test_vector_prefilter_keeps_seeded_ids_and_caps_pool_size(self) -> None:
        candidate_ids = self.repository.prefilter_vector_search_ids(
            limit=3,
            seeded_ids=["jrpg-demo", "atlus-sale", "jrpg-demo"],
        )

        self.assertEqual(candidate_ids[:2], ["jrpg-demo", "atlus-sale"])
        self.assertLessEqual(len(candidate_ids), 3)

    def test_vector_search_can_restrict_to_prefiltered_candidates(self) -> None:
        results = self.repository.vector_search_with_candidates(
            query="new jrpg demo",
            limit=5,
            candidate_ids=["jrpg-demo", "atlus-sale"],
        )

        self.assertTrue(results)
        self.assertTrue(all(article_id in {"jrpg-demo", "atlus-sale"} for article_id, _ in results))

    def test_concurrent_search_queries_preserve_all_query_updates(self) -> None:
        user_id = "concurrent-search-fan"
        query = "AFA Singapore"
        worker_count = 4
        barrier = threading.Barrier(worker_count)

        def run_query() -> None:
            barrier.wait(timeout=5)
            self.repository.record_search_query(user_id=user_id, query=query)

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(run_query) for _ in range(worker_count)]
            for future in futures:
                future.result(timeout=10)

        profile = self.repository.get_or_create_user_profile(user_id)
        self.assertEqual(profile.interaction_count, worker_count)
        self.assertEqual(profile.recent_queries, [query])
        self.assertAlmostEqual(profile.query_affinities[query.lower()], 1.52, places=3)

    def test_concurrent_search_and_interaction_updates_do_not_lose_writes(self) -> None:
        user_id = "concurrent-mixed-fan"
        search_count = 3
        interaction_count = 2
        worker_count = search_count + interaction_count
        barrier = threading.Barrier(worker_count)

        def run_search() -> None:
            barrier.wait(timeout=5)
            self.repository.record_search_query(user_id=user_id, query="AFA Singapore")

        def run_interaction() -> None:
            barrier.wait(timeout=5)
            self.repository.record_interaction(user_id=user_id, article_id="afa-guide", action="open")

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(run_search) for _ in range(search_count)]
            futures.extend(executor.submit(run_interaction) for _ in range(interaction_count))
            for future in futures:
                future.result(timeout=10)

        profile = self.repository.get_or_create_user_profile(user_id)
        self.assertEqual(profile.interaction_count, worker_count)
        self.assertAlmostEqual(profile.query_affinities["afa singapore"], 1.14, places=3)
        self.assertAlmostEqual(profile.tag_affinities["afa"], 1.74, places=3)
        self.assertAlmostEqual(profile.region_affinities["singapore"], 1.74, places=3)
