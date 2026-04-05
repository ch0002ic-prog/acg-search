from __future__ import annotations

from datetime import datetime, timezone
import json
import re

from bs4 import BeautifulSoup
import httpx

from app.schemas import EventMetadata
from app.services.event_metadata import format_event_date_label, normalize_guest_names
from app.sources.base import BaseSource, SourceArticle


EVENTBRITE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-SG,en;q=0.9",
    "Cache-Control": "no-cache",
}


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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


def _extract_offer(item: dict) -> dict:
    offers = item.get("offers")
    if isinstance(offers, list):
        for candidate in offers:
            if isinstance(candidate, dict):
                return candidate
        return {}
    return offers if isinstance(offers, dict) else {}


def _ticket_status_from_offer(offer: dict) -> str | None:
    if not offer:
        return None

    availability = _clean_text(str(offer.get("availability") or ""))
    lowered = availability.lower()
    if "soldout" in lowered or "sold out" in lowered:
        return "Sold out"
    if offer.get("url") or availability:
        return "Tickets on sale"
    return None


def _extract_guest_names(item: dict) -> list[str]:
    raw_performers = item.get("performer") or item.get("performers") or []
    candidates = raw_performers if isinstance(raw_performers, list) else [raw_performers]
    names: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, dict):
            names.append(_clean_text(candidate.get("name")))
        elif isinstance(candidate, str):
            names.append(_clean_text(candidate))
    return normalize_guest_names(names)


class EventbriteSource(BaseSource):
    def fetch(self, limit: int) -> list[SourceArticle]:
        response = httpx.get(
            self.feed_url,
            headers=EVENTBRITE_HEADERS,
            timeout=10,
            follow_redirects=True,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        articles: list[SourceArticle] = []
        seen_urls: set[str] = set()

        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw_payload = script.string or script.get_text(strip=True)
            if not raw_payload or "ItemList" not in raw_payload:
                continue
            try:
                parsed_payload = json.loads(raw_payload)
            except Exception:
                continue

            candidates = parsed_payload if isinstance(parsed_payload, list) else [parsed_payload]
            for candidate in candidates:
                if not isinstance(candidate, dict) or candidate.get("@type") != "ItemList":
                    continue

                for entry in candidate.get("itemListElement", []):
                    item = entry.get("item") if isinstance(entry, dict) else None
                    if not isinstance(item, dict):
                        continue

                    title = _clean_text(item.get("name"))
                    url = _clean_text(item.get("url"))
                    if not title or not url or url in seen_urls:
                        continue

                    description = _clean_text(item.get("description"))
                    location = item.get("location") if isinstance(item.get("location"), dict) else {}
                    venue = _clean_text(location.get("name")) if isinstance(location, dict) else ""
                    start_date = _parse_datetime(item.get("startDate"))
                    end_date_raw = _clean_text(item.get("endDate"))
                    end_date = _parse_datetime(end_date_raw) if end_date_raw else None
                    offer = _extract_offer(item)
                    guest_names = _extract_guest_names(item)

                    summary_parts = [description]
                    if venue:
                        summary_parts.append(f"Venue: {venue}.")
                    if end_date_raw and end_date_raw != item.get("startDate"):
                        summary_parts.append(f"Ends: {end_date_raw}.")
                    summary = " ".join(part for part in summary_parts if part)

                    article = SourceArticle(
                        title=title,
                        url=url,
                        published_at=start_date,
                        summary=summary,
                        content=summary,
                        category_hints=list(self.category_hints),
                        region_hints=list(self.region_hints),
                        image_url=_clean_text(item.get("image")) or None,
                        event_metadata=EventMetadata(
                            date_label=format_event_date_label(start_date, end_date),
                            venue=venue or None,
                            ticket_status=_ticket_status_from_offer(offer),
                            ticket_url=_clean_text(str(offer.get("url") or "")) or url,
                            guest_status="Named guests mentioned" if guest_names else None,
                            guest_names=guest_names,
                        ),
                    )
                    if not self.matches(article):
                        continue

                    seen_urls.add(url)
                    articles.append(article)
                    if len(articles) >= limit:
                        return articles

        return articles[:limit]