from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore


def _open_store(db_path: Path) -> BrainstackStore:
    store = BrainstackStore(db_path=str(db_path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _schema_snapshot(store: BrainstackStore) -> list[tuple[str, str]]:
    rows = store.conn.execute(
        """
        SELECT type, name
        FROM sqlite_master
        WHERE type IN ('table', 'index')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [(str(row["type"]), str(row["name"])) for row in rows]


def _migration_snapshot(store: BrainstackStore) -> list[str]:
    rows = store.conn.execute("SELECT name FROM applied_migrations ORDER BY name").fetchall()
    return [str(row["name"]) for row in rows]


def test_schema_initialization_seam_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstack.sqlite3"

    first = _open_store(db_path)
    try:
        schema_1 = _schema_snapshot(first)
        migrations_1 = _migration_snapshot(first)
    finally:
        first.close()

    second = _open_store(db_path)
    try:
        schema_2 = _schema_snapshot(second)
        migrations_2 = _migration_snapshot(second)
    finally:
        second.close()

    assert schema_1 == schema_2
    assert migrations_1 == migrations_2
    assert ("table", "applied_migrations") in schema_2
    assert ("index", "idx_semantic_evidence_scope_shelf") in schema_2
