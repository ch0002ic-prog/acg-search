from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.schemas import FeedResponse, RefreshResponse, SourceHealthEntry, SourceHealthRollupEntry, SourceHealthRunEntry, UserProfile


class FakeNewsService:
    def __init__(self) -> None:
        self.last_home_args: tuple[int, str | None] | None = None
        self.last_search_args: tuple[str, int, bool, str | None, bool] | None = None

    def home_feed(self, limit: int, user_id: str | None = None) -> FeedResponse:
        self.last_home_args = (limit, user_id)
        return FeedResponse(items=[])

    def search(
        self,
        query: str,
        limit: int,
        rerank: bool = True,
        user_id: str | None = None,
        track_profile: bool = True,
    ) -> FeedResponse:
        self.last_search_args = (query, limit, rerank, user_id, track_profile)
        return FeedResponse(items=[], query=query, expanded_query=query)


class FakeRepository:
    def __init__(self) -> None:
        self.last_profile_update: dict[str, object] | None = None
        self.last_interaction: tuple[str, str, str] | None = None
        self.last_stale_after_hours: int | None = None
        self.last_source_health_runs_args: tuple[int, str | None] | None = None
        self.last_source_health_rollups_args: tuple[int, int] | None = None

    def get_or_create_user_profile(self, user_id: str) -> UserProfile:
        return UserProfile(user_id=user_id)

    def update_user_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        pinned_categories: list[str] | None = None,
        pinned_tags: list[str] | None = None,
        pinned_entities: list[str] | None = None,
        pinned_regions: list[str] | None = None,
    ) -> UserProfile:
        self.last_profile_update = {
            "user_id": user_id,
            "display_name": display_name,
            "pinned_categories": pinned_categories or [],
            "pinned_tags": pinned_tags or [],
            "pinned_entities": pinned_entities or [],
            "pinned_regions": pinned_regions or [],
        }
        return UserProfile(
            user_id=user_id,
            display_name=display_name,
            pinned_categories=pinned_categories or [],
            pinned_tags=pinned_tags or [],
            pinned_entities=pinned_entities or [],
            pinned_regions=pinned_regions or [],
        )

    def record_interaction(self, user_id: str, article_id: str, action: str) -> UserProfile:
        self.last_interaction = (user_id, article_id, action)
        if article_id == "missing-article":
            raise LookupError("Unknown article id")
        return UserProfile(user_id=user_id, interaction_count=1)

    def list_source_health(self, stale_after_hours: int) -> list[SourceHealthEntry]:
        self.last_stale_after_hours = stale_after_hours
        return [
            SourceHealthEntry(
                source_name="Bandwagon Asia",
                status="ok",
                fetched_count=4,
                persisted_count=3,
                error_count=0,
                consecutive_failures=0,
                last_run_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
                last_success_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
                stale=False,
            ),
            SourceHealthEntry(
                source_name="Anime Festival Asia",
                status="error",
                fetched_count=0,
                persisted_count=0,
                error_count=1,
                consecutive_failures=2,
                last_run_at=datetime(2026, 4, 4, 8, 0, tzinfo=timezone.utc),
                last_success_at=datetime(2026, 4, 3, 8, 0, tzinfo=timezone.utc),
                last_error="upstream timeout",
                stale=True,
            ),
        ]

    def list_source_health_runs(self, limit: int = 50, source_name: str | None = None) -> list[SourceHealthRunEntry]:
        self.last_source_health_runs_args = (limit, source_name)
        return [
            SourceHealthRunEntry(
                id=2,
                source_name="Anime Festival Asia",
                request_id="req-2",
                status="error",
                fetched_count=0,
                persisted_count=0,
                error_count=1,
                consecutive_failures=2,
                last_error="upstream timeout",
                ran_at=datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc),
            ),
            SourceHealthRunEntry(
                id=1,
                source_name="Bandwagon Asia",
                request_id="req-1",
                status="ok",
                fetched_count=4,
                persisted_count=3,
                error_count=0,
                consecutive_failures=0,
                ran_at=datetime(2026, 4, 5, 7, 0, tzinfo=timezone.utc),
            ),
        ]

    def list_source_health_rollups(self, window_hours: int = 24, limit: int = 10) -> list[SourceHealthRollupEntry]:
        self.last_source_health_rollups_args = (window_hours, limit)
        return [
            SourceHealthRollupEntry(
                source_name="Anime Festival Asia",
                total_runs=3,
                healthy_runs=1,
                failing_runs=2,
                failure_rate=0.667,
                recent_statuses=["error", "error", "ok"],
                latest_status="error",
                latest_ran_at=datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc),
                latest_error="upstream timeout",
            ),
            SourceHealthRollupEntry(
                source_name="Bandwagon Asia",
                total_runs=2,
                healthy_runs=2,
                failing_runs=0,
                failure_rate=0.0,
                recent_statuses=["ok", "ok"],
                latest_status="ok",
                latest_ran_at=datetime(2026, 4, 5, 7, 0, tzinfo=timezone.utc),
            ),
        ]


class FakeIngestionService:
    def __init__(self) -> None:
        self.called = 0
        self.last_request_id: str | None = None

    def ingest(self, request_id: str | None = None) -> dict[str, object]:
        self.called += 1
        self.last_request_id = request_id
        return RefreshResponse(fetched=0, persisted=0, seed_used=False, errors=[]).model_dump()


class FakeStateStore:
    def __init__(self) -> None:
        self.persist_paths: list[str] = []

    def persist_from(self, db_path) -> bool:
        self.persist_paths.append(str(db_path))
        return True


def build_test_app(state_store: FakeStateStore | None = None) -> tuple[FastAPI, FakeNewsService, FakeRepository, FakeIngestionService]:
    app = FastAPI()
    main_module.install_request_timing_middleware(app)
    news_service = FakeNewsService()
    repository = FakeRepository()
    ingestion_service = FakeIngestionService()

    app.state.news_service = news_service
    app.state.repository = repository
    app.state.ingestion_service = ingestion_service
    app.state.state_store = state_store

    app.add_api_route("/api/news", main_module.news, methods=["GET"], response_model=FeedResponse)
    app.add_api_route("/api/search", main_module.search, methods=["POST"], response_model=FeedResponse)
    app.add_api_route("/api/profile", main_module.get_profile, methods=["GET"], response_model=UserProfile)
    app.add_api_route("/api/source-health", main_module.source_health, methods=["GET"])
    app.add_api_route("/api/source-health/runs", main_module.source_health_runs, methods=["GET"])
    app.add_api_route("/api/source-health/rollups", main_module.source_health_rollups, methods=["GET"])
    app.add_api_route("/api/profile", main_module.update_profile, methods=["POST"], response_model=UserProfile)
    app.add_api_route("/api/interactions", main_module.record_interaction, methods=["POST"], response_model=UserProfile)
    app.add_api_route("/api/refresh", main_module.refresh, methods=["POST"], response_model=RefreshResponse)

    return app, news_service, repository, ingestion_service


class ApiEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_settings = main_module.settings
        main_module.settings = replace(main_module.settings, allow_remote_refresh=False, default_feed_limit=12, request_slow_log_ms=750)

    def tearDown(self) -> None:
        main_module.settings = self.original_settings

    def test_news_rejects_limit_above_cap(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/news", params={"limit": 999})

        self.assertEqual(response.status_code, 422)

    def test_news_rejects_user_id_above_cap(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/news", params={"user_id": "x" * 65})

        self.assertEqual(response.status_code, 422)

    def test_profile_rejects_user_id_above_cap(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/profile", params={"user_id": "x" * 65})

        self.assertEqual(response.status_code, 422)

    def test_source_health_returns_summary_counts(self) -> None:
        app, _, repository, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/source-health", params={"stale_after_hours": 12})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(repository.last_stale_after_hours, 12)
        self.assertEqual(payload["healthy_count"], 1)
        self.assertEqual(payload["failing_count"], 1)
        self.assertEqual(payload["stale_count"], 1)
        self.assertEqual(len(payload["items"]), 2)

    def test_source_health_runs_returns_recent_history(self) -> None:
        app, _, repository, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/source-health/runs", params={"limit": 10, "source_name": "Anime Festival Asia"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(repository.last_source_health_runs_args, (10, "Anime Festival Asia"))
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["request_id"], "req-2")

    def test_source_health_rollups_returns_windowed_summary(self) -> None:
        app, _, repository, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/source-health/rollups", params={"window_hours": 24, "limit": 6})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(repository.last_source_health_rollups_args, (24, 6))
        self.assertEqual(payload["window_hours"], 24)
        self.assertEqual(payload["items"][0]["source_name"], "Anime Festival Asia")
        self.assertEqual(payload["items"][0]["recent_statuses"], ["error", "error", "ok"])

    def test_news_accepts_valid_limit_and_user_id(self) -> None:
        app, news_service, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.get("/api/news", params={"limit": 7, "user_id": "sg-fan-1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(news_service.last_home_args, (7, "sg-fan-1"))

    def test_search_rejects_query_above_cap(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.post("/api/search", json={"query": "x" * 201})

        self.assertEqual(response.status_code, 422)

    def test_search_forwards_track_profile_flag(self) -> None:
        app, news_service, _, _ = build_test_app()
        with self.assertLogs("app.main", level="INFO") as captured:
            with TestClient(app) as client:
                response = client.post(
                    "/api/search",
                    json={"query": "AFA Singapore", "limit": 9, "rerank": False, "user_id": "sg-fan-1", "track_profile": False},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(news_service.last_search_args, ("AFA Singapore", 9, False, "sg-fan-1", False))
        self.assertTrue(response.headers.get("X-Request-ID"))
        self.assertTrue(any("API request completed" in message and "/api/search" in message for message in captured.output))
        self.assertTrue(any("Search response ready" in message and response.headers["X-Request-ID"] in message for message in captured.output))

    def test_personalized_search_persists_runtime_state(self) -> None:
        state_store = FakeStateStore()
        app, _, _, _ = build_test_app(state_store=state_store)
        with TestClient(app) as client:
            response = client.post(
                "/api/search",
                json={"query": "AFA Singapore", "limit": 9, "rerank": False, "user_id": "sg-fan-1", "track_profile": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(state_store.persist_paths), 1)
        self.assertEqual(state_store.persist_paths[0], str(main_module.settings.db_path))

    def test_anonymous_search_skips_runtime_state_persistence(self) -> None:
        state_store = FakeStateStore()
        app, _, _, _ = build_test_app(state_store=state_store)
        with TestClient(app) as client:
            response = client.post("/api/search", json={"query": "AFA Singapore", "limit": 9, "rerank": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(state_store.persist_paths, [])

    def test_request_id_header_is_preserved_when_supplied(self) -> None:
        app, _, _, ingestion_service = build_test_app()
        with self.assertLogs("app.main", level="INFO") as captured:
            with TestClient(app, client=("127.0.0.1", 50000)) as client:
                response = client.post("/api/refresh", headers={"X-Request-ID": "demo-request-123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), "demo-request-123")
        self.assertEqual(ingestion_service.last_request_id, "demo-request-123")
        self.assertTrue(any("demo-request-123" in message for message in captured.output))

    def test_slow_request_logs_warning(self) -> None:
        main_module.settings = replace(main_module.settings, request_slow_log_ms=0)
        app, _, _, _ = build_test_app()
        with self.assertLogs("app.main", level="WARNING") as captured:
            with TestClient(app) as client:
                response = client.get("/api/news", params={"limit": 3})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any("Slow API request" in message and "/api/news" in message for message in captured.output))

    def test_profile_update_rejects_too_many_pinned_entities(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/profile",
                json={"user_id": "sg-fan-1", "pinned_entities": [f"entity-{index}" for index in range(17)]},
            )

        self.assertEqual(response.status_code, 422)

    def test_profile_update_accepts_bounded_lists(self) -> None:
        app, _, repository, _ = build_test_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/profile",
                json={
                    "user_id": "sg-fan-1",
                    "display_name": "Singapore Fan",
                    "pinned_categories": ["anime", "events"],
                    "pinned_entities": ["AFA Singapore"],
                    "pinned_regions": ["Singapore"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.last_profile_update["pinned_entities"], ["AFA Singapore"])

    def test_interaction_rejects_unknown_article(self) -> None:
        app, _, _, _ = build_test_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/interactions",
                json={"user_id": "sg-fan-1", "article_id": "missing-article", "action": "open"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Article not found.")

    def test_interaction_accepts_known_article(self) -> None:
        app, _, repository, _ = build_test_app()
        with TestClient(app) as client:
            response = client.post(
                "/api/interactions",
                json={"user_id": "sg-fan-1", "article_id": "afa-guide", "action": "like"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.last_interaction, ("sg-fan-1", "afa-guide", "like"))

    def test_refresh_is_allowed_for_loopback_clients(self) -> None:
        app, _, _, ingestion_service = build_test_app()
        with self.assertLogs("app.main", level="INFO") as captured:
            with TestClient(app, client=("127.0.0.1", 50000)) as client:
                response = client.post("/api/refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ingestion_service.called, 1)
        self.assertEqual(ingestion_service.last_request_id, response.headers.get("X-Request-ID"))
        self.assertTrue(any("API request completed" in message and "/api/refresh" in message for message in captured.output))

    def test_refresh_persists_runtime_state_after_ingest(self) -> None:
        state_store = FakeStateStore()
        app, _, _, ingestion_service = build_test_app(state_store=state_store)
        with TestClient(app, client=("127.0.0.1", 50000)) as client:
            response = client.post("/api/refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ingestion_service.called, 1)
        self.assertEqual(len(state_store.persist_paths), 1)

    def test_refresh_rejects_non_local_clients_by_default(self) -> None:
        app, _, _, ingestion_service = build_test_app()
        with TestClient(app, client=("198.51.100.10", 50000)) as client:
            response = client.post("/api/refresh")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Refresh is limited to local requests unless ALLOW_REMOTE_REFRESH=true.")
        self.assertEqual(ingestion_service.called, 0)

    def test_refresh_allows_non_local_clients_when_enabled(self) -> None:
        main_module.settings = replace(main_module.settings, allow_remote_refresh=True)
        app, _, _, ingestion_service = build_test_app()
        with TestClient(app, client=("198.51.100.10", 50000)) as client:
            response = client.post("/api/refresh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ingestion_service.called, 1)


if __name__ == "__main__":
    unittest.main()