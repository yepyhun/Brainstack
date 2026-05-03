#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from brainstack.adaptive_consolidation import build_adaptive_consolidation_report, build_derived_work_item


def _items() -> list[dict[str, Any]]:
    return [
        build_derived_work_item("dw_graph_complete", "graph_projection", "complete", source_event_id="evt_1", source_span_id="span_1"),
        build_derived_work_item("dw_current_complete", "current_truth_view", "complete", source_event_id="evt_2", source_span_id="span_2"),
        build_derived_work_item("dw_corpus_complete", "corpus_index", "complete", source_event_id="evt_3", source_span_id="span_3"),
        build_derived_work_item("dw_semantic_complete", "semantic_index", "complete", source_event_id="evt_4", source_span_id="span_4"),
    ]


def _failure_fixtures() -> list[dict[str, Any]]:
    return [
        build_derived_work_item(
            "dw_stalled_visible",
            "graph_projection",
            "pending",
            source_event_id="evt_f1",
            source_span_id="span_f1",
            retry_count=2,
            last_error_class="stalled_queue",
            freshness_status="stale",
        ),
        build_derived_work_item(
            "dw_malformed_visible",
            "current_truth_view",
            "failed",
            source_event_id="evt_f2",
            source_span_id="span_f2",
            retry_count=1,
            last_error_class="malformed_derived_payload",
            freshness_status="failed",
            payload={"raw_text": "private source text"},
        ),
        build_derived_work_item(
            "dw_rebuild_mismatch_visible",
            "current_truth_view",
            "failed",
            source_event_id="evt_f3",
            source_span_id="span_f3",
            retry_count=1,
            last_error_class="rebuild_mismatch",
            freshness_status="failed",
        ),
        build_derived_work_item(
            "dw_backend_unavailable_visible",
            "corpus_index",
            "failed",
            source_event_id="evt_f4",
            source_span_id="span_f4",
            retry_count=3,
            last_error_class="backend_unavailable",
            freshness_status="failed",
        ),
    ]


def build_report(*, baseline_path: str | None = None) -> dict[str, Any]:
    del baseline_path
    consolidation = build_adaptive_consolidation_report(
        _items(),
        baseline={"write_amplification": 6, "active_packet_tokens": 420, "projection_rebuild_size": 9},
        write_amplification=4,
        active_packet_tokens=360,
        projection_rebuild_size=7,
        duplicate_support_only_accumulation=0,
    )
    failure_visibility = build_adaptive_consolidation_report(_failure_fixtures())
    failures: list[str] = []
    if consolidation["status"] != "pass":
        failures.append("consolidation_status_not_pass")
    if not consolidation["anti_goal_proof"]["async_without_lying"]:
        failures.append("async_without_lying_not_proven")
    if not consolidation["bloat_control"]["bounded"]:
        failures.append("state_garbage_not_bounded")
    if failure_visibility["readiness"]["ready_claim_allowed"] is not False:
        failures.append("failure_readiness_claimed")
    if failure_visibility["counters"]["stalled_count"] != 1:
        failures.append("stalled_queue_not_visible")
    if failure_visibility["counters"]["malformed_payload_count"] != 1:
        failures.append("malformed_payload_not_visible")
    if failure_visibility["counters"]["rebuild_mismatch_count"] != 1:
        failures.append("rebuild_mismatch_not_visible")
    if failure_visibility["counters"]["backend_unavailable_count"] != 1:
        failures.append("backend_unavailable_not_visible")
    if "private source text" in json.dumps(failure_visibility, ensure_ascii=False, sort_keys=True):
        failures.append("failure_bundle_leaks_private_text")
    return {
        "schema": "brainstack.adaptive_consolidation_verifier.v1",
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "summary": {
            "async_without_lying": consolidation["anti_goal_proof"]["async_without_lying"],
            "bounded_state_garbage": consolidation["bloat_control"]["bounded"],
            "durable_truth_deferred_count": consolidation["counters"]["durable_truth_deferred_count"],
            "hidden_readiness_claim_count": consolidation["counters"]["hidden_readiness_claim_count"],
            "write_amplification_delta": consolidation["bloat_control"]["write_amplification_delta"],
            "active_packet_growth_delta": consolidation["bloat_control"]["active_packet_growth_delta"],
            "projection_rebuild_size_delta": consolidation["bloat_control"]["projection_rebuild_size_delta"],
            "failure_fixture_count": len(failure_visibility["items"]),
        },
        "consolidation": consolidation,
        "failure_visibility": failure_visibility,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify adaptive async consolidation boundaries and bloat controls.")
    parser.add_argument("--baseline", type=Path, default=None, help="Optional S01 hot-path baseline path.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write JSON report.")
    args = parser.parse_args()

    report = build_report(baseline_path=str(args.baseline) if args.baseline else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
