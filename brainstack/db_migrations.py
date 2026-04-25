from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1 = "canonical_communication_rows_v1"
MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1 = "explicit_identity_backfill_v1"
MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1 = "stable_logistics_typed_entities_v1"
MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2 = "stable_logistics_typed_entities_v2"
MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1 = "style_contract_profile_lane_v1"
MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1 = "behavior_contract_storage_v1"
MIGRATION_COMPILED_BEHAVIOR_POLICY_V1 = "compiled_behavior_policy_v1"
MIGRATION_COMPILED_BEHAVIOR_POLICY_V2 = "compiled_behavior_policy_v2"
MIGRATION_STYLE_CONTRACT_BEHAVIOR_DEMOTION_V1 = "style_contract_behavior_demotion_v1"
MIGRATION_RECENT_WORK_AUTHORITY_V1 = "recent_work_authority_v1"
MIGRATION_GRAPH_SOURCE_LINEAGE_V1 = "graph_source_lineage_v1"


@dataclass(frozen=True)
class MigrationSpec:
    name: str
    method_name: str


COMPATIBILITY_MIGRATIONS: tuple[MigrationSpec, ...] = (
    MigrationSpec(
        MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1,
        "_apply_canonical_communication_rows_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1,
        "_apply_explicit_identity_backfill_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1,
        "_apply_stable_logistics_typed_entities_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2,
        "_apply_stable_logistics_typed_entities_migration_v2",
    ),
    MigrationSpec(
        MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1,
        "_apply_style_contract_profile_lane_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1,
        "_apply_behavior_contract_storage_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_COMPILED_BEHAVIOR_POLICY_V1,
        "_apply_compiled_behavior_policy_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_COMPILED_BEHAVIOR_POLICY_V2,
        "_apply_compiled_behavior_policy_migration_v2",
    ),
    MigrationSpec(
        MIGRATION_STYLE_CONTRACT_BEHAVIOR_DEMOTION_V1,
        "_apply_style_contract_behavior_demotion_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_RECENT_WORK_AUTHORITY_V1,
        "_apply_recent_work_authority_migration_v1",
    ),
    MigrationSpec(
        MIGRATION_GRAPH_SOURCE_LINEAGE_V1,
        "_apply_graph_source_lineage_migration_v1",
    ),
)

KNOWN_MIGRATION_NAMES = tuple(spec.name for spec in COMPATIBILITY_MIGRATIONS)


class MigrationStore(Protocol):
    @property
    def conn(self) -> sqlite3.Connection: ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def migration_applied(conn: sqlite3.Connection, name: str) -> bool:
    migration_name = str(name or "").strip()
    row = conn.execute(
        "SELECT 1 FROM applied_migrations WHERE name = ? LIMIT 1",
        (migration_name,),
    ).fetchone()
    return row is not None


def mark_migration_applied(conn: sqlite3.Connection, name: str) -> None:
    migration_name = str(name or "").strip()
    if not migration_name:
        return
    conn.execute(
        """
        INSERT INTO applied_migrations(name, applied_at)
        VALUES(?, ?)
        ON CONFLICT(name) DO UPDATE SET applied_at = excluded.applied_at
        """,
        (migration_name, _utc_now_iso()),
    )


def run_compatibility_migrations(store: MigrationStore) -> None:
    for spec in COMPATIBILITY_MIGRATIONS:
        if migration_applied(store.conn, spec.name):
            continue
        migration = getattr(store, spec.method_name, None)
        if not callable(migration):
            raise RuntimeError(f"Brainstack migration method missing: {spec.method_name}")
        migration()


def applied_migration_names(conn: sqlite3.Connection) -> tuple[str, ...]:
    rows = conn.execute("SELECT name FROM applied_migrations ORDER BY name ASC").fetchall()
    return tuple(str(row["name"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows)


def unknown_applied_migration_names(conn: sqlite3.Connection) -> tuple[str, ...]:
    known = set(KNOWN_MIGRATION_NAMES)
    return tuple(name for name in applied_migration_names(conn) if name not in known)
