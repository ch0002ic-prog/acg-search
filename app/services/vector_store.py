from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.database import ArticleRepository
from app.schemas import ArticleRecord
from app.services.embeddings import build_hash_embedding


logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, settings: Settings, repository: ArticleRepository) -> None:
        self.settings = settings
        self.repository = repository
        self.backend = "local"
        self.collection: Any | None = None

        if settings.vector_backend == "chromadb":
            try:
                import chromadb

                settings.vector_dir.mkdir(parents=True, exist_ok=True)
                client = chromadb.PersistentClient(path=str(settings.vector_dir))
                self.collection = client.get_or_create_collection(name=settings.chroma_collection)
                self.backend = "chromadb"
            except Exception as exc:
                self.collection = None
                self.backend = "local"
                logger.warning("ChromaDB initialization failed; falling back to local vector search.", exc_info=exc)

    def upsert_articles(self, articles: list[ArticleRecord]) -> None:
        if not articles or self.backend != "chromadb" or self.collection is None:
            return

        self.collection.upsert(
            ids=[article.id for article in articles],
            documents=[article.combined_text() for article in articles],
            metadatas=[
                {
                    "title": article.title,
                    "source_name": article.source_name,
                    "published_at": article.published_at.isoformat(),
                }
                for article in articles
            ],
            embeddings=[build_hash_embedding(article.combined_text()) for article in articles],
        )

    def delete_articles(self, article_ids: list[str]) -> None:
        if not article_ids or self.backend != "chromadb" or self.collection is None:
            return

        self.collection.delete(ids=sorted(set(article_ids)))

    def search(self, query: str, limit: int, candidate_ids: list[str] | None = None) -> list[tuple[str, float]]:
        if self.backend == "chromadb" and self.collection is not None:
            result = self.collection.query(query_embeddings=[build_hash_embedding(query)], n_results=limit)
            ids = result.get("ids", [[]])[0]
            distances = result.get("distances", [[]])[0]
            scores: list[tuple[str, float]] = []
            for article_id, distance in zip(ids, distances, strict=False):
                scores.append((str(article_id), max(1.0 - float(distance), 0.0)))
            return scores

        prefilter_limit = max(self.settings.local_vector_prefilter_limit, limit * 12)
        prefiltered_ids = self.repository.prefilter_vector_search_ids(
            limit=prefilter_limit,
            seeded_ids=candidate_ids,
        )
        return self.repository.vector_search_with_candidates(
            query=query,
            limit=limit,
            candidate_ids=prefiltered_ids,
        )
