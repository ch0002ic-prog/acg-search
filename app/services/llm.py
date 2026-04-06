from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import hashlib
import json
import logging
import re
import threading
import time
from typing import Any

import httpx

from app.config import Settings
from app.schemas import ArticleRecord
from app.services.ranking import GENERIC_QUERY_TOKENS, build_digest_lines, expand_query_heuristically, infer_categories, infer_tags, query_anchor_tokens, strip_text


logger = logging.getLogger(__name__)
JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL | re.IGNORECASE)
RERANK_LABEL_PATTERN = re.compile(r"\bR[1-8]\b", re.IGNORECASE)
DIGEST_ITEM_LIMIT = 4
DIGEST_TITLE_MAX_CHARS = 140
DIGEST_SUMMARY_MAX_CHARS = 180


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


@dataclass(frozen=True)
class CallMetrics:
    duration_ms: float
    cache_hit: bool
    timed_out: bool = False


class _LocalResultCache:
    def __init__(self, ttl_seconds: int, max_entries: int) -> None:
        self.ttl_seconds = max(ttl_seconds, 0)
        self.max_entries = max(max_entries, 1)
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        if self.ttl_seconds <= 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any) -> None:
        if self.ttl_seconds <= 0:
            return
        now = time.monotonic()
        with self._lock:
            self._entries[key] = _CacheEntry(value=value, expires_at=now + self.ttl_seconds)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)


def _compact_digest_item(article: ArticleRecord) -> dict[str, str]:
    return {
        "id": article.id,
        "title": strip_text(article.title)[:DIGEST_TITLE_MAX_CHARS],
        "summary": strip_text(article.summary)[:DIGEST_SUMMARY_MAX_CHARS],
    }


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._query_expansion_cache = _LocalResultCache(
            ttl_seconds=settings.llm_cache_ttl_seconds,
            max_entries=settings.llm_cache_max_entries,
        )
        self._rerank_cache = _LocalResultCache(
            ttl_seconds=settings.llm_cache_ttl_seconds,
            max_entries=settings.llm_cache_max_entries,
        )
        self._digest_cache = _LocalResultCache(
            ttl_seconds=settings.llm_cache_ttl_seconds,
            max_entries=settings.llm_cache_max_entries,
        )

    def is_enabled(self) -> bool:
        return self.settings.llm_provider.strip().lower() != "none" and bool(self.settings.llm_model)

    def should_skip_inline_search_llm(self, query: str, heuristic_expansion: str | None = None) -> bool:
        provider = self.settings.llm_provider.strip().lower().replace("-", "_")
        if provider != "ollama" or not self.is_enabled():
            return False

        normalized_query = strip_text(query)
        fallback = strip_text(heuristic_expansion or expand_query_heuristically(query))
        anchor_count = len(query_anchor_tokens(query))
        query_tokens = set(re.findall(r"[a-z0-9]+", normalized_query.lower()))
        has_generic_context = any(token in query_tokens for token in GENERIC_QUERY_TOKENS)
        if fallback and fallback != normalized_query:
            return True
        if anchor_count >= 2:
            return True
        if anchor_count >= 1 and has_generic_context:
            return True
        if anchor_count >= 1 and any(character.isdigit() for character in normalized_query):
            return True
        return False

    def warmup(self) -> float | None:
        provider = self.settings.llm_provider.strip().lower().replace("-", "_")
        if provider != "ollama" or not self.is_enabled():
            return None

        started_at = time.perf_counter()
        try:
            self._chat("Reply with OK only.", max_tokens=8)
            self._chat('Return JSON with a single key ok set to true.', json_mode=True, max_tokens=16)
        except Exception as exc:
            logger.warning("LLM warmup failed; cold-path search may stay slower.", exc_info=exc)
            return None
        return _elapsed_ms(started_at)

    def summarize_and_tag(self, title: str, content: str) -> tuple[str, list[str], list[str]]:
        fallback_categories = infer_categories(title, content)
        fallback_tags = infer_tags(title, content)
        fallback_summary = self._fallback_summary(title=title, content=content)

        if not self.is_enabled() or not self.settings.enable_llm_enrichment:
            return fallback_summary, fallback_categories, fallback_tags

        prompt = (
            "Summarize this ACG news item for a Singapore audience in one concise sentence and return JSON "
            'with keys summary, categories, tags. Keep categories to broad feed buckets like anime, games, events, merch, esports.\n\n'
            f"Title: {title}\n"
            f"Content: {content[:2000]}"
        )
        try:
            raw = self._chat(prompt, json_mode=True)
            payload = self._load_json_response(raw)
            summary = strip_text(payload.get("summary", fallback_summary))
            categories = [strip_text(value).lower() for value in payload.get("categories", fallback_categories)]
            tags = [strip_text(value).lower() for value in payload.get("tags", fallback_tags)]
            return summary or fallback_summary, categories or fallback_categories, tags or fallback_tags
        except Exception as exc:
            logger.warning("LLM summarization failed; using heuristic enrichment instead.", exc_info=exc)
            return fallback_summary, fallback_categories, fallback_tags

    def expand_query(self, query: str) -> str:
        expanded_query, _metrics = self.expand_query_with_metadata(query)
        return expanded_query

    def expand_query_with_metadata(self, query: str) -> tuple[str, CallMetrics]:
        started_at = time.perf_counter()
        fallback = expand_query_heuristically(query)
        if not self.is_enabled():
            return fallback, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        cache_key = self._cache_key(
            "expand-query",
            {
                "provider": self.settings.llm_provider,
                "model": self.settings.llm_model,
                "query": strip_text(query),
            },
        )
        cached = self._query_expansion_cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=True)

        if self.should_skip_inline_search_llm(query, heuristic_expansion=fallback):
            self._query_expansion_cache.set(cache_key, fallback)
            return fallback, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        prompt = (
            "Expand this user query for an ACG news searcher in Singapore. Include close synonyms, game titles, events, or fandom terms, "
            "but keep the answer to a single comma-separated line.\n\n"
            f"Query: {query}"
        )
        try:
            response = strip_text(
                self._chat(
                    prompt,
                    max_tokens=self.settings.llm_expand_max_tokens,
                    timeout_seconds=self.settings.llm_expand_timeout_seconds,
                )
            )
            resolved = response or fallback
            self._query_expansion_cache.set(cache_key, resolved)
            return resolved, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)
        except (TimeoutError, httpx.TimeoutException):
            logger.warning(
                "LLM query expansion timed out after %.1f s; using heuristic expansion instead.",
                self.settings.llm_expand_timeout_seconds,
            )
            self._query_expansion_cache.set(cache_key, fallback)
            return fallback, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False, timed_out=True)
        except Exception as exc:
            logger.warning("LLM query expansion failed; using heuristic expansion instead.", exc_info=exc)
            self._query_expansion_cache.set(cache_key, fallback)
            return fallback, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

    def rerank_articles(self, query: str, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        reranked_articles, _metrics = self.rerank_articles_with_metadata(query, articles)
        return reranked_articles

    def rerank_articles_with_metadata(
        self,
        query: str,
        articles: list[ArticleRecord],
        allow_llm: bool = True,
    ) -> tuple[list[ArticleRecord], CallMetrics]:
        started_at = time.perf_counter()
        if not self.is_enabled() or len(articles) < 3:
            return articles, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        rerank_candidates = articles[:8]
        cache_key = self._cache_key(
            "rerank",
            {
                "provider": self.settings.llm_provider,
                "model": self.settings.llm_model,
                "query": strip_text(query),
                "items": [
                    {
                        "id": article.id,
                        "title": article.title[:180],
                        "summary": article.summary[:220],
                    }
                    for article in rerank_candidates
                ],
            },
        )
        cached = self._rerank_cache.get(cache_key)
        if isinstance(cached, list) and cached:
            article_by_id = {article.id: article for article in articles}
            reranked = [article_by_id[article_id] for article_id in cached if article_id in article_by_id]
            seen = {article.id for article in reranked}
            reranked.extend(article for article in articles if article.id not in seen)
            return reranked, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=True)

        if not allow_llm:
            self._rerank_cache.set(cache_key, [article.id for article in articles])
            return articles, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        labeled_articles = [(f"R{index}", article) for index, article in enumerate(rerank_candidates, start=1)]
        article_by_label = {label: article for label, article in labeled_articles}
        prompt_lines = [
            "Rank these labels from most to least relevant for the search query.",
            "Return only JSON with a single key labels whose value is an ordered list of labels.",
            f"Query: {query}",
        ]
        for label, article in labeled_articles:
            prompt_lines.append(
                f"LABEL={label} | TITLE={article.title[:180]} | SUMMARY={article.summary[:220]} | TAGS={', '.join(article.tags[:6])}"
            )
        try:
            raw = self._chat(
                "\n".join(prompt_lines),
                json_mode=True,
                max_tokens=self.settings.llm_rerank_max_tokens,
                timeout_seconds=self.settings.llm_rerank_timeout_seconds,
            )
            ordered_labels = self._parse_rerank_labels(raw)
            reranked = [article_by_label[label] for label in ordered_labels if label in article_by_label]
            seen = {article.id for article in reranked}
            reranked.extend(article for article in articles if article.id not in seen)
            self._rerank_cache.set(cache_key, [article.id for article in reranked])
            return reranked, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)
        except (TimeoutError, httpx.TimeoutException):
            logger.warning(
                "LLM reranking timed out after %.1f s; using score-based ordering instead.",
                self.settings.llm_rerank_timeout_seconds,
            )
            self._rerank_cache.set(cache_key, [article.id for article in articles])
            return articles, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False, timed_out=True)
        except Exception as exc:
            logger.warning("LLM reranking failed; using score-based ordering instead.", exc_info=exc)
            self._rerank_cache.set(cache_key, [article.id for article in articles])
            return articles, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

    def generate_digest(self, items: list[ArticleRecord], query: str | None = None) -> list[str]:
        digest_lines, _metrics = self.generate_digest_with_metadata(items, query=query)
        return digest_lines

    def generate_digest_with_metadata(
        self,
        items: list[ArticleRecord],
        query: str | None = None,
        allow_llm: bool = True,
    ) -> tuple[list[str], CallMetrics]:
        started_at = time.perf_counter()
        if not items:
            return build_digest_lines(items, query=query), CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        if not self.is_enabled():
            return build_digest_lines(items, query=query), CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        digest_items = [_compact_digest_item(item) for item in items[:DIGEST_ITEM_LIMIT]]
        cache_key = self._cache_key(
            "digest",
            {
                "provider": self.settings.llm_provider,
                "model": self.settings.llm_model,
                "query": strip_text(query or ""),
                "items": digest_items,
            },
        )
        cached = self._digest_cache.get(cache_key)
        if isinstance(cached, list) and cached:
            return [str(value) for value in cached], CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=True)

        if not allow_llm:
            fallback_lines = build_digest_lines(items, query=query)
            self._digest_cache.set(cache_key, fallback_lines)
            return fallback_lines, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

        prompt_lines = [
            "Turn these ACG headlines into exactly 3 short bullet points for a Singapore-based fan app.",
            "Use plain text only, one bullet per line, and focus on what matters immediately.",
        ]
        if query:
            prompt_lines.append(f"Search context: {query}")
        for article in digest_items:
            prompt_lines.append(f"- {article['title']}: {article['summary']}")

        try:
            raw = self._chat(
                "\n".join(prompt_lines),
                max_tokens=self.settings.llm_digest_max_tokens,
                timeout_seconds=self.settings.llm_digest_timeout_seconds,
            )
            lines = [strip_text(line.lstrip("-*• ")) for line in raw.splitlines() if strip_text(line)]
            resolved = lines[:3] or build_digest_lines(items, query=query)
            self._digest_cache.set(cache_key, resolved)
            return resolved, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)
        except (TimeoutError, httpx.TimeoutException):
            logger.warning(
                "LLM digest generation timed out after %.1f s; using deterministic digest lines instead.",
                self.settings.llm_digest_timeout_seconds,
            )
            fallback_lines = build_digest_lines(items, query=query)
            self._digest_cache.set(cache_key, fallback_lines)
            return fallback_lines, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False, timed_out=True)
        except Exception as exc:
            logger.warning("LLM digest generation failed; using deterministic digest lines instead.", exc_info=exc)
            fallback_lines = build_digest_lines(items, query=query)
            self._digest_cache.set(cache_key, fallback_lines)
            return fallback_lines, CallMetrics(duration_ms=_elapsed_ms(started_at), cache_hit=False)

    def _chat(
        self,
        prompt: str,
        json_mode: bool = False,
        max_tokens: int | None = None,
        timeout_seconds: float | None = None,
    ) -> str:
        provider = self.settings.llm_provider.strip().lower().replace("-", "_")
        timeout = timeout_seconds or self.settings.llm_timeout_seconds
        token_budget = max_tokens or self.settings.llm_max_tokens
        if provider == "ollama":
            payload: dict[str, Any] = {
                "model": self.settings.llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": token_budget,
                },
            }
            if json_mode:
                payload["format"] = "json"
            response = httpx.post(
                f"{self.settings.llm_base_url.rstrip('/')}/api/chat",
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if "message" in payload:
                return self._extract_text(payload["message"].get("content", ""))
            return self._extract_text(payload.get("response", ""))

        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"
        openai_payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "temperature": 0.2,
            "max_tokens": token_budget,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            openai_payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            self._resolve_chat_completions_url(),
            headers=headers,
            json=openai_payload,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        choice = payload.get("choices", [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        return self._extract_text(message.get("content", choice.get("text", "")))

    def _resolve_chat_completions_url(self) -> str:
        base_url = self.settings.llm_base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    def _extract_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or item.get("content") or item.get("value")
                if isinstance(text, str):
                    parts.append(text)
            return "\n".join(part for part in parts if part)
        if isinstance(content, dict):
            text = content.get("text") or content.get("content") or content.get("value")
            return text if isinstance(text, str) else json.dumps(content)
        return str(content)

    def _load_json_response(self, raw: str) -> dict[str, Any]:
        cleaned = strip_text(raw)
        if not cleaned:
            raise ValueError("LLM returned an empty response")

        fenced_match = JSON_BLOCK_PATTERN.search(cleaned)
        if fenced_match:
            cleaned = strip_text(fenced_match.group(1))

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            payload = json.loads(self._extract_json_substring(cleaned))

        if not isinstance(payload, dict):
            raise ValueError("LLM JSON response was not an object")
        return payload

    def _parse_rerank_labels(self, raw: str) -> list[str]:
        cleaned = strip_text(raw)
        if not cleaned:
            raise ValueError("LLM rerank response was empty")

        try:
            payload = self._load_json_response(cleaned)
            candidate_lists = [
                payload.get("labels"),
                payload.get("ids"),
                payload.get("order"),
            ]
            for candidate in candidate_lists:
                if isinstance(candidate, list):
                    parsed = [strip_text(str(value)).upper() for value in candidate if strip_text(str(value))]
                    if parsed:
                        return parsed
        except Exception:
            pass

        labels = [match.group(0).upper() for match in RERANK_LABEL_PATTERN.finditer(cleaned)]
        ordered: list[str] = []
        seen: set[str] = set()
        for label in labels:
            if label in seen:
                continue
            seen.add(label)
            ordered.append(label)
        if ordered:
            return ordered
        raise ValueError("No rerank labels found in LLM response")

    def _extract_json_substring(self, value: str) -> str:
        start_candidates = [index for index in (value.find("{"), value.find("[")) if index >= 0]
        if not start_candidates:
            raise ValueError("No JSON payload found in LLM response")
        start = min(start_candidates)
        end = max(value.rfind("}"), value.rfind("]"))
        if end < start:
            raise ValueError("Incomplete JSON payload found in LLM response")
        return value[start : end + 1]

    def _cache_key(self, namespace: str, payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return f"{namespace}:{hashlib.sha1(serialized.encode('utf-8')).hexdigest()}"

    def _fallback_summary(self, title: str, content: str) -> str:
        cleaned = strip_text(content)
        if cleaned:
            sentence = cleaned.split(".", maxsplit=1)[0]
            if sentence and len(sentence) > 40:
                return sentence[:180].rstrip()

        keywords = [token for token, _ in Counter(infer_tags(title, content)).most_common(3)]
        if keywords:
            return f"{title} is trending around {', '.join(keywords)}." 
        return title


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 1)
