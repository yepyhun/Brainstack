from __future__ import annotations

from pathlib import Path

from scripts.measure_public_memory_token_cost import measure_fixture_directory


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_memory_token_cost_baseline_is_measurement_only() -> None:
    report = measure_fixture_directory(FIXTURE_DIR)

    assert report["schema"] == "brainstack.public_memory_token_cost_baseline.v1"
    assert report["measurement_only"] is True
    assert report["production_optimization_enabled"] is False
    assert "savings_percent" not in report
    assert report["fixture_status"] == "pass"


def test_public_memory_token_cost_baseline_covers_public_scenarios() -> None:
    report = measure_fixture_directory(FIXTURE_DIR)

    assert report["aggregate"]["scenario_count"] >= 5
    assert report["aggregate"]["total_candidate_tokens"] > 0
    assert report["aggregate"]["selected_candidate_tokens"] > 0
    assert report["aggregate"]["trace_overhead_tokens"] > 0
    assert all(item["trace_complete_for_audit"] for item in report["scenarios"])


def test_contamination_fixture_has_measurable_dropped_candidate_cost() -> None:
    report = measure_fixture_directory(FIXTURE_DIR)
    scenario = next(
        item
        for item in report["scenarios"]
        if item["scenario_id"] == "assistant_contamination_public_001"
    )

    assert scenario["dropped_candidate_count"] > 0
    assert scenario["dropped_candidate_tokens"] > 0
    assert "dropped_assistant_claim_not_truth_authority" in scenario["dropped_tokens_by_reason"]
