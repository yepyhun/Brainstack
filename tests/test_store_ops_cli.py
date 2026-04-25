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
