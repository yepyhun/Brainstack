from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.tool_schemas import build_tool_schemas


PRINCIPAL_SCOPE = "principal:graph-conflict-lifecycle"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _make_conflict(store: BrainstackStore) -> int:
    first = store.upsert_graph_state(
        subject_name="Release Train",
        attribute="status",
        value_text="green",
        source="user:release-manager",
        metadata={"principal_scope_key": PRINCIPAL_SCOPE},
    )
    assert first["status"] == "inserted"
    conflict = store.upsert_graph_state(
        subject_name="Release Train",
        attribute="status",
        value_text="red",
        source="user:release-manager",
        metadata={"principal_scope_key": PRINCIPAL_SCOPE},
    )
    assert conflict["status"] == "conflict"
    return int(conflict["conflict_id"])


def test_unresolved_conflict_visible_but_not_promoted_as_current_replacement(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        conflicts = store.list_graph_conflicts(limit=10)

        assert [int(row["id"]) for row in conflicts] == [conflict_id]
        assert conflicts[0]["candidate_value_text"] == "red"
        assert conflicts[0]["current_value"] == "green"

        current = store.conn.execute(
            "SELECT value_text FROM graph_states WHERE attribute = 'status' AND is_current = 1"
        ).fetchone()
        assert current is not None
        assert current["value_text"] == "green"

        report = build_query_inspect(
            store,
            query="Release Train red status",
            session_id="session:conflict-lifecycle",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )
        conflict_rows = [
            row for row in report["selected_evidence"]["graph"] if row.get("row_type") == "conflict"
        ]
        assert conflict_rows
        assert conflict_rows[0]["fact_class"] == "conflict"
    finally:
        store.close()


def test_accept_current_closes_conflict_and_writes_resolution_ledger(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        result = store.resolve_graph_conflict(
            conflict_id=conflict_id,
            decision="accept_current",
            approved_by="operator:test",
            reason="Current release state remains authoritative.",
            evidence_refs=["evidence:current"],
        )

        assert result["status"] == "resolved"
        assert result["new_status"] == "accepted_current"
        assert store.list_graph_conflicts(limit=10) == []

        closed = store.list_graph_conflicts(limit=10, include_closed=True)
        assert closed[0]["status"] == "accepted_current"
        resolutions = store.list_graph_conflict_resolutions(conflict_id=conflict_id, limit=10)
        assert len(resolutions) == 1
        assert resolutions[0]["decision"] == "accept_current"
        assert resolutions[0]["evidence_refs"] == ["evidence:current"]

        current = store.conn.execute(
            "SELECT value_text FROM graph_states WHERE attribute = 'status' AND is_current = 1"
        ).fetchone()
        assert current is not None
        assert current["value_text"] == "green"
    finally:
        store.close()


def test_accept_candidate_uses_normal_supersession_path(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        result = store.resolve_graph_conflict(
            conflict_id=conflict_id,
            decision="accept_candidate",
            approved_by="operator:test",
            reason="Candidate is confirmed by operator evidence.",
        )

        assert result["new_status"] == "accepted_candidate"
        assert result["state_id"] > 0

        current = store.conn.execute(
            "SELECT id, value_text, is_current FROM graph_states WHERE attribute = 'status' AND is_current = 1"
        ).fetchone()
        assert current is not None
        assert current["value_text"] == "red"
        supersession = store.conn.execute(
            """
            SELECT prior_state_id, new_state_id
            FROM graph_supersessions
            WHERE new_state_id = ?
            """,
            (int(current["id"]),),
        ).fetchone()
        assert supersession is not None
    finally:
        store.close()


def test_quarantine_candidate_closes_conflict_without_promoting_candidate(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        result = store.resolve_graph_conflict(
            conflict_id=conflict_id,
            decision="quarantine_candidate",
            approved_by="operator:test",
            reason="Candidate lacks enough authority.",
        )

        assert result["new_status"] == "quarantined_candidate"
        assert result["state_id"] == 0
        assert store.list_graph_conflicts(limit=10) == []
        current = store.conn.execute(
            "SELECT value_text FROM graph_states WHERE attribute = 'status' AND is_current = 1"
        ).fetchone()
        assert current is not None
        assert current["value_text"] == "green"
    finally:
        store.close()


def test_supersede_with_new_value_requires_and_applies_operator_value(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        with pytest.raises(ValueError, match="new_value_text"):
            store.resolve_graph_conflict(
                conflict_id=conflict_id,
                decision="supersede_with_new_value",
                approved_by="operator:test",
                reason="Need normalized state.",
            )

        result = store.resolve_graph_conflict(
            conflict_id=conflict_id,
            decision="supersede_with_new_value",
            approved_by="operator:test",
            reason="Operator normalizes conflicting values.",
            new_value_text="yellow",
        )
        assert result["new_status"] == "superseded_with_new_value"
        current = store.conn.execute(
            "SELECT value_text FROM graph_states WHERE attribute = 'status' AND is_current = 1"
        ).fetchone()
        assert current is not None
        assert current["value_text"] == "yellow"
    finally:
        store.close()


def test_source_missing_conflict_cannot_be_resolved(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        conflict_id = _make_conflict(store)
        store.conn.execute("UPDATE graph_conflicts SET candidate_source = '' WHERE id = ?", (conflict_id,))
        store.conn.commit()

        with pytest.raises(ValueError, match="candidate_source"):
            store.resolve_graph_conflict(
                conflict_id=conflict_id,
                decision="quarantine_candidate",
                approved_by="operator:test",
                reason="Missing source must not close silently.",
            )
        assert store.list_graph_conflicts(limit=10)
    finally:
        store.close()


def test_bidirectional_duplicate_conflict_collapses_to_one_group(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        first = store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="green",
            source="user:release-manager",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        assert first["status"] == "inserted"
        red_conflict = store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="red",
            source="user:release-manager",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        assert red_conflict["status"] == "conflict"
        store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="red",
            source="operator:confirmed",
            supersede=True,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        green_conflict = store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="green",
            source="user:release-manager",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        assert green_conflict["status"] == "conflict"
        assert int(green_conflict["conflict_id"]) == int(red_conflict["conflict_id"])
        assert len(store.list_graph_conflicts(limit=10)) == 1
    finally:
        store.close()


def test_resolution_surface_is_not_model_callable() -> None:
    schemas = build_tool_schemas(
        capture_schema_version="test",
        maintenance_schema_version="test",
        maintenance_class_semantic_index="semantic_index",
        maintenance_class_style_source_hygiene="style_source_hygiene",
        owner_user_project="user_project",
        owner_agent_assignment="agent_assignment",
        source_explicit="explicit",
        source_manual_migration="manual_migration",
        runtime_handoff_update_model_callable=False,
    )
    tool_names = {schema.get("name") for schema in schemas}
    assert "brainstack_resolve_graph_conflict" not in tool_names
    assert "resolve_graph_conflict" not in tool_names


def test_migration_preserves_existing_conflict_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE applied_migrations(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
        CREATE TABLE graph_entities(id INTEGER PRIMARY KEY AUTOINCREMENT, canonical_name TEXT NOT NULL);
        CREATE TABLE graph_states(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            attribute TEXT NOT NULL,
            value_text TEXT NOT NULL,
            source TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            valid_from TEXT NOT NULL,
            valid_to TEXT,
            is_current INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE graph_conflicts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            attribute TEXT NOT NULL,
            current_state_id INTEGER NOT NULL,
            candidate_value_text TEXT NOT NULL,
            candidate_source TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        INSERT INTO graph_entities(id, canonical_name) VALUES(1, 'Legacy');
        INSERT INTO graph_states(id, entity_id, attribute, value_text, source, metadata_json, valid_from, is_current)
        VALUES(1, 1, 'status', 'green', 'legacy', '{}', '2026-04-30T00:00:00+00:00', 1);
        INSERT INTO graph_conflicts(
            id, entity_id, attribute, current_state_id, candidate_value_text,
            candidate_source, metadata_json, status, created_at, updated_at
        )
        VALUES(1, 1, 'status', 1, 'red', 'legacy', '{}', 'weird_legacy', '2026-04-30T00:00:00+00:00', '2026-04-30T00:00:00+00:00');
        """
    )
    conn.commit()
    conn.close()

    store = BrainstackStore(str(db_path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        rows = store.list_graph_conflicts(limit=10)
        assert len(rows) == 1
        assert rows[0]["status"] == "open"
        assert rows[0]["candidate_value_text"] == "red"
        resolutions_table = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'graph_conflict_resolutions'"
        ).fetchone()
        assert resolutions_table is not None
    finally:
        store.close()
