from __future__ import annotations

import unittest

from app.config import settings
from app.sources.registry import build_sources


class SourceRegistryTests(unittest.TestCase):
    def test_build_sources_expands_live_inventory_without_duplicate_names(self) -> None:
        sources = build_sources(settings)
        names = [source.name for source in sources]
        live_sources = [source for source in sources if source.source_type != "curated"]

        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(live_sources), 24)
        self.assertTrue(
            {
                "RPG Site",
                "Automaton West",
                "Noisy Pixel",
                "Kakuchopurei",
                "GamesHub",
                "Final Weapon",
                "Google News SEA Gacha",
                "Google News SEA TCG",
                "Google News SG Cosplay",
            }.issubset(set(names))
        )
        self.assertTrue(all(source.feed_url for source in live_sources))


if __name__ == "__main__":
    unittest.main()