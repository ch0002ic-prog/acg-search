from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.llm import CallMetrics, LLMService
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
                    article_id="artist-alley",
                    title="Artist Alley Singapore guide highlights AFA and SGCC creator booths",
                    summary="A Singapore artist alley guide maps Anime Festival Asia creator booths, SGCC tables, and merch lanes.",
                    content="Artist Alley Singapore coverage follows Anime Festival Asia and SGCC creator booths, merch lanes, and market-floor discoveries for local fans.",
                    categories=["events", "anime", "merch"],
                    tags=["afa", "sgcc", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.72,
                    published_at=now - timedelta(hours=4),
                    source_name="Bandwagon Asia",
                ),
                cls.make_article(
                    article_id="poppa-live",
                    title="POPPA by Moe Moe Q announces Singapore idol live and merch signing",
                    summary="Moe Moe Q's POPPA project schedules a Singapore idol live with fan benefits, merch, and stage appearances.",
                    content="POPPA, the idol organization managed under the Moe Moe Q (MMQ) brand, confirms a Singapore live set, fan perks, and merch signing plans.",
                    categories=["events", "anime", "merch"],
                    tags=["idol", "mmq", "poppa", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.73,
                    published_at=now - timedelta(hours=4),
                    source_name="Bandwagon Asia",
                ),
                cls.make_article(
                    article_id="lil-poppa-distractor",
                    title="Lil Poppa tribute merch chatter spreads through Singapore resale groups",
                    summary="An unrelated rapper merch rumor circulates through Singapore resale chats and collector groups.",
                    content="This unrelated entertainment story has nothing to do with Moe Moe Q, MMQ, POPPA idol activities, or Ani-Idol events.",
                    categories=["merch"],
                    tags=["singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.49,
                    published_at=now - timedelta(hours=1),
                    source_name="Google News SG Events",
                ),
                cls.make_article(
                    article_id="ani-idol-night",
                    title="Ani-Idol Singapore night adds anisong stage and cosplay idol showcase",
                    summary="Ani-Idol returns with anisong performances, idol stage acts, and fan meetups in Singapore.",
                    content="Ani-Idol Singapore brings idol performances, anime songs, cosplay showcases, and community meetup programming.",
                    categories=["events", "anime"],
                    tags=["idol", "anisong", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.69,
                    published_at=now - timedelta(hours=3),
                    source_name="Eventbrite SG Anime",
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
                    article_id="persona-revival",
                    title="Persona 4 Revival release date surfaces after merch listing",
                    summary="A fresh Persona 4 Revival report points to an Atlus reveal window after a new merch listing surfaced.",
                    content="Persona 4 Revival chatter grows after an Atlus-adjacent merch listing hinted at a release date window for the JRPG.",
                    categories=["games", "merch"],
                    tags=["jrpg", "atlus"],
                    region_tags=[],
                    sg_relevance=0.1,
                    published_at=now - timedelta(hours=6),
                    source_name="Google News JRPG",
                ),
                cls.make_article(
                    article_id="persona-cafe",
                    title="Persona 5 Royale collab cafe returns to Singapore's ANIPLUS Cafe",
                    summary="A Singapore cafe collaboration brings Persona menu items, merch, and reservation perks back to ANIPLUS.",
                    content="Persona fans in Singapore can book a returning ANIPLUS collab cafe with themed drinks, merch bundles, and cafe bonuses.",
                    categories=["anime", "events", "merch"],
                    tags=["jrpg", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.66,
                    published_at=now - timedelta(hours=5),
                    source_name="Google News Anime And Manga",
                ),
                cls.make_article(
                    article_id="persona-ai-distractor",
                    title="Persona AI announces manufacturing expansion in Singapore",
                    summary="A corporate software company named Persona AI announces a manufacturing leadership hire and expansion plan.",
                    content="This business update is unrelated to Atlus, Persona 4 Revival, JRPGs, or franchise merch and events.",
                    categories=["games"],
                    tags=["singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.61,
                    published_at=now - timedelta(hours=2),
                    source_name="Yahoo Finance Singapore",
                ),
                cls.make_article(
                    article_id="persona-non-grata-distractor",
                    title="Argentina declares Iranian envoy persona non grata",
                    summary="A diplomacy update uses the phrase persona non grata and has no connection to ACG coverage.",
                    content="This foreign affairs report is unrelated to Atlus, Persona 4 Revival, JRPG releases, or franchise merchandise.",
                    categories=["games"],
                    tags=[],
                    region_tags=[],
                    sg_relevance=0.0,
                    published_at=now - timedelta(hours=1),
                    source_name="Reuters World",
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
        url: str | None = None,
        source_type: str = "test",
    ) -> ArticleRecord:
        freshness = score_freshness(published_at)
        return ArticleRecord(
            id=article_id,
            title=title,
            url=url or f"https://example.com/{article_id}",
            source_name=source_name,
            source_type=source_type,
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
            "artist alley singapore": ("artist alley", "anime festival asia", "sgcc"),
            "poppa singapore": ("moe moe q", "mmq", "idol"),
            "moe moe q idol": ("moe moe q", "mmq", "idol"),
            "ani-idol singapore": ("ani-idol", "ani idol", "idol"),
            "idol live singapore": ("idol live", "ani-idol", "anisong", "moe moe q"),
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

    def test_result_types_distinguish_stories_events_and_source_pages(self) -> None:
        now = datetime.now(timezone.utc)
        story = self.make_article(
            article_id="story-record",
            title="AFA story",
            summary="News coverage",
            content="News coverage",
            categories=["anime"],
            tags=["afa"],
            region_tags=["Singapore"],
            sg_relevance=0.7,
            published_at=now,
            source_name="Anime Festival Asia",
            source_type="rss",
        )
        event = self.make_article(
            article_id="event-record",
            title="AFA ticket page",
            summary="Official event listing",
            content="Official event listing",
            categories=["events"],
            tags=["afa"],
            region_tags=["Singapore"],
            sg_relevance=0.7,
            published_at=now,
            source_name="Eventbrite SG Anime",
            source_type="event_listing",
        )
        source_page = self.make_article(
            article_id="source-page-record",
            title="AFA source page",
            summary="Keyword source page",
            content="Keyword source page",
            categories=["events"],
            tags=["afa"],
            region_tags=["Singapore"],
            sg_relevance=0.7,
            published_at=now,
            source_name="SG Source Pages",
            source_type="curated",
        )

        self.assertEqual(story.result_type, "article")
        self.assertEqual(event.result_type, "event")
        self.assertEqual(source_page.result_type, "source_page")
        self.assertEqual(source_page.model_dump(mode="json")["result_type"], "source_page")

    def test_recent_event_story_beats_stale_exact_phrase_match(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="neo-tokyo-festival-archive-2013",
                    title="Neo Tokyo Festival 2013 archive overview",
                    summary="Archive recap of Neo Tokyo Festival 2013.",
                    content="An old retrospective for Neo Tokyo Festival 2013.",
                    categories=["events", "anime"],
                    tags=["festival"],
                    region_tags=["Singapore"],
                    sg_relevance=0.83,
                    published_at=now - timedelta(days=365 * 10),
                    source_name="Archive Desk",
                ),
                self.make_article(
                    article_id="neo-tokyo-festival-current-2026",
                    title="Neo Tokyo Festival Singapore 2026 is back with new guests",
                    summary="Fresh Neo Tokyo Festival Singapore coverage for the current season.",
                    content="Current Neo Tokyo Festival Singapore coverage with guests, merch, and event highlights.",
                    categories=["events", "anime"],
                    tags=["festival"],
                    region_tags=["Singapore"],
                    sg_relevance=0.83,
                    published_at=now - timedelta(days=2),
                    source_name="Current Desk",
                ),
            ]
        )

        response = self.news_service.search(query="Neo Tokyo Festival", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].id, "neo-tokyo-festival-current-2026")

    def test_article_url_beats_media_viewer_url_for_same_query(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="afa-media-viewer",
                    title="AFA 2025 highlights photo gallery",
                    summary="A media-viewer page for AFA 2025 highlights.",
                    content="A media-viewer page for AFA 2025 highlights.",
                    categories=["events", "anime"],
                    tags=["afa"],
                    region_tags=["Singapore"],
                    sg_relevance=0.74,
                    published_at=now - timedelta(days=1),
                    source_name="Google News SG Events",
                    url="https://www.imdb.com/title/tt0973277/mediaviewer/rm625850625/",
                ),
                self.make_article(
                    article_id="afa-article-url",
                    title="AFA 2025 highlights from this year's Anime Festival Asia",
                    summary="A proper article page for AFA 2025 highlights.",
                    content="A proper article page for AFA 2025 highlights.",
                    categories=["events", "anime"],
                    tags=["afa"],
                    region_tags=["Singapore"],
                    sg_relevance=0.74,
                    published_at=now - timedelta(days=1),
                    source_name="Google News SG Events",
                    url="https://danamic.org/2025/11/29/afa-2025-highlights-from-this-years-anime-festival-asia/",
                ),
            ]
        )

        response = self.news_service.search(query="AFA 2025 highlights", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].id, "afa-article-url")

    def test_article_beats_source_page_when_strong_story_exists(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="artist-alley-source-page",
                    title="Lantern Lane Artist Alley official creator update page",
                    summary="Official creator-booth updates for Lantern Lane Artist Alley Singapore.",
                    content="Official creator-booth updates for Lantern Lane Artist Alley Singapore and creator booths.",
                    categories=["events", "anime", "merch"],
                    tags=["afa", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.82,
                    published_at=now,
                    source_name="SG Source Pages",
                    source_type="curated",
                ),
                self.make_article(
                    article_id="artist-alley-story",
                    title="Lantern Lane Artist Alley kicks off with sold-out creator showcase",
                    summary="A strong Lantern Lane Artist Alley story covering creator booths and fan turnout in Singapore.",
                    content="Lantern Lane Artist Alley coverage follows creator booths, fan turnout, and convention floor highlights in Singapore.",
                    categories=["events", "anime", "merch"],
                    tags=["hoyofest", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.82,
                    published_at=now - timedelta(days=1),
                    source_name="Google News HoyoFest",
                ),
            ]
        )

        response = self.news_service.search(query="Lantern Lane artist alley singapore", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].id, "artist-alley-story")

    def test_poppa_query_excludes_lil_poppa_false_positive(self) -> None:
        response = self.news_service.search(query="POPPA Singapore", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "POPPA by Moe Moe Q announces Singapore idol live and merch signing")
        self.assertNotIn(
            "Lil Poppa tribute merch rumor spreads through Singapore resale groups",
            [item.title for item in response.items],
        )

    def test_ani_idol_query_prefers_ani_idol_result(self) -> None:
        response = self.news_service.search(query="Ani-Idol Singapore", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "Ani-Idol Singapore night adds anisong stage and cosplay idol showcase")

    def test_moe_moe_q_query_prefers_poppa_result(self) -> None:
        response = self.news_service.search(query="Moe Moe Q idol", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "POPPA by Moe Moe Q announces Singapore idol live and merch signing")

    def test_artist_alley_query_prefers_artist_alley_result(self) -> None:
        response = self.news_service.search(query="artist alley singapore", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "Artist Alley Singapore guide highlights AFA and SGCC creator booths")

    def test_persona_query_excludes_non_franchise_false_positives(self) -> None:
        response = self.news_service.search(query="persona 4 revival", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertEqual(response.items[0].title, "Persona 4 Revival release date surfaces after merch listing")
        self.assertNotIn(
            "Persona AI announces manufacturing expansion in Singapore",
            [item.title for item in response.items],
        )
        self.assertNotIn(
            "Argentina declares Iranian envoy persona non grata",
            [item.title for item in response.items],
        )

    def test_broad_search_surfaces_multiple_sources(self) -> None:
        response = self.news_service.search(query="anime singapore", limit=3, rerank=False, user_id=None)
        self.assertEqual(len(response.items), 3)
        self.assertGreaterEqual(len({item.source_name for item in response.items}), 2)

    def test_search_exposes_timing_breakdown(self) -> None:
        response = self.news_service.search(query="AFA Singapore", limit=6, rerank=False, include_digest=False)

        self.assertIsNotNone(response.timings)
        assert response.timings is not None
        self.assertGreaterEqual(response.timings.total_ms, 0.0)
        self.assertGreaterEqual(response.timings.expand_ms, 0.0)
        self.assertGreaterEqual(response.timings.lexical_ms, 0.0)
        self.assertGreaterEqual(response.timings.vector_ms, 0.0)
        self.assertEqual(response.timings.digest_ms, 0.0)
        self.assertFalse(response.timings.vector_cache_hit)
        self.assertFalse(response.timings.rerank_cache_hit)
        self.assertEqual(response.timings.result_count, len(response.items))

    def test_search_short_circuits_inline_llm_after_expand_timeout(self) -> None:
        with (
            patch.object(
                self.llm_service,
                "should_skip_inline_search_llm",
                return_value=False,
            ),
            patch.object(
                self.llm_service,
                "expand_query_with_metadata",
                return_value=("HoyoFest Singapore", CallMetrics(duration_ms=2500.0, cache_hit=False, timed_out=True)),
            ),
            patch.object(
                self.llm_service,
                "rerank_articles_with_metadata",
                return_value=(self.repository.latest_articles(8), CallMetrics(duration_ms=0.3, cache_hit=False)),
            ) as mocked_rerank,
            patch.object(
                self.llm_service,
                "generate_digest_with_metadata",
                return_value=(["fallback digest"], CallMetrics(duration_ms=0.2, cache_hit=False)),
            ) as mocked_digest,
        ):
            response = self.news_service.search(query="HoyoFest Singapore", limit=5, rerank=True, include_digest=True)

        self.assertTrue(response.items)
        self.assertFalse(mocked_rerank.call_args.kwargs["allow_llm"])
        self.assertFalse(mocked_digest.call_args.kwargs["allow_llm"])

    def test_search_skips_inline_llm_for_specific_local_queries(self) -> None:
        with (
            patch.object(
                self.llm_service,
                "should_skip_inline_search_llm",
                return_value=True,
            ),
            patch.object(
                self.llm_service,
                "expand_query_with_metadata",
                return_value=("latest hoyofest singapore artist alley, HoyoFest Singapore", CallMetrics(duration_ms=0.2, cache_hit=False)),
            ),
            patch.object(
                self.llm_service,
                "rerank_articles_with_metadata",
                return_value=(self.repository.latest_articles(8), CallMetrics(duration_ms=0.1, cache_hit=False)),
            ) as mocked_rerank,
            patch.object(
                self.llm_service,
                "generate_digest_with_metadata",
                return_value=([], CallMetrics(duration_ms=0.0, cache_hit=False)),
            ) as mocked_digest,
        ):
            response = self.news_service.search(query="latest hoyofest singapore artist alley", limit=5, rerank=True, include_digest=True)

        self.assertTrue(response.items)
        self.assertFalse(mocked_rerank.call_args.kwargs["allow_llm"])
        self.assertFalse(mocked_digest.call_args.kwargs["allow_llm"])

    def test_search_digest_skips_llm_for_specific_local_queries(self) -> None:
        response = self.news_service.search(query="latest hoyofest singapore artist alley", limit=5, rerank=False, include_digest=False)
        article_ids = [item.id for item in response.items[:3]]

        with (
            patch.object(
                self.llm_service,
                "should_skip_inline_search_llm",
                return_value=True,
            ),
            patch.object(
                self.llm_service,
                "generate_digest_with_metadata",
                return_value=(["fallback digest"], CallMetrics(duration_ms=0.2, cache_hit=False)),
            ) as mocked_digest,
        ):
            digest, timings = self.news_service.search_digest(query="latest hoyofest singapore artist alley", article_ids=article_ids)

        self.assertEqual(digest, ["fallback digest"])
        self.assertFalse(mocked_digest.call_args.kwargs["allow_llm"])
        self.assertFalse(timings.cache_hit)

    def test_search_digest_can_prefer_llm_for_specific_local_queries(self) -> None:
        response = self.news_service.search(query="latest hoyofest singapore artist alley", limit=5, rerank=False, include_digest=False)
        article_ids = [item.id for item in response.items[:3]]

        with (
            patch.object(
                self.llm_service,
                "should_skip_inline_search_llm",
                return_value=True,
            ),
            patch.object(
                self.llm_service,
                "generate_digest_with_metadata",
                return_value=(["enhanced digest"], CallMetrics(duration_ms=2100.0, cache_hit=False)),
            ) as mocked_digest,
        ):
            digest, timings = self.news_service.search_digest(
                query="latest hoyofest singapore artist alley",
                article_ids=article_ids,
                prefer_llm=True,
            )

        self.assertEqual(digest, ["enhanced digest"])
        self.assertTrue(mocked_digest.call_args.kwargs["allow_llm"])
        self.assertTrue(timings.llm_requested)
        self.assertFalse(timings.llm_skipped)

    def test_search_digest_does_not_recommend_llm_upgrade_for_local_ollama(self) -> None:
        response = self.news_service.search(query="latest hoyofest singapore artist alley", limit=5, rerank=False, include_digest=False)
        article_ids = [item.id for item in response.items[:3]]

        with patch.object(self.llm_service, "should_skip_inline_search_llm", return_value=True):
            _digest, timings = self.news_service.search_digest(query="latest hoyofest singapore artist alley", article_ids=article_ids)

        self.assertFalse(timings.llm_requested)
        self.assertTrue(timings.llm_skipped)
        self.assertFalse(timings.llm_upgrade_recommended)

    def test_search_excludes_internal_link_results(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="afa-internal-watch",
                    title="AFA Singapore internal watchlist",
                    summary="Internal fallback note for AFA Singapore.",
                    content="This internal watch note should never be returned as a search result.",
                    categories=["events", "anime"],
                    tags=["afa", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.99,
                    published_at=now,
                    source_name="Prototype Seed",
                    url="/?query=AFA%20Singapore",
                )
            ]
        )

        response = self.news_service.search(query="afa singapore", limit=5, rerank=False, user_id=None)

        self.assertTrue(response.items)
        self.assertNotIn("AFA Singapore internal watchlist", [item.title for item in response.items])
        self.assertTrue(all(item.url.startswith("http") for item in response.items))

    def test_home_feed_excludes_internal_link_articles(self) -> None:
        now = datetime.now(timezone.utc)
        self.repository.upsert_articles(
            [
                self.make_article(
                    article_id="hoyofest-internal-seed",
                    title="Internal HoyoFest seed note",
                    summary="Internal fallback note for HoyoFest Singapore.",
                    content="This internal seed note should never appear in the home feed.",
                    categories=["events", "gacha", "merch"],
                    tags=["hoyofest", "singapore"],
                    region_tags=["Singapore"],
                    sg_relevance=0.99,
                    published_at=now,
                    source_name="Prototype Seed",
                    url="/?query=HoyoFest%20Singapore",
                )
            ]
        )

        response = self.news_service.home_feed(limit=12)

        self.assertTrue(response.items)
        self.assertNotIn("Internal HoyoFest seed note", [item.title for item in response.items])
        self.assertTrue(all(item.url.startswith("http") for item in response.items))

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
