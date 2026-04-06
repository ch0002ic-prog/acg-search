from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas import ArticleRecord, EntityGroup


def _strip_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True, slots=True)
class EntityRule:
    name: str
    kind: str
    aliases: tuple[str, ...]
    ambiguous_aliases: tuple[str, ...] = ()
    context_terms: tuple[str, ...] = ()


ENTITY_RULES: tuple[EntityRule, ...] = (
    EntityRule("AFA Singapore", "event", ("anime festival asia singapore", "anime festival asia", "afa singapore", "afa")),
    EntityRule("SGCC", "event", ("singapore comic con", "sgcc")),
    EntityRule("HoyoFest Singapore", "event", ("hoyofest singapore", "hoyofest", "hoyo fest singapore", "hoyo fest")),
    EntityRule("Doujin Market", "event", ("doujin market",)),
    EntityRule(
        "POPPA",
        "event",
        ("poppa", "moe moe q", "mmq", "poppa singapore", "poppa by moe moe q"),
        ambiguous_aliases=("poppa",),
        context_terms=("moe moe q", "mmq", "idol", "anisong", "cosplay", "live", "stage", "merch signing"),
    ),
    EntityRule("Ani-Idol", "event", ("ani-idol", "ani idol")),
    EntityRule("Otaket", "event", ("otaket",)),
    EntityRule("Grand Archive TCG", "franchise", ("grand archive tcg", "grand archive")),
    EntityRule("MLBB", "esports", ("mobile legends bang bang", "mobile legends", "mlbb")),
    EntityRule("Valorant", "esports", ("valorant", "vct pacific", "vct")),
    EntityRule("FFXIV Fan Festival", "event", ("ffxiv fan festival", "ffxiv fan fest", "ff14 fan festival", "ff14 fan fest")),
    EntityRule("Final Fantasy", "franchise", ("final fantasy",)),
    EntityRule(
        "Persona",
        "franchise",
        ("persona 4 revival", "persona 4", "persona"),
        ambiguous_aliases=("persona",),
        context_terms=(
            "persona 3",
            "persona 4",
            "persona 5",
            "atlus",
            "jrpg",
            "rpg",
            "revival",
            "reload",
            "royal",
            "royale",
            "phantom thieves",
            "aniplus",
            "collab",
            "cafe",
            "funko",
            "merch",
        ),
    ),
    EntityRule("Atlus", "publisher", ("atlus",)),
    EntityRule("Street Fighter 6", "game", ("street fighter 6", "sf6")),
    EntityRule("Dragon Quest", "franchise", ("dragon quest", "metal slime")),
    EntityRule("Macross", "franchise", ("macross frontier", "macross")),
)

ENTITY_KIND_BY_NAME = {rule.name: rule.kind for rule in ENTITY_RULES}
ENTITY_NAME_LOOKUP = {
    normalized_alias: rule.name
    for rule in ENTITY_RULES
    for normalized_alias in {
        _normalize_text(rule.name),
        *(_normalize_text(alias) for alias in rule.aliases),
    }
    if normalized_alias
}
_NORMALIZED_ENTITY_RULES: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (
        rule.name,
        rule.kind,
        tuple(sorted({_normalize_text(alias) for alias in rule.aliases if _normalize_text(alias)}, key=len, reverse=True)),
        tuple(sorted({_normalize_text(alias) for alias in rule.ambiguous_aliases if _normalize_text(alias)}, key=len, reverse=True)),
        tuple(sorted({_normalize_text(term) for term in rule.context_terms if _normalize_text(term)}, key=len, reverse=True)),
    )
    for rule in sorted(ENTITY_RULES, key=lambda rule: max(len(alias) for alias in rule.aliases), reverse=True)
)


def infer_entity_tags(*parts: str, for_query: bool = False) -> list[str]:
    normalized_text = _normalize_text(" ".join(_strip_text(part) for part in parts if _strip_text(part)))
    if not normalized_text:
        return []

    matches: list[str] = []
    seen: set[str] = set()
    for entity_name, _kind, aliases, ambiguous_aliases, context_terms in _NORMALIZED_ENTITY_RULES:
        if entity_name in seen:
            continue
        matched = False
        for alias in aliases:
            if alias not in normalized_text:
                continue
            if not for_query and alias in ambiguous_aliases and context_terms and not any(term in normalized_text for term in context_terms):
                continue
            matched = True
            break
        if matched:
            seen.add(entity_name)
            matches.append(entity_name)
    return matches


def infer_entity_kind(name: str) -> str:
    return ENTITY_KIND_BY_NAME.get(name, "topic")


def display_entity_name(value: str) -> str:
    normalized_value = _normalize_text(value)
    if normalized_value in ENTITY_NAME_LOOKUP:
        return ENTITY_NAME_LOOKUP[normalized_value]

    cleaned_value = _strip_text(value)
    if not cleaned_value:
        return ""
    if any(character.isupper() for character in cleaned_value):
        return cleaned_value
    return cleaned_value.title()


def entity_overlap_score(query: str, expanded_query: str, article: "ArticleRecord") -> float:
    query_entities = infer_entity_tags(query, for_query=True)
    if not query_entities:
        return 0.0

    article_entities = {
        entity.lower()
        for entity in (article.entity_tags or infer_entity_tags(article.title, article.summary))
    }
    if not article_entities:
        return 0.0

    overlap = [entity for entity in query_entities if entity.lower() in article_entities]
    return len(overlap) / len(query_entities)


def build_entity_groups(items: list["ArticleRecord"], limit: int = 6) -> list["EntityGroup"]:
    from app.schemas import EntityGroup

    if not items:
        return []

    grouped: dict[str, dict[str, object]] = {}
    for article in items:
        for entity_name in article.entity_tags:
            bucket = grouped.setdefault(
                entity_name,
                {
                    "count": 0,
                    "source_names": set(),
                    "headline": article.title,
                },
            )
            bucket["count"] = int(bucket["count"]) + 1
            source_names = bucket["source_names"]
            if isinstance(source_names, set):
                source_names.add(article.source_name)

    groups = [
        EntityGroup(
            name=entity_name,
            kind=infer_entity_kind(entity_name),
            count=int(payload["count"]),
            source_count=len(payload["source_names"]) if isinstance(payload["source_names"], set) else 0,
            headline=str(payload["headline"]),
            source_names=sorted(payload["source_names"])[:4] if isinstance(payload["source_names"], set) else [],
        )
        for entity_name, payload in grouped.items()
    ]
    groups.sort(key=lambda group: (group.count, group.source_count, group.name), reverse=True)
    return groups[:limit]