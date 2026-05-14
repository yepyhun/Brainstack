#!/usr/bin/env python3
"""Verify MemU-inspired memory-operation contracts stay bounded."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.memory_operation_pipeline import (  # noqa: E402
    build_memory_operation_pipeline_record,
    build_referenced_category_projection,
    build_retrieval_sufficiency_trace,
)


REPORT_SCHEMA = "brainstack.memory_operation_pipeline_proof.v1"


def build_report() -> dict[str, object]:
    pipeline = build_memory_operation_pipeline_record(
        operation="retrieval_packet_assembly",
        selected_seam="route_plan_to_packet_diagnostics",
        stages=[
            {"name": "route_plan", "status": "ok", "input_ref": "query", "output_ref": "plan"},
            {"name": "packet_budget", "status": "ok", "input_ref": "plan", "output_ref": "packet"},
        ],
        final_packet_state={"changed": False, "char_count": 420},
    )
    authority_change = build_memory_operation_pipeline_record(
        operation="retrieval_packet_assembly",
        selected_seam="route_plan_to_packet_diagnostics",
        stages=[{"name": "projection", "status": "ok"}],
        unchanged_authority=False,
    )
    projection = build_referenced_category_projection(
        category="current_truth",
        rows=[
            {
                "claim": "Current threshold is 0.9.",
                "receipt_id": "receipt-current",
                "truth_eligible": True,
                "is_current": True,
            },
            {
                "claim": "Old threshold was 0.5.",
                "receipt_id": "receipt-old",
                "truth_eligible": True,
                "is_current": False,
                "superseded_by": "receipt-current",
            },
            {
                "claim": "Support-only note.",
                "receipt_id": "receipt-support",
                "truth_eligible": False,
                "support_only": True,
            },
        ],
    )
    fast = build_retrieval_sufficiency_trace(
        query_class="profile",
        route_class="fast",
        evidence_counts={"profile": 2, "current_truth": 1},
    )
    degraded = build_retrieval_sufficiency_trace(
        query_class="documentation",
        route_class="semantic",
        evidence_counts={},
        backend_health={"semantic_status": "timeout"},
    )
    deep = build_retrieval_sufficiency_trace(
        query_class="documentation",
        route_class="corpus",
        evidence_counts={"corpus": 2, "graph": 1},
    )
    proof = {
        "pipeline_stage_record_is_read_only": pipeline["read_only"] is True
        and pipeline["truth_writer"] is False
        and pipeline["verdict"] == "healthy",
        "authority_change_fails_closed": authority_change["verdict"] == "critical",
        "projection_has_inline_refs": projection["authority_claims"][0]["rendered"].endswith("[ref:receipt-current]"),
        "projection_excludes_stale_authority": projection["authority_claim_count"] == 1
        and projection["excluded_count"] == 1,
        "support_only_not_authority": projection["support_claim_count"] == 1,
        "fast_profile_route_stops_without_corpus": fast["decision"] == "stop_fast",
        "degraded_semantic_backend_visible": degraded["decision"] == "degraded_partial",
        "corpus_needed_route_deepens": deep["decision"] == "deepen",
        "all_public_safe": all(
            item["public_safe"] is True
            for item in (pipeline, authority_change, projection, fast, degraded, deep)
        ),
        "read_only_side_effect_free": all(
            item["read_only"] is True and item["side_effect_free"] is True
            for item in (pipeline, authority_change, projection, fast, degraded, deep)
        ),
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "side_effect_free": True,
        "issues": issues,
        "proof": proof,
        "selected_seam": pipeline["selected_seam"],
        "route_decisions": {
            "fast": fast["decision"],
            "degraded": degraded["decision"],
            "deep": deep["decision"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify memory-operation pipeline contracts.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
