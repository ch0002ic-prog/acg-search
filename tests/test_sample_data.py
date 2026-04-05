from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.sample_data import load_sample_articles


class SampleDataTests(unittest.TestCase):
    def test_load_sample_articles_falls_back_to_repo_bootstrap_data_when_data_dir_is_empty(self) -> None:
        with TemporaryDirectory() as temp_dir:
            articles = load_sample_articles(Path(temp_dir))

        self.assertGreater(len(articles), 0)
        self.assertTrue(articles[0].title)
        self.assertTrue(articles[0].url)

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

    def test_load_sample_articles_prefers_deploy_snapshot_over_sample_seed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "sample_articles.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "sample-seed",
                            "title": "Sample Seed",
                            "url": "https://example.com/sample-seed",
                            "source_name": "Sample Seed",
                            "source_type": "seed",
                            "published_at": "2026-04-05T00:00:00+00:00",
                            "summary": "sample summary",
                            "content": "sample content",
                            "categories": ["anime"],
                            "tags": ["sample"],
                            "region_tags": ["Singapore"],
                            "sg_relevance": 0.8,
                            "freshness_score": 0.8,
                            "home_score": 0.8,
                            "source_quality": 0.6,
                            "image_url": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (temp_path / "deploy_articles.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "deploy-seed",
                            "title": "Deploy Snapshot",
                            "url": "https://example.com/deploy-seed",
                            "source_name": "Deploy Snapshot",
                            "source_type": "seed",
                            "published_at": "2026-04-05T00:00:00+00:00",
                            "summary": "deploy summary",
                            "content": "",
                            "categories": ["events"],
                            "tags": ["deploy"],
                            "region_tags": ["Singapore"],
                            "sg_relevance": 0.9,
                            "freshness_score": 0.9,
                            "home_score": 0.9,
                            "source_quality": 0.7,
                            "image_url": None,
                        }
                    ]
                ),
                encoding="utf-8",
            )

            articles = load_sample_articles(temp_path)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].id, "deploy-seed")


if __name__ == "__main__":
    unittest.main()