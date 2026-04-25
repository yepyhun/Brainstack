from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, Dict

from .db_diagnostics import build_db_substrate_snapshot
from .db_migrations import KNOWN_MIGRATION_NAMES, applied_migration_names, unknown_applied_migration_names


def backup_sqlite_store(*, source_path: str | Path, backup_path: str | Path) -> Dict[str, Any]:
    source = Path(source_path)
    backup = Path(backup_path)
    if not source.exists():
        raise FileNotFoundError(f"Brainstack DB not found: {source}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, backup)
    return {
        "schema": "brainstack.db_backup_receipt.v1",
        "status": "completed",
        "source_path": str(source),
        "backup_path": str(backup),
        "bytes": backup.stat().st_size,
    }


def restore_sqlite_store(*, backup_path: str | Path, target_path: str | Path) -> Dict[str, Any]:
    backup = Path(backup_path)
    target = Path(target_path)
    if not backup.exists():
        raise FileNotFoundError(f"Brainstack backup not found: {backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    return {
        "schema": "brainstack.db_restore_receipt.v1",
        "status": "completed",
        "backup_path": str(backup),
        "target_path": str(target),
        "bytes": target.stat().st_size,
    }


def migration_dry_run_report(db_path: str | Path) -> Dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"Brainstack DB not found: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        applied = applied_migration_names(conn)
        known = tuple(KNOWN_MIGRATION_NAMES)
        applied_set = set(applied)
        missing = tuple(name for name in known if name not in applied_set)
        unknown = unknown_applied_migration_names(conn)
        substrate = build_db_substrate_snapshot(conn)
        status = "clean" if not missing and not unknown and substrate.get("status") == "active" else "needs_attention"
        return {
            "schema": "brainstack.migration_dry_run_report.v1",
            "status": status,
            "db_path": str(path),
            "known_migrations": list(known),
            "applied_known_migrations": [name for name in applied if name in set(known)],
            "missing_known_migrations": list(missing),
            "unknown_applied_migrations": list(unknown),
            "db_substrate": substrate,
            "mutates": False,
        }
    finally:
        conn.close()
