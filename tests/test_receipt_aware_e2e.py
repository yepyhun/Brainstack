from __future__ import annotations

from scripts.run_receipt_aware_gateway_e2e import build_receipt_aware_gateway_e2e


def test_e2e_explicit_capture_requires_write_receipt() -> None:
    result = build_receipt_aware_gateway_e2e()
    scenario = next(s for s in result["scenarios"] if s["scenario_id"] == "provider_ack_without_receipt_blocked")

    assert scenario["status"] == "pass"
    assert scenario["trace"]["memory_commitment_guard"]["final_answer_allowed"] is False


def test_e2e_full_ack_requires_complete_receipt_coverage() -> None:
    result = build_receipt_aware_gateway_e2e()
    scenario = next(s for s in result["scenarios"] if s["scenario_id"] == "complete_capture_receipt_coverage")

    assert scenario["status"] == "pass"
    assert scenario["trace"]["receipt_coverage"]["coverage_status"] == "complete"
    assert scenario["trace"]["ack_plan"]["ack_mode"] == "full"


def test_e2e_partial_receipt_coverage_forbids_full_ack() -> None:
    result = build_receipt_aware_gateway_e2e()
    scenario = next(s for s in result["scenarios"] if s["scenario_id"] == "partial_capture_receipt_coverage")

    assert scenario["status"] == "pass"
    assert scenario["receipt_coverage"]["coverage_status"] == "partial"
    assert scenario["ack_plan"]["ack_mode"] == "partial"
    assert scenario["ack_plan"]["must_not_claim_full_commit"] is True


def test_e2e_reset_recall_matches_covered_proposals_only() -> None:
    result = build_receipt_aware_gateway_e2e()
    scenario = next(s for s in result["scenarios"] if s["scenario_id"] == "complete_capture_receipt_coverage")
    covered = scenario["trace"]["receipt_coverage"]["covered_proposals"]
    expected = [proposal["proposal_id"] for proposal in scenario["trace"]["capture_plan"]["proposals"]]

    assert covered == expected


def test_e2e_url_inspect_without_web_does_not_guess() -> None:
    result = build_receipt_aware_gateway_e2e()
    scenario = next(s for s in result["scenarios"] if s["scenario_id"] == "url_unavailable_no_guess")

    assert scenario["status"] == "pass"
    assert scenario["url_guard"]["reason_code"] == "CAPABILITY_UNAVAILABLE_DIAGNOSTIC"


def test_ga_dashboard_blocks_receiptless_commitment() -> None:
    result = build_receipt_aware_gateway_e2e()

    assert result["receiptless_commitment_count"] == 0
    assert result["incomplete_coverage_full_ack_count"] == 0
