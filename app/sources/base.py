from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.schemas import EventMetadata


@dataclass(slots=True)
class SourceArticle:
    title: str
    url: str
    published_at: datetime
    summary: str = ""
    content: str = ""
    category_hints: list[str] = field(default_factory=list)
    region_hints: list[str] = field(default_factory=list)
    image_url: str | None = None
    event_metadata: EventMetadata | None = None


@dataclass(slots=True)
class BaseSource(ABC):
    name: str
    feed_url: str
    quality: float = 0.7
    source_type: str = "rss"
    category_hints: list[str] = field(default_factory=list)
    region_hints: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    cleanup_mismatches: bool = False
    request_timeout_seconds: float | None = None
    max_attempts: int = 1

    def matches(self, article: SourceArticle) -> bool:
        haystack = " ".join([article.title, article.summary, article.content]).lower()
        if self.exclude_keywords and any(keyword.lower() in haystack for keyword in self.exclude_keywords):
            return False
        if not self.include_keywords:
            return True
        return any(keyword.lower() in haystack for keyword in self.include_keywords)

    @abstractmethod
    def fetch(self, limit: int) -> list[SourceArticle]:
        raise NotImplementedError
