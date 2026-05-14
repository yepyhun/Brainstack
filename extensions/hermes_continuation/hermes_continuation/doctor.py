"""Doctor checks for the optional Hermes continuation extension."""

from __future__ import annotations

from typing import Any

from .capability import validate_capability_assignment, validate_completion_proof
from .control_contract import build_continuation_control_contract
from .engine import build_autonomy_continuation_decision, build_autonomy_runtime_adapter_contract
from .trace_replay import render_replay_summary, replay_decision_trace
from .work_graph import validate_work_graph
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
    capability = validate_capability_assignment(
        {
            "work_requirement": {
                "assignee": "continuation-worker",
                "required_capabilities": ["inspect", "verify"],
            },
            "capabilities": [
                {
                    "worker_id": "continuation-worker",
                    "capabilities": ["inspect", "verify", "repair"],
                }
            ],
        }
    )
    completion = validate_completion_proof(
        {
            "status": "done",
            "artifact_refs": ["doctor:artifact"],
            "evidence_refs": ["doctor:evidence"],
            "verdict": "pass",
            "postcondition": "material_progress_verified",
            "proof_strength": "sufficient",
        }
    )
    work_graph = validate_work_graph(
        {
            "graph_id": "doctor-graph",
            "nodes": [
                {"id": "root", "status": "done", "artifact_refs": ["doctor:root"]},
                {"id": "worker-a", "status": "done", "artifact_refs": ["doctor:worker-a"]},
                {"id": "worker-b", "status": "ready"},
                {
                    "id": "fan-in",
                    "type": "fan_in",
                    "status": "done",
                    "decision": "next_frontier_created",
                    "parents": ["worker-a"],
                },
            ],
            "edges": [
                {
                    "edge_type": "fanout",
                    "from_node": "root",
                    "to_node": "worker-a",
                    "idempotency_key": "doctor:fanout:a",
                },
                {
                    "edge_type": "fanin",
                    "from_node": "worker-a",
                    "to_node": "fan-in",
                    "idempotency_key": "doctor:fanin:a",
                },
            ],
            "terminal_reason": "fan_in_bound",
        }
    )
    trace = replay_decision_trace(
        [
            {
                "trace_id": "doctor-trace-1",
                "decision": "split",
                "reason_codes": ["DOCTOR_FIXTURE"],
                "input_event_refs": ["doctor:event"],
                "kanban_task_refs": ["doctor:task"],
                "postcondition": "frontier_created",
                "open_frontier_node_ids": ["worker-b"],
            }
        ]
    )
    replay_summary = render_replay_summary(trace)
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
    if capability["verdict"] != "healthy" or capability["runnable"] is not True:
        issues.append("CAPABILITY_CONTRACT_NOT_HEALTHY")
    if completion["verdict"] != "healthy" or completion["is_material_progress"] is not True:
        issues.append("COMPLETION_PROOF_NOT_HEALTHY")
    if work_graph["verdict"] != "healthy":
        issues.append("WORK_GRAPH_NOT_HEALTHY")
    if trace["verdict"] != "healthy":
        issues.append("TRACE_REPLAY_NOT_HEALTHY")
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
        "capability": {
            "verdict": capability["verdict"],
            "runnable": capability["runnable"],
            "reason_codes": capability["reason_codes"],
        },
        "completion": {
            "verdict": completion["verdict"],
            "is_material_progress": completion["is_material_progress"],
            "reason_codes": completion["reason_codes"],
        },
        "work_graph": {
            "verdict": work_graph["verdict"],
            "actionable_frontier_count": work_graph["actionable_frontier_count"],
            "reason_codes": work_graph["reason_codes"],
        },
        "trace_replay": {
            "verdict": trace["verdict"],
            "summary": replay_summary,
        },
        "decision": {
            "verdict": decision["verdict"],
            "decision": decision["decision"],
            "reason_codes": decision["reason_codes"],
        },
        "runtime_adapter": {"verdict": adapter["verdict"], "reason_codes": adapter["reason_codes"]},
        "work_state": {"verdict": work_state["verdict"], "reason_codes": work_state["reason_codes"]},
    }
