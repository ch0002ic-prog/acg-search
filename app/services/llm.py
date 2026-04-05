from __future__ import annotations

from collections import Counter
import json
import logging
from typing import Any

import httpx

from app.config import Settings
from app.schemas import ArticleRecord
from app.services.ranking import build_digest_lines, expand_query_heuristically, infer_categories, infer_tags, strip_text


logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_enabled(self) -> bool:
        return self.settings.llm_provider.strip().lower() != "none" and bool(self.settings.llm_model)

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
            raw = self._chat(prompt)
            payload = json.loads(raw)
            summary = strip_text(payload.get("summary", fallback_summary))
            categories = [strip_text(value).lower() for value in payload.get("categories", fallback_categories)]
            tags = [strip_text(value).lower() for value in payload.get("tags", fallback_tags)]
            return summary or fallback_summary, categories or fallback_categories, tags or fallback_tags
        except Exception as exc:
            logger.warning("LLM summarization failed; using heuristic enrichment instead.", exc_info=exc)
            return fallback_summary, fallback_categories, fallback_tags

    def expand_query(self, query: str) -> str:
        fallback = expand_query_heuristically(query)
        if not self.is_enabled():
            return fallback

        prompt = (
            "Expand this user query for an ACG news searcher in Singapore. Include close synonyms, game titles, events, or fandom terms, "
            "but keep the answer to a single comma-separated line.\n\n"
            f"Query: {query}"
        )
        try:
            response = strip_text(self._chat(prompt))
            return response or fallback
        except Exception as exc:
            logger.warning("LLM query expansion failed; using heuristic expansion instead.", exc_info=exc)
            return fallback

    def rerank_articles(self, query: str, articles: list[ArticleRecord]) -> list[ArticleRecord]:
        if not self.is_enabled() or len(articles) < 3:
            return articles

        prompt_lines = [
            "Rank these article ids from most to least relevant for the search query.",
            "Return JSON with a single key ids whose value is an ordered list of ids.",
            f"Query: {query}",
        ]
        for article in articles[:8]:
            prompt_lines.append(
                f"ID={article.id} | TITLE={article.title} | SUMMARY={article.summary} | TAGS={', '.join(article.tags)}"
            )
        try:
            payload = json.loads(self._chat("\n".join(prompt_lines)))
            ordered_ids = payload.get("ids", [])
            ordered_map = {article.id: article for article in articles}
            reranked = [ordered_map[article_id] for article_id in ordered_ids if article_id in ordered_map]
            seen = {article.id for article in reranked}
            reranked.extend(article for article in articles if article.id not in seen)
            return reranked
        except Exception as exc:
            logger.warning("LLM reranking failed; using score-based ordering instead.", exc_info=exc)
            return articles

    def generate_digest(self, items: list[ArticleRecord], query: str | None = None) -> list[str]:
        if not items:
            return build_digest_lines(items, query=query)

        if not self.is_enabled():
            return build_digest_lines(items, query=query)

        prompt_lines = [
            "Turn these ACG headlines into 3 bullet points for a Singapore-based fan app.",
            "Keep each bullet to one sentence and focus on what matters immediately.",
        ]
        if query:
            prompt_lines.append(f"Search context: {query}")
        for article in items[:5]:
            prompt_lines.append(f"- {article.title}: {article.summary}")

        try:
            raw = self._chat("\n".join(prompt_lines))
            lines = [strip_text(line.lstrip("-*• ")) for line in raw.splitlines() if strip_text(line)]
            return lines[:3] or build_digest_lines(items, query=query)
        except Exception as exc:
            logger.warning("LLM digest generation failed; using deterministic digest lines instead.", exc_info=exc)
            return build_digest_lines(items, query=query)

    def _chat(self, prompt: str) -> str:
        provider = self.settings.llm_provider.strip().lower().replace("-", "_")
        timeout = self.settings.request_timeout_seconds
        if provider == "ollama":
            response = httpx.post(
                f"{self.settings.llm_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
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
        response = httpx.post(
            self._resolve_chat_completions_url(),
            headers=headers,
            json={
                "model": self.settings.llm_model,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}],
            },
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
