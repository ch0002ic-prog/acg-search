from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.index import app


class VercelEntrypointTests(unittest.TestCase):
    def test_root_and_static_assets_are_served_through_vercel_entrypoint(self) -> None:
        with TestClient(app) as client:
            health = client.get("/api/health")
            root = client.get("/")
            static_asset = client.get("/static/styles.css")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(root.status_code, 200)
        self.assertIn("ACG Search SG", root.text)
        self.assertEqual(static_asset.status_code, 200)
        self.assertIn(":root", static_asset.text)


if __name__ == "__main__":
    unittest.main()