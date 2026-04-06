from __future__ import annotations

from collections import Counter
import time

from app.database import ArticleRepository
from app.schemas import ArticleRecord, DigestTimings, FeedResponse, SearchTimings, UserProfile
from app.services.entities import build_entity_groups
from app.services.llm import LLMService
from app.services.ranking import (
    diversify_scored_articles,
    exact_query_phrase_boost,
    has_meaningful_query_match,
    query_anchor_tokens,
    query_signal_score,
    score_result_quality,
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
            ranked = [(article, article.home_score * score_result_quality(article)) for article in candidates]
        else:
            ranked = sorted(
                [
                    (
                        article,
                        (article.home_score + (0.22 * score_profile_match(article, profile)))
                        * score_result_quality(article),
                    )
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

    def search(
        self,
        query: str,
        limit: int,
        rerank: bool = True,
        user_id: str | None = None,
        track_profile: bool = True,
        include_digest: bool = True,
    ) -> FeedResponse:
        started_at = time.perf_counter()
        profile: UserProfile | None = None
        hidden_ids: set[str] = set()
        profile_started_at = time.perf_counter()
        if user_id:
            profile = (
                self.repository.record_search_query(user_id=user_id, query=query)
                if track_profile
                else self.repository.get_or_create_user_profile(user_id)
            )
            hidden_ids = self.repository.get_hidden_article_ids(user_id)
        profile_ms = _elapsed_ms(profile_started_at)

        skip_inline_search_llm = self.llm_service.should_skip_inline_search_llm(query)
        expanded_query, expand_metrics = self.llm_service.expand_query_with_metadata(query)
        strict_query = bool(query_anchor_tokens(query))
        retrieval_limit = max(limit * 5, 20)
        lexical_started_at = time.perf_counter()
        lexical_scores = dict(self.repository.lexical_search(expanded_query, limit=retrieval_limit))
        lexical_ms = _elapsed_ms(lexical_started_at)
        vector_scores_result, vector_metrics = self.vector_store.search_with_metadata(
            expanded_query,
            limit=retrieval_limit,
            candidate_ids=list(lexical_scores.keys()),
        )
        vector_scores = dict(vector_scores_result)
        vector_ms = vector_metrics.duration_ms

        candidate_ids = list(dict.fromkeys(list(lexical_scores.keys()) + list(vector_scores.keys())))
        hydrate_started_at = time.perf_counter()
        candidate_map = self.repository.get_articles_by_ids(candidate_ids)
        hydrate_ms = _elapsed_ms(hydrate_started_at)

        max_lexical = max(lexical_scores.values(), default=0.0)
        max_vector = max(vector_scores.values(), default=0.0)
        lexical_denominator = max_lexical if max_lexical > 0 else 1.0
        vector_denominator = max_vector if max_vector > 0 else 1.0
        ranked_candidates: list[tuple[ArticleRecord, float]] = []
        has_strong_non_source_page = False
        rank_started_at = time.perf_counter()
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
            phrase_boost = exact_query_phrase_boost(query=query, article=article)
            final_score = (
                (0.3 * lexical_score)
                + (0.22 * vector_score)
                + (0.28 * intent_score)
                + (0.1 * article.sg_relevance)
                + (0.1 * article.freshness_score)
                + (0.12 * profile_score)
            )
            final_score += phrase_boost
            final_score *= score_result_quality(article=article, query=query)
            if strict_query and final_score < 0.16:
                continue
            if article.result_type != "source_page" and (intent_score >= 0.45 or phrase_boost > 0):
                has_strong_non_source_page = True
            ranked_candidates.append((article, final_score))

        ranked: list[tuple[ArticleRecord, float]] = []
        for article, final_score in ranked_candidates:
            if has_strong_non_source_page and article.result_type == "source_page":
                final_score *= 0.72
            ranked.append((article, final_score))

        ranked.sort(key=lambda item: item[1], reverse=True)
        rank_ms = _elapsed_ms(rank_started_at)
        candidate_pool = ranked[: max(limit * 4, 18)]
        short_circuit_llm = skip_inline_search_llm or expand_metrics.timed_out
        rerank_ms = 0.0
        rerank_cache_hit = False
        if rerank:
            rerank_started_at = time.perf_counter()
            reranked_articles, rerank_metrics = self.llm_service.rerank_articles_with_metadata(
                query=query,
                articles=[article for article, _ in candidate_pool],
                allow_llm=not short_circuit_llm,
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
            rerank_ms = rerank_metrics.duration_ms or _elapsed_ms(rerank_started_at)
            rerank_cache_hit = rerank_metrics.cache_hit
            short_circuit_llm = short_circuit_llm or rerank_metrics.timed_out

        items = diversify_scored_articles(candidate_pool, limit)
        digest_lines: list[str] = []
        digest_ms = 0.0
        digest_cache_hit = False
        if include_digest:
            digest_lines, digest_metrics = self.llm_service.generate_digest_with_metadata(
                items,
                query=query,
                allow_llm=not short_circuit_llm,
            )
            digest_ms = digest_metrics.duration_ms
            digest_cache_hit = digest_metrics.cache_hit

        timings = SearchTimings(
            total_ms=_elapsed_ms(started_at),
            profile_ms=profile_ms,
            expand_ms=expand_metrics.duration_ms,
            lexical_ms=lexical_ms,
            vector_ms=vector_ms,
            hydrate_ms=hydrate_ms,
            rank_ms=rank_ms,
            rerank_ms=rerank_ms,
            digest_ms=digest_ms,
            lexical_candidates=len(lexical_scores),
            vector_candidates=len(vector_scores),
            result_count=len(items),
            query_expansion_cache_hit=expand_metrics.cache_hit,
            vector_cache_hit=vector_metrics.cache_hit,
            rerank_cache_hit=rerank_cache_hit,
            digest_cache_hit=digest_cache_hit,
            semantic_search_enabled=self.vector_store.semantic_search_enabled(),
        )

        return FeedResponse(
            items=items,
            digest=digest_lines,
            source_breakdown=dict(Counter(article.source_name for article in items)),
            entity_groups=build_entity_groups(items),
            query=query,
            expanded_query=expanded_query,
            profile=profile,
            timings=timings,
        )

    def search_digest(self, query: str | None, article_ids: list[str]) -> tuple[list[str], DigestTimings]:
        started_at = time.perf_counter()
        if not article_ids:
            return [], DigestTimings(total_ms=_elapsed_ms(started_at), lookup_ms=0.0, digest_ms=0.0, article_count=0, cache_hit=False)

        ordered_ids = list(dict.fromkeys(str(article_id) for article_id in article_ids if article_id))[:12]
        if not ordered_ids:
            return [], DigestTimings(total_ms=_elapsed_ms(started_at), lookup_ms=0.0, digest_ms=0.0, article_count=0, cache_hit=False)

        lookup_started_at = time.perf_counter()
        article_map = self.repository.get_articles_by_ids(ordered_ids)
        ordered_articles = [article_map[article_id] for article_id in ordered_ids if article_id in article_map]
        lookup_ms = _elapsed_ms(lookup_started_at)
        if not ordered_articles:
            return [], DigestTimings(total_ms=_elapsed_ms(started_at), lookup_ms=lookup_ms, digest_ms=0.0, article_count=0, cache_hit=False)

        digest, digest_metrics = self.llm_service.generate_digest_with_metadata(ordered_articles, query=query)
        return digest, DigestTimings(
            total_ms=_elapsed_ms(started_at),
            lookup_ms=lookup_ms,
            digest_ms=digest_metrics.duration_ms,
            article_count=len(ordered_articles),
            cache_hit=digest_metrics.cache_hit,
        )


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 1)
