#!/usr/bin/env python3
"""Verify the universal workstream controller decision contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.workstream_controller import (  # noqa: E402
    build_controller_decision,
    classify_cadence_job,
    controller_status,
    replay_controller_events,
)


REPORT_SCHEMA = "brainstack.workstream_controller_contract_proof.v1"


def build_report() -> dict[str, Any]:
    wait = build_controller_decision(workstream_id="smoke", event={}, scores={})
    ask = build_controller_decision(
        workstream_id="smoke",
        event={"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "risk"},
        scores={"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.8, "novelty": 0.8},
    )
    handoff = build_controller_decision(
        workstream_id="smoke",
        event={
            "kind": "task_completed",
            "changed_inputs": ["parent_done"],
            "idempotency_key": "handoff",
            "next_task_title": "Disposable next step",
        },
        scores={"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8},
    )
    duplicate = build_controller_decision(
        workstream_id="smoke",
        event={"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "seen"},
        state={"seen_idempotency_keys": ["seen"]},
        scores={"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8},
    )
    budget_stop = build_controller_decision(
        workstream_id="smoke",
        event={"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "budget"},
        state={"budget_remaining": 0},
        scores={"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8},
    )
    replay_a = replay_controller_events(
        workstream_id="smoke",
        events=[
            {"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "replay", "scores": {"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8}},
            {"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "replay", "scores": {"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8}},
        ],
    )
    replay_b = replay_controller_events(
        workstream_id="smoke",
        events=[
            {"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "replay", "scores": {"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8}},
            {"kind": "task_completed", "changed_inputs": ["done"], "idempotency_key": "replay", "scores": {"expected_value_next": 0.9, "confidence": 0.8, "intervention_risk": 0.1, "novelty": 0.8}},
        ],
    )
    status = controller_status([wait, handoff, duplicate, budget_stop])
    heartbeat = classify_cadence_job({"id": "heartbeat", "kind": "heartbeat", "fixed_schedule": True})
    filler = classify_cadence_job({"id": "builder", "creates_work": True, "fixed_schedule": True, "reads_events": False})
    event_gated = classify_cadence_job({"id": "candidate", "creates_artifact": True, "fixed_schedule": True, "reads_events": True})
    proof = {
        "no_change_waits_without_work": wait["decision"] == "wait" and wait["why_not_now"] == "no_meaningful_change",
        "high_risk_requires_approval": ask["decision"] == "ask" and ask["requires_approval"] is True,
        "high_value_completed_parent_allows_kanban_handoff": handoff["decision"] == "kanban_handoff"
        and handoff["handoff"]["allowed"] is True
        and handoff["side_effect_free"] is True,
        "duplicate_event_is_idempotent_wait": duplicate["decision"] == "wait" and duplicate["why_not_now"] == "duplicate_event",
        "budget_exhausted_stops": budget_stop["decision"] == "stop" and budget_stop["why_not_now"] == "budget_exhausted",
        "replay_is_deterministic": replay_a == replay_b,
        "replay_duplicate_second_decision_waits": replay_a[1]["decision"] == "wait" and replay_a[1]["why_not_now"] == "duplicate_event",
        "status_is_agent_facing_and_compact": status["agent_claim"] == "workstream_controller_decisions_available"
        and status["active_decision_count"] == 1,
        "heartbeat_remains_scheduled_not_brain": heartbeat["migration_target"] == "remain_scheduled_compact"
        and heartbeat["fixed_schedule_is_brain"] is False,
        "fixed_cadence_work_generator_requires_controller": filler["job_class"] == "controller_substitute"
        and filler["migration_target"] == "controller_decision_required",
        "event_reader_is_change_gated": event_gated["migration_target"] == "event_or_change_gated",
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
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify workstream controller contract.")
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
