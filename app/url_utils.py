from __future__ import annotations

from urllib.parse import urlparse


def is_external_http_url(value: str | None) -> bool:
    cleaned = (value or "").strip()
    if not cleaned:
        return False

    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return False

    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)