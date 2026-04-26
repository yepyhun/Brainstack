from __future__ import annotations

import json
from pathlib import Path

import pytest

from brainstack.db import BrainstackStore
from brainstack.db_ops import backup_sqlite_store, restore_sqlite_store
from brainstack.shelf_export import (
    dry_run_import_shelf_bundle,
    export_shelf_bundle,
    load_shelf_export_bundle,
    write_shelf_export_bundle,
)


PRINCIPAL_SCOPE = "principal:shelf-export"


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _seed_store(path: Path) -> None:
    store = _open_store(path)
    try:
        metadata = {
            "principal_scope_key": PRINCIPAL_SCOPE,
            "private_path": "/home/lauratom/private/should-redact.md",
            "api_key": "DUMMY_SECRET_VALUE_TEST_123456",
        }
        store.upsert_profile_item(
            stable_key="preference:export",
            category="preference",
            content="Shelf export should redact token=super-secret-value.",
            source="shelf-export.fixture",
            confidence=0.99,
            metadata=metadata,
        )
        store.add_continuity_event(
            session_id="export-session",
            turn_number=1,
            kind="note",
            content="Shelf export continuity row.",
            source="shelf-export.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.upsert_operating_record(
            stable_key="active:export",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type="active_work",
            content="Shelf export active work.",
            owner="user_project",
            source="shelf-export.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.upsert_graph_state(
            subject_name="Shelf Export",
            attribute="status",
            value_text="dry-run ready",
            source="shelf-export.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.ingest_corpus_source(
            {
                "source_adapter": "shelf_export_fixture",
                "source_id": "doc",
                "stable_key": "doc:shelf-export",
                "title": "Shelf Export Corpus",
                "doc_kind": "proof_note",
                "source_uri": "/private/source/shelf-export.md",
                "content": "Shelf export corpus citation.",
                "metadata": {"principal_scope_key": PRINCIPAL_SCOPE},
            }
        )
    finally:
        store.close()


def test_shelf_export_has_manifest_redaction_report_and_migration_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstack.sqlite"
    _seed_store(db_path)
    store = _open_store(db_path)
    try:
        bundle = export_shelf_bundle(
            store,
            shelves=("profile", "continuity", "operating", "graph", "corpus"),
            principal_scope_key=PRINCIPAL_SCOPE,
        )
    finally:
        store.close()

    assert bundle["schema"] == "brainstack.shelf_export_bundle.v1"
    manifest = bundle["manifest"]
    assert manifest["schema"] == "brainstack.shelf_export_manifest.v1"
    assert manifest["exported_at"]
    assert manifest["brainstack_version"]
    assert set(manifest["checksums"]) == {"profile", "continuity", "operating", "graph", "corpus"}
    assert all(len(value) == 64 for value in manifest["checksums"].values())
    assert str(db_path) not in json.dumps(manifest["source_store"], sort_keys=True)
    assert manifest["migration_ledger"]["schema"] == "brainstack.migration_dry_run_report.v1"
    assert manifest["write_import_supported"] is False
    assert manifest["write_import_blocker"] == "write_import_deferred_until_shelf_roundtrip_proof"
    assert manifest["redaction_report"]["schema"] == "brainstack.shelf_export_redaction.v1"
    assert manifest["redaction_report"]["reason_counts"]["secret_key_redacted"] >= 1
    assert manifest["redaction_report"]["reason_counts"]["private_path_redacted"] >= 1
    serialized = json.dumps(bundle, sort_keys=True)
    assert "DUMMY_SECRET_VALUE_TEST_123456" not in serialized
    assert "token=super-secret-value" not in serialized
    assert "/home/lauratom/private" not in serialized
    assert "/private/source" not in serialized


def test_shelf_export_write_and_dry_run_import_mutates_nothing(tmp_path: Path) -> None:
    source_db = tmp_path / "source.sqlite"
    target_db = tmp_path / "target.sqlite"
    bundle_path = tmp_path / "bundle.json"
    _seed_store(source_db)
    _seed_store(target_db)
    target_before = target_db.read_bytes()

    store = _open_store(source_db)
    try:
        bundle = export_shelf_bundle(store, shelves=("profile", "corpus"), principal_scope_key=PRINCIPAL_SCOPE)
    finally:
        store.close()
    receipt = write_shelf_export_bundle(bundle, bundle_path)
    loaded = load_shelf_export_bundle(bundle_path)
    dry_run = dry_run_import_shelf_bundle(loaded, target_path=target_db)

    assert receipt["status"] == "completed"
    assert receipt["mutates_store"] is False
    assert dry_run["schema"] == "brainstack.shelf_import_dry_run.v1"
    assert dry_run["mutates"] is False
    assert dry_run["status"] == "blocked_write_import"
    assert set(dry_run["duplicate_shelves"]) >= {"profile", "corpus"}
    assert target_db.read_bytes() == target_before


def test_shelf_import_dry_run_requires_supported_bundle_and_target(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{bad json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid shelf export bundle"):
        load_shelf_export_bundle(corrupt)

    with pytest.raises(ValueError, match="unsupported shelf export bundle schema"):
        dry_run_import_shelf_bundle({"schema": "wrong"}, target_path=tmp_path / "target.sqlite")

    with pytest.raises(ValueError, match="requires explicit target_path"):
        dry_run_import_shelf_bundle({"schema": "brainstack.shelf_export_bundle.v1", "manifest": {}, "shelves": {}}, target_path="")


def test_low_level_backup_restore_remains_byte_safety_path(tmp_path: Path) -> None:
    source_db = tmp_path / "source.sqlite"
    backup_db = tmp_path / "backup" / "source.sqlite"
    restored_db = tmp_path / "restored.sqlite"
    _seed_store(source_db)

    backup = backup_sqlite_store(source_path=source_db, backup_path=backup_db)
    restore = restore_sqlite_store(backup_path=backup_db, target_path=restored_db)

    assert backup["status"] == "completed"
    assert restore["status"] == "completed"
    assert source_db.read_bytes() == restored_db.read_bytes()
