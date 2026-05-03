#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.diagnostics import build_query_inspect  # noqa: E402
from brainstack.trace_tiering import validate_compact_query_trace_public_safety  # noqa: E402

SCHEMA = "brainstack.trace_tiering_verifier.v1"


def build_report() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="brainstack-m008-trace-tier-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            scope = "principal:m008:trace"
            session = "session:m008:trace"
            store.upsert_profile_item(
                stable_key="identity:m008:trace",
                category="identity",
                content="M008 trace tier profile evidence.",
                source="trace-tier.verifier",
                confidence=0.99,
                metadata={"principal_scope_key": scope, "truth_eligible": True},
            )
            full = build_query_inspect(store, query="trace tier profile", session_id=session, principal_scope_key=scope)
            compact = build_query_inspect(
                store,
                query="trace tier profile",
                session_id=session,
                principal_scope_key=scope,
                trace_mode="compact",
            )
        finally:
            store.close()
    compact_public_issues = validate_compact_query_trace_public_safety(compact)
    failures: list[str] = []
    if full.get("trace_mode") != "full" or full.get("compact_trace_available") is not True:
        failures.append("full_trace_contract_missing")
    if compact.get("schema") != "brainstack.compact_query_trace.v1":
        failures.append("compact_trace_schema_missing")
    if compact_public_issues:
        failures.append("compact_trace_public_safety_failed")
    if "selected_evidence" in compact or "suppressed_evidence" in compact:
        failures.append("compact_trace_contains_raw_evidence")
    return {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "full_trace": {
            "schema": full.get("schema"),
            "trace_mode": full.get("trace_mode"),
            "compact_trace_available": full.get("compact_trace_available"),
            "selected_evidence_shelves": sorted((full.get("selected_evidence") or {}).keys()),
        },
        "compact_trace": {
            "schema": compact.get("schema"),
            "trace_mode": compact.get("trace_mode"),
            "full_trace_available": compact.get("full_trace_available"),
            "selected_counts": compact.get("selected_counts"),
            "final_packet": compact.get("final_packet"),
        },
        "public_safe": not compact_public_issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify compact/full trace tiering.")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failure_reasons": report["failure_reasons"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
