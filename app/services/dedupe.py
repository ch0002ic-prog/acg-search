from __future__ import annotations

from typing import TYPE_CHECKING
import re
import unicodedata

from app.services.ranking import normalize_title, strip_text

if TYPE_CHECKING:
    from app.schemas import ArticleRecord


GOOGLE_NEWS_SUFFIX_PATTERN = re.compile(r"\s+-\s+[^-]{2,80}$")
EVENT_VARIANT_SUFFIX_PATTERN = re.compile(
    r"\s*\((?:(?!\)).)*(?:"
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r?sday)?|fri(?:day)?|"
    r"sat(?:urday)?(?:\s*[-/]\s*sun(?:day)?)?|sun(?:day)?|weekend|weekdays?|"
    r"周[一二三四五六日天]|[0-3]?\d[:.]?[0-5]?\d\s*(?:am|pm)?|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*|"
    r"\d{1,2}\s*[/-]\s*\d{1,2}"
    r")(?:(?!\)).)*\)\s*$",
    re.IGNORECASE,
)


def normalize_dedupe_title(title: str, source_type: str = "rss", source_name: str = "") -> str:
    cleaned = strip_text(unicodedata.normalize("NFKC", title or ""))
    if source_name.lower().startswith("google news"):
        cleaned = GOOGLE_NEWS_SUFFIX_PATTERN.sub("", cleaned).strip()

    if source_type == "event_listing":
        previous = None
        while cleaned and cleaned != previous:
            previous = cleaned
            cleaned = EVENT_VARIANT_SUFFIX_PATTERN.sub("", cleaned).rstrip(" -:")

    return normalize_title(cleaned)


def article_dedupe_key(article: "ArticleRecord") -> str:
    dedupe_title = normalize_dedupe_title(
        title=article.title,
        source_type=article.source_type,
        source_name=article.source_name,
    )
    return dedupe_title or article.id


def article_preference_signature(article: "ArticleRecord") -> tuple[float, ...]:
    normalized_title = normalize_title(strip_text(unicodedata.normalize("NFKC", article.title)))
    canonical_title = article_dedupe_key(article)
    is_title_variant = 1.0 if normalized_title != canonical_title else 0.0
    prefers_non_placeholder_url = 0.0 if "example.com" in strip_text(article.url).lower() else 1.0
    prefers_direct_source = 0.0 if article.source_name.lower().startswith("google news") else 1.0

    return (
        prefers_non_placeholder_url,
        prefers_direct_source,
        1.0 - is_title_variant,
        float(article.source_quality),
        float(min(len(strip_text(article.summary)), 240)),
        float(min(len(strip_text(article.content)), 480)),
        1.0 if article.image_url else 0.0,
        float(article.published_at.timestamp()),
        -float(len(strip_text(article.title))),
    )