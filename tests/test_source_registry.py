from __future__ import annotations

import unittest

from app.config import settings
from app.sources.registry import build_sources


class SourceRegistryTests(unittest.TestCase):
    def test_build_sources_expands_live_inventory_without_duplicate_names(self) -> None:
        sources = build_sources(settings)
        names = [source.name for source in sources]
        live_sources = [source for source in sources if source.source_type != "curated"]
        feed_urls = [source.feed_url for source in live_sources]

        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(feed_urls), len(set(feed_urls)))
        self.assertGreaterEqual(len(live_sources), 66)
        self.assertTrue({"SEA Merch News Pages", "SEA Official Event Pages"}.issubset(set(names)))
        self.assertTrue(
            {
                "RPG Site",
                "RPGamer",
                "Niche Gamer",
                "Anime Corner",
                "Crunchyroll News",
                "DualShockers",
                "Tokyo Otaku Mode",
                "Anime Feminist",
                "Final Fantasy XIV News",
                "Honey's Anime",
                "Otaku USA",
                "Geek Culture",
                "Esports.gg",
                "Esports Insider",
                "Operation Rainfall",
                "Anime Hunch",
                "Anime Trending",
                "Rice Digital",
                "MonsterVine",
                "NookGaming",
                "Nintendo Everything",
                "J-List Blog",
                "Google News SEA VTubers",
                "Google News SG Figures",
                "Google News SEA Fighting Games",
                "Google News SG Anisong",
                "Google News SEA Visual Novels",
                "Google News SG Collab Cafes",
                "Google News SEA Gunpla",
                "Google News SEA FFXIV",
                "Google News SG Pop-Up Stores",
                "Google News SEA Rhythm Games",
                "Google News SG Doujin Markets",
                "Google News SEA Anime Screenings",
                "Google News SG Convention Guests",
                "Google News SG Creator Hubs",
                "Google News SEA Anime Exhibitions",
                "Google News SEA Tokusatsu",
                "Google News SEA VTuber Concerts",
                "Google News SEA Capsule Toys",
                "Google News SEA Hobby Conventions",
                "Google News SEA Anime Stage Plays",
                "Google News SEA Arcade Prize Games",
                "Google News SEA Bushiroad TCG Festivals",
                "Google News SEA Anime Distributors",
                "Google News SEA VTuber Merch Collabs",
            }.issubset(set(names))
        )
        self.assertTrue(all(source.feed_url for source in live_sources))


if __name__ == "__main__":
    unittest.main()