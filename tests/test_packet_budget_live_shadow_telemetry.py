from __future__ import annotations

from scripts.measure_packet_budget_live_shadow_telemetry import measure_live_like_shadow


def test_live_like_shadow_telemetry_meets_activation_thresholds() -> None:
    report = measure_live_like_shadow(sample_count=24, max_candidate_tokens=120)

    assert report["measurement_only"] is True
    assert report["production_savings_claim"] is False
    assert report["active_rollout_applied"] is False
    assert report["scenario_count"] >= 20
    assert report["distinct_scenario_family_count"] >= 6
    assert report["output_changed_in_shadow"] is False
    assert report["protected_truth_drop_attempts"] == 0
    assert report["baseline_candidate_tokens"] > report["shadow_budget_candidate_tokens"]
    assert report["estimated_delta_tokens"] > 0
    assert report["activation_verdict"] == "ACTIVATE_ACTIVE_FOR_SUPPORTED_PACKET_PATHS"


def test_live_like_shadow_telemetry_keeps_retrieval_fusion_deferred() -> None:
    report = measure_live_like_shadow(sample_count=24, max_candidate_tokens=120)

    assert report["retrieval_fusion_next_phase_required"] is False
    assert report["fusion_signal_count"] < 3
    assert report["fusion_signal_metrics"]["cross_shelf_wrong_winner_count"] == 0
    assert report["fusion_signal_metrics"]["durable_truth_crowded_by_transcript_count"] == 0
