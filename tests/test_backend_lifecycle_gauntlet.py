from __future__ import annotations

from scripts.run_backend_lifecycle_gauntlet import run_gauntlet


def test_backend_lifecycle_gauntlet_metrics_pass() -> None:
    report, failures = run_gauntlet()

    assert report["status"] == "pass"
    assert report["scenario_count"] >= 80
    assert report["scenario_family_count"] >= 15
    assert report["doctor_false_fail_count"] == 0
    assert report["doctor_false_pass_count"] == 0
    assert report["silent_degraded_backend_count"] == 0
    assert report["force_unlock_path_count"] == 0
    assert report["hidden_backend_disable_count"] == 0
    assert report["backend_claim_mismatch_count"] == 0
    assert report["memory_core_regression_count"] == 0
    assert report["private_artifact_leak_count"] == 0
    assert report["manual_only_proof"] is False
    assert failures == []
