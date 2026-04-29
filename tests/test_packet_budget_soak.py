from __future__ import annotations

import json

from scripts.run_packet_budget_soak import run_packet_budget_soak


def test_packet_budget_soak_public_safe_thresholds() -> None:
    report = run_packet_budget_soak(sample_count=100, max_candidate_tokens=120)

    assert report["status"] == "pass"
    assert report["scenario_count"] >= 100
    assert report["scenario_family_count"] >= 10
    assert report["protected_truth_drop_attempts"] == 0
    assert report["selected_evidence_fingerprint_mismatch_count"] == 0
    assert report["trace_complete_count"] == report["scenario_count"]
    assert report["soak_artifact_leak_findings"] == 0
    assert report["failure_bundle_count"] == 0
    assert report["candidate_token_delta_percent"] > 0
    assert report["retrieval_fusion_next_phase_required"] is False

    text = json.dumps(report)
    assert "ExampleHandle" not in text
    assert "NevaMind" not in text
