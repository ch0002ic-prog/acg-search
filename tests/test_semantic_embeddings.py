from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.config import settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.embeddings import EmbeddingRecord, SemanticEmbeddingService
from app.services.ranking import compute_home_score, score_freshness
from app.services.vector_store import VectorStore


class SemanticEmbeddingResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class SemanticEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = TemporaryDirectory()
        base_path = Path(cls.temp_dir.name)
        cls.test_settings = replace(
            settings,
            db_path=base_path / "test-semantic.db",
            vector_dir=base_path / "vector-store",
            data_dir=base_path,
            vector_backend="local",
            llm_provider="none",
            llm_model=None,
            enable_llm_enrichment=False,
            embedding_provider="openai_compatible",
            embedding_base_url="https://embeddings.example",
            embedding_model="text-embedding-3-small",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def setUp(self) -> None:
        if self.test_settings.db_path.exists():
            self.test_settings.db_path.unlink()
        self.repository = ArticleRepository(self.test_settings.db_path)
        self.repository.init_database()
        self.vector_store = VectorStore(settings=self.test_settings, repository=self.repository)

    def make_article(
        self,
        article_id: str,
        title: str,
        summary: str,
        published_at: datetime,
        home_bias: float,
    ) -> ArticleRecord:
        freshness = score_freshness(published_at)
        return ArticleRecord(
            id=article_id,
            title=title,
            url=f"https://example.com/{article_id}",
            source_name="Semantic Test Feed",
            source_type="rss",
            published_at=published_at,
            summary=summary,
            content=summary,
            categories=["anime", "events"],
            tags=["singapore"],
            region_tags=["Singapore"],
            sg_relevance=0.72,
            freshness_score=freshness,
            home_score=compute_home_score(
                freshness_score=freshness,
                sg_relevance=0.72 + home_bias,
                categories=["anime", "events"],
                source_quality=0.8,
            ),
            source_quality=0.8,
        )

    def test_openai_embedding_client_parses_and_normalizes_response(self) -> None:
        service = SemanticEmbeddingService(self.test_settings)

        with patch(
            "app.services.embeddings.httpx.post",
            return_value=SemanticEmbeddingResponse(
                {
                    "data": [
                        {"index": 0, "embedding": [3.0, 4.0]},
                    ]
                }
            ),
        ) as mock_post:
            result = service.embed_query("AFA Singapore")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertAlmostEqual(result.vector[0], 0.6, places=3)
        self.assertAlmostEqual(result.vector[1], 0.8, places=3)
        self.assertTrue(result.signature.startswith("openai_compatible:text-embedding-3-small:"))
        self.assertEqual(mock_post.call_args.args[0], "https://embeddings.example/v1/embeddings")

    def test_embedding_requests_are_batched(self) -> None:
        batched_settings = replace(self.test_settings, embedding_batch_size=2)
        service = SemanticEmbeddingService(batched_settings)

        def fake_post(*args, **kwargs):
            inputs = kwargs["json"]["input"]
            payload = {
                "data": [
                    {"index": index, "embedding": [float(index + 1), 0.0]}
                    for index, _value in enumerate(inputs)
                ]
            }
            return SemanticEmbeddingResponse(payload)

        with patch("app.services.embeddings.httpx.post", side_effect=fake_post) as mock_post:
            records = service.embed_documents(["one", "two", "three"])

        self.assertEqual(len(records), 3)
        self.assertEqual(mock_post.call_count, 2)

    def test_vector_store_uses_semantic_embeddings_when_available(self) -> None:
        now = datetime.now(timezone.utc)
        article_a = self.make_article(
            article_id="idol-tech",
            title="Singapore idol technology showcase opens",
            summary="A hologram idol demo and virtual performance stage headline the expo.",
            published_at=now - timedelta(hours=2),
            home_bias=0.05,
        )
        article_b = self.make_article(
            article_id="idol-cafe",
            title="Singapore idol cafe menu announced",
            summary="A themed idol cafe pop-up adds desserts and drinks for fans.",
            published_at=now - timedelta(hours=1),
            home_bias=0.08,
        )
        signature = self.vector_store.current_semantic_signature()
        self.repository.upsert_articles(
            [article_a, article_b],
            semantic_embeddings={
                article_a.id: EmbeddingRecord(vector=[1.0, 0.0], signature=signature),
                article_b.id: EmbeddingRecord(vector=[0.0, 1.0], signature=signature),
            },
        )

        with patch.object(
            self.vector_store.semantic_embedding_service,
            "embed_query",
            return_value=EmbeddingRecord(vector=[1.0, 0.0], signature=signature),
        ):
            scores = self.vector_store.search(query="virtual idol stage", limit=2)

        self.assertEqual(scores[0][0], article_a.id)
        self.assertGreater(scores[0][1], scores[1][1])

    def test_vector_store_does_not_fall_back_to_hash_when_semantic_mode_is_enabled(self) -> None:
        now = datetime.now(timezone.utc)
        article = self.make_article(
            article_id="idol-tech",
            title="Singapore idol technology showcase opens",
            summary="A hologram idol demo and virtual performance stage headline the expo.",
            published_at=now - timedelta(hours=2),
            home_bias=0.05,
        )
        self.repository.upsert_articles([article])

        with (
            patch.object(self.vector_store.semantic_embedding_service, "embed_query", return_value=None),
            patch.object(
                self.repository,
                "vector_search_with_candidates",
                side_effect=AssertionError("hash fallback should not run in semantic mode"),
            ),
        ):
            scores = self.vector_store.search(query="virtual idol stage", limit=2)

        self.assertEqual(scores, [])


if __name__ == "__main__":
    unittest.main()