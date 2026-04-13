from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from typing import Literal, cast

from app.schemas import ArticleRecord, SourceHealthEntry, SourceHealthRollupEntry, SourceHealthRunEntry, UserProfile
from app.services.dedupe import article_dedupe_key, article_preference_signature
from app.services.entities import display_entity_name, infer_entity_tags
from app.services.embeddings import EmbeddingRecord, build_hash_embedding, cosine_similarity
from app.services.event_metadata import coerce_event_metadata, infer_event_metadata, merge_event_metadata
from app.services.ranking import build_fts_query, infer_query_preferences, strip_text
from app.url_utils import is_external_http_url


INTERACTION_WEIGHTS: dict[str, float] = {
    "open": 0.3,
    "like": 0.85,
    "dismiss": -0.95,
}
SEARCH_WEIGHT = 0.38
MAX_RECENT_QUERIES = 8
MAX_AFFINITY = 3.0
MIN_AFFINITY = -2.0


def _external_url_sql(column_name: str = "url") -> str:
    return f"(LOWER({column_name}) LIKE 'http://%' OR LOWER({column_name}) LIKE 'https://%')"


class ArticleRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def init_database(self) -> None:
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    source_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    categories TEXT NOT NULL DEFAULT '[]',
                    tags TEXT NOT NULL DEFAULT '[]',
                    entity_tags TEXT NOT NULL DEFAULT '[]',
                    region_tags TEXT NOT NULL DEFAULT '[]',
                    sg_relevance REAL NOT NULL DEFAULT 0,
                    freshness_score REAL NOT NULL DEFAULT 0,
                    home_score REAL NOT NULL DEFAULT 0,
                    source_quality REAL NOT NULL DEFAULT 0.5,
                    image_url TEXT,
                    event_metadata TEXT NOT NULL DEFAULT '{}',
                    embedding TEXT NOT NULL DEFAULT '[]',
                    semantic_embedding TEXT NOT NULL DEFAULT '[]',
                    semantic_embedding_signature TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                    article_id UNINDEXED,
                    title,
                    summary,
                    content,
                    tags,
                    source_name,
                    region_tags
                );

                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT,
                    pinned_categories TEXT NOT NULL DEFAULT '[]',
                    pinned_tags TEXT NOT NULL DEFAULT '[]',
                    pinned_entities TEXT NOT NULL DEFAULT '[]',
                    pinned_regions TEXT NOT NULL DEFAULT '[]',
                    category_affinities TEXT NOT NULL DEFAULT '{}',
                    tag_affinities TEXT NOT NULL DEFAULT '{}',
                    entity_affinities TEXT NOT NULL DEFAULT '{}',
                    region_affinities TEXT NOT NULL DEFAULT '{}',
                    query_affinities TEXT NOT NULL DEFAULT '{}',
                    recent_queries TEXT NOT NULL DEFAULT '[]',
                    interaction_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    article_id TEXT,
                    action TEXT NOT NULL,
                    query TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_articles_home_published
                ON articles(home_score DESC, published_at DESC);

                CREATE INDEX IF NOT EXISTS idx_user_interactions_article_id
                ON user_interactions(article_id);

                CREATE TABLE IF NOT EXISTS source_health (
                    source_name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    persisted_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_success_at TEXT,
                    last_error TEXT
                );

                CREATE TABLE IF NOT EXISTS source_health_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    request_id TEXT,
                    status TEXT NOT NULL,
                    fetched_count INTEGER NOT NULL DEFAULT 0,
                    persisted_count INTEGER NOT NULL DEFAULT 0,
                    error_count INTEGER NOT NULL DEFAULT 0,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    ran_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_source_health_runs_name_ran_at
                ON source_health_runs(source_name, ran_at DESC, id DESC);
                """
            )
            self._ensure_table_columns(
                connection,
                "articles",
                {
                    "entity_tags": "TEXT NOT NULL DEFAULT '[]'",
                    "event_metadata": "TEXT NOT NULL DEFAULT '{}'",
                    "semantic_embedding": "TEXT NOT NULL DEFAULT '[]'",
                    "semantic_embedding_signature": "TEXT NOT NULL DEFAULT ''",
                },
            )
            self._ensure_table_columns(
                connection,
                "user_profiles",
                {
                    "display_name": "TEXT",
                    "pinned_categories": "TEXT NOT NULL DEFAULT '[]'",
                    "pinned_tags": "TEXT NOT NULL DEFAULT '[]'",
                    "pinned_entities": "TEXT NOT NULL DEFAULT '[]'",
                    "pinned_regions": "TEXT NOT NULL DEFAULT '[]'",
                    "category_affinities": "TEXT NOT NULL DEFAULT '{}'",
                    "tag_affinities": "TEXT NOT NULL DEFAULT '{}'",
                    "entity_affinities": "TEXT NOT NULL DEFAULT '{}'",
                    "region_affinities": "TEXT NOT NULL DEFAULT '{}'",
                    "query_affinities": "TEXT NOT NULL DEFAULT '{}'",
                    "recent_queries": "TEXT NOT NULL DEFAULT '[]'",
                    "interaction_count": "INTEGER NOT NULL DEFAULT 0",
                    "updated_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                },
            )
            self._ensure_table_columns(
                connection,
                "source_health",
                {
                    "status": "TEXT NOT NULL DEFAULT 'error'",
                    "fetched_count": "INTEGER NOT NULL DEFAULT 0",
                    "persisted_count": "INTEGER NOT NULL DEFAULT 0",
                    "error_count": "INTEGER NOT NULL DEFAULT 0",
                    "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
                    "last_run_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                    "last_success_at": "TEXT",
                    "last_error": "TEXT",
                },
            )
            self._ensure_table_columns(
                connection,
                "source_health_runs",
                {
                    "request_id": "TEXT",
                    "status": "TEXT NOT NULL DEFAULT 'error'",
                    "fetched_count": "INTEGER NOT NULL DEFAULT 0",
                    "persisted_count": "INTEGER NOT NULL DEFAULT 0",
                    "error_count": "INTEGER NOT NULL DEFAULT 0",
                    "consecutive_failures": "INTEGER NOT NULL DEFAULT 0",
                    "last_error": "TEXT",
                    "ran_at": "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
                },
            )
            connection.commit()

    def _ensure_table_columns(self, connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
        existing = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        for column_name, definition in columns.items():
            if column_name not in existing:
                connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def count_articles(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM articles").fetchone()
        return int(row["count"])

    def count_source_health(self) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM source_health").fetchone()
        return int(row["count"])

    def upsert_articles(
        self,
        articles: list[ArticleRecord],
        semantic_embeddings: dict[str, EmbeddingRecord] | None = None,
    ) -> None:
        if not articles:
            return

        with self.connect() as connection:
            for article in articles:
                embedding = json.dumps(build_hash_embedding(article.combined_text()))
                semantic_embedding_record = semantic_embeddings.get(article.id) if semantic_embeddings else None
                semantic_embedding = json.dumps(semantic_embedding_record.vector if semantic_embedding_record else [])
                semantic_embedding_signature = semantic_embedding_record.signature if semantic_embedding_record else ""
                connection.execute(
                    """
                    INSERT INTO articles (
                        id, title, url, source_name, source_type, published_at, summary, content,
                        categories, tags, entity_tags, region_tags, sg_relevance, freshness_score, home_score,
                        source_quality, image_url, event_metadata, embedding, semantic_embedding,
                        semantic_embedding_signature, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(url) DO UPDATE SET
                        id = excluded.id,
                        title = excluded.title,
                        source_name = excluded.source_name,
                        source_type = excluded.source_type,
                        published_at = excluded.published_at,
                        summary = excluded.summary,
                        content = excluded.content,
                        categories = excluded.categories,
                        tags = excluded.tags,
                        entity_tags = excluded.entity_tags,
                        region_tags = excluded.region_tags,
                        sg_relevance = excluded.sg_relevance,
                        freshness_score = excluded.freshness_score,
                        home_score = excluded.home_score,
                        source_quality = excluded.source_quality,
                        image_url = excluded.image_url,
                        event_metadata = excluded.event_metadata,
                        embedding = excluded.embedding,
                        semantic_embedding = CASE
                            WHEN excluded.semantic_embedding_signature != '' THEN excluded.semantic_embedding
                            ELSE articles.semantic_embedding
                        END,
                        semantic_embedding_signature = CASE
                            WHEN excluded.semantic_embedding_signature != '' THEN excluded.semantic_embedding_signature
                            ELSE articles.semantic_embedding_signature
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        article.id,
                        article.title,
                        article.url,
                        article.source_name,
                        article.source_type,
                        article.published_at.isoformat(),
                        article.summary,
                        article.content,
                        json.dumps(article.categories),
                        json.dumps(article.tags),
                        json.dumps(article.entity_tags),
                        json.dumps(article.region_tags),
                        article.sg_relevance,
                        article.freshness_score,
                        article.home_score,
                        article.source_quality,
                        article.image_url,
                        json.dumps(article.event_metadata.model_dump() if article.event_metadata else {}),
                        embedding,
                        semantic_embedding,
                        semantic_embedding_signature,
                    ),
                )

                connection.execute("DELETE FROM articles_fts WHERE article_id = ?", (article.id,))
                connection.execute(
                    """
                    INSERT INTO articles_fts (article_id, title, summary, content, tags, source_name, region_tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        article.id,
                        article.title,
                        article.summary,
                        article.content,
                        " ".join(article.tags),
                        article.source_name,
                        " ".join(article.region_tags),
                    ),
                )
            connection.commit()

    def update_semantic_embeddings(self, semantic_embeddings: dict[str, EmbeddingRecord]) -> int:
        if not semantic_embeddings:
            return 0

        updated = 0
        with self.connect() as connection:
            for article_id, embedding_record in semantic_embeddings.items():
                cursor = connection.execute(
                    """
                    UPDATE articles
                    SET semantic_embedding = ?,
                        semantic_embedding_signature = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(embedding_record.vector), embedding_record.signature, article_id),
                )
                updated += int(cursor.rowcount or 0)
            connection.commit()
        return updated

    def prune_duplicate_articles(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM articles").fetchall()
            keepers: dict[str, ArticleRecord] = {}
            delete_ids: set[str] = set()
            interaction_remap: dict[str, str] = {}

            for row in rows:
                article = self._row_to_article(row)
                dedupe_key = article_dedupe_key(article)
                existing = keepers.get(dedupe_key)
                if existing is None:
                    keepers[dedupe_key] = article
                    continue

                if article_preference_signature(article) > article_preference_signature(existing):
                    delete_ids.add(existing.id)
                    interaction_remap[existing.id] = article.id
                    keepers[dedupe_key] = article
                else:
                    delete_ids.add(article.id)
                    interaction_remap[article.id] = existing.id

            if delete_ids:
                ordered_ids = sorted(delete_ids)
                placeholders = ", ".join("?" for _ in ordered_ids)
                self._remap_user_interactions(connection, self._collapse_article_remap(interaction_remap))
                connection.execute(f"DELETE FROM articles_fts WHERE article_id IN ({placeholders})", ordered_ids)
                connection.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", ordered_ids)
                self._delete_orphan_user_interactions(connection)
                connection.commit()

        return sorted(delete_ids)

    def cleanup_orphan_user_interactions(self) -> int:
        with self.connect() as connection:
            deleted = self._delete_orphan_user_interactions(connection)
            connection.commit()
        return deleted

    def prune_non_external_articles(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute("SELECT id, url FROM articles").fetchall()
            delete_ids = sorted(
                str(row["id"])
                for row in rows
                if not is_external_http_url(str(row["url"] or ""))
            )
            if not delete_ids:
                return []

            placeholders = ", ".join("?" for _ in delete_ids)
            connection.execute(f"DELETE FROM articles_fts WHERE article_id IN ({placeholders})", delete_ids)
            connection.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", delete_ids)
            self._delete_orphan_user_interactions(connection)
            connection.commit()

        return delete_ids

    def record_source_health(
        self,
        source_name: str,
        status: str,
        fetched_count: int,
        persisted_count: int,
        error_count: int,
        last_error: str | None = None,
        ran_at: datetime | None = None,
        request_id: str | None = None,
        retention_days: int | None = None,
    ) -> SourceHealthEntry:
        with self.connect() as connection:
            self._begin_immediate(connection)
            entry = self._upsert_source_health(
                connection,
                source_name=source_name,
                status=status,
                fetched_count=fetched_count,
                persisted_count=persisted_count,
                error_count=error_count,
                last_error=last_error,
                ran_at=ran_at,
                request_id=request_id,
            )
            self._prune_source_health_runs(connection, retention_days=retention_days)
            connection.commit()
        return entry

    def record_source_health_batch(self, entries: list[dict[str, object]], retention_days: int | None = None) -> None:
        if not entries:
            return

        with self.connect() as connection:
            self._begin_immediate(connection)
            for entry in entries:
                fetched_count_value = entry.get("fetched_count", 0)
                persisted_count_value = entry.get("persisted_count", 0)
                error_count_value = entry.get("error_count", 0)
                ran_at_value = entry.get("ran_at")
                request_id_value = entry.get("request_id")
                self._upsert_source_health(
                    connection,
                    source_name=str(entry["source_name"]),
                    status=str(entry["status"]),
                    fetched_count=self._coerce_int(fetched_count_value),
                    persisted_count=self._coerce_int(persisted_count_value),
                    error_count=self._coerce_int(error_count_value),
                    last_error=str(entry["last_error"]) if entry.get("last_error") is not None else None,
                    ran_at=ran_at_value if isinstance(ran_at_value, datetime) else None,
                    request_id=str(request_id_value) if request_id_value is not None else None,
                )
            self._prune_source_health_runs(connection, retention_days=retention_days)
            connection.commit()

    def bootstrap_source_health(self, entries: list[SourceHealthEntry], request_id: str | None = None) -> None:
        if not entries:
            return

        with self.connect() as connection:
            for entry in entries:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO source_health (
                        source_name,
                        status,
                        fetched_count,
                        persisted_count,
                        error_count,
                        consecutive_failures,
                        last_run_at,
                        last_success_at,
                        last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.source_name,
                        entry.status,
                        entry.fetched_count,
                        entry.persisted_count,
                        entry.error_count,
                        entry.consecutive_failures,
                        entry.last_run_at.astimezone(timezone.utc).isoformat(),
                        entry.last_success_at.astimezone(timezone.utc).isoformat() if entry.last_success_at else None,
                        entry.last_error,
                    ),
                )
                self._insert_source_health_run(
                    connection,
                    source_name=entry.source_name,
                    request_id=strip_text(request_id)[:128] if request_id else None,
                    status=entry.status,
                    fetched_count=entry.fetched_count,
                    persisted_count=entry.persisted_count,
                    error_count=entry.error_count,
                    consecutive_failures=entry.consecutive_failures,
                    last_error=entry.last_error,
                    ran_at=entry.last_run_at.astimezone(timezone.utc),
                )
            connection.commit()

    def replace_source_health_snapshot(self, entries: list[SourceHealthEntry], request_id: str | None = None) -> None:
        if not entries:
            return

        with self.connect() as connection:
            self._begin_immediate(connection)
            connection.execute("DELETE FROM source_health_runs")
            connection.execute("DELETE FROM source_health")
            for entry in entries:
                connection.execute(
                    """
                    INSERT INTO source_health (
                        source_name,
                        status,
                        fetched_count,
                        persisted_count,
                        error_count,
                        consecutive_failures,
                        last_run_at,
                        last_success_at,
                        last_error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.source_name,
                        entry.status,
                        entry.fetched_count,
                        entry.persisted_count,
                        entry.error_count,
                        entry.consecutive_failures,
                        entry.last_run_at.astimezone(timezone.utc).isoformat(),
                        entry.last_success_at.astimezone(timezone.utc).isoformat() if entry.last_success_at else None,
                        entry.last_error,
                    ),
                )
                self._insert_source_health_run(
                    connection,
                    source_name=entry.source_name,
                    request_id=strip_text(request_id)[:128] if request_id else None,
                    status=entry.status,
                    fetched_count=entry.fetched_count,
                    persisted_count=entry.persisted_count,
                    error_count=entry.error_count,
                    consecutive_failures=entry.consecutive_failures,
                    last_error=entry.last_error,
                    ran_at=entry.last_run_at.astimezone(timezone.utc),
                )
            connection.commit()

    def prune_source_health_sources(self, active_source_names: list[str]) -> tuple[int, int]:
        normalized_names = sorted(
            {
                normalized
                for name in active_source_names
                if (normalized := strip_text(name)[:160])
            }
        )

        with self.connect() as connection:
            self._begin_immediate(connection)
            if normalized_names:
                placeholders = ", ".join("?" for _ in normalized_names)
                delete_runs = connection.execute(
                    f"DELETE FROM source_health_runs WHERE source_name NOT IN ({placeholders})",
                    normalized_names,
                )
                delete_health = connection.execute(
                    f"DELETE FROM source_health WHERE source_name NOT IN ({placeholders})",
                    normalized_names,
                )
            else:
                delete_runs = connection.execute("DELETE FROM source_health_runs")
                delete_health = connection.execute("DELETE FROM source_health")
            connection.commit()

        return int(delete_health.rowcount or 0), int(delete_runs.rowcount or 0)

    def list_source_health(
        self,
        stale_after_hours: int,
        now: datetime | None = None,
    ) -> list[SourceHealthEntry]:
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM source_health ORDER BY source_name COLLATE NOCASE ASC"
            ).fetchall()
        return [
            self._row_to_source_health(row, now=current_time, stale_after_hours=stale_after_hours)
            for row in rows
        ]

    def list_source_health_runs(
        self,
        limit: int = 50,
        source_name: str | None = None,
    ) -> list[SourceHealthRunEntry]:
        bounded_limit = max(1, min(limit, 200))
        query = "SELECT * FROM source_health_runs"
        params: list[object] = []
        if source_name:
            query += " WHERE source_name = ?"
            params.append(strip_text(source_name)[:160])
        query += " ORDER BY ran_at DESC, id DESC LIMIT ?"
        params.append(bounded_limit)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_source_health_run(row) for row in rows]

    def list_source_health_rollups(
        self,
        window_hours: int = 24,
        limit: int = 10,
        now: datetime | None = None,
    ) -> list[SourceHealthRollupEntry]:
        bounded_hours = max(1, min(window_hours, 168))
        bounded_limit = max(1, min(limit, 50))
        current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        cutoff = (current_time - timedelta(hours=bounded_hours)).isoformat()

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    runs.source_name,
                    COUNT(*) AS total_runs,
                    SUM(CASE WHEN runs.status = 'ok' THEN 1 ELSE 0 END) AS healthy_runs,
                    SUM(CASE WHEN runs.status = 'error' THEN 1 ELSE 0 END) AS failing_runs,
                    MAX(runs.ran_at) AS latest_ran_at,
                    (
                        SELECT latest.status
                        FROM source_health_runs AS latest
                        WHERE latest.source_name = runs.source_name AND latest.ran_at >= ?
                        ORDER BY latest.ran_at DESC, latest.id DESC
                        LIMIT 1
                    ) AS latest_status,
                    (
                        SELECT latest.last_error
                        FROM source_health_runs AS latest
                        WHERE latest.source_name = runs.source_name AND latest.ran_at >= ?
                        ORDER BY latest.ran_at DESC, latest.id DESC
                        LIMIT 1
                    ) AS latest_error
                FROM source_health_runs AS runs
                WHERE runs.ran_at >= ?
                GROUP BY runs.source_name
                ORDER BY
                    CAST(SUM(CASE WHEN runs.status = 'error' THEN 1 ELSE 0 END) AS REAL) / COUNT(*) DESC,
                    MAX(runs.ran_at) DESC,
                    runs.source_name COLLATE NOCASE ASC
                LIMIT ?
                """,
                (cutoff, cutoff, cutoff, bounded_limit),
            ).fetchall()

            return [
                self._row_to_source_health_rollup(
                    row,
                    recent_statuses=self._list_recent_source_statuses(
                        connection,
                        source_name=str(row["source_name"]),
                        cutoff=cutoff,
                    ),
                )
                for row in rows
            ]

    def prune_source_health_runs(
        self,
        retention_days: int,
        now: datetime | None = None,
    ) -> int:
        with self.connect() as connection:
            self._begin_immediate(connection)
            deleted = self._prune_source_health_runs(connection, retention_days=retention_days, now=now)
            connection.commit()
        return deleted

    def refresh_article_entities(self) -> list[ArticleRecord]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM articles").fetchall()

        updated_articles: list[ArticleRecord] = []
        for row in rows:
            article = self._row_to_article(row)
            inferred_entities = infer_entity_tags(article.title, article.summary)
            if inferred_entities == article.entity_tags:
                continue
            updated_articles.append(article.model_copy(update={"entity_tags": inferred_entities}))

        if updated_articles:
            self.upsert_articles(updated_articles)
        return updated_articles

    def list_articles_missing_semantic_embeddings(self, expected_signature: str) -> list[ArticleRecord]:
        if not expected_signature:
            return []

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM articles
                WHERE semantic_embedding_signature != ?
                   OR semantic_embedding IS NULL
                   OR semantic_embedding = '[]'
                ORDER BY published_at DESC
                """,
                (expected_signature,),
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def latest_articles(self, limit: int, exclude_ids: set[str] | None = None) -> list[ArticleRecord]:
        query = """
            SELECT *
            FROM articles
        """
        params: list[object] = []
        conditions = [_external_url_sql("url")]
        if exclude_ids:
            placeholders = ", ".join("?" for _ in exclude_ids)
            conditions.append(f"id NOT IN ({placeholders})")
            params.extend(sorted(exclude_ids))
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY home_score DESC, published_at DESC LIMIT ?"
        params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_article(row) for row in rows]

    def list_articles_by_source_names(self, source_names: list[str]) -> list[ArticleRecord]:
        if not source_names:
            return []

        placeholders = ", ".join("?" for _ in source_names)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM articles WHERE source_name IN ({placeholders}) ORDER BY published_at DESC",
                source_names,
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def list_google_news_wrapper_articles(self) -> list[ArticleRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM articles
                WHERE source_name LIKE 'Google News%'
                  AND LOWER(url) LIKE 'https://news.google.com/%'
                ORDER BY published_at DESC
                """
            ).fetchall()
        return [self._row_to_article(row) for row in rows]

    def replace_articles(self, replacements: list[tuple[str, ArticleRecord]]) -> list[str]:
        normalized_replacements = [
            (str(old_id), article)
            for old_id, article in replacements
            if old_id and article.id and old_id != article.id
        ]
        if not normalized_replacements:
            return []

        self.upsert_articles([article for _, article in normalized_replacements])

        delete_ids = sorted({old_id for old_id, _ in normalized_replacements})
        interaction_remap = {old_id: article.id for old_id, article in normalized_replacements}
        placeholders = ", ".join("?" for _ in delete_ids)

        with self.connect() as connection:
            self._begin_immediate(connection)
            self._remap_user_interactions(connection, self._collapse_article_remap(interaction_remap))
            connection.execute(f"DELETE FROM articles_fts WHERE article_id IN ({placeholders})", delete_ids)
            connection.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", delete_ids)
            self._delete_orphan_user_interactions(connection)
            connection.commit()

        return delete_ids

    def delete_articles(self, article_ids: list[str]) -> None:
        if not article_ids:
            return

        ordered_ids = sorted(set(str(article_id) for article_id in article_ids if article_id))
        if not ordered_ids:
            return

        placeholders = ", ".join("?" for _ in ordered_ids)
        with self.connect() as connection:
            connection.execute(f"DELETE FROM articles_fts WHERE article_id IN ({placeholders})", ordered_ids)
            connection.execute(f"DELETE FROM articles WHERE id IN ({placeholders})", ordered_ids)
            self._delete_orphan_user_interactions(connection)
            connection.commit()

    def lexical_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT articles_fts.article_id, bm25(articles_fts, 4.0, 2.0, 1.0, 0.8, 0.3, 0.3) AS rank
                FROM articles_fts
                JOIN articles ON articles.id = articles_fts.article_id
                WHERE articles_fts MATCH ? AND """
                + _external_url_sql("articles.url")
                + """
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

        results: list[tuple[str, float]] = []
        for row in rows:
            rank = abs(float(row["rank"]))
            results.append((str(row["article_id"]), 1.0 / (1.0 + rank)))
        return results

    def vector_search(self, query: str, limit: int) -> list[tuple[str, float]]:
        return self.vector_search_with_candidates(query=query, limit=limit, candidate_ids=None)

    def vector_search_with_candidates(
        self,
        query: str,
        limit: int,
        candidate_ids: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        if limit <= 0:
            return []

        query_embedding = build_hash_embedding(query)
        with self.connect() as connection:
            if candidate_ids is None:
                rows = connection.execute(
                    f"SELECT id, embedding FROM articles WHERE {_external_url_sql('url')} ORDER BY home_score DESC, published_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                filtered_candidate_ids = list(dict.fromkeys(str(article_id) for article_id in candidate_ids if article_id))
                if not filtered_candidate_ids:
                    return []
                placeholders = ", ".join("?" for _ in filtered_candidate_ids)
                rows = connection.execute(
                    f"SELECT id, embedding FROM articles WHERE id IN ({placeholders}) AND {_external_url_sql('url')}",
                    filtered_candidate_ids,
                ).fetchall()

        scored: list[tuple[str, float]] = []
        for row in rows:
            embedding = json.loads(row["embedding"] or "[]")
            if not embedding:
                continue
            score = cosine_similarity(query_embedding, embedding)
            scored.append((str(row["id"]), max(score, 0.0)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def semantic_vector_search_with_candidates(
        self,
        query_embedding: list[float],
        embedding_signature: str,
        limit: int,
        candidate_ids: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        if limit <= 0 or not query_embedding or not embedding_signature:
            return []

        with self.connect() as connection:
            if candidate_ids is None:
                rows = connection.execute(
                    f"SELECT id, semantic_embedding FROM articles WHERE semantic_embedding_signature = ? AND {_external_url_sql('url')} ORDER BY home_score DESC, published_at DESC LIMIT ?",
                    (embedding_signature, limit),
                ).fetchall()
            else:
                filtered_candidate_ids = list(dict.fromkeys(str(article_id) for article_id in candidate_ids if article_id))
                if not filtered_candidate_ids:
                    return []
                placeholders = ", ".join("?" for _ in filtered_candidate_ids)
                rows = connection.execute(
                    f"SELECT id, semantic_embedding FROM articles WHERE id IN ({placeholders}) AND semantic_embedding_signature = ? AND {_external_url_sql('url')}",
                    [*filtered_candidate_ids, embedding_signature],
                ).fetchall()

        scored: list[tuple[str, float]] = []
        for row in rows:
            embedding = json.loads(row["semantic_embedding"] or "[]")
            if not embedding:
                continue
            score = cosine_similarity(query_embedding, embedding)
            scored.append((str(row["id"]), max(score, 0.0)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    def prefilter_vector_search_ids(self, limit: int, seeded_ids: list[str] | None = None) -> list[str]:
        if limit <= 0:
            return []

        selected_ids = list(dict.fromkeys(str(article_id) for article_id in (seeded_ids or []) if article_id))[:limit]
        remaining = limit - len(selected_ids)
        if remaining <= 0:
            return selected_ids

        query = "SELECT id FROM articles"
        params: list[object] = []
        conditions = [_external_url_sql("url")]
        if selected_ids:
            placeholders = ", ".join("?" for _ in selected_ids)
            conditions.append(f"id NOT IN ({placeholders})")
            params.extend(selected_ids)
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY home_score DESC, published_at DESC LIMIT ?"
        params.append(remaining)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()

        selected_ids.extend(str(row["id"]) for row in rows)
        return selected_ids

    def get_articles_by_ids(self, article_ids: list[str]) -> dict[str, ArticleRecord]:
        if not article_ids:
            return {}

        placeholders = ", ".join("?" for _ in article_ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM articles WHERE id IN ({placeholders}) AND {_external_url_sql('url')}",
                article_ids,
            ).fetchall()
        return {article.id: article for article in (self._row_to_article(row) for row in rows)}

    def get_or_create_user_profile(self, user_id: str, display_name: str | None = None) -> UserProfile:
        normalized_user_id = self._normalize_user_id(user_id)
        with self.connect() as connection:
            self._ensure_user_profile(connection, normalized_user_id, display_name)
            connection.commit()
            row = self._fetch_profile_row(connection, normalized_user_id)
        if row is None:
            raise ValueError("Unable to initialize user profile")
        return self._row_to_profile(row)

    def update_user_profile(
        self,
        user_id: str,
        display_name: str | None = None,
        pinned_categories: list[str] | None = None,
        pinned_tags: list[str] | None = None,
        pinned_entities: list[str] | None = None,
        pinned_regions: list[str] | None = None,
    ) -> UserProfile:
        normalized_user_id = self._normalize_user_id(user_id)
        with self.connect() as connection:
            self._begin_immediate(connection)
            self._ensure_user_profile(connection, normalized_user_id, display_name)
            row = self._fetch_profile_row(connection, normalized_user_id)
            if row is None:
                raise ValueError("Unable to load profile for update")
            profile = self._row_to_profile(row)
            connection.execute(
                """
                UPDATE user_profiles
                SET display_name = ?,
                    pinned_categories = ?,
                    pinned_tags = ?,
                    pinned_entities = ?,
                    pinned_regions = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (
                    strip_text(display_name)[:60] if display_name else profile.display_name,
                    json.dumps(self._normalize_list(pinned_categories if pinned_categories is not None else profile.pinned_categories)),
                    json.dumps(self._normalize_list(pinned_tags if pinned_tags is not None else profile.pinned_tags)),
                    json.dumps(self._normalize_list(pinned_entities if pinned_entities is not None else profile.pinned_entities)),
                    json.dumps(self._normalize_list(pinned_regions if pinned_regions is not None else profile.pinned_regions)),
                    normalized_user_id,
                ),
            )
            connection.commit()
            updated_row = self._fetch_profile_row(connection, normalized_user_id)
        if updated_row is None:
            raise ValueError("Unable to persist profile changes")
        return self._row_to_profile(updated_row)

    def record_search_query(self, user_id: str, query: str) -> UserProfile:
        normalized_user_id = self._normalize_user_id(user_id)
        cleaned_query = strip_text(query)[:200]
        with self.connect() as connection:
            self._begin_immediate(connection)
            self._ensure_user_profile(connection, normalized_user_id)
            row = self._fetch_profile_row(connection, normalized_user_id)
            if row is None:
                raise ValueError("Unable to load profile for search update")
            profile = self._row_to_profile(row)
            if not cleaned_query:
                connection.commit()
                return profile

            categories, tags, regions = infer_query_preferences(cleaned_query)
            entities = infer_entity_tags(cleaned_query, for_query=True)
            category_affinities = dict(profile.category_affinities)
            tag_affinities = dict(profile.tag_affinities)
            entity_affinities = dict(profile.entity_affinities)
            region_affinities = dict(profile.region_affinities)
            query_affinities = dict(profile.query_affinities)

            for category in categories:
                self._bump_affinity(category_affinities, category, SEARCH_WEIGHT)
            for tag in tags:
                self._bump_affinity(tag_affinities, tag, SEARCH_WEIGHT)
            for entity in entities:
                self._bump_affinity(entity_affinities, entity, SEARCH_WEIGHT)
            for region in regions:
                self._bump_affinity(region_affinities, region, SEARCH_WEIGHT)
            self._bump_affinity(query_affinities, cleaned_query.lower(), SEARCH_WEIGHT)
            recent_queries = self._update_recent_queries(profile.recent_queries, cleaned_query)

            connection.execute(
                "INSERT INTO user_interactions (user_id, action, query) VALUES (?, ?, ?)",
                (normalized_user_id, "search", cleaned_query),
            )
            self._persist_profile_state(
                connection,
                profile=profile,
                category_affinities=category_affinities,
                tag_affinities=tag_affinities,
                entity_affinities=entity_affinities,
                region_affinities=region_affinities,
                query_affinities=query_affinities,
                recent_queries=recent_queries,
                interaction_count=profile.interaction_count + 1,
            )
            connection.commit()
            updated_row = self._fetch_profile_row(connection, normalized_user_id)
        if updated_row is None:
            raise ValueError("Unable to persist search query")
        return self._row_to_profile(updated_row)

    def record_interaction(self, user_id: str, article_id: str, action: str) -> UserProfile:
        if action not in INTERACTION_WEIGHTS:
            raise ValueError(f"Unsupported interaction action: {action}")

        normalized_user_id = self._normalize_user_id(user_id)
        weight = INTERACTION_WEIGHTS[action]

        with self.connect() as connection:
            self._begin_immediate(connection)
            self._ensure_user_profile(connection, normalized_user_id)
            row = self._fetch_profile_row(connection, normalized_user_id)
            if row is None:
                raise ValueError("Unable to load profile for interaction update")
            profile = self._row_to_profile(row)

            article_row = connection.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
            if article_row is None:
                raise LookupError(f"Unknown article id: {article_id}")
            article = self._row_to_article(article_row)

            category_affinities = dict(profile.category_affinities)
            tag_affinities = dict(profile.tag_affinities)
            entity_affinities = dict(profile.entity_affinities)
            region_affinities = dict(profile.region_affinities)
            query_affinities = dict(profile.query_affinities)

            for category in article.categories:
                self._bump_affinity(category_affinities, category, weight)
            for tag in article.tags:
                self._bump_affinity(tag_affinities, tag, weight)
            for entity in article.entity_tags:
                self._bump_affinity(entity_affinities, entity, weight)
            for region in article.region_tags:
                self._bump_affinity(region_affinities, region, weight)
            if action == "like":
                self._bump_affinity(query_affinities, article.title.lower(), 0.22)

            connection.execute(
                "INSERT INTO user_interactions (user_id, article_id, action) VALUES (?, ?, ?)",
                (normalized_user_id, article_id, action),
            )
            self._persist_profile_state(
                connection,
                profile=profile,
                category_affinities=category_affinities,
                tag_affinities=tag_affinities,
                entity_affinities=entity_affinities,
                region_affinities=region_affinities,
                query_affinities=query_affinities,
                recent_queries=profile.recent_queries,
                interaction_count=profile.interaction_count + 1,
            )
            connection.commit()
            updated_row = self._fetch_profile_row(connection, normalized_user_id)
        if updated_row is None:
            raise ValueError("Unable to persist interaction")
        return self._row_to_profile(updated_row)

    def get_hidden_article_ids(self, user_id: str, limit: int = 200) -> set[str]:
        normalized_user_id = self._normalize_user_id(user_id)
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT article_id
                FROM user_interactions
                WHERE user_id = ? AND action = 'dismiss' AND article_id IS NOT NULL
                GROUP BY article_id
                ORDER BY MAX(id) DESC
                LIMIT ?
                """,
                (normalized_user_id, limit),
            ).fetchall()
        return {str(row["article_id"]) for row in rows if row["article_id"]}

    def _ensure_user_profile(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        display_name: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO user_profiles (user_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = COALESCE(excluded.display_name, user_profiles.display_name)
            """,
            (user_id, strip_text(display_name)[:60] if display_name else None),
        )

    def _fetch_profile_row(self, connection: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    def _begin_immediate(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    def _upsert_source_health(
        self,
        connection: sqlite3.Connection,
        source_name: str,
        status: str,
        fetched_count: int,
        persisted_count: int,
        error_count: int,
        last_error: str | None,
        ran_at: datetime | None,
        request_id: str | None,
    ) -> SourceHealthEntry:
        normalized_name = strip_text(source_name)[:160]
        if not normalized_name:
            raise ValueError("Source name is required for source health tracking")
        if status not in {"ok", "error"}:
            raise ValueError(f"Unsupported source health status: {status}")

        run_at = (ran_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        existing = connection.execute(
            "SELECT last_success_at, consecutive_failures FROM source_health WHERE source_name = ?",
            (normalized_name,),
        ).fetchone()
        previous_last_success = str(existing["last_success_at"]) if existing and existing["last_success_at"] else None
        consecutive_failures = 0 if status == "ok" else int(existing["consecutive_failures"] or 0) + 1 if existing else 1
        stored_last_success = run_at.isoformat() if status == "ok" else previous_last_success
        stored_last_error = None if status == "ok" else (strip_text(last_error or "")[:500] or None)

        connection.execute(
            """
            INSERT INTO source_health (
                source_name,
                status,
                fetched_count,
                persisted_count,
                error_count,
                consecutive_failures,
                last_run_at,
                last_success_at,
                last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_name) DO UPDATE SET
                status = excluded.status,
                fetched_count = excluded.fetched_count,
                persisted_count = excluded.persisted_count,
                error_count = excluded.error_count,
                consecutive_failures = excluded.consecutive_failures,
                last_run_at = excluded.last_run_at,
                last_success_at = excluded.last_success_at,
                last_error = excluded.last_error
            """,
            (
                normalized_name,
                status,
                max(fetched_count, 0),
                max(persisted_count, 0),
                max(error_count, 0),
                max(consecutive_failures, 0),
                run_at.isoformat(),
                stored_last_success,
                stored_last_error,
            ),
        )
        row = connection.execute(
            "SELECT * FROM source_health WHERE source_name = ?",
            (normalized_name,),
        ).fetchone()
        if row is None:
            raise ValueError("Unable to persist source health entry")
        self._insert_source_health_run(
            connection,
            source_name=normalized_name,
            request_id=strip_text(request_id)[:128] if request_id else None,
            status=status,
            fetched_count=max(fetched_count, 0),
            persisted_count=max(persisted_count, 0),
            error_count=max(error_count, 0),
            consecutive_failures=max(consecutive_failures, 0),
            last_error=stored_last_error,
            ran_at=run_at,
        )
        return self._row_to_source_health(row, now=run_at, stale_after_hours=24)

    def _insert_source_health_run(
        self,
        connection: sqlite3.Connection,
        source_name: str,
        request_id: str | None,
        status: str,
        fetched_count: int,
        persisted_count: int,
        error_count: int,
        consecutive_failures: int,
        last_error: str | None,
        ran_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO source_health_runs (
                source_name,
                request_id,
                status,
                fetched_count,
                persisted_count,
                error_count,
                consecutive_failures,
                last_error,
                ran_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_name,
                request_id,
                status,
                fetched_count,
                persisted_count,
                error_count,
                consecutive_failures,
                last_error,
                ran_at.isoformat(),
            ),
        )

    def _prune_source_health_runs(
        self,
        connection: sqlite3.Connection,
        retention_days: int | None,
        now: datetime | None = None,
    ) -> int:
        if retention_days is None or retention_days <= 0:
            return 0

        cutoff = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(days=max(retention_days, 1))).isoformat()
        cursor = connection.execute(
            "DELETE FROM source_health_runs WHERE ran_at < ?",
            (cutoff,),
        )
        return int(cursor.rowcount or 0)

    def _collapse_article_remap(self, interaction_remap: dict[str, str]) -> dict[str, str]:
        collapsed: dict[str, str] = {}
        for source_id, target_id in interaction_remap.items():
            resolved_target = target_id
            seen = {source_id}
            while resolved_target in interaction_remap and resolved_target not in seen:
                seen.add(resolved_target)
                resolved_target = interaction_remap[resolved_target]
            if resolved_target != source_id:
                collapsed[source_id] = resolved_target
        return collapsed

    def _remap_user_interactions(self, connection: sqlite3.Connection, interaction_remap: dict[str, str]) -> None:
        for source_id, target_id in interaction_remap.items():
            connection.execute(
                "UPDATE user_interactions SET article_id = ? WHERE article_id = ?",
                (target_id, source_id),
            )

    def _delete_orphan_user_interactions(self, connection: sqlite3.Connection) -> int:
        cursor = connection.execute(
            """
            DELETE FROM user_interactions
            WHERE article_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM articles
                  WHERE articles.id = user_interactions.article_id
              )
            """
        )
        return int(cursor.rowcount or 0)

    def _persist_profile_state(
        self,
        connection: sqlite3.Connection,
        profile: UserProfile,
        category_affinities: dict[str, float],
        tag_affinities: dict[str, float],
        entity_affinities: dict[str, float],
        region_affinities: dict[str, float],
        query_affinities: dict[str, float],
        recent_queries: list[str],
        interaction_count: int,
    ) -> None:
        connection.execute(
            """
            UPDATE user_profiles
            SET display_name = ?,
                pinned_categories = ?,
                pinned_tags = ?,
                pinned_entities = ?,
                pinned_regions = ?,
                category_affinities = ?,
                tag_affinities = ?,
                entity_affinities = ?,
                region_affinities = ?,
                query_affinities = ?,
                recent_queries = ?,
                interaction_count = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            """,
            (
                profile.display_name,
                json.dumps(self._normalize_list(profile.pinned_categories)),
                json.dumps(self._normalize_list(profile.pinned_tags)),
                json.dumps(self._normalize_list(profile.pinned_entities)),
                json.dumps(self._normalize_list(profile.pinned_regions)),
                json.dumps(self._normalize_affinity_map(category_affinities)),
                json.dumps(self._normalize_affinity_map(tag_affinities)),
                json.dumps(self._normalize_affinity_map(entity_affinities)),
                json.dumps(self._normalize_affinity_map(region_affinities)),
                json.dumps(self._normalize_affinity_map(query_affinities)),
                json.dumps([strip_text(value) for value in recent_queries if strip_text(value)][:MAX_RECENT_QUERIES]),
                interaction_count,
                profile.user_id,
            ),
        )

    def _row_to_profile(self, row: sqlite3.Row) -> UserProfile:
        category_affinities = self._normalize_affinity_map(json.loads(row["category_affinities"] or "{}"))
        tag_affinities = self._normalize_affinity_map(json.loads(row["tag_affinities"] or "{}"))
        entity_affinities = self._normalize_affinity_map(json.loads(row["entity_affinities"] or "{}"))
        region_affinities = self._normalize_affinity_map(json.loads(row["region_affinities"] or "{}"))
        query_affinities = self._normalize_affinity_map(json.loads(row["query_affinities"] or "{}"))

        return UserProfile(
            user_id=str(row["user_id"]),
            display_name=row["display_name"],
            pinned_categories=self._normalize_list(json.loads(row["pinned_categories"] or "[]")),
            pinned_tags=self._normalize_list(json.loads(row["pinned_tags"] or "[]")),
            pinned_entities=self._display_entities(json.loads(row["pinned_entities"] or "[]")),
            pinned_regions=self._normalize_list(json.loads(row["pinned_regions"] or "[]")),
            top_categories=self._top_positive_keys(category_affinities),
            top_tags=self._top_positive_keys(tag_affinities),
            top_entities=self._top_positive_entities(entity_affinities),
            top_regions=self._top_positive_keys(region_affinities),
            recent_queries=[strip_text(value) for value in json.loads(row["recent_queries"] or "[]") if strip_text(value)],
            interaction_count=int(row["interaction_count"] or 0),
            category_affinities=category_affinities,
            tag_affinities=tag_affinities,
            entity_affinities=entity_affinities,
            region_affinities=region_affinities,
            query_affinities=query_affinities,
            updated_at=self._parse_datetime(str(row["updated_at"])),
        )

    def _normalize_user_id(self, user_id: str) -> str:
        return strip_text(user_id).lower()[:64]

    def _normalize_list(self, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = strip_text(value).lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized

    def _normalize_affinity_map(self, values: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        for key, raw_value in values.items():
            normalized_key = strip_text(str(key)).lower()
            if not normalized_key:
                continue
            bounded = max(min(float(raw_value), MAX_AFFINITY), MIN_AFFINITY)
            if abs(bounded) < 0.05:
                continue
            cleaned[normalized_key] = round(bounded, 3)
        return cleaned

    def _coerce_int(self, value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float, str)):
            return int(value)
        return 0

    def _bump_affinity(self, affinity_map: dict[str, float], key: str, delta: float) -> None:
        normalized_key = strip_text(key).lower()
        if not normalized_key:
            return
        affinity_map[normalized_key] = affinity_map.get(normalized_key, 0.0) + delta

    def _update_recent_queries(self, existing_queries: list[str], query: str) -> list[str]:
        cleaned_query = strip_text(query)
        deduped = [cleaned_query]
        deduped.extend(value for value in existing_queries if value.lower() != cleaned_query.lower())
        return deduped[:MAX_RECENT_QUERIES]

    def _top_positive_keys(self, affinity_map: dict[str, float], limit: int = 4) -> list[str]:
        return [
            key
            for key, score in sorted(affinity_map.items(), key=lambda item: item[1], reverse=True)
            if score > 0.15
        ][:limit]

    def _top_positive_entities(self, affinity_map: dict[str, float], limit: int = 4) -> list[str]:
        return [
            display_entity_name(key)
            for key, score in sorted(affinity_map.items(), key=lambda item: item[1], reverse=True)
            if score > 0.15
        ][:limit]

    def _display_entities(self, values: list[str]) -> list[str]:
        return [display_entity_name(value) for value in self._normalize_list(values)]

    def _parse_datetime(self, value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _row_to_source_health(
        self,
        row: sqlite3.Row,
        now: datetime,
        stale_after_hours: int,
    ) -> SourceHealthEntry:
        last_run_at = self._parse_datetime(str(row["last_run_at"]))
        last_success_at = self._parse_datetime(str(row["last_success_at"])) if row["last_success_at"] else None
        stale_anchor = last_success_at or last_run_at
        stale = (now - stale_anchor).total_seconds() >= max(stale_after_hours, 1) * 3600
        status = str(row["status"])
        if status not in {"ok", "error"}:
            status = "error"
        return SourceHealthEntry(
            source_name=str(row["source_name"]),
            status=cast(Literal["ok", "error"], status),
            fetched_count=int(row["fetched_count"] or 0),
            persisted_count=int(row["persisted_count"] or 0),
            error_count=int(row["error_count"] or 0),
            consecutive_failures=int(row["consecutive_failures"] or 0),
            last_run_at=last_run_at,
            last_success_at=last_success_at,
            last_error=str(row["last_error"]) if row["last_error"] else None,
            stale=stale,
        )

    def _row_to_source_health_run(self, row: sqlite3.Row) -> SourceHealthRunEntry:
        status = str(row["status"])
        if status not in {"ok", "error"}:
            status = "error"
        return SourceHealthRunEntry(
            id=int(row["id"] or 0),
            source_name=str(row["source_name"]),
            request_id=str(row["request_id"]) if row["request_id"] else None,
            status=cast(Literal["ok", "error"], status),
            fetched_count=int(row["fetched_count"] or 0),
            persisted_count=int(row["persisted_count"] or 0),
            error_count=int(row["error_count"] or 0),
            consecutive_failures=int(row["consecutive_failures"] or 0),
            last_error=str(row["last_error"]) if row["last_error"] else None,
            ran_at=self._parse_datetime(str(row["ran_at"])),
        )

    def _list_recent_source_statuses(
        self,
        connection: sqlite3.Connection,
        source_name: str,
        cutoff: str,
        limit: int = 8,
    ) -> list[Literal["ok", "error"]]:
        rows = connection.execute(
            """
            SELECT status
            FROM source_health_runs
            WHERE source_name = ? AND ran_at >= ?
            ORDER BY ran_at DESC, id DESC
            LIMIT ?
            """,
            (source_name, cutoff, limit),
        ).fetchall()

        statuses: list[Literal["ok", "error"]] = []
        for row in rows:
            status = str(row["status"])
            if status not in {"ok", "error"}:
                continue
            statuses.append(cast(Literal["ok", "error"], status))
        return statuses

    def _row_to_source_health_rollup(
        self,
        row: sqlite3.Row,
        recent_statuses: list[Literal["ok", "error"]],
    ) -> SourceHealthRollupEntry:
        latest_status = str(row["latest_status"])
        if latest_status not in {"ok", "error"}:
            latest_status = "error"
        total_runs = int(row["total_runs"] or 0)
        failing_runs = int(row["failing_runs"] or 0)
        healthy_runs = int(row["healthy_runs"] or 0)
        failure_rate = 0.0 if total_runs <= 0 else round(failing_runs / total_runs, 3)
        return SourceHealthRollupEntry(
            source_name=str(row["source_name"]),
            total_runs=total_runs,
            healthy_runs=healthy_runs,
            failing_runs=failing_runs,
            failure_rate=failure_rate,
            recent_statuses=recent_statuses,
            latest_status=cast(Literal["ok", "error"], latest_status),
            latest_ran_at=self._parse_datetime(str(row["latest_ran_at"])),
            latest_error=str(row["latest_error"]) if row["latest_error"] else None,
        )

    def _row_to_article(self, row: sqlite3.Row) -> ArticleRecord:
        published_at = datetime.fromisoformat(str(row["published_at"]))
        stored_event_metadata = coerce_event_metadata(json.loads(row["event_metadata"] or "{}"))
        inferred_event_metadata = infer_event_metadata(
            title=str(row["title"]),
            summary=str(row["summary"]),
            content=str(row["content"]),
            source_type=str(row["source_type"]),
            published_at=published_at,
            url=str(row["url"]),
            source_name=str(row["source_name"]),
        )
        return ArticleRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            url=str(row["url"]),
            source_name=str(row["source_name"]),
            source_type=str(row["source_type"]),
            published_at=published_at,
            summary=str(row["summary"]),
            content=str(row["content"]),
            categories=json.loads(row["categories"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            entity_tags=json.loads(row["entity_tags"] or "[]"),
            region_tags=json.loads(row["region_tags"] or "[]"),
            sg_relevance=float(row["sg_relevance"]),
            freshness_score=float(row["freshness_score"]),
            home_score=float(row["home_score"]),
            source_quality=float(row["source_quality"]),
            image_url=row["image_url"],
            event_metadata=merge_event_metadata(stored_event_metadata, inferred_event_metadata),
        )
