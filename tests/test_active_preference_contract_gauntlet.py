from __future__ import annotations

from scripts.run_active_preference_contract_gauntlet import run_gauntlet


def test_active_preference_contract_public_safe_gauntlet(tmp_path) -> None:
    report = run_gauntlet(output_dir=tmp_path)
    metrics = report["metrics"]

    assert report["status"] == "pass"
    assert metrics["scenario_count"] >= 150
    assert metrics["scenario_family_count"] >= 15
    assert metrics["accepted_explicit_preference_accuracy"] == "100%"
    assert metrics["ambiguous_preference_active_false_positive_count"] == 0
    assert metrics["assistant_claim_active_false_positive_count"] == 0
    assert metrics["no_op_false_positive_count"] == 0
    assert metrics["supersession_failure_count"] == 0
    assert metrics["delivery_missing_count"] == 0
    assert metrics["delivery_false_claim_count"] == 0
    assert metrics["compaction_rebuild_delivery_failure_count"] == 0
    assert metrics["prompt_rebuild_id_missing_count"] == 0
    assert metrics["compaction_event_id_missing_count"] == 0
    assert metrics["contract_version_missing_count"] == 0
    assert metrics["contract_status_missing_count"] == 0
    assert metrics["overflow_silent_drop_count"] == 0
    assert metrics["soul_override_failure_count"] == 0
    assert metrics["private_artifact_leak_count"] == 0
    assert metrics["raw_private_text_in_trace_count"] == 0
    assert metrics["unsupported_backend_dependency_count"] == 0
    assert metrics["manual_only_proof"] is False
