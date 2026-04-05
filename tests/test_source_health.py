from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import threading
import unittest

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord, SourceHealthEntry
from app.services.ingestion import IngestionService
from app.services.llm import LLMService
from app.services.ranking import compute_home_score, score_freshness
from app.services.vector_store import VectorStore
from app.sources.base import BaseSource, SourceArticle


class SuccessSource(BaseSource):
    def __init__(self, articles: list[SourceArticle], **kwargs) -> None:
        super().__init__(**kwargs)
        self._articles = articles

    def fetch(self, limit: int) -> list[SourceArticle]:
        return self._articles[:limit]


class FailingSource(BaseSource):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = message

    def fetch(self, limit: int) -> list[SourceArticle]:
        raise RuntimeError(self.message)


class SourceHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = TemporaryDirectory()
        base_path = Path(cls.temp_dir.name)
        cls.test_settings = replace(
            settings,
            db_path=base_path / "test-source-health.db",
            vector_dir=base_path / "vector-store",
            data_dir=base_path,
            vector_backend="local",
            llm_provider="none",
            llm_model=None,
            enable_llm_enrichment=False,
            source_health_stale_hours=24,
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

    def test_ingest_records_source_health_for_success_and_failure(self) -> None:
        now = datetime.now(timezone.utc)
        success_source = SuccessSource(
            name="Bandwagon Asia",
            feed_url="https://example.com/bandwagon",
            quality=0.8,
            source_type="rss",
            category_hints=["events", "anime"],
            region_hints=["Singapore"],
            articles=[
                SourceArticle(
                    title="Anime Festival Asia Singapore 2026 guide",
                    url="https://example.com/afa-guide",
                    published_at=now - timedelta(hours=1),
                    summary="Guests, merch lanes, and ticket updates for Singapore fans.",
                )
            ],
        )
        failing_source = FailingSource(
            name="Anime Festival Asia",
            feed_url="https://example.com/afa",
            quality=0.82,
            source_type="rss",
            category_hints=["events", "anime"],
            region_hints=["Singapore"],
            message="upstream timeout",
        )
        ingestion_service = IngestionService(
            settings=self.test_settings,
            repository=self.repository,
            vector_store=self.vector_store,
            llm_service=self.llm_service,
            sources=[success_source, failing_source],
        )

        result = ingestion_service.ingest(limit_per_source=10, request_id="test-ingest-1")
        items = self.repository.list_source_health(stale_after_hours=24, now=now)
        by_name = {item.source_name: item for item in items}

        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["persisted"], 1)
        self.assertIn("Bandwagon Asia", by_name)
        self.assertIn("Anime Festival Asia", by_name)
        self.assertEqual(by_name["Bandwagon Asia"].status, "ok")
        self.assertEqual(by_name["Bandwagon Asia"].fetched_count, 1)
        self.assertEqual(by_name["Bandwagon Asia"].persisted_count, 1)
        self.assertEqual(by_name["Bandwagon Asia"].error_count, 0)
        self.assertFalse(by_name["Bandwagon Asia"].stale)
        self.assertEqual(by_name["Anime Festival Asia"].status, "error")
        self.assertEqual(by_name["Anime Festival Asia"].fetched_count, 0)
        self.assertEqual(by_name["Anime Festival Asia"].persisted_count, 0)
        self.assertEqual(by_name["Anime Festival Asia"].error_count, 1)
        self.assertEqual(by_name["Anime Festival Asia"].consecutive_failures, 1)
        self.assertIn("upstream timeout", by_name["Anime Festival Asia"].last_error or "")
        runs = self.repository.list_source_health_runs(limit=10)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].request_id, "test-ingest-1")
        self.assertEqual(runs[0].source_name, "Anime Festival Asia")
        self.assertEqual(runs[1].source_name, "Bandwagon Asia")

    def test_source_health_preserves_last_success_and_marks_stale_after_repeated_failures(self) -> None:
        first_success = datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc)
        first_failure = first_success + timedelta(hours=6)
        second_failure = first_success + timedelta(days=1)
        now = first_success + timedelta(days=4)

        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=3,
            persisted_count=2,
            error_count=0,
            ran_at=first_success,
        )
        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="timeout",
            ran_at=first_failure,
        )
        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="timeout again",
            ran_at=second_failure,
        )

        item = self.repository.list_source_health(stale_after_hours=24, now=now)[0]

        self.assertEqual(item.status, "error")
        self.assertEqual(item.consecutive_failures, 2)
        self.assertEqual(item.last_success_at, first_success)
        self.assertEqual(item.last_run_at, second_failure)
        self.assertTrue(item.stale)
        self.assertEqual(item.last_error, "timeout again")

        runs = self.repository.list_source_health_runs(limit=5, source_name="Bandwagon Asia")
        self.assertEqual(len(runs), 3)
        self.assertEqual(runs[0].request_id, None)
        self.assertEqual(runs[0].status, "error")
        self.assertEqual(runs[0].consecutive_failures, 2)
        self.assertEqual(runs[-1].status, "ok")

        rollup_now = second_failure + timedelta(hours=1)
        rollups = self.repository.list_source_health_rollups(window_hours=24, limit=5, now=rollup_now)
        self.assertEqual(len(rollups), 1)
        self.assertEqual(rollups[0].source_name, "Bandwagon Asia")
        self.assertEqual(rollups[0].total_runs, 2)
        self.assertEqual(rollups[0].failing_runs, 2)
        self.assertEqual(rollups[0].failure_rate, 1.0)
        self.assertEqual(rollups[0].recent_statuses, ["error", "error"])

    def test_bootstrap_source_health_snapshot_seeds_entries_and_runs(self) -> None:
        now = datetime(2026, 4, 5, 11, 0, tzinfo=timezone.utc)
        entries = [
            SourceHealthEntry(
                source_name="Anime Festival Asia",
                status="ok",
                fetched_count=4,
                persisted_count=3,
                error_count=0,
                consecutive_failures=0,
                last_run_at=now,
                last_success_at=now,
                last_error=None,
                stale=False,
            ),
            SourceHealthEntry(
                source_name="Bandwagon Asia",
                status="error",
                fetched_count=0,
                persisted_count=0,
                error_count=1,
                consecutive_failures=2,
                last_run_at=now - timedelta(hours=1),
                last_success_at=now - timedelta(hours=4),
                last_error="upstream timeout",
                stale=False,
            ),
        ]

        self.repository.bootstrap_source_health(entries, request_id="deploy-snapshot")

        items = {item.source_name: item for item in self.repository.list_source_health(stale_after_hours=24, now=now)}
        runs = self.repository.list_source_health_runs(limit=10)

        self.assertEqual(len(items), 2)
        self.assertEqual(items["Anime Festival Asia"].status, "ok")
        self.assertEqual(items["Bandwagon Asia"].consecutive_failures, 2)
        self.assertEqual(items["Bandwagon Asia"].last_error, "upstream timeout")
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].request_id, "deploy-snapshot")
        self.assertEqual(runs[1].request_id, "deploy-snapshot")
        rollups = self.repository.list_source_health_rollups(window_hours=24, limit=5, now=now)
        by_name = {rollup.source_name: rollup for rollup in rollups}
        self.assertEqual(len(rollups), 2)
        self.assertEqual(by_name["Anime Festival Asia"].healthy_runs, 1)
        self.assertEqual(by_name["Bandwagon Asia"].failing_runs, 1)

    def test_concurrent_source_health_failures_do_not_lose_counts(self) -> None:
        worker_count = 6
        barrier = threading.Barrier(worker_count)

        def write_failure(index: int) -> None:
            barrier.wait(timeout=5)
            self.repository.record_source_health(
                source_name="Bandwagon Asia",
                status="error",
                fetched_count=0,
                persisted_count=0,
                error_count=1,
                last_error=f"timeout-{index}",
                request_id=f"concurrent-{index}",
            )

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(write_failure, index) for index in range(worker_count)]
            for future in futures:
                future.result(timeout=10)

        item = self.repository.list_source_health(stale_after_hours=24)[0]
        runs = self.repository.list_source_health_runs(limit=worker_count + 2, source_name="Bandwagon Asia")

        self.assertEqual(item.source_name, "Bandwagon Asia")
        self.assertEqual(item.status, "error")
        self.assertEqual(item.consecutive_failures, worker_count)
        self.assertEqual(len(runs), worker_count)

    def test_prune_source_health_runs_removes_entries_older_than_retention_window(self) -> None:
        old_run = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
        recent_run = datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc)
        prune_now = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)

        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=2,
            persisted_count=2,
            error_count=0,
            ran_at=old_run,
            request_id="old-run",
        )
        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=1,
            persisted_count=1,
            error_count=0,
            ran_at=recent_run,
            request_id="recent-run",
        )

        deleted = self.repository.prune_source_health_runs(retention_days=30, now=prune_now)
        remaining_runs = self.repository.list_source_health_runs(limit=10, source_name="Bandwagon Asia")

        self.assertEqual(deleted, 1)
        self.assertEqual(len(remaining_runs), 1)
        self.assertEqual(remaining_runs[0].request_id, "recent-run")

    def test_source_health_rollups_ignore_runs_outside_window(self) -> None:
        old_run = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
        inside_window = datetime(2026, 4, 5, 8, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc)

        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="old timeout",
            ran_at=old_run,
        )
        self.repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=2,
            persisted_count=2,
            error_count=0,
            ran_at=inside_window,
        )
        self.repository.record_source_health(
            source_name="Anime Festival Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="recent timeout",
            ran_at=inside_window,
        )

        rollups = self.repository.list_source_health_rollups(window_hours=24, limit=5, now=now)

        self.assertEqual(len(rollups), 2)
        self.assertEqual(rollups[0].source_name, "Anime Festival Asia")
        self.assertEqual(rollups[0].failure_rate, 1.0)
        self.assertEqual(rollups[0].recent_statuses, ["error"])
        self.assertEqual(rollups[1].source_name, "Bandwagon Asia")
        self.assertEqual(rollups[1].total_runs, 1)
        self.assertEqual(rollups[1].healthy_runs, 1)
        self.assertEqual(rollups[1].recent_statuses, ["ok"])


if __name__ == "__main__":
    unittest.main()