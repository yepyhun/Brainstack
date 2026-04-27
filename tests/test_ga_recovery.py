from __future__ import annotations

from pathlib import Path

from scripts.ga_recovery import (
    backup_restore_roundtrip,
    clean_install_probe,
    migration_report,
    recovery_commands,
    rollback_proof,
)


def test_clean_install_fresh_hermes() -> None:
    report = clean_install_probe({"files": [{"source": "brainstack/__init__.py"}], "secrets_included": False})

    assert report["passed"] is True
    assert report["payload_count"] == 1


def test_upgrade_previous_release_requires_manifest_payload() -> None:
    report = clean_install_probe({"files": [], "secrets_included": False})

    assert report["passed"] is False


def test_migration_requires_backup_path() -> None:
    report = migration_report(before_version=1, after_version=2, backup_present=False, dry_run=True)

    assert report["passed"] is False
    assert report["destructive_without_backup"] is True


def test_backup_restore_roundtrip_preserves_hashes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "brainstack.db").write_text("x", encoding="utf-8")

    report = backup_restore_roundtrip(source, tmp_path / "backup", tmp_path / "restored")

    assert report["passed"] is True
    assert report["hashes_match"] is True


def test_rollback_proof_requires_previous_and_current_state() -> None:
    report = rollback_proof({"a": "new"}, {"a": "old"})

    assert report["passed"] is True
    assert report["changed_files"] == ["a"]


def test_recovery_commands_include_doctor_and_backup() -> None:
    text = recovery_commands()

    assert "brainstack_backup create" in text
    assert "brainstack_doctor --ga" in text
    assert "brainstack_trace explain-turn" in text
