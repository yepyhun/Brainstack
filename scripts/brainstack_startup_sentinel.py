#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping


_DERIVED_PREFIXES = ("tier2:", "consolidation:", "session_recap:", "pulse:", "background:")
_BAD_VISIBILITY = {"history_only", "contradiction_only", "inspect_only"}
_CURRENT_ALLOWED = {"user_explicit_assignment", "trusted_host_assignment", "operator_repair"}


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


def _nested(meta: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = meta.get(key)
    return value if isinstance(value, Mapping) else {}


def _has_permit_or_trusted_context(meta: Mapping[str, Any]) -> bool:
    permit = _nested(meta, "truth_write_permit")
    context = _nested(meta, "durable_write_context")
    admission = _nested(meta, "admission")
    return bool(
        permit.get("permit_id")
        or admission.get("claim_id")
        or context.get("trusted_context_id")
        or context.get("migration_id")
        or context.get("operator_action_id")
        or context.get("canary_run_id")
    )


def _source_authority(meta: Mapping[str, Any]) -> str:
    permit = _nested(meta, "truth_write_permit")
    context = _nested(meta, "durable_write_context")
    admission = _nested(meta, "admission")
    return str(
        context.get("source_authority")
        or permit.get("source_authority")
        or meta.get("source_authority")
        or admission.get("authority_class")
        or ""
    ).strip().casefold()


def _support_visibility(meta: Mapping[str, Any]) -> str:
    admission = _nested(meta, "admission")
    return str(meta.get("support_visibility") or admission.get("support_visibility") or "").strip().casefold()


def _is_bad_support(meta: Mapping[str, Any]) -> bool:
    visibility = _support_visibility(meta)
    if visibility not in _BAD_VISIBILITY:
        return False
    if bool(meta.get("truth_eligible")):
        return True
    if bool(meta.get("model_facing_default")):
        return True
    admission = _nested(meta, "admission")
    return bool(admission.get("truth_eligible"))


def _is_derived_source(source: str, meta: Mapping[str, Any]) -> bool:
    source_text = str(source or "").strip().casefold()
    if any(source_text.startswith(prefix) for prefix in _DERIVED_PREFIXES):
        return True
    authority = _source_authority(meta)
    return authority in {
        "tier2_summary",
        "pulse_background",
        "session_recap",
        "assistant_claim",
        "assistant_self_claim",
        "graph_inference",
        "transcript_event",
        "runtime_diagnostic",
    }


def _rows(conn: sqlite3.Connection, query: str) -> Iterable[sqlite3.Row]:
    try:
        return list(conn.execute(query).fetchall())
    except sqlite3.Error:
        return []


def run_sentinel(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    violations: list[dict[str, Any]] = []
    try:
        for table, id_col in [
            ("profile_items", "id"),
            ("graph_states", "id"),
            ("graph_relations", "id"),
        ]:
            for row in _rows(conn, f"SELECT * FROM {table} WHERE active = 1"):
                meta = _decode(row["metadata_json"] if "metadata_json" in row.keys() else "")
                source = str(row["source"] if "source" in row.keys() else "")
                if _is_derived_source(source, meta) and not _has_permit_or_trusted_context(meta):
                    violations.append(
                        {
                            "table": table,
                            "row_id": int(row[id_col]),
                            "violation": "DERIVED_TRUTH_WITHOUT_PERMIT",
                            "source": source,
                        }
                    )
                if _is_bad_support(meta):
                    violations.append(
                        {
                            "table": table,
                            "row_id": int(row[id_col]),
                            "violation": "SUPPORT_ONLY_MARKED_TRUTH_OR_MODEL_FACING",
                            "source": source,
                        }
                    )

        for row in _rows(conn, "SELECT * FROM operating_records"):
            meta = _decode(row["metadata_json"])
            current = bool(meta.get("current_assignment_authority")) or str(row["record_type"]).strip() == "current_assignment_state"
            if current and _source_authority(meta) and _source_authority(meta) not in _CURRENT_ALLOWED:
                violations.append(
                    {
                        "table": "operating_records",
                        "row_id": int(row["id"]),
                        "violation": "CURRENT_ASSIGNMENT_AUTHORITY_NOT_ALLOWED",
                        "source": str(row["source"]),
                    }
                )
            if _is_bad_support(meta):
                violations.append(
                    {
                        "table": "operating_records",
                        "row_id": int(row["id"]),
                        "violation": "SUPPORT_ONLY_MARKED_TRUTH_OR_MODEL_FACING",
                        "source": str(row["source"]),
                    }
                )
    finally:
        conn.close()

    return {
        "schema": "brainstack.startup_sentinel.v1",
        "db_path": str(db_path),
        "p0_count": len(violations),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cheap Brainstack startup P0 sentinel.")
    parser.add_argument("db_path")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()
    result = run_sentinel(Path(args.db_path))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if int(result["p0_count"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
