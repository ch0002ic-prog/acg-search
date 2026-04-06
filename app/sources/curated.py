from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from app.sources.base import BaseSource, SourceArticle
from app.url_utils import is_external_http_url


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


@dataclass(slots=True)
class CuratedSource(BaseSource):
    file_path: Path | None = None

    def fetch(self, limit: int) -> list[SourceArticle]:
        if self.file_path is None or not self.file_path.exists():
            return []

        payload = json.loads(self.file_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return []

        articles: list[SourceArticle] = []
        for item in payload[:limit]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not title or not url or not is_external_http_url(url):
                continue

            article = SourceArticle(
                title=title,
                url=url,
                published_at=_parse_datetime(str(item.get("published_at") or "")),
                summary=str(item.get("summary") or "").strip(),
                content=str(item.get("content") or "").strip(),
                category_hints=[str(value).strip() for value in item.get("category_hints", []) if str(value).strip()],
                region_hints=[str(value).strip() for value in item.get("region_hints", []) if str(value).strip()],
                image_url=str(item.get("image_url") or "").strip() or None,
            )
            if self.matches(article):
                articles.append(article)

        return articles[:limit]