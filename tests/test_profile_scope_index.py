from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from brainstack.db import BrainstackStore


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_profile_scope_index_returns_exact_principal_without_like_fallback_for_1000_principals(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        for index in range(1000):
            scope_key = f"principal:{index:04d}"
            store.upsert_profile_item(
                stable_key="style.reply_tone",
                category="style_preference",
                content=f"Style contract for {scope_key}",
                source="user_explicit",
                confidence=0.9,
                metadata={
                    "principal_scope_key": scope_key,
                    "memory_write_receipt_id": f"receipt:{index:04d}",
                },
            )

        store.reset_profile_scope_lookup_diagnostics()
        item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:0777")
        diagnostics = store.profile_scope_lookup_diagnostics()
        plan = store.conn.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT id
            FROM profile_items
            WHERE active = 1 AND logical_stable_key = ? AND principal_scope_key = ?
            ORDER BY confidence DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            ("style.reply_tone", "principal:0777"),
        ).fetchall()
        plan_text = " ".join(str(column) for row in plan for column in tuple(row))

        assert item is not None
        assert item["content"] == "Style contract for principal:0777"
        assert item["metadata"]["memory_write_receipt_id"] == "receipt:0777"
        assert item["profile_scope_lookup"]["path"] == "indexed"
        assert diagnostics["indexed_lookup_count"] == 1
        assert diagnostics["exact_storage_fallback_count"] == 0
        assert diagnostics["like_fallback_count"] == 0
        assert "idx_profile_scope_lookup" in plan_text
    finally:
        store.close()


def test_profile_scope_index_backfill_preserves_legacy_receipt_metadata_without_fallback(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        now = "2026-05-05T00:00:00Z"
        metadata = {
            "memory_write_receipt_id": "receipt:legacy",
            "provenance": {"source_ids": ["legacy:test"]},
        }
        store.conn.execute(
            """
            INSERT INTO profile_items (
                stable_key, logical_stable_key, principal_scope_key, category, content, source,
                confidence, metadata_json, first_seen_at, updated_at, active
            ) VALUES (?, '', '', ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "style.reply_tone::principal_scope::principal:legacy",
                "style_preference",
                "Legacy scoped style.",
                "user_explicit",
                0.95,
                json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                now,
                now,
            ),
        )
        store.conn.commit()

        updated = store._backfill_profile_scope_index_columns()
        store.conn.commit()
        store.reset_profile_scope_lookup_diagnostics()
        item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:legacy")
        diagnostics = store.profile_scope_lookup_diagnostics()

        assert updated == 1
        assert item is not None
        assert item["content"] == "Legacy scoped style."
        assert item["storage_key"] == "style.reply_tone::principal_scope::principal:legacy"
        assert item["stable_key"] == "style.reply_tone"
        assert item["principal_scope_key"] == "principal:legacy"
        assert item["metadata"]["memory_write_receipt_id"] == "receipt:legacy"
        assert item["metadata"]["provenance"]["source_ids"] == ["legacy:test"]
        assert item["profile_scope_lookup"]["path"] == "indexed"
        assert diagnostics["like_fallback_count"] == 0
        assert diagnostics["exact_storage_fallback_count"] == 0
    finally:
        store.close()


def test_profile_scope_index_migration_opens_legacy_profile_table_without_scope_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy-profile-scope.sqlite3"
    now = "2026-05-05T00:00:00Z"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE profile_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stable_key TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    conn.execute(
        """
        INSERT INTO profile_items (
            stable_key, category, content, source, confidence,
            metadata_json, first_seen_at, updated_at, active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            "style.reply_tone::principal_scope::principal:legacy-upgrade",
            "style_preference",
            "Legacy upgrade style.",
            "user_explicit",
            0.91,
            json.dumps({"memory_write_receipt_id": "receipt:legacy-upgrade"}, ensure_ascii=True, sort_keys=True),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    store = BrainstackStore(str(db_path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        columns = {str(row["name"] or "") for row in store.conn.execute("PRAGMA table_info(profile_items)").fetchall()}
        indexes = {str(row["name"] or "") for row in store.conn.execute("PRAGMA index_list(profile_items)").fetchall()}
        item = store.get_profile_item(stable_key="style.reply_tone", principal_scope_key="principal:legacy-upgrade")

        assert {"logical_stable_key", "principal_scope_key"}.issubset(columns)
        assert {"idx_profile_scope_lookup", "idx_profile_scope_list"}.issubset(indexes)
        assert item is not None
        assert item["content"] == "Legacy upgrade style."
        assert item["profile_scope_lookup"]["path"] == "indexed"
    finally:
        store.close()
