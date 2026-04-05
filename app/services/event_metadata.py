from __future__ import annotations

from datetime import datetime
import re

from app.schemas import EventMetadata


MONTH_PATTERN = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_TEXT_PATTERN = re.compile(
    rf"\b(?:{MONTH_PATTERN}\s+\d{{1,2}}(?:\s*[-to]+\s*\d{{1,2}})?(?:,\s*\d{{4}})?|\d{{1,2}}\s*(?:-|to)\s*\d{{1,2}}\s+{MONTH_PATTERN}(?:\s+\d{{4}})?|\d{{1,2}}\s+{MONTH_PATTERN}(?:\s+\d{{4}})?)\b",
    re.IGNORECASE,
)
ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})(?:[T ][0-9:+\-.Z]+)?\b")
VENUE_LABEL_PATTERN = re.compile(r"\bVenue:\s*([^\.]+)", re.IGNORECASE)

KNOWN_VENUES = (
    "Suntec Singapore Convention & Exhibition Centre",
    "Suntec Singapore",
    "Singapore Expo",
    "Sands Expo and Convention Centre",
    "Marina Bay Sands",
    "Marina Square",
    "Bugis+",
    "Plaza Singapura",
    "VivoCity",
    "Capitol Singapore",
    "Esplanade",
    "Ngee Ann City",
)

VENUE_ALIASES: dict[str, str] = {
    "suntec convention centre": "Suntec Singapore Convention & Exhibition Centre",
    "suntec convention & exhibition centre": "Suntec Singapore Convention & Exhibition Centre",
    "suntec singapore convention centre": "Suntec Singapore Convention & Exhibition Centre",
    "sands expo": "Sands Expo and Convention Centre",
    "marina bay sands expo": "Sands Expo and Convention Centre",
}

SOURCE_SPECIFIC_METADATA_SOURCES = {"Bandwagon Asia", "Anime Festival Asia"}

EVENT_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("anime festival asia", "festival"),
    ("afa singapore", "festival"),
    ("workshop", "workshop"),
    ("popup", "popup"),
    ("collab cafe", "collab cafe"),
    ("comic con", "convention"),
    ("qualifier", "qualifier"),
    ("tournament", "tournament"),
    ("concert", "concert"),
    ("screening", "screening"),
    ("meetup", "meetup"),
    ("comic con", "convention"),
    ("convention", "convention"),
    ("festival", "festival"),
    ("cafe", "cafe"),
    ("expo", "expo"),
)

GUEST_NAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:guests? include|guest lineup(?: includes| features)?|featuring|starring)\s+([^\.]+)", re.IGNORECASE),
    re.compile(r"\blineup:\s*([^\.]+)", re.IGNORECASE),
    re.compile(r"\b(?:special guests?|guests?)\s*:\s*([^\.]+)", re.IGNORECASE),
)

GUEST_NAME_STOPWORDS = {
    "special",
    "guests",
    "guest",
    "lineup",
    "creator",
    "alley",
    "plans",
    "tickets",
    "ticket",
    "sale",
    "fans",
    "artists",
    "illustrators",
    "makers",
    "venue",
    "convention",
    "exhibition",
    "centre",
    "center",
    "singapore",
}

TICKET_STATUS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(sold out|fully booked)\b", re.IGNORECASE), "Sold out"),
    (re.compile(r"\bwaitlist\b", re.IGNORECASE), "Waitlist only"),
    (re.compile(r"\b(registration open|register now|rsvp now|book now|book your spot)\b", re.IGNORECASE), "Registration open"),
    (re.compile(r"\b(tickets? (?:on sale|available|go live|going live|window opens)|ticketing update)\b", re.IGNORECASE), "Tickets on sale"),
)

SOURCE_TICKET_STATUS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(ticket guide|ticketing guide)\b", re.IGNORECASE), "Ticket guide available"),
    (
        re.compile(
            r"\b(?:early bird|general sale|public sale|presale|pre-sale|priority sale|ticket sales?)\b[^\.]{0,64}\b(?:open|opens|starting|starts|begin|begins|from)\b",
            re.IGNORECASE,
        ),
        "Ticket window announced",
    ),
)

GUEST_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(guest lineup|guest list|special guests?|guest details?)\b", re.IGNORECASE), "Guest lineup mentioned"),
    (re.compile(r"\b(creator alley|artist alley|performer lineup|stage lineup)\b", re.IGNORECASE), "Lineup details mentioned"),
)

MERCH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(collab cafe|popup store|popup)\b", re.IGNORECASE), "Popup or collab activation mentioned"),
    (re.compile(r"\b(merch|goods|booth|exclusive item|exclusive merch|pre-?order)\b", re.IGNORECASE), "Merch or booth updates mentioned"),
)


def _clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _format_date(value: datetime) -> str:
    return value.strftime("%d %b %Y").lstrip("0").replace(" 0", " ")


def format_event_date_label(start_date: datetime | None, end_date: datetime | None = None) -> str | None:
    if not start_date:
        return None

    start_label = _format_date(start_date)
    if not end_date:
        return start_label

    end_label = _format_date(end_date)
    return start_label if start_label == end_label else f"{start_label} to {end_label}"


def _parse_iso_date(value: str | None) -> datetime | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    candidate = cleaned.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _extract_text_date(text: str) -> str | None:
    match = DATE_TEXT_PATTERN.search(text)
    if not match:
        return None
    return _clean_text(match.group(0)).replace("  ", " ")


def _extract_event_dates(text: str, source_type: str, published_at: datetime | None) -> str | None:
    explicit_date = _extract_text_date(text)
    if explicit_date:
        return explicit_date

    iso_matches = ISO_DATE_PATTERN.findall(text)
    if source_type != "event_listing" or not published_at:
        if not iso_matches:
            return None
        parsed = _parse_iso_date(iso_matches[0])
        return _format_date(parsed) if parsed else None

    start_label = _format_date(published_at)
    if not iso_matches:
        return start_label

    end_date = _parse_iso_date(iso_matches[-1])
    if not end_date:
        return start_label
    return format_event_date_label(published_at, end_date)


def _extract_venue(text: str) -> str | None:
    lowered = text.lower()
    for alias, canonical in VENUE_ALIASES.items():
        if alias in lowered:
            return canonical
    for venue in KNOWN_VENUES:
        if venue.lower() in lowered:
            return venue

    labeled_matches = VENUE_LABEL_PATTERN.findall(text)
    if labeled_matches:
        return _clean_text(labeled_matches[-1])
    return None


def _extract_status(text: str, rules: tuple[tuple[re.Pattern[str], str], ...]) -> str | None:
    for pattern, label in rules:
        if pattern.search(text):
            return label
    return None


def _extract_ticket_status(text: str, source_name: str | None = None) -> str | None:
    if source_name in SOURCE_SPECIFIC_METADATA_SOURCES:
        specific_status = _extract_status(text, SOURCE_TICKET_STATUS_RULES)
        if specific_status:
            return specific_status
    return _extract_status(text, TICKET_STATUS_RULES)


def _looks_like_guest_name(value: str) -> bool:
    cleaned = _clean_text(value)
    if not cleaned:
        return False

    words = cleaned.split()
    if len(words) > 4:
        return False
    normalized_words = [re.sub(r"[^a-z0-9]+", "", word.lower()) for word in words]
    if any(word in GUEST_NAME_STOPWORDS for word in normalized_words):
        return False
    if not any(character.isupper() for character in cleaned):
        return False
    return True


def normalize_guest_names(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        cleaned = _clean_text(value)
        if not cleaned or not _looks_like_guest_name(cleaned):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _extract_guest_names(text: str) -> list[str]:
    matches: list[tuple[int, int, str]] = []
    for pattern in GUEST_NAME_PATTERNS:
        for match in pattern.finditer(text):
            raw_fragment = match.group(1)
            fragment = re.split(r"\b(?:with|at|for|during|plus|while)\b", raw_fragment, maxsplit=1, flags=re.IGNORECASE)[0]
            fragment = re.split(r"\b(?:special guests?|guests?)\s*:\s*", fragment, maxsplit=1, flags=re.IGNORECASE)[-1]
            for index, part in enumerate(re.split(r",|\band\b|&", fragment, flags=re.IGNORECASE)):
                candidate = _clean_text(re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9'!\-\. ]+$", "", part))
                if _looks_like_guest_name(candidate):
                    matches.append((match.start(1), index, candidate))
    ordered_matches = [candidate for _, _, candidate in sorted(matches, key=lambda item: (item[0], item[1]))]
    return normalize_guest_names(ordered_matches)


def coerce_event_metadata(value: EventMetadata | dict[str, object] | None) -> EventMetadata | None:
    if value is None:
        return None
    if isinstance(value, EventMetadata):
        return value
    if isinstance(value, dict):
        return EventMetadata(**value)
    return None


def merge_event_metadata(primary: EventMetadata | dict[str, object] | None, fallback: EventMetadata | dict[str, object] | None) -> EventMetadata | None:
    primary_metadata = coerce_event_metadata(primary)
    fallback_metadata = coerce_event_metadata(fallback)
    if primary_metadata is None and fallback_metadata is None:
        return None

    guest_names = normalize_guest_names(
        [
            *((primary_metadata.guest_names if primary_metadata else []) or []),
            *((fallback_metadata.guest_names if fallback_metadata else []) or []),
        ]
    )
    guest_status = (primary_metadata.guest_status if primary_metadata else None) or (fallback_metadata.guest_status if fallback_metadata else None)
    if guest_names and not guest_status:
        guest_status = "Named guests mentioned"
    if guest_status == "Named guests mentioned" and not guest_names:
        fallback_status = fallback_metadata.guest_status if fallback_metadata else None
        guest_status = fallback_status if fallback_status and fallback_status != "Named guests mentioned" else None

    merged = EventMetadata(
        event_type=(primary_metadata.event_type if primary_metadata else None) or (fallback_metadata.event_type if fallback_metadata else None),
        date_label=(primary_metadata.date_label if primary_metadata else None) or (fallback_metadata.date_label if fallback_metadata else None),
        venue=(primary_metadata.venue if primary_metadata else None) or (fallback_metadata.venue if fallback_metadata else None),
        ticket_status=(primary_metadata.ticket_status if primary_metadata else None) or (fallback_metadata.ticket_status if fallback_metadata else None),
        ticket_url=(primary_metadata.ticket_url if primary_metadata else None) or (fallback_metadata.ticket_url if fallback_metadata else None),
        guest_status=guest_status,
        guest_names=guest_names,
        merch_status=(primary_metadata.merch_status if primary_metadata else None) or (fallback_metadata.merch_status if fallback_metadata else None),
    )

    if not any(
        [
            merged.event_type,
            merged.date_label,
            merged.venue,
            merged.ticket_status,
            merged.ticket_url,
            merged.guest_status,
            merged.guest_names,
            merged.merch_status,
        ]
    ):
        return None
    return merged


def _infer_event_type(text: str, source_type: str) -> str | None:
    if source_type == "event_listing":
        lowered = text.lower()
        for keyword, label in EVENT_TYPE_RULES:
            if keyword in lowered:
                return label
        return "event"

    lowered = text.lower()
    for keyword, label in EVENT_TYPE_RULES:
        if keyword in lowered:
            return label
    return None


def infer_event_metadata(
    title: str,
    summary: str = "",
    content: str = "",
    source_type: str = "rss",
    published_at: datetime | None = None,
    url: str | None = None,
    source_name: str | None = None,
) -> EventMetadata | None:
    text = _clean_text(" ".join(part for part in [title, summary, content] if _clean_text(part)))
    if not text:
        return None

    guest_names = _extract_guest_names(text)
    guest_status = _extract_status(text, GUEST_RULES)
    if guest_names:
        guest_status = "Named guests mentioned"

    metadata = EventMetadata(
        event_type=_infer_event_type(text, source_type),
        date_label=_extract_event_dates(text, source_type, published_at),
        venue=_extract_venue(text),
        ticket_status=_extract_ticket_status(text, source_name),
        ticket_url=_clean_text(url) if source_type == "event_listing" and _clean_text(url) else None,
        guest_status=guest_status,
        guest_names=guest_names,
        merch_status=_extract_status(text, MERCH_RULES),
    )

    if not any(
        [
            metadata.event_type,
            metadata.date_label,
            metadata.venue,
            metadata.ticket_status,
            metadata.ticket_url,
            metadata.guest_status,
            metadata.guest_names,
            metadata.merch_status,
        ]
    ):
        return None
    return metadata