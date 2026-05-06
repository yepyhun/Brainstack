#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from brainstack.adaptive_route_plan import evaluate_tank_shadow_oracle


def _current_truth_view(row_count: int = 1) -> dict[str, Any]:
    return {
        "schema": "brainstack.current_truth_view.v1",
        "status": "pass",
        "current_truth_rows": [
            {
                "event_id": "cme_current_1",
                "stable_fact_id": "profile:preferred_language",
                "target_slot": "profile.preferred_language",
                "answerable_current_truth": True,
                "receipt_id": "receipt_1",
                "source_event_id": "evt_1",
                "source_span_id": "span_1",
                "source_quote_hash": "sha256:quote",
            }
        ][:row_count],
        "counters": {"unsafe_answer_truth_projection_count": 0},
        "rebuild": {"freshness_status": "fresh", "freshness_diagnostics_present": True},
    }


def _cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "simple_profile",
            "query": "structured profile request",
            "query_understanding": {"profile_slot_targets": ["identity.name"]},
            "required_evidence_classes": ["profile"],
        },
        {
            "case_id": "ambiguous_query",
            "query": "structured ambiguous request",
            "query_understanding": {"ambiguity": True, "required_evidence_classes": ["profile"]},
            "required_evidence_classes": ["profile"],
        },
        {
            "case_id": "relation_tracking",
            "query": "structured relation request",
            "query_understanding": {"required_evidence_classes": ["temporal_graph"]},
            "required_evidence_classes": ["temporal_graph"],
        },
        {
            "case_id": "temporal_change",
            "query": "structured temporal change request",
            "query_understanding": {"required_evidence_classes": ["temporal_graph", "continuity"]},
            "required_evidence_classes": ["temporal_graph", "continuity"],
        },
        {
            "case_id": "conflict",
            "query": "structured conflict request",
            "query_understanding": {"required_evidence_classes": ["conflict"]},
            "required_evidence_classes": ["conflict"],
        },
        {
            "case_id": "corpus_answer",
            "query": "structured corpus answer request",
            "query_understanding": {"required_evidence_classes": ["corpus"]},
            "required_evidence_classes": ["corpus"],
        },
        {
            "case_id": "large_knowledge_body",
            "query": "structured large knowledge request",
            "query_understanding": {"required_evidence_classes": ["corpus", "aggregate"]},
            "required_evidence_classes": ["corpus", "aggregate"],
        },
        {
            "case_id": "multilingual_paraphrase",
            "query": "structured profile question",
            "query_understanding": {"profile_slot_targets": ["profile.preferred_language"], "language": "hu"},
            "required_evidence_classes": ["profile"],
        },
        {
            "case_id": "low_confidence",
            "query": "structured low confidence request",
            "query_understanding": {"low_candidate_confidence": True, "required_evidence_classes": ["profile"]},
            "required_evidence_classes": ["profile"],
        },
        {
            "case_id": "broker_disagreement",
            "query": "structured broker disagreement request",
            "query_understanding": {"broker_disagreement": True, "required_evidence_classes": ["corpus"]},
            "required_evidence_classes": ["corpus"],
        },
        {
            "case_id": "degraded_backend",
            "query": "structured degraded backend request",
            "query_understanding": {"required_evidence_classes": ["corpus"]},
            "required_evidence_classes": ["corpus"],
            "backend_health": {"corpus": "degraded"},
        },
        {
            "case_id": "protected_evidence",
            "query": "structured protected evidence request",
            "query_understanding": {"protected_evidence_risk": True, "required_evidence_classes": ["current_truth"]},
            "required_evidence_classes": ["current_truth"],
        },
    ]


def build_report() -> dict[str, Any]:
    report = evaluate_tank_shadow_oracle(_cases(), current_truth_view=_current_truth_view(1))
    report = dict(report)
    report["schema"] = "brainstack.tank_escalation_safety_verifier.v1"
    report["oracle"] = "full_depth_tank_shadow"
    report["safe_failure_mode"] = "over_escalation_not_under_retrieval"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify adaptive hotpath cannot under-call full-depth tank retrieval.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write JSON report.")
    args = parser.parse_args()

    report = build_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
