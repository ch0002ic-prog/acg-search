from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.sources.curated import CuratedSource


class CuratedSourceTests(unittest.TestCase):
    def test_fetch_returns_curated_articles_from_local_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "curated_articles.json"
            file_path.write_text(
                json.dumps(
                    [
                        {
                            "title": "POPPA by Moe Moe Q Singapore idol live watch",
                            "url": "https://example.com/poppa",
                            "published_at": "2026-04-01T12:00:00+00:00",
                            "summary": "Curated MMQ/POPPA coverage.",
                            "content": "Curated MMQ/POPPA coverage.",
                            "category_hints": ["events", "anime"],
                            "region_hints": ["Singapore"],
                        },
                        {
                            "title": "Ani-Idol Singapore anisong stage watch",
                            "url": "https://example.com/ani-idol",
                            "published_at": "2026-04-01T12:00:00+00:00",
                            "summary": "Curated Ani-Idol coverage.",
                            "content": "Curated Ani-Idol coverage.",
                            "category_hints": ["events", "anime"],
                            "region_hints": ["Singapore"],
                        },
                        {
                            "title": "HoyoFest Singapore watch for HoYoVerse merch booths and cafe drops",
                            "url": "https://example.com/hoyofest",
                            "published_at": "2026-04-06T12:00:00+00:00",
                            "summary": "Curated HoyoFest coverage.",
                            "content": "Curated HoyoFest coverage.",
                            "category_hints": ["events", "gacha", "merch"],
                            "region_hints": ["Singapore"],
                        },
                        {
                            "title": "Artist Alley Singapore watch for Anime Festival Asia and SGCC creator booths",
                            "url": "https://example.com/artist-alley",
                            "published_at": "2026-04-06T12:00:00+00:00",
                            "summary": "Curated artist alley coverage.",
                            "content": "Curated artist alley coverage.",
                            "category_hints": ["events", "anime", "merch"],
                            "region_hints": ["Singapore"],
                        },
                        {
                            "title": "Internal curated watch that should be skipped",
                            "url": "/?query=internal-watch",
                            "published_at": "2026-04-06T12:00:00+00:00",
                            "summary": "This should never be returned.",
                            "content": "This should never be returned.",
                            "category_hints": ["events"],
                            "region_hints": ["Singapore"],
                        },
                    ]
                ),
                encoding="utf-8",
            )

            source = CuratedSource(
                name="SG Source Pages",
                feed_url="local://curated-sg-search-watch",
                file_path=file_path,
                region_hints=["Singapore"],
            )
            articles = source.fetch(limit=5)

        self.assertEqual(len(articles), 4)
        self.assertEqual(articles[0].title, "POPPA by Moe Moe Q Singapore idol live watch")
        self.assertEqual(articles[1].title, "Ani-Idol Singapore anisong stage watch")
        self.assertEqual(articles[2].title, "HoyoFest Singapore watch for HoYoVerse merch booths and cafe drops")
        self.assertEqual(articles[3].title, "Artist Alley Singapore watch for Anime Festival Asia and SGCC creator booths")

    def test_repository_curated_articles_have_unique_titles_and_urls(self) -> None:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        curated_files = sorted(data_dir.glob("curated*_articles.json"))
        curated_articles = [
            article
            for file_path in curated_files
            for article in json.loads(file_path.read_text(encoding="utf-8"))
        ]

        titles = [article["title"] for article in curated_articles]
        urls = [article["url"] for article in curated_articles]

        self.assertGreaterEqual(len(curated_files), 3)
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(len(urls), len(set(urls)))
        self.assertTrue(all(url.startswith(("http://", "https://")) for url in urls))


if __name__ == "__main__":
    unittest.main()