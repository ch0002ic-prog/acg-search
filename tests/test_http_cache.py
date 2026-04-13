from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

import app.main as main_module


class HttpCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        static_dir = Path(self.temp_dir.name)
        (static_dir / "styles.css").write_text("body { color: black; }\n", encoding="utf-8")
        (static_dir / "index.html").write_text("<html><body>ok</body></html>\n", encoding="utf-8")
        (static_dir / "favicon.ico").write_bytes(b"ico")

        self.original_settings = main_module.settings
        main_module.settings = replace(main_module.settings, disable_http_cache=True, static_dir=static_dir, root_dir=static_dir)

        app = FastAPI()
        app.mount("/static", main_module.CacheControlledStaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(static_dir / "index.html", headers=main_module.NO_CACHE_HEADERS)

        app.add_api_route("/favicon.ico", main_module.favicon, methods=["GET"], include_in_schema=False)

        self.client = TestClient(app)

    def tearDown(self) -> None:
        main_module.settings = self.original_settings
        self.temp_dir.cleanup()

    def test_static_assets_are_served_with_no_cache_headers(self) -> None:
        response = self.client.get("/static/styles.css")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store, no-cache, must-revalidate, max-age=0")

    def test_static_assets_do_not_return_304_on_conditional_request(self) -> None:
        first = self.client.get("/static/styles.css")
        second = self.client.get("/static/styles.css", headers={"If-None-Match": first.headers.get("etag", "")})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

    def test_index_is_served_with_no_cache_headers(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store, no-cache, must-revalidate, max-age=0")

    def test_favicon_is_served_with_no_cache_headers(self) -> None:
        response = self.client.get("/favicon.ico")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ico")
        self.assertEqual(response.headers.get("cache-control"), "no-store, no-cache, must-revalidate, max-age=0")
