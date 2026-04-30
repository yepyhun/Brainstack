#!/usr/bin/env python3
"""Audit graph conflict lifecycle contract in a public-safe temp store."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_audit() -> dict[str, Any]:
    from brainstack.db import BrainstackStore

    with tempfile.TemporaryDirectory(prefix="brainstack-graph-conflict-audit-") as temp:
        store = BrainstackStore(
            str(Path(temp) / "brainstack.sqlite3"),
            graph_backend="sqlite",
            corpus_backend="sqlite",
        )
        store.open()
        try:
            first = store.upsert_graph_state(
                subject_name="Release Train",
                attribute="status",
                value_text="green",
                source="public-audit:user",
                metadata={"principal_scope_key": "principal:public-audit"},
            )
            conflict = store.upsert_graph_state(
                subject_name="Release Train",
                attribute="status",
                value_text="red",
                source="public-audit:user",
                metadata={"principal_scope_key": "principal:public-audit"},
            )
            open_before = store.list_graph_conflicts(limit=10)
            release_blocked_before_resolution = bool(open_before)
            resolution = store.resolve_graph_conflict(
                conflict_id=int(conflict["conflict_id"]),
                decision="accept_current",
                approved_by="public-audit-operator",
                reason="Public audit keeps current state.",
                evidence_refs=["public-audit:evidence:1"],
            )
            open_after = store.list_graph_conflicts(limit=10)
            resolutions = store.list_graph_conflict_resolutions(
                conflict_id=int(conflict["conflict_id"]),
                limit=10,
            )
            closed = store.list_graph_conflicts(limit=10, include_closed=True)
        finally:
            store.close()

    status = "pass"
    issues: list[str] = []
    if first.get("status") != "inserted":
        issues.append("initial_state_not_inserted")
    if conflict.get("status") != "conflict":
        issues.append("conflict_not_created")
    if not release_blocked_before_resolution:
        issues.append("open_conflict_did_not_block_release")
    if resolution.get("status") != "resolved":
        issues.append("resolution_not_recorded")
    if open_after:
        issues.append("open_conflict_remained_after_resolution")
    if len(resolutions) != 1:
        issues.append("resolution_ledger_missing")
    if not any(row.get("status") == "accepted_current" for row in closed):
        issues.append("closed_status_not_visible")
    if issues:
        status = "fail"
    return {
        "schema": "brainstack.graph_conflict_lifecycle_audit.v1",
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
        "release_blocked_before_resolution": release_blocked_before_resolution,
        "open_conflict_count_after_resolution": len(open_after),
        "resolution_ledger_count": len(resolutions),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = run_audit()
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
