#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_local_workload_performance_replay import build_report as build_workload_report  # noqa: E402
from scripts.verify_retrieval_context_envelope import run_probe as run_envelope_probe  # noqa: E402
from scripts.verify_source_sync_spine import run_probe as run_source_sync_probe  # noqa: E402

REPORT_SCHEMA = "brainstack.retrieval_packet_source_destructive_proof.v1"


def _case(case_id: str, checks: Mapping[str, bool], payload: Mapping[str, Any]) -> dict[str, Any]:
    failed = sorted(key for key, passed in checks.items() if passed is not True)
    return {
        "case_id": case_id,
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": dict(checks),
        "payload": dict(payload),
    }


def build_report() -> dict[str, Any]:
    envelope = run_envelope_probe()
    source_sync = run_source_sync_probe()
    workload = build_workload_report()
    workload_summary = workload.get("summary") if isinstance(workload.get("summary"), Mapping) else {}
    workload_cases = {
        str(case.get("case_id")): case
        for case in list(workload.get("cases") or [])
        if isinstance(case, Mapping)
    }
    no_memory = workload_cases.get("no_memory_minimal", {})
    current_truth = workload_cases.get("current_truth_lookup", {})
    stale_correction = workload_cases.get("stale_correction", {})
    profile_only = workload_cases.get("profile_only", {})
    deep = workload_cases.get("corpus_semantic_supported", {})

    cases = [
        _case(
            "agent_facing_envelope_labels_current_stale_support",
            {
                "probe_passed": envelope.get("status") == "pass",
                "current_route": envelope.get("current_route") == "current_truth",
                "current_truth_count": envelope.get("current_truth_count") == 1,
                "stale_prior_conflict_count": envelope.get("stale_prior_conflict_count") == 1,
                "source_expand_handles": envelope.get("source_expand_handles") == 1,
                "no_memory_semantic_disabled": envelope.get("no_memory_semantic_enabled") is False,
                "public_safe": envelope.get("public_safe") is True,
                "no_private_payload": envelope.get("raw_private_payload_in_envelope") is False,
                "no_private_scope": envelope.get("raw_private_scope_in_envelope") is False,
            },
            envelope,
        ),
        _case(
            "source_sync_handles_are_bounded_and_source_only",
            {
                "probe_passed": source_sync.get("status") == "pass",
                "full_sync_changed": source_sync.get("full_sync_status") == "changed",
                "unchanged_sync_idempotent": source_sync.get("unchanged_sync_status") == "unchanged",
                "changed_sync_changed": source_sync.get("changed_sync_status") == "changed",
                "delete_sync_changed": source_sync.get("delete_sync_status") == "changed",
                "truth_authority_is_admission": source_sync.get("truth_authority") == "admission_receipts_only",
                "no_raw_private_source": source_sync.get("raw_private_source_in_status") is False,
            },
            source_sync,
        ),
        _case(
            "hard_gated_routes_do_not_reenable_backend_work",
            {
                "workload_passed": workload.get("status") == "pass",
                "hard_gated_semantic_zero": int(workload_summary.get("hard_gated_semantic_backend_calls") or 0) == 0,
                "current_truth_no_rebuild": int(current_truth.get("current_truth_rebuild_calls") or 0) == 0
                and int(stale_correction.get("current_truth_rebuild_calls") or 0) == 0,
                "no_memory_no_shelves": all(int(value or 0) == 0 for value in dict(no_memory.get("shelf_backend_calls") or {}).values()),
                "profile_skips_graph_corpus": int(dict(profile_only.get("shelf_backend_calls") or {}).get("search_graph") or 0) == 0
                and int(dict(profile_only.get("shelf_backend_calls") or {}).get("search_corpus") or 0) == 0,
                "protected_truth_not_dropped": int(workload_summary.get("protected_truth_drop_attempts") or 0) == 0,
                "deep_route_keeps_semantic": int(deep.get("semantic_backend_call_total") or 0) > 0,
            },
            {
                "summary": workload_summary,
                "no_memory": no_memory,
                "profile_only": profile_only,
                "current_truth": current_truth,
                "stale_correction": stale_correction,
                "deep": deep,
            },
        ),
    ]
    failures = [case for case in cases if case["status"] != "pass"]
    proof = {
        "agent_facing_context_matches_current_stale_support_counts": cases[0]["status"] == "pass",
        "source_expand_handles_public_safe": cases[1]["status"] == "pass",
        "source_sync_remains_source_only": source_sync.get("truth_authority") == "admission_receipts_only",
        "hard_gated_routes_keep_backend_calls_skipped": cases[2]["status"] == "pass",
        "stale_support_not_rendered_as_fresh_answer": envelope.get("stale_prior_conflict_count") == 1
        and envelope.get("current_truth_count") == 1,
        "no_private_source_or_scope_leak": envelope.get("raw_private_payload_in_envelope") is False
        and envelope.get("raw_private_scope_in_envelope") is False
        and source_sync.get("raw_private_source_in_status") is False,
        "deep_route_capability_preserved": int(deep.get("semantic_backend_call_total") or 0) > 0,
    }
    issues = [key for key, value in proof.items() if value is not True] + [case["case_id"] for case in failures]
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "llm_calls_performed": False,
        "issue_count": len(issues),
        "issues": issues,
        "proof": proof,
        "case_count": len(cases),
        "failure_case_ids": [case["case_id"] for case in failures],
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "case_count", "issue_count", "issues")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
