from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.config import Settings


try:
    import psycopg
except ImportError:  # pragma: no cover - only relevant when the optional dependency is missing.
    psycopg = None


logger = logging.getLogger(__name__)


class SqliteSnapshotStateStore:
    def __init__(self, database_url: str, snapshot_key: str, connect_timeout_seconds: int = 10) -> None:
        self.database_url = database_url
        self.snapshot_key = snapshot_key
        self.connect_timeout_seconds = connect_timeout_seconds

    def _connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is configured.")
        return psycopg.connect(self.database_url, connect_timeout=self.connect_timeout_seconds)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_state_snapshots (
                        snapshot_key TEXT PRIMARY KEY,
                        payload BYTEA NOT NULL,
                        checksum TEXT NOT NULL,
                        size_bytes BIGINT NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            connection.commit()

    def restore_to(self, db_path: Path) -> bool:
        self.ensure_schema()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload, checksum FROM app_state_snapshots WHERE snapshot_key = %s",
                    (self.snapshot_key,),
                )
                row = cursor.fetchone()

        if row is None:
            return False

        payload = row[0]
        payload_bytes = payload.tobytes() if isinstance(payload, memoryview) else bytes(payload)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(payload_bytes)
        logger.info("Restored SQLite snapshot from durable store: key=%s size_bytes=%s", self.snapshot_key, len(payload_bytes))
        return True

    def persist_from(self, db_path: Path) -> bool:
        if not db_path.exists():
            logger.warning("Skipped durable state persistence because SQLite database was missing: %s", db_path)
            return False

        payload = db_path.read_bytes()
        checksum = hashlib.sha256(payload).hexdigest()
        size_bytes = len(payload)

        self.ensure_schema()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT checksum FROM app_state_snapshots WHERE snapshot_key = %s",
                    (self.snapshot_key,),
                )
                current = cursor.fetchone()
                if current is not None and current[0] == checksum:
                    connection.commit()
                    return False

                cursor.execute(
                    """
                    INSERT INTO app_state_snapshots (snapshot_key, payload, checksum, size_bytes)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (snapshot_key) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        checksum = EXCLUDED.checksum,
                        size_bytes = EXCLUDED.size_bytes,
                        updated_at = NOW()
                    """,
                    (self.snapshot_key, payload, checksum, size_bytes),
                )
            connection.commit()

        logger.info("Persisted SQLite snapshot to durable store: key=%s size_bytes=%s", self.snapshot_key, size_bytes)
        return True


def build_state_store(settings: Settings) -> SqliteSnapshotStateStore | None:
    if not settings.database_url:
        return None
    return SqliteSnapshotStateStore(
        database_url=settings.database_url,
        snapshot_key=settings.state_snapshot_key,
        connect_timeout_seconds=settings.state_store_connect_timeout_seconds,
    )