from __future__ import annotations

import json
from pathlib import Path

from app.schemas import ArticleRecord


def _candidate_sample_paths(data_dir: Path) -> list[Path]:
    repo_data_dir = Path(__file__).resolve().parents[2] / "data"
    return list(
        dict.fromkeys(
            [
                data_dir / "deploy_articles.json",
                data_dir / "sample_articles.json",
                repo_data_dir / "deploy_articles.json",
                repo_data_dir / "sample_articles.json",
            ]
        )
    )


def load_sample_articles(data_dir: Path) -> list[ArticleRecord]:
    for sample_path in _candidate_sample_paths(data_dir):
        if not sample_path.exists():
            continue
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        return [ArticleRecord.model_validate(record) for record in records]
    return []
