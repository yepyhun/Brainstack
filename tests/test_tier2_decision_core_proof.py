from __future__ import annotations

from scripts.run_tier2_decision_core_proof import run_proof


def test_tier2_decision_core_proof_passes() -> None:
    report = run_proof()

    assert report["status"] == "pass"
    assert report["cases_total"] >= 10
    assert report["cases_passed"] == report["cases_total"]
    assert all(value == 0 for value in report["critical_counters"].values())
    assert report["smarter_than_baseline"]["duplicate_prevention"] is True
    assert report["smarter_than_baseline"]["update_correctness"] is True
    assert report["smarter_than_baseline"]["conflict_precision"] is True
    assert report["smarter_than_baseline"]["support_preservation"] is True
    assert report["smarter_than_baseline"]["projection_consistency"] is True
    assert report["smarter_than_baseline"]["multilingual_metamorphic_stability"] is True
    assert report["smarter_than_baseline"]["baseline_advantage_cases"] >= 4

