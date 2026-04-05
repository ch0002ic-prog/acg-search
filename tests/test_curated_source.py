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
                    ]
                ),
                encoding="utf-8",
            )

            source = CuratedSource(
                name="Curated SG Idol Watch",
                feed_url="local://curated-sg-idol-watch",
                file_path=file_path,
                region_hints=["Singapore"],
            )
            articles = source.fetch(limit=5)

        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0].title, "POPPA by Moe Moe Q Singapore idol live watch")
        self.assertEqual(articles[1].title, "Ani-Idol Singapore anisong stage watch")


if __name__ == "__main__":
    unittest.main()