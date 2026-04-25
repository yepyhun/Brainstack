from __future__ import annotations

import sqlite3
from typing import Any, Dict

from .db_migrations import (
    KNOWN_MIGRATION_NAMES,
    applied_migration_names,
    unknown_applied_migration_names,
)
from .db_schema import expected_schema_objects, missing_schema_objects, schema_objects


MAX_DIAGNOSTIC_ITEMS = 20


def _object_payload(items: tuple[tuple[str, str], ...]) -> list[Dict[str, str]]:
    return [{"type": item_type, "name": name} for item_type, name in items[:MAX_DIAGNOSTIC_ITEMS]]


def build_db_substrate_snapshot(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Return bounded read-only schema and migration-ledger health."""
    issues: list[str] = []
    schema_error = ""
    migration_error = ""
    actual_objects: tuple[tuple[str, str], ...] = ()
    missing_objects: tuple[tuple[str, str], ...] = ()
    applied_names: tuple[str, ...] = ()
    unknown_names: tuple[str, ...] = ()

    try:
        actual_objects = schema_objects(conn)
        missing_objects = missing_schema_objects(conn)
    except Exception as exc:
        schema_error = f"{type(exc).__name__}: {exc}"
        issues.append("schema_snapshot_failed")

    try:
        applied_names = applied_migration_names(conn)
        unknown_names = unknown_applied_migration_names(conn)
    except Exception as exc:
        migration_error = f"{type(exc).__name__}: {exc}"
        issues.append("migration_ledger_unreadable")

    known_set = set(KNOWN_MIGRATION_NAMES)
    applied_known_names = tuple(name for name in applied_names if name in known_set)
    missing_known_names = tuple(name for name in KNOWN_MIGRATION_NAMES if name not in set(applied_names))

    if missing_objects:
        issues.append("missing_schema_objects")
    if missing_known_names:
        issues.append("missing_known_migrations")
    if unknown_names:
        issues.append("unknown_applied_migrations")

    status = "active" if not issues else "degraded"
    if status == "active":
        reason = "DB schema objects and migration ledger match the known Brainstack substrate."
    else:
        reason = "; ".join(issues)

    return {
        "kind": "db_substrate",
        "requested": True,
        "active": status == "active",
        "status": status,
        "reason": reason,
        "schema_object_count": len(actual_objects),
        "expected_schema_object_count": len(expected_schema_objects()),
        "missing_schema_objects": _object_payload(missing_objects),
        "missing_schema_object_count": len(missing_objects),
        "known_migration_count": len(KNOWN_MIGRATION_NAMES),
        "applied_known_migration_count": len(applied_known_names),
        "missing_known_migrations": list(missing_known_names[:MAX_DIAGNOSTIC_ITEMS]),
        "missing_known_migration_count": len(missing_known_names),
        "unknown_applied_migrations": list(unknown_names[:MAX_DIAGNOSTIC_ITEMS]),
        "unknown_applied_migration_count": len(unknown_names),
        "schema_error": schema_error,
        "migration_error": migration_error,
    }
