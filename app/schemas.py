from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field


CategoryValue = Annotated[str, Field(min_length=1, max_length=32)]
TagValue = Annotated[str, Field(min_length=1, max_length=48)]
EntityValue = Annotated[str, Field(min_length=1, max_length=80)]
RegionValue = Annotated[str, Field(min_length=1, max_length=32)]
ResultType = Literal["article", "event", "source_page"]


class EventMetadata(BaseModel):
    event_type: str | None = None
    date_label: str | None = None
    venue: str | None = None
    ticket_status: str | None = None
    ticket_url: str | None = None
    guest_status: str | None = None
    guest_names: list[str] = Field(default_factory=list)
    merch_status: str | None = None


class ArticleRecord(BaseModel):
    id: str
    title: str
    url: str
    source_name: str
    source_type: str = "rss"
    published_at: datetime
    summary: str = ""
    content: str = ""
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    entity_tags: list[str] = Field(default_factory=list)
    region_tags: list[str] = Field(default_factory=list)
    sg_relevance: float = 0.0
    freshness_score: float = 0.0
    home_score: float = 0.0
    source_quality: float = 0.5
    image_url: str | None = None
    event_metadata: EventMetadata | None = None

    @computed_field(return_type=ResultType)
    @property
    def result_type(self) -> ResultType:
        if self.source_type == "curated":
            return "source_page"
        if self.source_type == "event_listing":
            return "event"
        return "article"

    def combined_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.title,
                self.summary,
                self.content,
                " ".join(self.categories),
                " ".join(self.tags),
                " ".join(self.entity_tags),
                " ".join(self.region_tags),
            ]
            if part
        )

    def search_text(self) -> str:
        return " ".join(
            part
            for part in [
                self.title,
                self.summary,
            ]
            if part
        )


class SearchTimings(BaseModel):
    total_ms: float = 0.0
    profile_ms: float = 0.0
    expand_ms: float = 0.0
    lexical_ms: float = 0.0
    vector_ms: float = 0.0
    hydrate_ms: float = 0.0
    rank_ms: float = 0.0
    rerank_ms: float = 0.0
    digest_ms: float = 0.0
    lexical_candidates: int = 0
    vector_candidates: int = 0
    result_count: int = 0
    query_expansion_cache_hit: bool = False
    vector_cache_hit: bool = False
    rerank_cache_hit: bool = False
    digest_cache_hit: bool = False
    semantic_search_enabled: bool = False


class DigestTimings(BaseModel):
    total_ms: float = 0.0
    lookup_ms: float = 0.0
    digest_ms: float = 0.0
    article_count: int = 0
    cache_hit: bool = False
    llm_requested: bool = False
    llm_skipped: bool = False
    llm_timed_out: bool = False
    llm_upgrade_recommended: bool = False


class FeedResponse(BaseModel):
    items: list[ArticleRecord]
    digest: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_breakdown: dict[str, int] = Field(default_factory=dict)
    entity_groups: list["EntityGroup"] = Field(default_factory=list)
    query: str | None = None
    expanded_query: str | None = None
    profile: "UserProfile | None" = None
    timings: SearchTimings | None = None


class EntityGroup(BaseModel):
    name: str
    kind: str
    count: int
    source_count: int
    headline: str
    source_names: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    user_id: str
    display_name: str | None = None
    pinned_categories: list[str] = Field(default_factory=list)
    pinned_tags: list[str] = Field(default_factory=list)
    pinned_entities: list[str] = Field(default_factory=list)
    pinned_regions: list[str] = Field(default_factory=list)
    top_categories: list[str] = Field(default_factory=list)
    top_tags: list[str] = Field(default_factory=list)
    top_entities: list[str] = Field(default_factory=list)
    top_regions: list[str] = Field(default_factory=list)
    recent_queries: list[str] = Field(default_factory=list)
    interaction_count: int = 0
    category_affinities: dict[str, float] = Field(default_factory=dict)
    tag_affinities: dict[str, float] = Field(default_factory=dict)
    entity_affinities: dict[str, float] = Field(default_factory=dict)
    region_affinities: dict[str, float] = Field(default_factory=dict)
    query_affinities: dict[str, float] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=12, ge=1, le=50)
    rerank: bool = True
    user_id: str | None = Field(default=None, min_length=1, max_length=64)
    track_profile: bool = True
    include_digest: bool = False


class DigestRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    article_ids: list[str] = Field(min_length=1, max_length=12)
    prefer_llm: bool = False


class DigestResponse(BaseModel):
    digest: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    query: str | None = None
    article_count: int = 0
    timings: DigestTimings | None = None


class ProfileUpdateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=60)
    pinned_categories: list[CategoryValue] = Field(default_factory=list, max_length=12)
    pinned_tags: list[TagValue] = Field(default_factory=list, max_length=16)
    pinned_entities: list[EntityValue] = Field(default_factory=list, max_length=16)
    pinned_regions: list[RegionValue] = Field(default_factory=list, max_length=8)


class InteractionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    article_id: str = Field(min_length=1, max_length=64)
    action: Literal["open", "like", "dismiss"]


class RefreshResponse(BaseModel):
    fetched: int
    persisted: int
    seed_used: bool
    errors: list[str] = Field(default_factory=list)


class SourceHealthEntry(BaseModel):
    source_name: str
    status: Literal["ok", "error"]
    fetched_count: int = 0
    persisted_count: int = 0
    error_count: int = 0
    consecutive_failures: int = 0
    last_run_at: datetime
    last_success_at: datetime | None = None
    last_error: str | None = None
    stale: bool = False


class SourceHealthResponse(BaseModel):
    items: list[SourceHealthEntry] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    healthy_count: int = 0
    failing_count: int = 0
    stale_count: int = 0


class SourceHealthRunEntry(BaseModel):
    id: int
    source_name: str
    request_id: str | None = None
    status: Literal["ok", "error"]
    fetched_count: int = 0
    persisted_count: int = 0
    error_count: int = 0
    consecutive_failures: int = 0
    last_error: str | None = None
    ran_at: datetime


class SourceHealthRunsResponse(BaseModel):
    items: list[SourceHealthRunEntry] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SourceHealthRollupEntry(BaseModel):
    source_name: str
    total_runs: int = 0
    healthy_runs: int = 0
    failing_runs: int = 0
    failure_rate: float = 0.0
    recent_statuses: list[Literal["ok", "error"]] = Field(default_factory=list)
    latest_status: Literal["ok", "error"]
    latest_ran_at: datetime
    latest_error: str | None = None


class SourceHealthRollupsResponse(BaseModel):
    items: list[SourceHealthRollupEntry] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_hours: int = 24
