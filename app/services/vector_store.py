from __future__ import annotations

from dataclasses import dataclass
import hashlib
import logging
from typing import Any

from app.config import Settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.embeddings import EmbeddingRecord, SemanticEmbeddingService, build_hash_embedding, hash_embedding_signature


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorSearchMetrics:
    duration_ms: float
    cache_hit: bool


class VectorStore:
    def __init__(
        self,
        settings: Settings,
        repository: ArticleRepository,
        semantic_embedding_service: SemanticEmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.semantic_embedding_service = semantic_embedding_service or SemanticEmbeddingService(settings)
        self.backend = "local"
        self.collection: Any | None = None
        self.collection_name = self._resolve_collection_name()

        if settings.vector_backend == "chromadb":
            try:
                import chromadb

                settings.vector_dir.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=str(settings.vector_dir))
                self.collection = client.get_or_create_collection(name=self.collection_name)
                self.backend = "chromadb"
            except Exception as exc:
                self.collection = None
                self.backend = "local"
                logger.warning("ChromaDB initialization failed; falling back to local vector search.", exc_info=exc)

    def semantic_search_enabled(self) -> bool:
        return self.semantic_embedding_service.is_enabled()

    def current_semantic_signature(self) -> str:
        return self.semantic_embedding_service.current_signature()

    def build_semantic_embeddings(self, articles: list[ArticleRecord]) -> dict[str, EmbeddingRecord]:
        if not articles or not self.semantic_search_enabled():
            return {}

        embeddings = self.semantic_embedding_service.embed_documents([article.combined_text() for article in articles])
        if len(embeddings) != len(articles):
            return {}
        return {
            article.id: embedding
            for article, embedding in zip(articles, embeddings, strict=False)
        }

    def upsert_articles(
        self,
        articles: list[ArticleRecord],
        semantic_embeddings: dict[str, EmbeddingRecord] | None = None,
    ) -> None:
        if not articles or self.backend != "chromadb" or self.collection is None:
            return

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, object]] = []
        embeddings_payload: list[list[float]] = []

        if self.semantic_search_enabled():
            active_embeddings = semantic_embeddings if semantic_embeddings is not None else self.build_semantic_embeddings(articles)
            if not active_embeddings:
                return
            for article in articles:
                embedding_record = active_embeddings.get(article.id)
                if embedding_record is None or not embedding_record.vector:
                    continue
                ids.append(article.id)
                documents.append(article.combined_text())
                metadatas.append(
                    {
                        "title": article.title,
                        "source_name": article.source_name,
                        "published_at": article.published_at.isoformat(),
                        "embedding_signature": embedding_record.signature,
                    }
                )
                embeddings_payload.append(embedding_record.vector)
        else:
            signature = hash_embedding_signature()
            for article in articles:
                ids.append(article.id)
                documents.append(article.combined_text())
                metadatas.append(
                    {
                        "title": article.title,
                        "source_name": article.source_name,
                        "published_at": article.published_at.isoformat(),
                        "embedding_signature": signature,
                    }
                )
                embeddings_payload.append(build_hash_embedding(article.combined_text()))

        if not ids:
            return

        self.collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings_payload,
        )

    def delete_articles(self, article_ids: list[str]) -> None:
        if not article_ids or self.backend != "chromadb" or self.collection is None:
            return

        self.collection.delete(ids=sorted(set(article_ids)))

    def search(self, query: str, limit: int, candidate_ids: list[str] | None = None) -> list[tuple[str, float]]:
        scores, _metrics = self.search_with_metadata(query=query, limit=limit, candidate_ids=candidate_ids)
        return scores

    def search_with_metadata(self, query: str, limit: int, candidate_ids: list[str] | None = None) -> tuple[list[tuple[str, float]], VectorSearchMetrics]:
        import time

        started_at = time.perf_counter()
        if self.semantic_search_enabled():
            scores, cache_hit = self._search_semantic(query=query, limit=limit, candidate_ids=candidate_ids)
            return scores, VectorSearchMetrics(duration_ms=round((time.perf_counter() - started_at) * 1000, 1), cache_hit=cache_hit)

        if self.backend == "chromadb" and self.collection is not None and not self.semantic_search_enabled():
            result = self.collection.query(query_embeddings=[build_hash_embedding(query)], n_results=limit)
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            scores: list[tuple[str, float]] = []
            for article_id, distance in zip(ids, distances, strict=False):
                scores.append((str(article_id), max(1.0 - float(distance), 0.0)))
            return scores, VectorSearchMetrics(duration_ms=round((time.perf_counter() - started_at) * 1000, 1), cache_hit=False)

        prefilter_limit = max(self.settings.local_vector_prefilter_limit, limit * 12)
        prefiltered_ids = self.repository.prefilter_vector_search_ids(
            limit=prefilter_limit,
            seeded_ids=candidate_ids,
        )
        scores = self.repository.vector_search_with_candidates(
            query=query,
            limit=limit,
            candidate_ids=prefiltered_ids,
        )
        return scores, VectorSearchMetrics(duration_ms=round((time.perf_counter() - started_at) * 1000, 1), cache_hit=False)

    def _search_semantic(self, query: str, limit: int, candidate_ids: list[str] | None = None) -> tuple[list[tuple[str, float]], bool]:
        query_embedding, embedding_metrics = self.semantic_embedding_service.embed_query_with_metadata(query)
        if query_embedding is None or not query_embedding.vector:
            return [], embedding_metrics.cache_hit

        if self.backend == "chromadb" and self.collection is not None:
            result = self.collection.query(query_embeddings=[query_embedding.vector], n_results=limit)
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            scores: list[tuple[str, float]] = []
            for article_id, distance in zip(ids, distances, strict=False):
                scores.append((str(article_id), max(1.0 - float(distance), 0.0)))
            return scores, embedding_metrics.cache_hit

        prefilter_limit = max(self.settings.local_vector_prefilter_limit, limit * 12)
        prefiltered_ids = self.repository.prefilter_vector_search_ids(
            limit=prefilter_limit,
            seeded_ids=candidate_ids,
        )
        scores = self.repository.semantic_vector_search_with_candidates(
            query_embedding=query_embedding.vector,
            embedding_signature=query_embedding.signature,
            limit=limit,
            candidate_ids=prefiltered_ids,
        )
        return scores, embedding_metrics.cache_hit

    def _resolve_collection_name(self) -> str:
        signature = self.current_semantic_signature() if self.semantic_search_enabled() else hash_embedding_signature()
        suffix = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:10]
        return f"{self.settings.chroma_collection}_{suffix}"
