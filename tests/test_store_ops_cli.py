from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "brainstack_store_ops.py"


def _create_store(path: Path) -> None:
    store = BrainstackStore(str(path))
    try:
        store.open()
        store.add_transcript_entry(
            session_id="ops-cli-proof",
            turn_number=1,
            kind="user",
            content="ops cli safety proof",
            source="test",
        )
        store.upsert_profile_item(
            stable_key="ops-cli-profile",
            category="preference",
            content="store ops cli profile token=must-redact",
            source="test",
            confidence=0.9,
            metadata={"api_key": "sk-storeopssecret123456"},
        )
    finally:
        store.close()


def _run(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *[str(arg) for arg in args]],
        check=False,
        text=True,
        capture_output=True,
    )


def _json(stdout: str) -> dict:
    return json.loads(stdout)


def test_store_ops_cli_backup_restore_and_report(tmp_path: Path) -> None:
    source = tmp_path / "brainstack.sqlite"
    backup = tmp_path / "backup" / "brainstack.sqlite"
    restored = tmp_path / "restored.sqlite"
    _create_store(source)

    backup_result = _run("backup", "--db", source, "--out", backup)
    restore_result = _run("restore", "--backup", backup, "--db", restored)
    report_result = _run("migration-report", "--db", restored, "--json")

    assert backup_result.returncode == 0, backup_result.stderr
    assert restore_result.returncode == 0, restore_result.stderr
    assert report_result.returncode == 0, report_result.stderr

    backup_receipt = _json(backup_result.stdout)
    restore_receipt = _json(restore_result.stdout)
    report = _json(report_result.stdout)

    assert backup_receipt["schema"] == "brainstack.db_backup_receipt.v1"
    assert restore_receipt["schema"] == "brainstack.db_restore_receipt.v1"
    assert report["schema"] == "brainstack.migration_dry_run_report.v1"
    assert report["mutates"] is False
    assert source.read_bytes() == restored.read_bytes()

    store = BrainstackStore(str(restored))
    try:
        store.open()
        doctor = build_memory_kernel_doctor(store, strict=True)
    finally:
        store.close()
    assert doctor["verdict"] == "pass"


def test_store_ops_cli_missing_db_fails_clearly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite"
    result = _run("migration-report", "--db", missing, "--json")

    assert result.returncode == 2
    payload = _json(result.stdout)
    assert payload["schema"] == "brainstack.store_ops_error.v1"
    assert payload["status"] == "error"
    assert payload["error_type"] == "FileNotFoundError"
    assert str(missing) in payload["message"]


def test_store_ops_cli_shelf_export_and_import_dry_run(tmp_path: Path) -> None:
    source = tmp_path / "brainstack.sqlite"
    target = tmp_path / "target.sqlite"
    bundle = tmp_path / "bundle.json"
    _create_store(source)
    _create_store(target)
    target_before = target.read_bytes()

    export_result = _run("shelf-export", "--db", source, "--out", bundle, "--shelves", "profile")
    dry_run_result = _run("shelf-import-dry-run", "--bundle", bundle, "--target-db", target)

    assert export_result.returncode == 0, export_result.stderr
    assert dry_run_result.returncode == 0, dry_run_result.stderr
    export_receipt = _json(export_result.stdout)
    dry_run = _json(dry_run_result.stdout)
    bundle_text = bundle.read_text(encoding="utf-8")

    assert export_receipt["schema"] == "brainstack.shelf_export_cli_receipt.v1"
    assert dry_run["schema"] == "brainstack.shelf_import_dry_run.v1"
    assert dry_run["mutates"] is False
    assert dry_run["status"] == "blocked_write_import"
    assert "profile" in dry_run["duplicate_shelves"]
    assert "sk-storeopssecret123456" not in bundle_text
    assert "token=must-redact" not in bundle_text
    assert target.read_bytes() == target_before
