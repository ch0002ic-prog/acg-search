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
        self.assertEqual(mocked_chat.call_args.kwargs["timeout_seconds"], self.service.settings.llm_rerank_timeout_seconds)

    def test_rerank_articles_falls_back_after_timeout_and_caches_result(self) -> None:
        with patch.object(self.service, "_chat", side_effect=TimeoutError("rerank timed out")) as mocked_chat:
            first, first_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles)
            second, second_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles)

        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertTrue(first_metrics.timed_out)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual([article.id for article in first], ["a1", "a2", "a3"])
        self.assertEqual([article.id for article in second], ["a1", "a2", "a3"])

    def test_rerank_articles_can_skip_llm_and_cache_fallback(self) -> None:
        with patch.object(self.service, "_chat") as mocked_chat:
            first, first_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles, allow_llm=False)
            second, second_metrics = self.service.rerank_articles_with_metadata("HoyoFest Singapore", self.articles, allow_llm=False)

        self.assertEqual([article.id for article in first], ["a1", "a2", "a3"])
        self.assertEqual([article.id for article in second], ["a1", "a2", "a3"])
        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertFalse(first_metrics.timed_out)
        self.assertEqual(mocked_chat.call_count, 0)

    def test_expand_query_uses_local_cache(self) -> None:
        with patch.object(self.service, "_chat", return_value="cosplay, anime festival asia") as mocked_chat:
            first, first_metrics = self.service.expand_query_with_metadata("cosplay")
            second, second_metrics = self.service.expand_query_with_metadata("cosplay")

        self.assertEqual(first, second)
        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(mocked_chat.call_args.kwargs["max_tokens"], self.service.settings.llm_expand_max_tokens)
        self.assertEqual(mocked_chat.call_args.kwargs["timeout_seconds"], self.service.settings.llm_expand_timeout_seconds)

    def test_should_skip_inline_search_llm_for_specific_ollama_queries(self) -> None:
        self.assertTrue(self.service.should_skip_inline_search_llm("latest hoyofest singapore artist alley"))
        self.assertTrue(self.service.should_skip_inline_search_llm("street fighter 6 ingrid"))
        self.assertTrue(self.service.should_skip_inline_search_llm("cosplay singapore"))
        self.assertFalse(self.service.should_skip_inline_search_llm("cosplay"))

    def test_expand_query_skips_llm_for_specific_ollama_queries(self) -> None:
        with patch.object(self.service, "_chat") as mocked_chat:
            first, first_metrics = self.service.expand_query_with_metadata("latest hoyofest singapore artist alley")
            second, second_metrics = self.service.expand_query_with_metadata("latest hoyofest singapore artist alley")

        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertFalse(first_metrics.timed_out)
        self.assertEqual(mocked_chat.call_count, 0)
        self.assertIn("HoYoVerse", first)

    def test_expand_query_falls_back_after_timeout_and_caches_result(self) -> None:
        with patch.object(self.service, "_chat", side_effect=TimeoutError("expand timed out")) as mocked_chat:
            first, first_metrics = self.service.expand_query_with_metadata("cosplay")
            second, second_metrics = self.service.expand_query_with_metadata("cosplay")

        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertTrue(first_metrics.timed_out)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(first, second)
        self.assertEqual(first, "cosplay")

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
        self.assertEqual(mocked_chat.call_args.kwargs["timeout_seconds"], self.service.settings.llm_digest_timeout_seconds)

    def test_generate_digest_trims_prompt_payload(self) -> None:
        long_summary = "A" * 500
        articles = [
            self.make_article("a1", "Title 1", long_summary),
            self.make_article("a2", "Title 2", long_summary),
            self.make_article("a3", "Title 3", long_summary),
            self.make_article("a4", "Title 4", long_summary),
            self.make_article("a5", "Title 5", long_summary),
        ]

        with patch.object(self.service, "_chat", return_value="- First line\n- Second line\n- Third line") as mocked_chat:
            digest, _metrics = self.service.generate_digest_with_metadata(articles, query="HoyoFest Singapore")

        prompt = mocked_chat.call_args.args[0]
        self.assertEqual(digest, ["First line", "Second line", "Third line"])
        self.assertNotIn(("A" * 181), prompt)
        self.assertIn("Title 4", prompt)
        self.assertNotIn("Title 5", prompt)

    def test_generate_digest_falls_back_after_timeout_and_caches_result(self) -> None:
        with patch.object(self.service, "_chat", side_effect=TimeoutError("digest timed out")) as mocked_chat:
            first, first_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore")
            second, second_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore")

        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertTrue(first_metrics.timed_out)
        self.assertGreaterEqual(first_metrics.duration_ms, 0)
        self.assertEqual(mocked_chat.call_count, 1)
        self.assertEqual(len(first), 4)
        self.assertEqual(second, first)
        self.assertTrue(first[0].startswith("For this search"))

    def test_generate_digest_can_skip_llm_and_cache_fallback(self) -> None:
        with patch.object(self.service, "_chat") as mocked_chat:
            first, first_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore", allow_llm=False)
            second, second_metrics = self.service.generate_digest_with_metadata(self.articles, query="HoyoFest Singapore", allow_llm=False)

        self.assertFalse(first_metrics.cache_hit)
        self.assertTrue(second_metrics.cache_hit)
        self.assertFalse(first_metrics.timed_out)
        self.assertEqual(mocked_chat.call_count, 0)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()