"""Doctor checks for the optional Hermes continuation extension."""

from __future__ import annotations

from typing import Any

from .control_contract import build_continuation_control_contract
from .engine import build_autonomy_continuation_decision, build_autonomy_runtime_adapter_contract
from .work_state import build_durable_work_state_contract


def continuation_extension_doctor() -> dict[str, Any]:
    """Return a compact, side-effect-free extension health proof."""

    event_driven = build_continuation_control_contract(
        {
            "controller": {"controller_mode": "event_primary"},
            "event_cursor": {"persisted": True, "stale": False},
            "token_policy": {"model_calls": 0, "max_input_tokens": 0},
            "terminal_events": [{"event_key": "task:1:completed", "has_continuation_record": True}],
        }
    )
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-doctor"},
            "scores": {"expected_value_next": 0.9, "confidence": 0.8, "independence_score": 0.8},
            "controller_state": {"current_fanout": 0, "max_fanout": 3},
        }
    )
    adapter = build_autonomy_runtime_adapter_contract(
        {
            "decision": decision,
            "runtime": {
                "side_effect_channel": "hermes_kanban",
                "idempotent_applier": True,
                "failure_reported_as_state": True,
            },
            "receipt": {"written": True},
            "cursor": {"persisted": True},
        }
    )
    work_state = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "doctor-work",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["doctor:fixture"],
                    "side_effect_durable": True,
                    "acknowledged": True,
                    "handoff": {"next_action": "inspect next event"},
                }
            ]
        }
    )

    issues: list[str] = []
    if event_driven["verdict"] != "healthy":
        issues.append("CONTROL_CONTRACT_NOT_HEALTHY")
    if decision["decision"] not in {"split", "continue", "verify"}:
        issues.append("DECISION_ENGINE_UNEXPECTED_DECISION")
    if adapter["verdict"] != "healthy":
        issues.append("RUNTIME_ADAPTER_NOT_HEALTHY")
    if work_state["verdict"] != "healthy":
        issues.append("WORK_STATE_NOT_HEALTHY")

    return {
        "schema": "hermes_continuation.doctor.v1",
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "read_only": True,
        "side_effect_free": True,
        "control_contract": {
            "verdict": event_driven["verdict"],
            "controller_mode": event_driven["controller_mode"],
            "token_policy": event_driven["token_policy"],
        },
        "decision": {
            "verdict": decision["verdict"],
            "decision": decision["decision"],
            "reason_codes": decision["reason_codes"],
        },
        "runtime_adapter": {"verdict": adapter["verdict"], "reason_codes": adapter["reason_codes"]},
        "work_state": {"verdict": work_state["verdict"], "reason_codes": work_state["reason_codes"]},
    }
