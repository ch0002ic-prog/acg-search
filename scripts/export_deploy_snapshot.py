from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import ArticleRepository
from app.schemas import ArticleRecord


def _build_summary(article: ArticleRecord) -> str:
    focus_terms = article.entity_tags[:2] or article.tags[:3] or article.categories[:2]
    focus_text = ", ".join(focus_terms)
    region_text = ", ".join(article.region_tags[:2])
    venue = article.event_metadata.venue if article.event_metadata and article.event_metadata.venue else None

    clauses = [f"ACG coverage from {article.source_name}"]
    if region_text:
        clauses.append(f"for {region_text}")
    if focus_text:
        clauses.append(f"focused on {focus_text}")
    if venue:
        clauses.append(f"with venue context for {venue}")
    return " ".join(clauses) + "."


def _to_snapshot_record(article: ArticleRecord) -> dict[str, object]:
    record = article.model_dump(mode="json")
    record["summary"] = _build_summary(article)
    record["content"] = ""
    return record


def export_snapshot(db_path: Path, output_path: Path, limit: int) -> int:
    repository = ArticleRepository(db_path)
    articles = repository.latest_articles(limit=max(1, limit))
    if not articles:
        raise SystemExit(f"No articles found in {db_path}")

    snapshot = [_to_snapshot_record(article) for article in articles]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return len(snapshot)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a bundled deployment snapshot from the local article store.")
    parser.add_argument("--db-path", type=Path, default=ROOT_DIR / "data" / "articles.db")
    parser.add_argument("--output", type=Path, default=ROOT_DIR / "data" / "deploy_articles.json")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    count = export_snapshot(db_path=args.db_path, output_path=args.output, limit=args.limit)
    print(json.dumps({"exported": count, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()