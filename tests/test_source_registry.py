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
        self.assertGreaterEqual(len(live_sources), 40)
        self.assertTrue(
            {
                "RPG Site",
                "RPGamer",
                "Niche Gamer",
                "Anime Corner",
                "Honey's Anime",
                "Otaku USA",
                "Geek Culture",
                "Esports.gg",
                "Esports Insider",
                "Operation Rainfall",
                "Anime Hunch",
                "Anime Trending",
                "NookGaming",
                "Nintendo Everything",
                "J-List Blog",
                "Confirm Good",
                "Google News SEA VTubers",
                "Google News SG Figures",
                "Google News SEA Fighting Games",
                "Google News SG Anisong",
            }.issubset(set(names))
        )
        self.assertTrue(all(source.feed_url for source in live_sources))


if __name__ == "__main__":
    unittest.main()