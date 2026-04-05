from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VercelConfigTests(unittest.TestCase):
    def test_vercel_config_uses_fastapi_framework_and_only_api_function_overrides(self) -> None:
        config = json.loads((ROOT / "vercel.json").read_text())

        self.assertEqual(config.get("framework"), "fastapi")

        functions = config.get("functions", {})
        self.assertIsInstance(functions, dict)
        for pattern in functions:
            self.assertTrue(
                pattern.startswith("api/"),
                msg=f"Unsupported Vercel functions override outside api/: {pattern}",
            )


if __name__ == "__main__":
    unittest.main()