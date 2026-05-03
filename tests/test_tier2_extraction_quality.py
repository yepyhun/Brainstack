from __future__ import annotations

from brainstack.tier2_extraction_quality import (
    build_tier2_extraction_quality_report,
    public_safe_fixtures,
)


def test_tier2_extraction_quality_report_passes_public_safe_fixtures() -> None:
    report = build_tier2_extraction_quality_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["metrics"]["proposal_precision"] == 1.0
    assert report["metrics"]["proposal_recall"] == 1.0
    assert report["metrics"]["update_supersession_correctness"] == 1.0
    assert report["metrics"]["conflict_precision"] == 1.0
    assert report["metrics"]["support_preservation"] == 1.0
    assert report["metrics"]["multilingual_robustness"] == 1.0
    assert report["metrics"]["donor_drift_detection"] == 1.0
    assert report["bloat_impact"]["status"] == "pass"
    assert all(value == 0 for value in report["harmful_counters"].values())
    assert report["failure_bundles"]["unresolved"] == []
    assert {item["bundle_id"] for item in report["failure_bundles"]["resolved"]} >= {
        "assistant_authored_truth_attempt_blocked",
        "missing_verified_source_blocked",
        "unsupported_donor_action_drift_blocked",
        "ignored_donor_action_not_durable_truth",
    }


def test_tier2_extraction_quality_fails_closed_on_oracle_mismatch() -> None:
    fixtures = public_safe_fixtures()
    fixtures[0]["expected_decisions"][0]["decision_class"] = "inspect_only"

    report = build_tier2_extraction_quality_report(fixtures=fixtures)

    assert report["status"] == "fail"
    assert report["harmful_counters"]["unresolved_failure_bundles"] == 1
    assert report["failure_bundles"]["unresolved"][0]["fixture_id"] == "durable_profile_fact"


def test_tier2_extraction_quality_blocks_unsafe_donor_output_from_truth() -> None:
    report = build_tier2_extraction_quality_report()
    cases = {case["id"]: case for case in report["cases"]}

    assert cases["assistant_authored_truth_dropped"]["batch_status"] == "degraded"
    assert cases["assistant_authored_truth_dropped"]["decision_count"] == 0
    assert cases["missing_source_inspect_only"]["decisions"][0]["truth_eligible"] is False
    assert cases["unsupported_donor_action_drift"]["decisions"][0]["truth_eligible"] is False
    assert cases["ignored_action_not_truth"]["decisions"][0]["truth_eligible"] is False


def test_tier2_extraction_quality_bloat_budget_is_enforced() -> None:
    report = build_tier2_extraction_quality_report(bloat_ratio_threshold=0.1)

    assert report["status"] == "fail"
    assert report["bloat_impact"]["status"] == "fail"
    assert report["harmful_counters"]["bloat_budget_failures"] == 1
