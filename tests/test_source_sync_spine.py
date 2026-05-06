from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor
from brainstack.source_sync_spine import (
    DELETION_DEACTIVATE_MISSING,
    DELETION_RETAIN_MISSING,
    SourceSyncConfig,
    build_source_sync_status,
    run_source_sync,
)


PRINCIPAL_SCOPE = "principal:source-sync-spine"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _config(root: Path, *, deletion_policy: str = DELETION_RETAIN_MISSING) -> SourceSyncConfig:
    return SourceSyncConfig(
        source_root=root,
        allow_patterns=("*.md",),
        source_set_id="fixture-source-set",
        principal_scope_key=PRINCIPAL_SCOPE,
        deletion_policy=deletion_policy,
    )


def test_source_sync_full_unchanged_and_changed_paths_are_cursor_backed(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "alpha.md").write_text("# Alpha\n\nFirst source body.", encoding="utf-8")
    store = _open_store(tmp_path)
    try:
        first = run_source_sync(store, _config(root))
        second = run_source_sync(store, _config(root))
        (root / "alpha.md").write_text("# Alpha\n\nChanged source body.", encoding="utf-8")
        third = run_source_sync(store, _config(root))

        assert first["status"] == "changed"
        assert first["counts"]["inserted"] == 1
        assert second["status"] == "unchanged"
        assert second["cursor"] == first["cursor"]
        assert third["status"] == "changed"
        assert third["counts"]["updated"] == 1
        assert third["cursor"] != first["cursor"]
        assert store.conn.execute("SELECT COUNT(*) AS count FROM corpus_documents").fetchone()["count"] == 1

        status = build_source_sync_status(store, source_set_id="fixture-source-set", principal_scope_key=PRINCIPAL_SCOPE)
        assert status["status"] == "active"
        assert status["latest_run"]["status"] == "changed"
        assert status["active_document_count"] == 1
        assert status["truth_authority"] == "admission_receipts_only"
    finally:
        store.close()


def test_source_sync_deletion_policy_is_explicit_and_never_hidden(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    stale = root / "stale.md"
    stale.write_text("# Stale\n\nRemove me.", encoding="utf-8")
    store = _open_store(tmp_path)
    try:
        run_source_sync(store, _config(root))
        stale.unlink()
        retained = run_source_sync(store, _config(root))

        assert retained["status"] == "unchanged"
        assert retained["deletion_policy"] == DELETION_RETAIN_MISSING
        assert retained["counts"]["retained_missing"] == 1
        assert retained["counts"]["deactivated"] == 0
        assert store.search_corpus(query="Remove me", limit=2)

        deactivated = run_source_sync(store, _config(root, deletion_policy=DELETION_DEACTIVATE_MISSING))
        assert deactivated["status"] == "changed"
        assert deactivated["counts"]["deactivated"] == 1
        assert store.search_corpus(query="Remove me", limit=2) == []
    finally:
        store.close()


def test_source_sync_status_is_public_safe_and_blocks_private_file_noise(tmp_path: Path) -> None:
    root = tmp_path / "private-source-root"
    root.mkdir()
    (root / "visible.md").write_text("# Visible\n\nPublic-safe body.", encoding="utf-8")
    (root / "secret-token.md").write_text("do not ingest", encoding="utf-8")
    store = _open_store(tmp_path)
    try:
        result = run_source_sync(
            store,
            SourceSyncConfig(
                source_root=root,
                allow_patterns=("*.md",),
                source_set_id=str(root),
                principal_scope_key=PRINCIPAL_SCOPE,
            ),
        )
        status = build_source_sync_status(store, principal_scope_key=PRINCIPAL_SCOPE)
        doctor = build_memory_kernel_doctor(store)
        combined = f"{result} {status} {doctor}"

        assert result["public_safe"] is True
        assert result["raw_private_source_in_status"] is False
        assert result["counts"]["skipped"] == 1
        assert "secret-token.md" not in combined
        assert str(root) not in combined
        assert "private-source-root" not in combined
        assert result["source_set_id"].startswith("source_sync_local:private:")
        assert doctor["capabilities"]["source_sync_spine"]["status"] == "active"
    finally:
        store.close()


def test_source_sync_never_creates_durable_truth_or_graph_rows(tmp_path: Path) -> None:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "truthy.md").write_text("# Candidate\n\nThis is source support, not admitted truth.", encoding="utf-8")
    store = _open_store(tmp_path)
    try:
        result = run_source_sync(store, _config(root))

        assert result["connector_writes_durable_truth"] is False
        assert result["truth_authority"] == "admission_receipts_only"
        for table in (
            "admission_receipts",
            "canonical_memory_events",
            "graph_entities",
            "graph_relations",
            "task_items",
            "behavior_contracts",
        ):
            assert store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"] == 0
        assert store.conn.execute("SELECT COUNT(*) AS count FROM corpus_documents").fetchone()["count"] == 1
    finally:
        store.close()
