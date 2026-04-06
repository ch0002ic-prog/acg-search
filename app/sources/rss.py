from __future__ import annotations

import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import html
import re
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

import httpx

from app.sources.base import BaseSource, SourceArticle
from app.url_utils import is_external_http_url


ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
GOOGLE_NEWS_HOST = "news.google.com"
GOOGLE_NEWS_GARTURL_PREFIX = bytes([0x08, 0x13, 0x22]).decode("latin1")
GOOGLE_NEWS_GARTURL_SUFFIX = bytes([0xD2, 0x01, 0x00]).decode("latin1")
GOOGLE_NEWS_URL_CACHE: dict[str, str] = {}
GOOGLE_NEWS_URL_CACHE_MAXSIZE = 512
RSS_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-SG,en;q=0.9",
    "Cache-Control": "no-cache",
}


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


def _remember_google_news_url(wrapper_url: str, resolved_url: str) -> str:
    if wrapper_url in GOOGLE_NEWS_URL_CACHE:
        GOOGLE_NEWS_URL_CACHE.pop(wrapper_url, None)
    GOOGLE_NEWS_URL_CACHE[wrapper_url] = resolved_url
    while len(GOOGLE_NEWS_URL_CACHE) > GOOGLE_NEWS_URL_CACHE_MAXSIZE:
        GOOGLE_NEWS_URL_CACHE.pop(next(iter(GOOGLE_NEWS_URL_CACHE)))
    return resolved_url


def _google_news_base64_id(source_url: str) -> str | None:
    try:
        parsed = urlparse(source_url)
    except Exception:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.hostname != GOOGLE_NEWS_HOST or len(path_parts) < 2:
        return None
    if path_parts[-2] not in {"articles", "read"}:
        return None
    return path_parts[-1] or None


def _decode_google_news_inline_target(base64_id: str) -> str | None:
    try:
        raw = base64_id + "=="
        decoded_bytes = base64.urlsafe_b64decode(raw)
        decoded_text = decoded_bytes.decode("latin1")
    except Exception:
        return None

    if decoded_text.startswith(GOOGLE_NEWS_GARTURL_PREFIX):
        decoded_text = decoded_text[len(GOOGLE_NEWS_GARTURL_PREFIX) :]
    if decoded_text.endswith(GOOGLE_NEWS_GARTURL_SUFFIX):
        decoded_text = decoded_text[: -len(GOOGLE_NEWS_GARTURL_SUFFIX)]
    if not decoded_text:
        return None

    bytes_array = bytearray(decoded_text, "latin1")
    length = bytes_array[0]
    if length >= 0x80:
        candidate = decoded_text[2 : length + 1]
    else:
        candidate = decoded_text[1 : length + 1]
    return candidate or None


def _extract_google_news_decode_params(base64_id: str, client: httpx.Client) -> tuple[str, str] | None:
    for candidate_url in (
        f"https://{GOOGLE_NEWS_HOST}/articles/{base64_id}",
        f"https://{GOOGLE_NEWS_HOST}/rss/articles/{base64_id}",
    ):
        try:
            response = client.get(candidate_url)
            response.raise_for_status()
        except Exception:
            continue

        signature_match = re.search(r'data-n-a-sg="([^"]+)"', response.text)
        timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', response.text)
        if signature_match and timestamp_match:
            return html.unescape(signature_match.group(1)), html.unescape(timestamp_match.group(1))
    return None


def _request_google_news_canonical_url(base64_id: str, signature: str, timestamp: str, client: httpx.Client) -> str | None:
    payload = [
        "Fbv4je",
        (
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
            f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{base64_id}",{timestamp},"{signature}"]'
        ),
    ]

    response = client.post(
        f"https://{GOOGLE_NEWS_HOST}/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        data=f"f.req={quote(json.dumps([[payload]]))}",
    )
    response.raise_for_status()

    payload_text = response.text.split("\n\n", 1)
    if len(payload_text) != 2:
        return None

    parsed = json.loads(payload_text[1])
    result_entry = next(
        (
            entry
            for entry in parsed
            if isinstance(entry, list) and len(entry) >= 3 and entry[0] == "wrb.fr" and entry[2]
        ),
        None,
    )
    if result_entry is None:
        return None

    decoded_payload = json.loads(result_entry[2])
    if len(decoded_payload) < 2:
        return None
    decoded_url = str(decoded_payload[1] or "").strip()
    return decoded_url or None


def _resolve_google_news_url(source_url: str, client: httpx.Client) -> str:
    cached = GOOGLE_NEWS_URL_CACHE.get(source_url)
    if cached:
        return cached

    base64_id = _google_news_base64_id(source_url)
    if not base64_id:
        return source_url

    inline_candidate = _decode_google_news_inline_target(base64_id)
    if inline_candidate and is_external_http_url(inline_candidate) and urlparse(inline_candidate).hostname != GOOGLE_NEWS_HOST:
        return _remember_google_news_url(source_url, inline_candidate)

    try:
        params = _extract_google_news_decode_params(base64_id, client)
        if not params:
            return source_url
        decoded_url = _request_google_news_canonical_url(base64_id, params[0], params[1], client)
    except Exception:
        return source_url

    if decoded_url and is_external_http_url(decoded_url) and urlparse(decoded_url).hostname != GOOGLE_NEWS_HOST:
        return _remember_google_news_url(source_url, decoded_url)
    return source_url


def resolve_google_news_url(source_url: str, client: httpx.Client | None = None) -> str:
    if client is not None:
        return _resolve_google_news_url(source_url, client)

    with httpx.Client(headers=RSS_REQUEST_HEADERS, timeout=10, follow_redirects=True) as owned_client:
        return _resolve_google_news_url(source_url, owned_client)


class RssSource(BaseSource):
    def fetch(self, limit: int) -> list[SourceArticle]:
        with httpx.Client(
            headers=RSS_REQUEST_HEADERS,
            timeout=10,
            follow_redirects=True,
        ) as client:
            response = client.get(self.feed_url)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            articles: list[SourceArticle] = []

            channel_items = root.findall("./channel/item")
            if channel_items:
                for item in channel_items[:limit]:
                    title = _strip_html(item.findtext("title"))
                    url = _resolve_google_news_url(_strip_html(item.findtext("link")), client)
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
                url = _resolve_google_news_url(url, client)
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
