#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brainstack.core.admission import TruthShelf, TruthWritePermit


_DERIVED_PREFIXES = ("tier2:", "consolidation:", "session_recap:", "pulse:", "background:")


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_permit_or_admission(meta: Mapping[str, Any]) -> bool:
    return bool(
        isinstance(meta.get("truth_write_permit"), Mapping)
        or isinstance(meta.get("admission"), Mapping)
        or isinstance(meta.get("durable_write_context"), Mapping)
    )


def _is_derived(source: str) -> bool:
    text = str(source or "").strip().casefold()
    return any(text.startswith(prefix) for prefix in _DERIVED_PREFIXES)


def _stamp(meta: Mapping[str, Any], *, shelf: TruthShelf, slot: str, migration_id: str) -> dict[str, Any]:
    permit = TruthWritePermit.migration(migration_id=migration_id, shelf=shelf, slot=slot)
    payload = dict(meta)
    payload.update(permit.metadata_payload())
    payload["legacy_permit_migration"] = migration_id
    return payload


def stamp_legacy_permits(db_path: Path, *, apply: bool, migration_id: str) -> dict[str, Any]:
    if apply:
        backup = db_path.with_suffix(db_path.suffix + f".{migration_id}.bak")
        if not backup.exists():
            shutil.copy2(db_path, backup)
    else:
        backup = None

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    updates: list[dict[str, Any]] = []
    try:
        for row in conn.execute("SELECT id, stable_key, source, metadata_json FROM profile_items WHERE active = 1"):
            meta = _decode(row["metadata_json"])
            if not _is_derived(str(row["source"])) or _has_permit_or_admission(meta):
                continue
            stamped = _stamp(
                meta,
                shelf=TruthShelf.PROFILE,
                slot=str(row["stable_key"] or ""),
                migration_id=migration_id,
            )
            updates.append({"table": "profile_items", "row_id": int(row["id"]), "source": str(row["source"])})
            if apply:
                conn.execute(
                    "UPDATE profile_items SET metadata_json = ? WHERE id = ?",
                    (json.dumps(stamped, ensure_ascii=True, sort_keys=True), int(row["id"])),
                )

        for row in conn.execute("SELECT id, predicate, source, metadata_json FROM graph_relations WHERE active = 1"):
            meta = _decode(row["metadata_json"])
            if not _is_derived(str(row["source"])) or _has_permit_or_admission(meta):
                continue
            stamped = _stamp(
                meta,
                shelf=TruthShelf.GRAPH,
                slot=str(row["predicate"] or ""),
                migration_id=migration_id,
            )
            updates.append({"table": "graph_relations", "row_id": int(row["id"]), "source": str(row["source"])})
            if apply:
                conn.execute(
                    "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                    (json.dumps(stamped, ensure_ascii=True, sort_keys=True), int(row["id"])),
                )

        if apply:
            conn.commit()
    finally:
        conn.close()

    return {
        "schema": "brainstack.legacy_write_permit_migration.v1",
        "db_path": str(db_path),
        "migration_id": migration_id,
        "apply": apply,
        "backup_path": str(backup) if backup else "",
        "updated_count": len(updates),
        "updates": updates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Stamp legacy derived durable rows with migration permits.")
    parser.add_argument("db_path")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--migration-id", default="phase1671_legacy_permit_migration")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    result = stamp_legacy_permits(Path(args.db_path), apply=bool(args.apply), migration_id=str(args.migration_id))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
