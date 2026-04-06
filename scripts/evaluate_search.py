from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import build_runtime


@dataclass(frozen=True)
class SearchCase:
    query: str
    expected_keywords: tuple[str, ...]
    allow_empty: bool = False


SEARCH_CASES: tuple[SearchCase, ...] = (
    SearchCase("AFA Singapore", ("anime festival asia", "afa")),
    SearchCase("SGCC guests", ("singapore comic con", "sgcc", "guest")),
    SearchCase("doujin market", ("doujin market", "doujin")),
    SearchCase("grand archive singapore", ("grand archive", "tcg")),
    SearchCase("manga workshop singapore", ("manga", "workshop", "drawing")),
    SearchCase("anime merch singapore", ("merch", "market", "figure", "collectible", "cafe")),
    SearchCase("cosplay singapore", ("cosplay", "anime festival asia", "sgcc")),
    SearchCase("new JRPG demo", ("jrpg", "atlus", "falcom", "square enix", "persona", "demo")),
    SearchCase("HoyoFest Singapore", ("hoyofest", "hoyoverse", "genshin", "honkai", "zenless")),
    SearchCase("POPPA Singapore", ("moe moe q", "mmq", "idol")),
    SearchCase("Moe Moe Q idol", ("moe moe q", "mmq", "idol")),
    SearchCase("Ani-Idol Singapore", ("ani idol", "idol", "anisong")),
    SearchCase("idol live singapore", ("idol", "ani idol", "anisong", "moe moe q")),
    SearchCase("MLBB qualifiers", ("mlbb", "mobile legends", "qualifier", "tournament"), allow_empty=True),
    SearchCase("valorant singapore", ("valorant", "riot", "vct", "pacific"), allow_empty=True),
    SearchCase("anime convention singapore", ("anime", "convention", "festival", "market")),
    SearchCase("artist alley singapore", ("artist alley", "anime festival asia", "sgcc", "market")),
    SearchCase("board games singapore", ("boardgame", "board game", "mahjong", "game on")),
    SearchCase("tcg singapore", ("tcg", "grand archive", "cards", "tournament")),
    SearchCase("otaket singapore", ("otaket",)),
    SearchCase("indie games singapore", ("indie games", "playtest", "gamedev")),
    SearchCase("manga drawing singapore", ("manga drawing", "manga", "drawing")),
    SearchCase("mahjong singapore", ("mahjong",)),
    SearchCase("dungeons dragons singapore", ("dungeon of the mad mage", "dungeons dragons", "5e")),
    SearchCase("anime market singapore", ("anime market", "doki", "market singapore")),
    SearchCase("persona 4 revival", ("persona 4 revival", "persona")),
    SearchCase("gamedev singapore", ("gamedev",)),
    SearchCase("final fantasy twists", ("final fantasy", "plot twists")),
    SearchCase("akuma rise switch", ("akuma rise", "switch")),
    SearchCase("street fighter 6 ingrid", ("street fighter 6", "ingrid")),
    SearchCase("zelda puzzle", ("legend of zelda", "puzzle")),
    SearchCase("macross figure", ("macross", "figure")),
    SearchCase("digital art manga workshop", ("digital art", "manga", "workshop")),
    SearchCase("playtest party singapore", ("playtest party", "indie games")),
    SearchCase("ff14 fan fest", ("ffxiv fan festival", "ffxiv", "fan festival"), allow_empty=True),
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def keyword_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    normalized = normalize_text(text)
    return [keyword for keyword in keywords if normalize_text(keyword) in normalized]


def main() -> None:
    _, news_service, _ = build_runtime()

    report: list[dict[str, object]] = []
    passed = 0
    wrapper_url_failures: list[str] = []
    source_page_top1_queries: list[str] = []
    top1_type_counts = {"article": 0, "event": 0, "source_page": 0}

    for case in SEARCH_CASES:
        response = news_service.search(query=case.query, limit=5, rerank=True, user_id=None)
        items = response.items
        wrapper_hits = [item.url for item in items[:5] if "news.google.com" in item.url.lower()]
        top1_result_type = items[0].result_type if items else None
        if top1_result_type in top1_type_counts:
            top1_type_counts[top1_result_type] += 1
        if top1_result_type == "source_page":
            source_page_top1_queries.append(case.query)

        result_rows: list[dict[str, object]] = []
        top1_has_match = False
        top3_has_match = False
        for index, item in enumerate(items[:5], start=1):
            hits = keyword_hits(
                " ".join([item.title, item.summary]),
                case.expected_keywords,
            )
            if index == 1 and hits:
                top1_has_match = True
            if index <= 3 and hits:
                top3_has_match = True
            result_rows.append(
                {
                    "rank": index,
                    "title": item.title,
                    "source": item.source_name,
                    "keyword_hits": hits,
                    "sg_relevance": round(item.sg_relevance, 2),
                }
            )

        if not items and case.allow_empty:
            status = "pass"
        elif not items:
            status = "fail"
        else:
            status = "pass" if top1_has_match or (case.allow_empty and top3_has_match) else "fail"

        if wrapper_hits:
            status = "fail"
            wrapper_url_failures.append(case.query)

        if status == "pass":
            passed += 1

        report.append(
            {
                "query": case.query,
                "status": status,
                "allow_empty": case.allow_empty,
                "result_count": len(items),
                "top1_has_expected_keyword": top1_has_match,
                "top3_has_expected_keyword": top3_has_match,
                "top1_result_type": top1_result_type,
                "wrapper_url_hits": wrapper_hits,
                "results": result_rows,
            }
        )

    print(
        json.dumps(
            {
                "passed": passed,
                "total": len(report),
                "pass_rate": round(passed / len(report), 3),
                "wrapper_url_failures": wrapper_url_failures,
                "top1_type_counts": top1_type_counts,
                "source_page_top1_queries": source_page_top1_queries,
                "cases": report,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()