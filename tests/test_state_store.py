from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import app.services.state_store as state_store_module
from app.services.state_store import SqliteSnapshotStateStore


class FakeCursor:
    def __init__(self, storage: dict[str, dict[str, object]]) -> None:
        self.storage = storage
        self._row = None

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        normalized = " ".join(query.split())
        if normalized.startswith("CREATE TABLE IF NOT EXISTS app_state_snapshots"):
            self._row = None
            return

        if normalized.startswith("SELECT payload, checksum FROM app_state_snapshots"):
            snapshot_key = params[0]
            row = self.storage.get(snapshot_key)
            self._row = None if row is None else (memoryview(row["payload"]), row["checksum"])
            return

        if normalized.startswith("SELECT checksum FROM app_state_snapshots"):
            snapshot_key = params[0]
            row = self.storage.get(snapshot_key)
            self._row = None if row is None else (row["checksum"],)
            return

        if normalized.startswith("INSERT INTO app_state_snapshots"):
            snapshot_key, payload, checksum, size_bytes = params
            self.storage[snapshot_key] = {
                "payload": bytes(payload),
                "checksum": checksum,
                "size_bytes": size_bytes,
            }
            self._row = None
            return

        raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        return self._row

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeConnection:
    def __init__(self, storage: dict[str, dict[str, object]]) -> None:
        self.storage = storage

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.storage)

    def commit(self) -> None:
        return None

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakePsycopg:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, object]] = {}
        self.connect_calls: list[tuple[str, int]] = []

    def connect(self, database_url: str, connect_timeout: int) -> FakeConnection:
        self.connect_calls.append((database_url, connect_timeout))
        return FakeConnection(self.storage)


class SqliteSnapshotStateStoreTests(unittest.TestCase):
    def test_persist_from_skips_unchanged_payload(self) -> None:
        fake_psycopg = FakePsycopg()
        store = SqliteSnapshotStateStore(
            database_url="postgresql://example.com/acg-search",
            snapshot_key="acg-search-runtime",
            connect_timeout_seconds=5,
        )

        with TemporaryDirectory() as temp_dir, patch.object(state_store_module, "psycopg", fake_psycopg):
            db_path = Path(temp_dir) / "articles.db"
            db_path.write_bytes(b"seed-data")

            self.assertTrue(store.persist_from(db_path))
            self.assertFalse(store.persist_from(db_path))

            db_path.write_bytes(b"updated-data")
            self.assertTrue(store.persist_from(db_path))

        self.assertEqual(fake_psycopg.storage["acg-search-runtime"]["payload"], b"updated-data")
        self.assertTrue(all(call == ("postgresql://example.com/acg-search", 5) for call in fake_psycopg.connect_calls))

    def test_restore_to_writes_snapshot_bytes(self) -> None:
        fake_psycopg = FakePsycopg()
        fake_psycopg.storage["acg-search-runtime"] = {
            "payload": b"restored-data",
            "checksum": "checksum",
            "size_bytes": len(b"restored-data"),
        }
        store = SqliteSnapshotStateStore(
            database_url="postgresql://example.com/acg-search",
            snapshot_key="acg-search-runtime",
            connect_timeout_seconds=5,
        )

        with TemporaryDirectory() as temp_dir, patch.object(state_store_module, "psycopg", fake_psycopg):
            db_path = Path(temp_dir) / "nested" / "articles.db"

            self.assertTrue(store.restore_to(db_path))
            self.assertEqual(db_path.read_bytes(), b"restored-data")


if __name__ == "__main__":
    unittest.main()