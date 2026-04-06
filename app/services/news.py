from __future__ import annotations

from collections import Counter

from app.database import ArticleRepository
from app.schemas import ArticleRecord, FeedResponse, UserProfile
from app.services.entities import build_entity_groups
from app.services.llm import LLMService
from app.services.ranking import (
    diversify_scored_articles,
    exact_query_phrase_boost,
    has_meaningful_query_match,
    query_anchor_tokens,
    query_signal_score,
    score_profile_match,
)
from app.services.vector_store import VectorStore


class NewsService:
    def __init__(
        self,
        repository: ArticleRepository,
        vector_store: VectorStore,
        llm_service: LLMService,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.llm_service = llm_service

    def home_feed(self, limit: int, user_id: str | None = None) -> FeedResponse:
        profile = self.repository.get_or_create_user_profile(user_id) if user_id else None
        hidden_ids = self.repository.get_hidden_article_ids(user_id) if user_id else set()
        candidates = self.repository.latest_articles(max(limit * 4, 36), exclude_ids=hidden_ids)

        if profile is None:
            ranked = [(article, article.home_score) for article in candidates]
        else:
            ranked = sorted(
                [
                    (article, article.home_score + (0.22 * score_profile_match(article, profile)))
                    for article in candidates
                ],
                key=lambda item: item[1],
                reverse=True,
            )
        items = diversify_scored_articles(ranked, limit)

        return FeedResponse(
            items=items,
            digest=self.llm_service.generate_digest(items),
            source_breakdown=dict(Counter(article.source_name for article in items)),
            entity_groups=build_entity_groups(items),
            profile=profile,
        )

    def search(self, query: str, limit: int, rerank: bool = True, user_id: str | None = None, track_profile: bool = True) -> FeedResponse:
        profile: UserProfile | None = None
        hidden_ids: set[str] = set()
        if user_id:
            profile = (
                self.repository.record_search_query(user_id=user_id, query=query)
                if track_profile
                else self.repository.get_or_create_user_profile(user_id)
            )
            hidden_ids = self.repository.get_hidden_article_ids(user_id)

        expanded_query = self.llm_service.expand_query(query)
        strict_query = bool(query_anchor_tokens(query))
        retrieval_limit = max(limit * 5, 20)
        lexical_scores = dict(self.repository.lexical_search(expanded_query, limit=retrieval_limit))
        vector_scores = dict(
            self.vector_store.search(
                expanded_query,
                limit=retrieval_limit,
                candidate_ids=list(lexical_scores.keys()),
            )
        )

        candidate_ids = list(dict.fromkeys(list(lexical_scores.keys()) + list(vector_scores.keys())))
        candidate_map = self.repository.get_articles_by_ids(candidate_ids)

        max_lexical = max(lexical_scores.values(), default=0.0)
        max_vector = max(vector_scores.values(), default=0.0)
        lexical_denominator = max_lexical if max_lexical > 0 else 1.0
        vector_denominator = max_vector if max_vector > 0 else 1.0
        ranked: list[tuple[ArticleRecord, float]] = []
        for article_id in candidate_ids:
            if article_id in hidden_ids:
                continue
            article = candidate_map.get(article_id)
            if article is None:
                continue
            lexical_score = lexical_scores.get(article_id, 0.0) / lexical_denominator
            vector_score = vector_scores.get(article_id, 0.0) / vector_denominator
            intent_score = query_signal_score(query=query, expanded_query=expanded_query, article=article)
            if strict_query and not has_meaningful_query_match(query=query, expanded_query=expanded_query, article=article):
                continue
            profile_score = score_profile_match(article, profile)
            final_score = (
                (0.3 * lexical_score)
                + (0.22 * vector_score)
                + (0.28 * intent_score)
                + (0.1 * article.sg_relevance)
                + (0.1 * article.freshness_score)
                + (0.12 * profile_score)
            )
            final_score += exact_query_phrase_boost(query=query, article=article)
            if strict_query and final_score < 0.16:
                continue
            ranked.append((article, final_score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        candidate_pool = ranked[: max(limit * 4, 18)]
        if rerank:
            reranked_articles = self.llm_service.rerank_articles(
                query=query,
                articles=[article for article, _ in candidate_pool],
            )
            score_map = {article.id: score for article, score in candidate_pool}
            rerank_count = max(len(reranked_articles) - 1, 1)
            candidate_pool = [
                (
                    article,
                    score_map.get(article.id, 0.0) + (0.08 * (1 - (index / rerank_count))),
                )
                for index, article in enumerate(reranked_articles)
            ]

        items = diversify_scored_articles(candidate_pool, limit)

        return FeedResponse(
            items=items,
            digest=self.llm_service.generate_digest(items, query=query),
            source_breakdown=dict(Counter(article.source_name for article in items)),
            entity_groups=build_entity_groups(items),
            query=query,
            expanded_query=expanded_query,
            profile=profile,
        )
