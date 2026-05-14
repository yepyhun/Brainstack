#!/usr/bin/env python3
"""Verify the operating-loop liveness and split-brain contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.continuation_control_contract import build_continuation_control_contract  # noqa: E402
from brainstack.operating_loop import build_operating_loop_verdict  # noqa: E402


REPORT_SCHEMA = "brainstack.operating_loop_liveness_contract_proof.v1"


def build_report() -> dict[str, object]:
    healthy = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {
                "dispatcher_state": "workers_running",
                "running_worker_count": 1,
                "ready_task_count": 1,
            },
            "signal_bus": {"last_run_age_seconds": 60, "stale_after_seconds": 600},
            "executor": {"last_run_age_seconds": 45, "stale_after_seconds": 600},
            "next_action": {"exists": True},
        }
    )
    split_brain = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {
                "dispatcher_state": "blocked_ready_tasks",
                "running_worker_count": 0,
                "ready_task_count": 2,
                "blocked_unknown_assignee_count": 2,
                "wait_reasons": [
                    {"task_id": "t-a", "reason_code": "blocked_unknown_assignee", "assignee": "worker"}
                ],
            },
            "signal_bus": {"last_run_age_seconds": 5000, "stale_after_seconds": 600},
            "executor": {"last_run_age_seconds": 5000, "stale_after_seconds": 600},
            "builder": {"last_run_age_seconds": 30, "stale_after_seconds": 900},
        }
    )
    intentional = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {"dispatcher_state": "ready_idle"},
            "next_action": {"human_gate": True},
        }
    )
    insufficient = build_operating_loop_verdict({})
    artifact_only = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {"dispatcher_state": "ready_idle"},
            "builder": {"last_run_age_seconds": 20, "stale_after_seconds": 900},
            "signal_bus": {"last_run_age_seconds": 1200, "stale_after_seconds": 600},
            "executor": {"last_run_age_seconds": 1200, "stale_after_seconds": 600},
        }
    )
    cadence_primary = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {"dispatcher_state": "ready_idle"},
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
            "frontier_continuation": build_continuation_control_contract(
                {
                    "allocator": {
                        "id": "allocator",
                        "fixed_schedule": True,
                        "creates_work": True,
                        "reads_events": False,
                    }
                }
            ),
        }
    )

    proof = {
        "healthy_requires_frontier_and_fresh_lanes": healthy["verdict"] == "healthy",
        "split_brain_is_critical_not_healthy": split_brain["verdict"] == "critical"
        and split_brain["split_brain_detected"] is True
        and "SPLIT_BRAIN_ACTIVITY" in split_brain["reason_codes"],
        "intentional_stop_is_not_critical": intentional["verdict"] == "stopped_intentionally",
        "empty_evidence_is_not_healthy": insufficient["verdict"] == "insufficient_evidence",
        "fresh_artifact_cannot_mask_stale_loop": artifact_only["verdict"] == "critical"
        and artifact_only["split_brain_detected"] is True,
        "cadence_primary_frontier_is_not_healthy": cadence_primary["verdict"] == "degraded"
        and "frontier_continuation_degraded" in cadence_primary["blockers"],
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True
            for item in (healthy, split_brain, intentional, insufficient, artifact_only, cadence_primary)
        ),
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "side_effect_free": True,
        "issues": issues,
        "proof": proof,
        "scenario_verdicts": {
            "healthy": healthy["verdict"],
            "split_brain": split_brain["verdict"],
            "intentional": intentional["verdict"],
            "insufficient": insufficient["verdict"],
            "artifact_only": artifact_only["verdict"],
            "cadence_primary": cadence_primary["verdict"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify operating-loop liveness contract.")
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
