from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None

from app.database import ArticleRepository


def _find_open_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class BrowserNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright is not installed")

        cls.temp_dir = TemporaryDirectory()
        cls.data_dir = Path(cls.temp_dir.name)
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.sample_path = cls.data_dir / "sample_articles.json"
        cls.sample_path.write_text(json.dumps(cls._sample_articles(), indent=2), encoding="utf-8")

        cls.db_path = cls.data_dir / "browser-test.db"
        cls._seed_source_health(cls.db_path)

        cls.port = _find_open_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        env = {
            **dict(**__import__("os").environ),
            "DATA_DIR": str(cls.data_dir),
            "DB_PATH": str(cls.db_path),
            "VECTOR_DIR": str(cls.data_dir / "browser-vector-store"),
            "VECTOR_BACKEND": "local",
            "LLM_PROVIDER": "none",
            "DISABLE_HTTP_CACHE": "true",
            "DEFAULT_FEED_LIMIT": "8",
        }
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(cls.port)],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        cls._wait_for_server()

        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "playwright"):
            cls.playwright.stop()
        if hasattr(cls, "server"):
            cls.server.terminate()
            try:
                cls.server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=10)
            if cls.server.stdout is not None:
                cls.server.stdout.close()
        if hasattr(cls, "temp_dir"):
            cls.temp_dir.cleanup()

    @classmethod
    def _wait_for_server(cls) -> None:
        deadline = time.time() + 20
        last_error: Exception | None = None
        while time.time() < deadline:
            if cls.server.poll() is not None:
                output = cls.server.stdout.read() if cls.server.stdout else ""
                raise RuntimeError(f"Browser test server exited early: {output}")
            try:
                with urllib.request.urlopen(f"{cls.base_url}/api/health", timeout=1) as response:
                    payload = json.load(response)
                if payload.get("status") == "ok":
                    return
            except Exception as exc:  # pragma: no cover
                last_error = exc
                time.sleep(0.2)
        raise RuntimeError(f"Timed out waiting for browser test server: {last_error}")

    @classmethod
    def _seed_source_health(cls, db_path: Path) -> None:
        repository = ArticleRepository(db_path)
        repository.init_database()
        now = datetime.now(timezone.utc)

        repository.record_source_health(
            source_name="Anime Festival Asia",
            status="ok",
            fetched_count=4,
            persisted_count=3,
            error_count=0,
            ran_at=now - timedelta(hours=6),
            request_id="req-browser-afa-ok",
        )
        repository.record_source_health(
            source_name="Anime Festival Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="upstream timeout",
            ran_at=now - timedelta(hours=2),
            request_id="req-browser-afa-error-1",
        )
        repository.record_source_health(
            source_name="Anime Festival Asia",
            status="error",
            fetched_count=0,
            persisted_count=0,
            error_count=1,
            last_error="upstream timeout again",
            ran_at=now - timedelta(hours=1),
            request_id="req-browser-afa-error-2",
        )
        repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=5,
            persisted_count=4,
            error_count=0,
            ran_at=now - timedelta(hours=4),
            request_id="req-browser-bandwagon-ok-1",
        )
        repository.record_source_health(
            source_name="Bandwagon Asia",
            status="ok",
            fetched_count=3,
            persisted_count=2,
            error_count=0,
            ran_at=now - timedelta(minutes=30),
            request_id="req-browser-bandwagon-ok-2",
        )

    @staticmethod
    def _sample_articles() -> list[dict[str, object]]:
        return [
            {
                "id": "browser-afa-guide",
                "title": "Anime Festival Asia Singapore 2026 ticket guide",
                "url": "https://example.com/browser-afa-guide",
                "source_name": "Bandwagon Asia",
                "source_type": "rss",
                "published_at": "2026-04-05T08:30:00+00:00",
                "summary": "Early bird sales open 14 Nov 2026 at Suntec Convention Centre featuring LiSA and Aimer.",
                "content": "Bandwagon previews Anime Festival Asia Singapore ticket windows, guest reveals, and merch lanes.",
                "categories": ["events", "anime", "merch"],
                "tags": ["afa", "singapore"],
                "entity_tags": ["AFA Singapore"],
                "region_tags": ["Singapore", "SEA"],
                "sg_relevance": 0.95,
                "freshness_score": 0.92,
                "home_score": 0.94,
                "source_quality": 0.82,
                "image_url": None,
            },
            {
                "id": "browser-afa-lineup",
                "title": "Anime Festival Asia Singapore guest lineup update",
                "url": "https://example.com/browser-afa-lineup",
                "source_name": "Anime Festival Asia",
                "source_type": "rss",
                "published_at": "2026-04-05T07:40:00+00:00",
                "summary": "Guests: LiSA, Aimer. Ticket guide for AFA Singapore is now live at Suntec Convention & Exhibition Centre.",
                "content": "The official AFA feed highlights guests, merch lanes, and entry planning for Singapore fans.",
                "categories": ["events", "anime", "merch"],
                "tags": ["afa", "singapore"],
                "entity_tags": ["AFA Singapore"],
                "region_tags": ["Singapore"],
                "sg_relevance": 0.94,
                "freshness_score": 0.9,
                "home_score": 0.93,
                "source_quality": 0.86,
                "image_url": None,
            },
            {
                "id": "browser-mlbb",
                "title": "MLBB Singapore community qualifier watch",
                "url": "https://example.com/browser-mlbb",
                "source_name": "Prototype Seed",
                "source_type": "seed",
                "published_at": "2026-04-05T06:00:00+00:00",
                "summary": "Community MLBB brackets build momentum for the next Singapore weekend.",
                "content": "A control story to keep the browser test feed mixed and realistic.",
                "categories": ["esports", "games"],
                "tags": ["mlbb", "singapore"],
                "entity_tags": ["MLBB"],
                "region_tags": ["Singapore", "SEA"],
                "sg_relevance": 0.86,
                "freshness_score": 0.84,
                "home_score": 0.85,
                "source_quality": 0.7,
                "image_url": None,
            },
        ]

    def test_back_forward_restores_search_and_cluster_modal_state(self) -> None:
        page = self.browser.new_page()
        try:
            page.goto(self.base_url, wait_until="networkidle")
            page.wait_for_function(
                "() => document.querySelector('#feed-title')?.textContent?.includes('Singapore-weighted headline stack')"
            )

            page.locator("#query-input").fill("AFA Singapore")
            page.get_by_role("button", name="Search Feed").click()

            page.wait_for_function(
                "() => document.querySelector('#feed-title')?.textContent?.includes('AFA Singapore')"
            )
            self.assertIn("query=AFA", page.url)
            self.assertEqual(page.locator("#query-input").input_value(), "AFA Singapore")

            page.locator(".cluster-card summary").first.click()
            page.wait_for_function("() => document.querySelector('.cluster-card')?.open === true")
            page.get_by_role("button", name="Cluster detail").first.click()
            page.wait_for_function("() => document.querySelector('#cluster-detail-modal')?.open === true")
            page.wait_for_function("() => window.location.search.includes('entity=')")
            self.assertIn("entity=AFA", page.url)

            page.get_by_role("button", name="Close").click()
            page.wait_for_function("() => document.querySelector('#cluster-detail-modal')?.open === false")
            page.wait_for_function("() => !window.location.search.includes('entity=')")
            self.assertIn("query=AFA", page.url)
            self.assertNotIn("entity=", page.url)

            page.go_back()
            page.wait_for_function("() => document.querySelector('#cluster-detail-modal')?.open === true")
            page.wait_for_function("() => window.location.search.includes('entity=')")
            self.assertIn("entity=AFA", page.url)

            page.go_back()
            page.wait_for_function("() => document.querySelector('#cluster-detail-modal')?.open === false")
            page.wait_for_function(
                "() => document.querySelector('#feed-title')?.textContent?.includes('AFA Singapore')"
            )
            page.wait_for_function("() => !window.location.search.includes('entity=')")
            self.assertIn("query=AFA", page.url)
            self.assertNotIn("entity=", page.url)

            page.go_back()
            page.wait_for_function(
                "() => document.querySelector('#feed-title')?.textContent?.includes('Singapore-weighted headline stack')"
            )
            self.assertEqual(page.locator("#query-input").input_value(), "")
            self.assertNotIn("query=", page.url)

            page.go_forward()
            page.wait_for_function(
                "() => document.querySelector('#feed-title')?.textContent?.includes('AFA Singapore')"
            )
            self.assertEqual(page.locator("#query-input").input_value(), "AFA Singapore")

            page.go_forward()
            page.wait_for_function("() => document.querySelector('#cluster-detail-modal')?.open === true")
            page.wait_for_function("() => window.location.search.includes('entity=')")
            self.assertIn("entity=AFA", page.url)
        finally:
            page.close()

    def test_source_health_rollup_preview_and_modal_history(self) -> None:
        page = self.browser.new_page()
        try:
            page.goto(self.base_url, wait_until="networkidle")
            page.wait_for_function(
                "() => document.querySelectorAll('#source-health-rollups .source-health-rollup-card').length >= 2"
            )

            afa_rollup = page.locator("#source-health-rollups .source-health-rollup-card").filter(has_text="Anime Festival Asia").first
            self.assertEqual(afa_rollup.locator(".source-health-sparkline-dot").count(), 3)

            afa_rollup.get_by_role("button", name="Preview runs").click()
            page.wait_for_function(
                "() => document.querySelector('#source-health-runs')?.textContent?.includes('Recent runs for Anime Festival Asia')"
            )
            self.assertIn("Anime Festival Asia", page.locator("#source-health-runs").text_content() or "")

            page.locator("#source-health-runs").get_by_role("button", name="Full history").click()
            page.wait_for_function("() => document.querySelector('#source-health-modal')?.open === true")
            page.wait_for_function(
                "() => (document.querySelector('#source-health-modal-list')?.textContent || '').includes('req-browser-afa-error-2')"
            )

            self.assertEqual(page.locator("#source-health-modal-title").text_content(), "Anime Festival Asia")
            self.assertIn("timeout", page.locator("#source-health-modal-status").text_content() or "")
            self.assertGreaterEqual(page.locator("#source-health-modal-list .source-health-modal-item").count(), 3)
            self.assertIn("req-browser-afa-error-2", page.locator("#source-health-modal-list").text_content() or "")

            page.locator("#source-health-modal-close").click()
            page.wait_for_function("() => document.querySelector('#source-health-modal')?.open === false")

            page.locator("#source-health-runs").get_by_role("button", name="Show all").click()
            page.wait_for_function(
                "() => document.querySelector('#source-health-runs')?.textContent?.includes('Recent ingest runs')"
            )
        finally:
            page.close()


if __name__ == "__main__":
    unittest.main()