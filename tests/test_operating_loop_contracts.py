from __future__ import annotations

from scripts.verify_hermes_auxiliary_compression_guard import build_report as build_compression_report
from scripts.verify_frontier_continuation_contract import build_report as build_frontier_continuation_report
from scripts.verify_durable_work_state_contract import build_report as build_durable_work_report
from scripts.verify_kanban_recovery_candidate_contract import build_report as build_recovery_report
from scripts.verify_operating_loop_liveness_contract import build_report as build_liveness_report
from scripts.verify_scheduler_lane_health_contract import build_report as build_scheduler_report
from brainstack.operating_loop import build_operating_loop_verdict


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


def test_operating_loop_with_active_frontier_and_recent_failures_is_degraded() -> None:
    verdict = build_operating_loop_verdict(
        {
            "kanban_required": True,
            "kanban_runtime_snapshot": {
                "dispatcher_state": "workers_running",
                "running_worker_count": 2,
                "ready_task_count": 0,
                "recent_failure_event_kinds": ["crashed", "blocked"],
            },
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
            "next_action": {"exists": True, "requires_kanban": True},
        }
    )

    assert verdict["verdict"] == "degraded"
    assert "recent_kanban_failures" in verdict["warnings"]


def test_operating_loop_with_active_frontier_and_blocked_tasks_is_degraded() -> None:
    verdict = build_operating_loop_verdict(
        {
            "kanban_required": True,
            "kanban_runtime_snapshot": {
                "dispatcher_state": "workers_running",
                "running_worker_count": 1,
                "ready_task_count": 1,
                "blocked_task_count": 5,
            },
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
            "next_action": {"exists": True, "requires_kanban": True},
        }
    )

    assert verdict["verdict"] == "degraded"
    assert "blocked_kanban_tasks" in verdict["warnings"]
    assert "KANBAN_BLOCKED_TASKS_PRESENT" in verdict["reason_codes"]


def test_frontier_continuation_contract_blocks_cadence_primary_claim() -> None:
    report = build_frontier_continuation_report()

    _assert_report_passes(report)
    assert report["scenario_verdicts"]["cadence_primary"] == "degraded"
    assert report["scenario_verdicts"]["missing_continuation"] == "critical"


def test_durable_work_state_contract_blocks_ack_before_durability() -> None:
    report = build_durable_work_report()

    _assert_report_passes(report)
    assert report["scenario_verdicts"]["ack_before_durability"] == "critical"
    assert report["operating_loop_verdict"] == "critical"


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
