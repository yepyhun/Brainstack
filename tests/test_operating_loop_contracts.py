from __future__ import annotations

from scripts.verify_hermes_auxiliary_compression_guard import build_report as build_compression_report
from scripts.verify_kanban_recovery_candidate_contract import build_report as build_recovery_report
from scripts.verify_operating_loop_liveness_contract import build_report as build_liveness_report
from scripts.verify_scheduler_lane_health_contract import build_report as build_scheduler_report


def _assert_report_passes(report: dict) -> None:
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["side_effect_free"] is True
    assert report["issues"] == []
    assert all(report["proof"].values())


def test_operating_loop_liveness_contract_blocks_split_brain() -> None:
    report = build_liveness_report()

    _assert_report_passes(report)
    assert report["scenario_verdicts"]["split_brain"] == "critical"
    assert report["scenario_verdicts"]["artifact_only"] == "critical"


def test_kanban_recovery_candidate_contract_is_read_only() -> None:
    report = build_recovery_report()

    _assert_report_passes(report)
    assert report["candidate_count"] >= 4
    assert report["summary"]["failure_class_counts"]["unknown_assignee"] == 1


def test_scheduler_lane_health_contract_detects_starvation() -> None:
    report = build_scheduler_report()

    _assert_report_passes(report)
    assert report["scenario_verdicts"]["starvation"] == "critical"


def test_hermes_auxiliary_compression_guard_detects_bad_fd_incident() -> None:
    report = build_compression_report()

    _assert_report_passes(report)
    assert report["incident_guard_status"] == "fail"
    assert report["clean_guard_status"] == "pass"

