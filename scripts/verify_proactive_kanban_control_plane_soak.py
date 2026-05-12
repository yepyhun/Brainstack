#!/usr/bin/env python3
"""Run the proactive/Kanban/controller control-plane soak gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_context_pressure_queue_liveness_proof import build_report as build_context_pressure_report  # noqa: E402
from scripts.verify_host_tool_result_budget import DEFAULT_HERMES_SOURCE, build_report as build_host_tool_budget_report  # noqa: E402
from scripts.verify_kanban_capability_evidence_ladder import build_report as build_kanban_report  # noqa: E402
from scripts.verify_kanban_recovery_candidate_contract import build_report as build_recovery_report  # noqa: E402
from scripts.verify_live_safe_kanban_gauntlet import build_report as build_kanban_gauntlet_report  # noqa: E402
from scripts.verify_operating_loop_liveness_contract import build_report as build_liveness_report  # noqa: E402
from scripts.verify_proactive_inspect_execute_split import build_report as build_inspect_execute_report  # noqa: E402
from scripts.verify_scheduler_lane_health_contract import build_report as build_scheduler_report  # noqa: E402
from scripts.verify_workstream_controller_contract import build_report as build_controller_report  # noqa: E402
from scripts.verify_hermes_auxiliary_compression_guard import build_report as build_compression_guard_report  # noqa: E402
from scripts.verify_frontier_continuation_contract import build_report as build_frontier_continuation_report  # noqa: E402


REPORT_SCHEMA = "brainstack.proactive_kanban_control_plane_soak.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _passed(report: Mapping[str, Any]) -> bool:
    return report.get("status") == "pass" and report.get("public_safe") is True and not report.get("issues")


def build_report() -> dict[str, Any]:
    kanban = build_kanban_report()
    inspect_execute = build_inspect_execute_report()
    gauntlet = build_kanban_gauntlet_report()
    controller = build_controller_report()
    host_budget = build_host_tool_budget_report(DEFAULT_HERMES_SOURCE)
    context_pressure = build_context_pressure_report()
    liveness = build_liveness_report()
    recovery = build_recovery_report()
    scheduler = build_scheduler_report()
    compression_guard = build_compression_guard_report()
    frontier_continuation = build_frontier_continuation_report()
    reports = {
        "kanban_capability_evidence_ladder": kanban,
        "proactive_inspect_execute_split": inspect_execute,
        "live_safe_kanban_gauntlet": gauntlet,
        "workstream_controller_contract": controller,
        "host_tool_result_budget": host_budget,
        "context_pressure_queue_liveness": context_pressure,
        "operating_loop_liveness_contract": liveness,
        "kanban_recovery_candidate_contract": recovery,
        "scheduler_lane_health_contract": scheduler,
        "hermes_auxiliary_compression_guard": compression_guard,
        "frontier_continuation_contract": frontier_continuation,
    }
    kanban_proof = _mapping(kanban.get("proof"))
    inspect_proof = _mapping(inspect_execute.get("proof"))
    gauntlet_proof = _mapping(gauntlet.get("proof"))
    controller_proof = _mapping(controller.get("proof"))
    host_proof = _mapping(host_budget.get("proof"))
    pressure_proof = _mapping(context_pressure.get("proof"))
    liveness_proof = _mapping(liveness.get("proof"))
    recovery_proof = _mapping(recovery.get("proof"))
    scheduler_proof = _mapping(scheduler.get("proof"))
    compression_proof = _mapping(compression_guard.get("proof"))
    continuation_proof = _mapping(frontier_continuation.get("proof"))
    proof = {
        "runtime_truth_snapshot_present": kanban_proof.get("dispatcher_snapshot_reports_wait_reasons") is True
        and kanban_proof.get("dispatcher_snapshot_reports_e2e_final_state") is True,
        "no_foreground_wait_guard_present": inspect_proof.get("foreground_wait_guard_concurrent_path") is True
        and inspect_proof.get("foreground_wait_guard_sequential_path") is True,
        "kanban_usefulness_gauntlet_present": gauntlet_proof.get("disposable_completed_task_reaches_final_state") is True
        and gauntlet_proof.get("controlled_block_is_not_false_success") is True,
        "controller_contract_blocks_filler": controller_proof.get("no_change_waits_without_work") is True
        and controller_proof.get("fixed_cadence_work_generator_requires_controller") is True,
        "event_replay_is_deterministic": controller_proof.get("replay_is_deterministic") is True
        and controller_proof.get("replay_duplicate_second_decision_waits") is True,
        "host_tool_context_pressure_guarded": host_proof.get("skill_view_86k_would_not_inline") is True
        and host_proof.get("brainstack_inspect_95k_would_not_inline") is True,
        "queue_liveness_guarded": pressure_proof.get("queue_liveness_report_passes") is True
        or context_pressure.get("status") == "pass",
        "operating_loop_split_brain_guarded": liveness_proof.get("split_brain_is_critical_not_healthy") is True
        and liveness_proof.get("fresh_artifact_cannot_mask_stale_loop") is True,
        "kanban_recovery_candidates_guarded": recovery_proof.get("unknown_assignee_candidate_present") is True
        and recovery_proof.get("does_not_auto_reassign_default") is True,
        "scheduler_starvation_guarded": scheduler_proof.get("heavy_job_plus_stale_lane_is_critical") is True,
        "compression_bad_fd_guarded": compression_proof.get("incident_detector_catches_bad_fd") is True
        and compression_proof.get("owner_classified_as_hermes") is True,
        "frontier_continuation_not_cadence_primary": continuation_proof.get("cadence_primary_is_degraded_not_healthy") is True
        and continuation_proof.get("terminal_event_without_continuation_is_critical") is True
        and continuation_proof.get("operating_loop_cannot_hide_cadence_primary") is True,
    }
    component_statuses = {name: report.get("status") for name, report in reports.items()}
    issues = [
        f"{name}:status"
        for name, report in reports.items()
        if not _passed(report)
    ]
    issues.extend(f"proof:{key}" for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "issues": sorted(issues),
        "proof": proof,
        "component_statuses": component_statuses,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify proactive/Kanban control-plane soak.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
