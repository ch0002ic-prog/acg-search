from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.config import settings
from app.schemas import ArticleRecord
from app.services.llm import LLMService


class LLMServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.test_settings = replace(
            settings,
            llm_provider="ollama",
            llm_model="qwen2.5:3b",
        )

    def setUp(self) -> None:
        self.service = LLMService(self.test_settings)
        self.articles = [
            self.make_article("a1", "Top HoyoFest Singapore headline", "Artist Alley and sold out tickets"),
            self.make_article("a2", "Dates and venue announced", "Next year dates for Hoyo Fest"),
            self.make_article("a3", "New Artist Alley details", "Artist Alley expansion at HoYo FEST"),
        ]

    def make_article(self, article_id: str, title: str, summary: str) -> ArticleRecord:
        return ArticleRecord(
            id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            source_name="Test Feed",
            published_at=datetime.now(timezone.utc),
            summary=summary,
            content=summary,
            tags=["hoyofest"],
        )

    def test_rerank_articles_accepts_json_label_output(self) -> None:
        with patch.object(self.service, "_chat", return_value='{"labels": ["R3", "R1", "R2"]}'):
            reranked = self.service.rerank_articles("HoyoFest Singapore", self.articles)

        self.assertEqual([article.id for article in reranked[:3]], ["a3", "a1", "a2"])

    def test_rerank_articles_accepts_plain_label_list_output(self) -> None:
        with patch.object(self.service, "_chat", return_value="R2, R1, R3"):
            reranked = self.service.rerank_articles("HoyoFest Singapore", self.articles)

        self.assertEqual([article.id for article in reranked[:3]], ["a2", "a1", "a3"])

    def test_rerank_articles_uses_local_cache(self) -> None:
        with patch.object(self.service, "_chat", return_value='{"labels": ["R3", "R1", "R2"]}') as mocked_chat:
            first, first_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles)
            second, second_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles)

        self.assertEqual([article.id for article in first[:3]], ["a3", "a1", "a2"])
        self.assertEqual([article.id for article in second[:3]], ["a3", "a1", "a2"])
        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(mocked_chat.call_args.kwargs["max_tokens"], self.service.settings.llm_rerank_max_tokens)

    def test_expand_query_uses_local_cache(self) -> None:
        with patch.object(self.service, "_chat", return_value="HoyoFest Singapore, Artist Alley") as mocked_chat:
            first, first_metrics = self.service.expand_query_with_metadata("HoyoFest Singapore")
            second, second_metrics = self.service.expand_query_with_metadata("HoyoFest Singapore")

        self.assertEqual(first, second)
        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(mocked_chat.call_args.kwargs["max_tokens"], self.service.settings.llm_expand_max_tokens)

    def test_generate_digest_uses_local_cache(self) -> None:
        with patch.object(self.service, "_chat", return_value="- First line\n- Second line\n- Third line") as mocked_chat:
            first, first_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore")
            second, second_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore")

        self.assertEqual(first, ["First line", "Second line", "Third line"])
        self.assertEqual(second, first)
        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(mocked_chat.call_args.kwargs["max_tokens"], self.service.settings.llm_digest_max_tokens)


if __name__ == "__main__":
    unittest.main()