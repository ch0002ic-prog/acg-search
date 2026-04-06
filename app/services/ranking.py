from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
import re

from app.schemas import ArticleRecord, UserProfile
from app.services.entities import entity_overlap_score, infer_entity_tags


CATEGORY_KEYWORDS: dict[str, set[str]] = {
    "events": {"festival", "event", "con", "convention", "artist alley", "booth", "ticket"},
    "anime": {"anime", "animanga", "otaku", "seasonal", "ova", "idol"},
    "manga": {"manga", "manhwa", "webtoon", "light novel"},
    "games": {"game", "gaming", "jrpg", "visual novel", "demo", "release"},
    "gacha": {"gacha", "banner", "pull", "hoyoverse", "genshin", "star rail", "zenless"},
    "esports": {"esports", "qualifier", "tournament", "valorant", "mlbb", "playoffs"},
    "merch": {"merch", "figure", "collectible", "popup", "collab", "cafe", "store", "sale"},
    "comics": {"comics", "comic", "graphic novel", "doujin"},
}

CATEGORY_PRIORITY: dict[str, float] = {
    "events": 1.0,
    "esports": 0.92,
    "merch": 0.88,
    "games": 0.84,
    "gacha": 0.83,
    "anime": 0.8,
    "manga": 0.76,
    "comics": 0.72,
}

TAG_KEYWORDS: dict[str, set[str]] = {
    "afa": {"anime festival asia", "afa"},
    "singapore": {"singapore", "sg", "suntec", "marina bay", "orchard", "bugis"},
    "sgcc": {"singapore comic con", "sgcc"},
    "hoyofest": {"hoyofest", "hoyo fest"},
    "idol": {"idol", "anisong", "ani-idol", "ani idol", "poppa", "moe moe q", "mmq"},
    "jrpg": {"jrpg", "turn-based", "atlus", "falcom", "square enix", "persona"},
    "hoyoverse": {"hoyoverse", "genshin", "honkai", "zenless"},
    "mlbb": {"mobile legends", "mlbb"},
    "donghua": {"donghua", "bilibili", "link click"},
}

SG_SIGNALS: dict[str, float] = {
    "singapore": 0.35,
    "sg": 0.15,
    "suntec": 0.2,
    "marina bay": 0.15,
    "anime festival asia": 0.28,
    "afa": 0.2,
    "hoyofest": 0.22,
    "singapore comic con": 0.26,
    "doujin market": 0.22,
    "poppa": 0.14,
    "moe moe q": 0.14,
    "ani-idol": 0.14,
    "ani idol": 0.14,
    "artist alley": 0.12,
    "mlbb": 0.12,
    "mobile legends": 0.12,
    "valorant": 0.08,
    "sea": 0.08,
    "southeast asia": 0.12,
    "sgd": 0.25,
    "freebie": 0.1,
    "discount": 0.08,
    "promo": 0.08,
}

QUERY_EXPANSIONS: dict[str, list[str]] = {
    "cyberpunk": ["Cyberpunk 2077", "Edgerunners", "Phantom Liberty"],
    "mlbb": ["Mobile Legends", "M7", "Singapore qualifiers"],
    "jrpg": ["turn-based RPG", "Atlus", "Falcom", "Square Enix"],
    "idol": ["Ani-Idol", "anisong live", "idol showcase"],
    "ani idol": ["Ani-Idol", "idol showcase", "anisong live", "cosplay idol"],
    "ani-idol": ["Ani-Idol", "idol showcase", "anisong live", "cosplay idol"],
    "poppa": ["POPPA", "Moe Moe Q", "MMQ", "idol live", "merch signing"],
    "mmq": ["Moe Moe Q", "POPPA", "idol live", "idol"],
    "moe moe q": ["Moe Moe Q", "POPPA", "MMQ", "idol live", "merch signing"],
    "hoyoverse": ["Genshin Impact", "Honkai Star Rail", "Zenless Zone Zero", "HoyoFest Singapore"],
    "hoyofest": ["HoyoFest Singapore", "HoYoVerse", "Genshin Impact", "Honkai Star Rail", "Zenless Zone Zero"],
    "afa": ["Anime Festival Asia", "AFA Singapore", "artist alley", "ticketing"],
    "sgcc": ["Singapore Comic Con", "SGCC", "guest", "showfloor"],
    "convention": ["festival", "comic con", "market", "expo"],
    "merch": ["market", "collectible", "figure", "pop-up", "store"],
    "board games": ["boardgames", "tabletop", "mahjong"],
    "boardgame": ["boardgames", "tabletop", "mahjong"],
    "workshop": ["drawing workshop", "inking workshop", "art workshop"],
}

STOPWORDS = {
    "and",
    "or",
    "the",
    "to",
    "for",
    "with",
    "of",
    "a",
    "an",
    "in",
    "on",
    "new",
}

GENERIC_QUERY_TOKENS = {"singapore", "sg", "sea", "news", "latest", "today"}
MEANINGFUL_SHORT_QUERY_TOKENS = {"afa", "sgcc", "mlbb", "tcg", "ff14", "ffxiv", "sf6", "vct"}


def strip_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def infer_categories(*parts: str) -> list[str]:
    text = " ".join(parts).lower()
    categories: list[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)
    return categories or ["games"]


def infer_tags(*parts: str) -> list[str]:
    text = " ".join(parts).lower()
    tags: list[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            tags.append(tag)
    return tags


def infer_region_tags(*parts: str) -> list[str]:
    text = " ".join(parts).lower()
    region_tags: list[str] = []
    if any(signal in text for signal in {"singapore", "sg", "suntec", "marina bay"}):
        region_tags.append("Singapore")
    if any(signal in text for signal in {"sea", "southeast asia", "asean"}):
        region_tags.append("SEA")
    return region_tags


def infer_query_preferences(query: str) -> tuple[list[str], list[str], list[str]]:
    lowered = query.lower()
    categories = infer_categories(query)
    if categories == ["games"] and not any(
        keyword in lowered
        for keyword in {"game", "gaming", "jrpg", "gacha", "esports", "valorant", "mlbb", "persona", "ff"}
    ):
        categories = []
    return categories, infer_tags(query), infer_region_tags(query)


def score_singapore_relevance(*parts: str) -> float:
    text = " ".join(parts).lower()
    score = 0.0
    for keyword, weight in SG_SIGNALS.items():
        if keyword in text:
            score += weight
    return min(score, 1.0)


def score_freshness(published_at: datetime, now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    age_hours = max((now - published_at).total_seconds() / 3600, 0)
    return math.exp(-age_hours / 72)


def score_category_priority(categories: list[str]) -> float:
    if not categories:
        return 0.5
    return max(CATEGORY_PRIORITY.get(category, 0.55) for category in categories)


def compute_home_score(
    freshness_score: float,
    sg_relevance: float,
    categories: list[str],
    source_quality: float,
) -> float:
    return round(
        (0.45 * freshness_score)
        + (0.25 * sg_relevance)
        + (0.15 * score_category_priority(categories))
        + (0.15 * source_quality),
        4,
    )


def build_digest_lines(items: list[ArticleRecord], query: str | None = None) -> list[str]:
    if not items:
        if query:
            return [
                f"No strong matches were found for '{query}' in the current article store.",
                "Try a broader Singapore or SEA phrasing, or refresh sources to ingest newer stories.",
            ]
        return ["No headlines are available yet. Trigger a refresh to ingest new sources."]

    prefix = "For this search" if query else "Across the latest feed"
    lines = [f"{prefix}, the strongest stories cluster around Singapore-relevant events, merch drops, and live-service games."]
    for article in items[:3]:
        category_label = article.categories[0].title() if article.categories else "News"
        lines.append(f"{category_label}: {article.title}")
    return lines


def build_fts_query(query: str) -> str:
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if token not in STOPWORDS]
    unique_tokens = list(dict.fromkeys(tokens))
    return " OR ".join(f"{token}*" for token in unique_tokens[:8])


def expand_query_heuristically(query: str) -> str:
    expanded_terms = [query.strip()]
    lowered = query.lower()
    for trigger, terms in QUERY_EXPANSIONS.items():
        if trigger in lowered:
            expanded_terms.extend(terms)
    return ", ".join(dict.fromkeys(term for term in expanded_terms if term))


def _meaningful_query_tokens(query: str) -> list[str]:
    tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if token not in STOPWORDS]
    return [token for token in tokens if len(token) > 3 or token in MEANINGFUL_SHORT_QUERY_TOKENS]


def query_anchor_tokens(query: str) -> list[str]:
    original_tokens = _meaningful_query_tokens(query)
    return [token for token in original_tokens if token not in GENERIC_QUERY_TOKENS]


def has_meaningful_query_match(query: str, expanded_query: str, article: ArticleRecord) -> bool:
    anchor_tokens = query_anchor_tokens(query)
    query_entities = infer_entity_tags(query, for_query=True)
    entity_score = entity_overlap_score(query=query, expanded_query=expanded_query, article=article)
    if entity_score > 0:
        return True
    if not anchor_tokens:
        return True

    text = article.search_text().lower()
    title = article.title.lower()
    phrase_candidates = [strip_text(part).lower() for part in expanded_query.split(",") if strip_text(part)]

    anchor_hits = sum(1 for token in anchor_tokens if token in text)
    title_hits = sum(1 for token in anchor_tokens if token in title)
    phrase_hits = sum(1 for phrase in phrase_candidates[:6] if len(phrase) > 2 and phrase in text)
    specific_phrase_hits = sum(
        1
        for phrase in phrase_candidates[:6]
        if len(phrase) > 2 and len(re.findall(r"[a-z0-9]+", phrase)) >= 2 and phrase in text
    )
    if query_entities and entity_score == 0:
        return specific_phrase_hits > 0
    if phrase_hits > 0:
        return True
    if len(anchor_tokens) == 1:
        return (anchor_hits + title_hits) > 0
    return max(anchor_hits, title_hits) >= 2


def query_signal_score(query: str, expanded_query: str, article: ArticleRecord) -> float:
    text = article.search_text().lower()
    title = article.title.lower()
    entity_score = entity_overlap_score(query=query, expanded_query=expanded_query, article=article)
    original_tokens = _meaningful_query_tokens(query)
    anchor_tokens = [token for token in original_tokens if token not in GENERIC_QUERY_TOKENS]
    phrase_candidates = [strip_text(part).lower() for part in expanded_query.split(",") if strip_text(part)]
    original_phrase = strip_text(query).lower()

    token_hits = sum(1 for token in original_tokens if token in text)
    title_hits = sum(1 for token in anchor_tokens if token in title)
    anchor_hits = sum(1 for token in anchor_tokens if token in text)
    phrase_hits = sum(1 for phrase in phrase_candidates[:6] if len(phrase) > 2 and phrase in text)
    original_phrase_in_text = bool(original_phrase and len(original_phrase) > 2 and original_phrase in text)
    original_phrase_in_title = bool(original_phrase and len(original_phrase) > 2 and original_phrase in title)

    token_score = token_hits / len(original_tokens) if original_tokens else 0.0
    title_score = title_hits / len(anchor_tokens) if anchor_tokens else 0.0
    anchor_score = anchor_hits / len(anchor_tokens) if anchor_tokens else token_score
    phrase_score = phrase_hits / max(min(len(phrase_candidates[:6]), 3), 1)

    score = (0.35 * token_score) + (0.3 * anchor_score) + (0.2 * phrase_score) + (0.15 * title_score)
    if original_phrase_in_text:
        score += 0.18
    if original_phrase_in_title:
        score += 0.22
    if anchor_tokens and anchor_hits == 0 and phrase_hits == 0:
        score *= 0.15
    elif len(anchor_tokens) >= 2 and phrase_hits == 0 and anchor_hits < len(anchor_tokens):
        score *= max(anchor_hits / len(anchor_tokens), 0.25)

    if entity_score > 0:
        score = min(score + (0.24 * entity_score), 1.0)

    return min(score, 1.0)


def exact_query_phrase_boost(query: str, article: ArticleRecord) -> float:
    cleaned_query = strip_text(query).lower()
    query_tokens = [token for token in re.findall(r"[a-z0-9]+", cleaned_query) if token not in STOPWORDS]
    if len(query_tokens) < 2 or len(cleaned_query) <= 2:
        return 0.0

    title = article.title.lower()
    text = article.search_text().lower()
    if cleaned_query in title:
        return 0.12
    if cleaned_query in text:
        return 0.07
    return 0.0


def _scale_affinity(value: float) -> float:
    return max(min(value / 1.2, 1.0), -1.0)


def _average_affinity(values: list[str], affinity_map: dict[str, float]) -> float:
    if not values:
        return 0.0
    hits = [_scale_affinity(affinity_map.get(value.lower(), 0.0)) for value in values]
    return sum(hits) / len(hits)


def _pinned_match_score(values: list[str], pinned_values: list[str]) -> float:
    if not values or not pinned_values:
        return 0.0
    normalized_values = {value.lower() for value in values}
    normalized_pinned = {value.lower() for value in pinned_values}
    return 1.0 if normalized_values & normalized_pinned else 0.0


def _query_memory_score(article: ArticleRecord, profile: UserProfile) -> float:
    text = article.combined_text().lower()
    strongest = 0.0

    for query, weight in profile.query_affinities.items():
        tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if token not in STOPWORDS]
        if not tokens:
            continue
        hit_ratio = sum(1 for token in tokens if token in text) / len(tokens)
        strongest = max(strongest, hit_ratio * max(_scale_affinity(weight), 0.0))

    if strongest > 0:
        return min(strongest, 1.0)

    for query in profile.recent_queries[:4]:
        cleaned = strip_text(query).lower()
        if cleaned and cleaned in text:
            return 0.45

    return 0.0


def score_profile_match(article: ArticleRecord, profile: UserProfile | None) -> float:
    if profile is None:
        return 0.0

    category_score = _average_affinity(article.categories, profile.category_affinities)
    tag_score = _average_affinity(article.tags, profile.tag_affinities)
    entity_score = _average_affinity(article.entity_tags, profile.entity_affinities)
    region_score = _average_affinity(article.region_tags, profile.region_affinities)
    pinned_entity_match = _pinned_match_score(article.entity_tags, profile.pinned_entities)
    pinned_score = min(
            (0.32 * _pinned_match_score(article.categories, profile.pinned_categories))
            + (0.18 * _pinned_match_score(article.tags, profile.pinned_tags))
        + (0.3 * pinned_entity_match)
            + (0.2 * _pinned_match_score(article.region_tags, profile.pinned_regions)),
        1.0,
    )
    query_score = _query_memory_score(article, profile)

    score = max(
        min(
            (0.2 * category_score)
            + (0.18 * tag_score)
            + (0.22 * entity_score)
            + (0.08 * region_score)
            + (0.18 * pinned_score)
            + (0.14 * query_score),
            1.0,
        ),
        -1.0,
    )
    if pinned_entity_match:
        score = max(score, 0.85)
    return score


def diversify_scored_articles(scored_articles: list[tuple[ArticleRecord, float]], limit: int) -> list[ArticleRecord]:
    if limit <= 0 or not scored_articles:
        return []

    pool = list(scored_articles[: max(limit * 4, limit)])
    selected: list[ArticleRecord] = []
    source_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    title_counts: Counter[str] = Counter()

    while pool and len(selected) < limit:
        best_index = 0
        best_score: float | None = None

        for index, (article, base_score) in enumerate(pool):
            source_key = article.source_name.lower()
            primary_category = article.categories[0].lower() if article.categories else ""
            title_key = normalize_title(article.title)

            adjusted_score = base_score
            adjusted_score -= 0.04 * source_counts[source_key]
            adjusted_score -= 0.03 * category_counts[primary_category]
            adjusted_score -= 0.18 * title_counts[title_key]
            adjusted_score -= 0.002 * index

            if best_score is None or adjusted_score > best_score:
                best_score = adjusted_score
                best_index = index

        article, _ = pool.pop(best_index)
        selected.append(article)
        source_counts[article.source_name.lower()] += 1
        if article.categories:
            category_counts[article.categories[0].lower()] += 1
        title_counts[normalize_title(article.title)] += 1

    return selected
