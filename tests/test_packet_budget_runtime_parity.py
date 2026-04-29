from __future__ import annotations

from scripts.verify_packet_budget_runtime_parity import verify_runtime_parity


def test_runtime_parity_probe_verifies_active_and_disabled_paths() -> None:
    report = verify_runtime_parity()

    assert report["status"] == "pass"
    assert report["wizard_payload_contains_change"] is True
    assert report["active_budget_trace_present"] is True
    assert report["protected_truth_drop_attempts_runtime"] == 0
    assert report["candidate_token_delta_percent_runtime"] > 0
    assert report["operator_disable_path_verified"] is True
    assert report["disabled_mode_trace_explicit"] is True
    assert report["source_runtime_parity"] is True
