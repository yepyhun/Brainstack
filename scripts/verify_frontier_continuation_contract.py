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

from brainstack.operating_loop import (  # noqa: E402
    build_frontier_continuation_contract,
    build_operating_loop_verdict,
)


REPORT_SCHEMA = "brainstack.frontier_continuation_contract_proof.v1"


def build_report() -> dict[str, object]:
    event_driven = build_frontier_continuation_contract(
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
    cadence_primary = build_frontier_continuation_contract(
        {
            "allocator": {
                "id": "allocator",
                "fixed_schedule": True,
                "creates_work": True,
                "reads_events": False,
            }
        }
    )
    missing_continuation = build_frontier_continuation_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "terminal_events": [{"event_id": "evt-gap", "task_id": "t-gap", "kind": "task_completed"}],
        }
    )
    duplicate = build_frontier_continuation_contract(
        {
            "controller": {"event_bridge_enabled": True},
            "terminal_events": [{"event_id": "evt-dup", "task_id": "t-dup", "kind": "task_completed"}],
            "continuation_records": [
                {"source_event_id": "evt-dup", "decision": "next_frontier_created"},
                {"source_event_id": "evt-dup", "decision": "next_frontier_created"},
            ],
        }
    )
    stopped = build_frontier_continuation_contract(
        {
            "state": "stopped_intentionally",
            "terminal_events": [{"event_id": "evt-stop", "task_id": "t-stop", "kind": "task_completed"}],
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
        and event_driven["controller_mode"] == "event_plus_watchdog",
        "cadence_primary_is_degraded_not_healthy": cadence_primary["verdict"] == "degraded"
        and cadence_primary["controller_mode"] == "cadence_primary"
        and cadence_primary["cadence_primary_allocator"] is True,
        "terminal_event_without_continuation_is_critical": missing_continuation["verdict"] == "critical"
        and missing_continuation["continuation_gap_count"] == 1,
        "continuation_record_closes_duplicate_terminal_event": duplicate["verdict"] == "healthy"
        and duplicate["continuation_gap_count"] == 0,
        "intentional_stop_is_not_critical": stopped["verdict"] == "stopped_intentionally",
        "operating_loop_cannot_hide_cadence_primary": operating_loop["verdict"] == "degraded"
        and "frontier_continuation_degraded" in operating_loop["blockers"],
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True
            for item in (event_driven, cadence_primary, missing_continuation, duplicate, stopped)
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
