from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.db_ops import backup_sqlite_store, migration_dry_run_report, restore_sqlite_store
from brainstack.diagnostics import build_memory_kernel_doctor


def _create_store(path: Path) -> None:
    store = BrainstackStore(str(path))
    try:
        store.open()
        store.add_transcript_entry(
            session_id="ops-proof",
            turn_number=1,
            kind="user",
            content="ops safety proof",
            source="test",
        )
    finally:
        store.close()


def test_backup_and_restore_preserve_healthy_store(tmp_path: Path) -> None:
    source = tmp_path / "brainstack.sqlite"
    backup = tmp_path / "backup" / "brainstack.sqlite"
    restored = tmp_path / "restored.sqlite"
    _create_store(source)

    backup_receipt = backup_sqlite_store(source_path=source, backup_path=backup)
    restore_receipt = restore_sqlite_store(backup_path=backup, target_path=restored)

    assert backup_receipt["status"] == "completed"
    assert restore_receipt["status"] == "completed"
    assert source.read_bytes() == restored.read_bytes()

    store = BrainstackStore(str(restored))
    try:
        store.open()
        report = build_memory_kernel_doctor(store, strict=True)
        assert report["verdict"] == "pass"
        assert report["capabilities"]["db_substrate"]["status"] == "active"
    finally:
        store.close()


def test_migration_dry_run_reports_without_mutating(tmp_path: Path) -> None:
    source = tmp_path / "brainstack.sqlite"
    _create_store(source)

    before = source.read_bytes()
    report = migration_dry_run_report(source)
    after = source.read_bytes()

    assert before == after
    assert report["schema"] == "brainstack.migration_dry_run_report.v1"
    assert report["status"] == "clean"
    assert report["mutates"] is False
    assert report["missing_known_migrations"] == []
    assert report["unknown_applied_migrations"] == []


def test_migration_dry_run_surfaces_unknown_applied_migration(tmp_path: Path) -> None:
    source = tmp_path / "brainstack.sqlite"
    _create_store(source)
    store = BrainstackStore(str(source))
    try:
        store.open()
        store.conn.execute(
            "INSERT INTO applied_migrations(name, applied_at) VALUES(?, ?)",
            ("future_unknown_migration", "2026-04-25T00:00:00+00:00"),
        )
        store.conn.commit()
    finally:
        store.close()

    report = migration_dry_run_report(source)

    assert report["status"] == "needs_attention"
    assert report["unknown_applied_migrations"] == ["future_unknown_migration"]
