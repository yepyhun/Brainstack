from __future__ import annotations

from scripts.verify_tank_escalation_safety import build_report


def test_tank_escalation_safety_verifier_has_zero_false_negative_misses() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.tank_escalation_safety_verifier.v1"
    assert report["status"] == "pass"
    assert report["false_negative_tank_miss_count"] == 0
    assert report["safe_failure_mode"] == "over_escalation_not_under_retrieval"
    assert all(
        case["sufficiency_status"] in {"sufficient", "escalated_to_tank"}
        for case in report["cases"]
    )
