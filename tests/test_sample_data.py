from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.sample_data import load_sample_articles


class SampleDataTests(unittest.TestCase):
    def test_load_sample_articles_falls_back_to_repo_seed_when_data_dir_is_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            articles = load_sample_articles(Path(temp_dir))

        self.assertGreater(len(articles), 0)
        self.assertEqual(articles[0].source_name, "Prototype Seed")

    def test_load_sample_articles_prefers_runtime_data_dir_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            sample_path = Path(temp_dir) / "sample_articles.json"
            sample_path.write_text(
                json.dumps(
                    [
                        {
                            "id": "runtime-seed",
                            "title": "Runtime Seed",
                            "url": "https://example.com/runtime-seed",
                            "source_name": "Runtime Seed",
                            "source_type": "seed",
                            "published_at": "2026-04-05T00:00:00+00:00",
                            "summary": "runtime summary",
                            "content": "runtime content",
                            "categories": ["anime"],
                            "tags": ["runtime"],
                            "region_tags": ["Singapore"],
                            "sg_relevance": 1.0,
                            "freshness_score": 1.0,
                            "home_score": 1.0,
                            "source_quality": 0.7,
                            "image_url": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            articles = load_sample_articles(Path(temp_dir))

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].id, "runtime-seed")


if __name__ == "__main__":
    unittest.main()