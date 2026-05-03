from __future__ import annotations

from scripts.verify_adaptive_evidence_kernel import build_report


def test_adaptive_evidence_kernel_final_report_passes_integrated_contract() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.adaptive_evidence_kernel_report.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["active_default"] is True
    assert report["protected_truth_drops"] == 0
    assert report["tank_false_negative_misses"] == 0
    assert report["bad_success_checks"]["status"] == "pass"
    assert report["runtime_cases"]
    assert all(case["status"] == "pass" for case in report["runtime_cases"])
    assert report["integrated_components"]["adaptive_route_plan"]["status"] == "pass"
    assert report["integrated_components"]["adaptive_evidence_broker"]["status"] == "pass"
    assert report["integrated_components"]["current_truth_view"]["status"] == "pass"
    assert report["integrated_components"]["async_consolidation"]["status"] == "pass"


def test_adaptive_evidence_kernel_fails_bad_success_states() -> None:
    fixtures = {
        "default_off": "active default must remain enabled",
        "shadow_only": "shadow-only packet budget is not product-ready",
        "hidden_fallback": "hidden fallback must be visible",
        "depth_disabled_for_tokens": "token savings cannot disable depth",
        "second_truth_authority": "current-truth view cannot become second truth authority",
        "stale_current_truth": "stale current-truth view blocks final kernel",
        "invisible_async_failure": "async failure must be visible",
        "tank_false_negative": "tank false-negative miss blocks final kernel",
        "public_safety_leak": "public reports must stay public-safe",
    }

    for fixture, expected_reason in fixtures.items():
        report = build_report(fixture=fixture)

        assert report["status"] == "fail"
        assert expected_reason in report["bad_success_checks"]["failure_reasons"]
        assert report["release_gate"]["release_allowed"] is False
