from __future__ import annotations

from pathlib import Path

from scripts.run_public_memory_kernel_fixtures import run_fixture_directory


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_evidence_trace_has_selected_and_dropped_reason_codes() -> None:
    result = run_fixture_directory(FIXTURE_DIR)

    for scenario in result["scenarios"]:
        trace = scenario["trace"]
        for candidate in trace["candidates"]:
            assert candidate["reason_code"]
            assert candidate["raw_text_included"] is False


def test_evidence_trace_proves_assistant_claim_dropped() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    scenario = next(
        item
        for item in result["scenarios"]
        if item["scenario_id"] == "assistant_contamination_public_001"
    )
    trace = scenario["trace"]

    assert trace["selected_answer_evidence"] == []
    assert trace["dropped_summary"] == [
        {
            "count": 1,
            "reason_code": "dropped_assistant_claim_not_truth_authority",
        }
    ]


def test_receipt_backed_trace_includes_proof_chain() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    scenario = next(
        item
        for item in result["scenarios"]
        if item["scenario_id"] == "explicit_capture_complete_public_001"
    )
    stages = [item["stage"] for item in scenario["trace"]["proof_chain"]]

    assert "source_span" in stages
    assert "capture_proposal" in stages
    assert "admission_decision" in stages
    assert "write_receipt" in stages
    assert "retrieval_candidate" in stages
    assert "packet_selection" in stages
