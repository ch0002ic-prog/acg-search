from __future__ import annotations

import json
from pathlib import Path

from app.schemas import ArticleRecord


def load_sample_articles(data_dir: Path) -> list[ArticleRecord]:
    sample_path = data_dir / "sample_articles.json"
    if not sample_path.exists():
        return []

    records = json.loads(sample_path.read_text(encoding="utf-8"))
    return [ArticleRecord.model_validate(record) for record in records]
