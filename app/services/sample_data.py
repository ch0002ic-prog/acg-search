from __future__ import annotations

import json
from pathlib import Path

from app.schemas import ArticleRecord, SourceHealthEntry
from app.url_utils import is_external_http_url


def _repo_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data"


def _candidate_paths(data_dir: Path, filenames: list[str]) -> list[Path]:
    repo_data_dir = _repo_data_dir()
    ordered_paths = [data_dir / filename for filename in filenames]
    ordered_paths.extend(repo_data_dir / filename for filename in filenames)
    return list(dict.fromkeys(ordered_paths))


def _candidate_sample_paths(data_dir: Path) -> list[Path]:
    return _candidate_paths(data_dir, ["deploy_articles.json", "sample_articles.json"])


def _candidate_source_health_paths(data_dir: Path) -> list[Path]:
    return _candidate_paths(data_dir, ["deploy_source_health.json"])


def load_sample_articles(data_dir: Path) -> list[ArticleRecord]:
    for sample_path in _candidate_sample_paths(data_dir):
        if not sample_path.exists():
            continue
        records = json.loads(sample_path.read_text(encoding="utf-8"))
        articles = [
            ArticleRecord.model_validate(record)
            for record in records
            if is_external_http_url(str(record.get("url") or ""))
        ]
        if articles:
            return articles
    return []


def load_source_health_snapshot(data_dir: Path) -> list[SourceHealthEntry]:
    for snapshot_path in _candidate_source_health_paths(data_dir):
        if not snapshot_path.exists():
            continue
        records = json.loads(snapshot_path.read_text(encoding="utf-8"))
        return [SourceHealthEntry.model_validate(record) for record in records]
    return []
