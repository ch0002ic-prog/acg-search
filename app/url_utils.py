from __future__ import annotations

from urllib.parse import urlparse


LOW_QUALITY_MEDIA_SEGMENTS = {
    "album",
    "albums",
    "gallery",
    "galleries",
    "image",
    "images",
    "mediaviewer",
    "photo",
    "photos",
    "slideshow",
}

LOW_QUALITY_VIDEO_SEGMENTS = {
    "video",
    "videos",
    "watch",
}


def is_external_http_url(value: str | None) -> bool:
    cleaned = (value or "").strip()
    if not cleaned:
        return False

    try:
        parsed = urlparse(cleaned)
    except ValueError:
        return False

    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def score_external_url_quality(value: str | None) -> float:
    if not is_external_http_url(value):
        return 0.0

    parsed = urlparse((value or "").strip())
    path = (parsed.path or "").strip().lower()
    path_segments = [segment for segment in path.split("/") if segment]

    score = 1.0
    if not path_segments:
        score = min(score, 0.76)

    if any(segment in LOW_QUALITY_MEDIA_SEGMENTS for segment in path_segments):
        score = min(score, 0.36)
    elif any(segment in LOW_QUALITY_VIDEO_SEGMENTS for segment in path_segments):
        score = min(score, 0.62)

    hostname = (parsed.hostname or "").lower()
    if hostname.endswith("imdb.com") and "mediaviewer" in path_segments:
        score = min(score, 0.24)

    return score