from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import re
from xml.etree import ElementTree as ET

import httpx

from app.sources.base import BaseSource, SourceArticle


ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}


def _strip_html(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


class RssSource(BaseSource):
    def fetch(self, limit: int) -> list[SourceArticle]:
        response = httpx.get(
            self.feed_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/135.0.0.0 Safari/537.36"
                ),
                "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
                "Accept-Language": "en-SG,en;q=0.9",
                "Cache-Control": "no-cache",
            },
            timeout=10,
            follow_redirects=True,
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        articles: list[SourceArticle] = []

        channel_items = root.findall("./channel/item")
        if channel_items:
            for item in channel_items[:limit]:
                title = _strip_html(item.findtext("title"))
                url = _strip_html(item.findtext("link"))
                summary = _strip_html(item.findtext("description"))
                published_at = _parse_datetime(item.findtext("pubDate"))
                image_url = None
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    image_url = enclosure.attrib.get("url")
                if title and url:
                    article = SourceArticle(
                        title=title,
                        url=url,
                        published_at=published_at,
                        summary=summary,
                        category_hints=list(self.category_hints),
                        region_hints=list(self.region_hints),
                        image_url=image_url,
                    )
                    if self.matches(article):
                        articles.append(article)
            return articles

        atom_entries = root.findall("atom:entry", ATOM_NAMESPACE)
        for entry in atom_entries[:limit]:
            title = _strip_html(entry.findtext("atom:title", default="", namespaces=ATOM_NAMESPACE))
            link_element = entry.find("atom:link", ATOM_NAMESPACE)
            url = link_element.attrib.get("href", "") if link_element is not None else ""
            summary = _strip_html(
                entry.findtext("atom:summary", default="", namespaces=ATOM_NAMESPACE)
                or entry.findtext("atom:content", default="", namespaces=ATOM_NAMESPACE)
            )
            published_at = _parse_datetime(
                entry.findtext("atom:updated", default="", namespaces=ATOM_NAMESPACE)
                or entry.findtext("atom:published", default="", namespaces=ATOM_NAMESPACE)
            )
            if title and url:
                article = SourceArticle(
                    title=title,
                    url=url,
                    published_at=published_at,
                    summary=summary,
                    category_hints=list(self.category_hints),
                    region_hints=list(self.region_hints),
                )
                if self.matches(article):
                    articles.append(article)

        return articles
