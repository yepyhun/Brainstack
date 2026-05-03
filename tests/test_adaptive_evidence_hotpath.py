from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from brainstack.adaptive_evidence_hotpath import (
    HOTPATH_REPORT_SCHEMA,
    build_hotpath_report,
    summarize_hotpath_case,
    validate_hotpath_report,
)
from scripts.verify_adaptive_evidence_hotpath import run_hotpath_baseline


PRIVATE_TEXT = "Laura private raw memory text must never appear"


def _sample_packet() -> dict[str, Any]:
    return {
        "routing": {
            "requested_mode": "fact",
            "applied_mode": "fact",
            "source": "test",
            "reason": f"route reason containing {PRIVATE_TEXT}",
            "fallback_used": False,
            "resolution_status": "resolved",
        },
        "channels": [
            {"name": "keyword", "status": "ok", "candidate_count": 2},
            {"name": "graph", "status": "ok", "candidate_count": 1},
        ],
        "profile_items": [{"stable_key": "identity:name", "content": PRIVATE_TEXT}],
        "task_rows": [],
        "operating_rows": [],
        "matched": [{"content": PRIVATE_TEXT}],
        "recent": [],
        "transcript_rows": [],
        "graph_rows": [{"subject_name": PRIVATE_TEXT}],
        "corpus_rows": [],
        "fused_candidates": [{"key": "profile:identity:name"}, {"key": "graph:1"}],
        "packet_budget": {
            "mode": "shadow",
            "enabled": True,
            "applied_to_output": False,
            "status": "applied",
            "estimated_tokens_before": 42,
            "selected_candidate_tokens": 30,
            "dropped_candidate_tokens": 12,
            "authority_minimum_tokens": 10,
            "fail_closed": False,
            "budget_decisions": [
                {
                    "candidate_id": "profile:identity:name",
                    "decision": "selected",
                    "reason_code": "selected_budget_protected_authority",
                    "token_estimate": 10,
                },
                {
                    "candidate_id": "matched:1",
                    "decision": "dropped",
                    "reason_code": "dropped_budget_support_only",
                    "token_estimate": 12,
                },
            ],
            "raw_text_in_budget_trace": False,
            "answer_evidence_preserved": True,
            "receipt_coverage_preserved": True,
            "authority_fields_preserved": True,
            "scope_fields_preserved": True,
        },
        "block": PRIVATE_TEXT,
    }


def test_hotpath_case_summary_is_public_safe_and_structural_only() -> None:
    packet = _sample_packet()
    before = deepcopy(packet)

    case = summarize_hotpath_case(
        case_id="case_profile_current_truth",
        query_class="profile_current_truth",
        query_text=f"What is my name? {PRIVATE_TEXT}",
        packet=packet,
        latency_ms=12.3456,
        bloat_report={
            "schema": "brainstack.persistent_bloat_report.v1",
            "status": "pass",
            "issue_count": 0,
            "metrics": {
                "write_amplification": {
                    "storage_rows": 3,
                    "answer_authority_rows": 1,
                    "ratio": 3.0,
                }
            },
            "metric_statuses": {"write_amplification": {"status": "pass", "issue_code": ""}},
        },
        behavior_changed_from_unbudgeted=False,
        storage_mutation_count=0,
    )

    encoded = json.dumps(case, sort_keys=True)
    assert PRIVATE_TEXT not in encoded
    assert "block" not in case
    assert "query_text" not in case
    assert case["route"]["applied_mode"] == "fact"
    assert case["route"]["reason_fingerprint"].startswith("sha256:")
    assert case["shelf_fanout"] == {
        "profile": 1,
        "task": 0,
        "operating": 0,
        "continuity_match": 1,
        "continuity_recent": 0,
        "transcript": 0,
        "graph": 1,
        "corpus": 0,
    }
    assert case["candidate_counts"]["fused"] == 2
    assert case["candidate_counts"]["budget_selected"] == 1
    assert case["candidate_counts"]["budget_dropped"] == 1
    assert case["token_estimate"]["estimated_tokens_before"] == 42
    assert case["protected_truth_counters"]["protected_drop_attempts"] == 0
    assert case["write_amplification"]["ratio"] == 3.0
    assert case["read_only_probe"]["behavior_changed_from_unbudgeted"] is False
    assert packet == before


def test_hotpath_report_validation_rejects_raw_payload_shapes() -> None:
    report = build_hotpath_report(
        cases=[
            summarize_hotpath_case(
                case_id="case_minimal",
                query_class="no_memory_minimal",
                query_text="No memory probe",
                packet=_sample_packet(),
                latency_ms=1.0,
            )
        ]
    )

    assert report["schema"] == HOTPATH_REPORT_SCHEMA
    assert validate_hotpath_report(report) == []

    poisoned = deepcopy(report)
    poisoned["cases"][0]["raw_text"] = PRIVATE_TEXT
    errors = validate_hotpath_report(poisoned)
    assert "public_safe_forbidden_key:cases.0.raw_text" in errors


@pytest.mark.parametrize(
    "query_class",
    [
        "no_memory_minimal",
        "profile_current_truth",
        "temporal_graph",
        "corpus",
        "continuity",
        "noisy_high_fanout",
    ],
)
def test_verifier_covers_required_query_classes(query_class: str, tmp_path: Path) -> None:
    report = run_hotpath_baseline(out_path=tmp_path / "hotpath.json")

    assert query_class in {case["query_class"] for case in report["cases"]}
    assert (tmp_path / "hotpath.json").exists()
    assert validate_hotpath_report(report) == []
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["behavior_delta_count"] == 0
    assert report["storage_mutation_count"] == 0
    assert PRIVATE_TEXT not in json.dumps(report, sort_keys=True)


def test_verifier_exits_nonzero_on_schema_or_public_safety_failure(tmp_path: Path) -> None:
    report = build_hotpath_report(
        cases=[
            summarize_hotpath_case(
                case_id="case_minimal",
                query_class="no_memory_minimal",
                query_text="No memory probe",
                packet=_sample_packet(),
                latency_ms=1.0,
            )
        ]
    )
    report["schema"] = "wrong"

    errors = validate_hotpath_report(report)

    assert "invalid_schema" in errors
