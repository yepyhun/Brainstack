#!/usr/bin/env python3
"""Verify event-driven frontier continuation contract."""

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


REPORT_SCHEMA = "brainstack.frontier_continuation_contract_proof.v1"


def build_report() -> dict[str, object]:
    event_driven = build_continuation_control_contract(
        {
            "controller": {"event_bridge_enabled": True, "watchdog_enabled": True},
            "terminal_events": [
                {
                    "event_id": "evt-1",
                    "task_id": "t-1",
                    "kind": "task_completed",
                    "continuation_decision": "next_frontier_created",
                }
            ],
        }
    )
    cadence_primary = build_continuation_control_contract(
        {
            "allocator": {
                "id": "allocator",
                "fixed_schedule": True,
                "creates_work": True,
                "reads_events": False,
            }
        }
    )
    missing_continuation = build_continuation_control_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "terminal_events": [{"event_id": "evt-gap", "task_id": "t-gap", "kind": "task_completed"}],
        }
    )
    duplicate = build_continuation_control_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "terminal_events": [{"event_id": "evt-dup", "task_id": "t-dup", "kind": "task_completed"}],
            "continuation_records": [
                {"source_event_id": "evt-dup", "decision": "next_frontier_created"},
                {"source_event_id": "evt-dup", "decision": "next_frontier_created"},
            ],
        }
    )
    stopped = build_continuation_control_contract(
        {
            "state": "stopped_intentionally",
            "terminal_events": [{"event_id": "evt-stop", "task_id": "t-stop", "kind": "task_completed"}],
        }
    )
    prompt_primary = build_continuation_control_contract(
        {
            "controller": {"controller_mode": "prompt_primary", "normal_path_uses_llm": True},
            "token_policy": {"model_calls": 1, "max_input_tokens": 50000},
        }
    )
    dry_run_as_live = build_continuation_control_contract(
        {
            "controller": {
                "event_bridge_enabled": True,
                "dry_run": True,
                "presented_as_live": True,
            }
        }
    )
    cursor_stale = build_continuation_control_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "event_cursor": {"last_event_id": 10, "max_terminal_event_id": 12},
        }
    )
    llm_worker = build_continuation_control_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "token_policy": {"role": "worker", "model_calls": 1, "max_input_tokens": 2000},
        }
    )
    operating_loop = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {"dispatcher_state": "ready_idle"},
            "frontier_continuation": cadence_primary,
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
        }
    )

    proof = {
        "event_bridge_plus_watchdog_is_healthy": event_driven["verdict"] == "healthy"
        and event_driven["controller_mode"] == "event_primary",
        "cadence_primary_is_degraded_not_healthy": cadence_primary["verdict"] == "degraded"
        and cadence_primary["controller_mode"] == "cadence_primary"
        and cadence_primary["cadence_primary_allocator"] is True,
        "prompt_primary_token_waste_is_critical": prompt_primary["verdict"] == "critical"
        and prompt_primary["controller_mode"] == "prompt_primary"
        and prompt_primary["token_policy"] == "violation",
        "dry_run_cannot_satisfy_live_health": dry_run_as_live["verdict"] == "critical"
        and "DRY_RUN_PRESENTED_AS_LIVE" in dry_run_as_live["reason_codes"],
        "stale_event_cursor_is_degraded": cursor_stale["verdict"] == "degraded"
        and cursor_stale["controller_mode"] == "event_primary_stale",
        "llm_worker_is_allowed_when_not_primary_control": llm_worker["verdict"] == "healthy"
        and llm_worker["token_policy"] == "llm_worker_allowed",
        "terminal_event_without_continuation_is_critical": missing_continuation["verdict"] == "critical"
        and missing_continuation["continuation_gap_count"] == 1,
        "continuation_record_closes_duplicate_terminal_event": duplicate["verdict"] == "healthy"
        and duplicate["continuation_gap_count"] == 0,
        "intentional_stop_is_not_critical": stopped["verdict"] == "stopped_intentionally",
        "operating_loop_cannot_hide_cadence_primary": operating_loop["verdict"] == "degraded"
        and "frontier_continuation_degraded" in operating_loop["blockers"],
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True
            for item in (
                event_driven,
                cadence_primary,
                missing_continuation,
                duplicate,
                stopped,
                prompt_primary,
                dry_run_as_live,
                cursor_stale,
                llm_worker,
            )
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
            "event_driven": event_driven["verdict"],
            "cadence_primary": cadence_primary["verdict"],
            "missing_continuation": missing_continuation["verdict"],
            "duplicate": duplicate["verdict"],
            "stopped": stopped["verdict"],
            "prompt_primary": prompt_primary["verdict"],
            "dry_run_as_live": dry_run_as_live["verdict"],
            "cursor_stale": cursor_stale["verdict"],
            "llm_worker": llm_worker["verdict"],
            "operating_loop_with_cadence_primary": operating_loop["verdict"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify frontier continuation contract.")
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
