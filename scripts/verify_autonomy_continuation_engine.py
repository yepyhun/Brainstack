#!/usr/bin/env python3
"""Verify the universal autonomy continuation engine contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXT = ROOT / "extensions" / "hermes_continuation"
if EXT.exists() and str(EXT) not in sys.path:
    sys.path.insert(0, str(EXT))

from hermes_continuation.engine import (  # noqa: E402
    build_autonomy_continuation_decision,
    build_autonomy_runtime_adapter_contract,
)
from hermes_continuation.capability import (  # noqa: E402
    validate_capability_assignment,
    validate_completion_proof,
)
from hermes_continuation.trace_replay import (  # noqa: E402
    render_replay_summary,
    replay_decision_trace,
    validate_decision_trace,
)
from hermes_continuation.work_graph import validate_work_graph  # noqa: E402


REPORT_SCHEMA = "hermes_continuation.engine_proof.v1"


def _decision(name: str, evidence: dict) -> dict:
    result = build_autonomy_continuation_decision(evidence)
    return {"name": name, **result}


def _build_replay_fixture() -> dict:
    seen: list[str] = []
    decisions: list[dict] = []
    for index in range(120):
        evidence = {
            "event": {
                "kind": "task_completed",
                "event_id": f"evt-replay-{index}",
                "task_id": f"t-replay-{index}",
            },
            "controller_state": {"seen_idempotency_keys": seen},
            "scores": {
                "expected_value_next": 0.72,
                "confidence": 0.74,
                "progress_delta": 0.4,
                "novelty": 0.3,
            },
        }
        result = build_autonomy_continuation_decision(evidence)
        decisions.append(result)
        seen.append(result["idempotency_key"])

    duplicate = build_autonomy_continuation_decision(
        {
            "event": {
                "kind": "task_completed",
                "event_id": "evt-replay-42",
                "task_id": "t-replay-42",
                "idempotency_key": decisions[42]["idempotency_key"],
            },
            "controller_state": {"seen_idempotency_keys": seen},
        }
    )
    return {
        "count": len(decisions),
        "unique_idempotency_keys": len({item["idempotency_key"] for item in decisions}),
        "all_read_only": all(item["read_only"] and item["side_effect_free"] for item in decisions),
        "duplicate_decision": duplicate["decision"],
        "duplicate_ignored": duplicate["duplicate_ignored"],
    }


def build_report() -> dict[str, object]:
    scenarios = {
        "no_signal": _decision("no_signal", {}),
        "high_risk_human": _decision(
            "high_risk_human",
            {
                "event": {"kind": "approval_received", "event_id": "evt-risk"},
                "scores": {"expected_value_next": 0.9, "confidence": 0.9, "intervention_risk": 0.9},
                "safety": {"external_side_effect": True, "approval_missing": True},
            },
        ),
        "local_repair": _decision(
            "local_repair",
            {
                "event": {"kind": "task_completed", "event_id": "evt-repair", "artifact_missing": True},
                "safety": {"local_repair_available": True},
            },
        ),
        "wrong_step": _decision(
            "wrong_step",
            {
                "event": {"kind": "task_completed", "event_id": "evt-wrong", "previous_step_wrong": True},
                "scores": {"repair_urgency": 0.9, "confidence": 0.8},
            },
        ),
        "split": _decision(
            "split",
            {
                "event": {"kind": "frontier_below_saturation", "event_id": "evt-split"},
                "controller_state": {"current_fanout": 1, "max_fanout": 4},
                "scores": {
                    "expected_value_next": 0.9,
                    "confidence": 0.8,
                    "independence_score": 0.9,
                    "intervention_risk": 0.1,
                },
                "rolling_next5": [{"id": "branch", "summary": "branch verifier"}],
            },
        ),
        "verify": _decision(
            "verify",
            {
                "event": {"kind": "task_completed", "event_id": "evt-verify"},
                "scores": {"expected_value_next": 0.9, "confidence": 0.4},
            },
        ),
        "evolver": _decision(
            "evolver",
            {
                "event": {"kind": "evolver_signal_observed", "event_id": "evt-evo"},
                "evolver_signal": {"observed": True, "directive": "execute"},
            },
        ),
        "private_leak": _decision(
            "private_leak",
            {
                "event": {"kind": "task_completed", "event_id": "evt-private"},
                "adapter": {"private_data_present": True},
            },
        ),
        "filler_loop": _decision(
            "filler_loop",
            {
                "event": {"kind": "frontier_empty", "event_id": "evt-filler"},
                "scores": {"repetition_penalty": 0.8, "expected_value_next": 0.2, "confidence": 0.8},
            },
        ),
    }
    replay = _build_replay_fixture()
    capability_unknown = validate_capability_assignment(
        {
            "work_requirement": {"assignee": "worker", "required_capabilities": ["verify"]},
            "capabilities": [{"worker_id": "verifier", "capabilities": ["verify"]}],
        }
    )
    capability_valid = validate_capability_assignment(
        {
            "work_requirement": {"assignee": "verifier", "required_capabilities": ["inspect", "verify"]},
            "capabilities": [{"worker_id": "verifier", "capabilities": ["inspect", "verify"]}],
        }
    )
    completion_empty_done = validate_completion_proof({"status": "done"})
    completion_sufficient = validate_completion_proof(
        {
            "status": "done",
            "artifact_refs": ["artifact:1"],
            "evidence_refs": ["evidence:1"],
            "verdict": "pass",
            "postcondition": "material_progress_verified",
            "proof_strength": "sufficient",
        }
    )
    work_graph_missing_fanin = validate_work_graph(
        {
            "graph_id": "missing-fanin",
            "nodes": [
                {"id": "root", "status": "done", "artifact_refs": ["artifact:root"]},
                {"id": "child-a", "status": "ready"},
            ],
            "edges": [
                {
                    "edge_type": "fanout",
                    "from_node": "root",
                    "to_node": "child-a",
                    "idempotency_key": "fanout:child-a",
                }
            ],
        }
    )
    work_graph_valid = validate_work_graph(
        {
            "graph_id": "valid-graph",
            "nodes": [
                {"id": "root", "status": "done", "artifact_refs": ["artifact:root"]},
                {"id": "child-a", "status": "done", "artifact_refs": ["artifact:child-a"]},
                {"id": "child-b", "status": "ready"},
                {
                    "id": "fan-in",
                    "type": "fan_in",
                    "status": "done",
                    "decision": "next_frontier_created",
                    "parents": ["child-a"],
                },
            ],
            "edges": [
                {
                    "edge_type": "fanout",
                    "from_node": "root",
                    "to_node": "child-a",
                    "idempotency_key": "fanout:child-a",
                },
                {
                    "edge_type": "fanin",
                    "from_node": "child-a",
                    "to_node": "fan-in",
                    "idempotency_key": "fanin:child-a",
                },
            ],
        }
    )
    trace_missing_evidence = validate_decision_trace(
        {
            "trace_id": "trace-missing-evidence",
            "decision": "continue",
            "reason_codes": ["TEST"],
            "postcondition": "frontier_created",
        }
    )
    trace_replay = replay_decision_trace(
        [
            {
                "trace_id": "trace-1",
                "decision": "split",
                "reason_codes": ["FRONTIER_CREATED"],
                "input_event_refs": ["event:1"],
                "kanban_task_refs": ["task:1"],
                "postcondition": "frontier_created",
            },
            {
                "trace_id": "trace-1",
                "decision": "split",
                "reason_codes": ["FRONTIER_CREATED"],
                "input_event_refs": ["event:1"],
                "kanban_task_refs": ["task:1"],
                "postcondition": "frontier_created",
            },
            {
                "trace_id": "trace-human",
                "decision": "human_needed",
                "reason_codes": ["APPROVAL_REQUIRED"],
                "input_event_refs": ["event:2"],
                "postcondition": "waiting_for_approval",
            },
        ]
    )
    trace_summary = render_replay_summary(trace_replay)
    adapter_bad = build_autonomy_runtime_adapter_contract(
        {
            "decision": scenarios["split"],
            "runtime": {"side_effect_channel": "custom_shell"},
            "receipt": {"written": False},
            "cursor": {"persisted": False},
        }
    )
    adapter_good = build_autonomy_runtime_adapter_contract(
        {
            "decision": scenarios["split"],
            "runtime": {
                "side_effect_channel": "hermes_kanban",
                "idempotent_applier": True,
                "failure_reported_as_state": True,
            },
            "receipt": {"written": True},
            "cursor": {"persisted": True},
        }
    )
    proof = {
        "no_signal_waits_without_filler": scenarios["no_signal"]["decision"] == "wait"
        and "NO_SIGNAL_NO_FILLER" in scenarios["no_signal"]["reason_codes"],
        "high_risk_requires_human": scenarios["high_risk_human"]["decision"] == "human_needed",
        "local_repair_not_human_escape": scenarios["local_repair"]["decision"] == "repair",
        "wrong_step_backtracks": scenarios["wrong_step"]["decision"] == "repair",
        "independent_high_value_splits": scenarios["split"]["decision"] == "split",
        "low_confidence_high_value_verifies": scenarios["verify"]["decision"] == "verify",
        "evolver_signal_is_inert": scenarios["evolver"]["decision"] == "verify",
        "private_adapter_leak_blocks": scenarios["private_leak"]["verdict"] == "critical",
        "filler_loop_learns_not_spins": scenarios["filler_loop"]["decision"] == "learn",
        "replay_100_plus_events_unique": replay["count"] >= 100
        and replay["unique_idempotency_keys"] == replay["count"],
        "restart_duplicate_is_suppressed": replay["duplicate_decision"] == "wait" and replay["duplicate_ignored"] is True,
        "read_only_side_effect_free": replay["all_read_only"]
        and all(item["read_only"] and item["side_effect_free"] for item in scenarios.values()),
        "runtime_adapter_rejects_unowned_side_effects": adapter_bad["verdict"] == "critical"
        and "SIDE_EFFECT_CHANNEL_NOT_HERMES_OWNED" in adapter_bad["reason_codes"],
        "runtime_adapter_accepts_hermes_owned_receipted_idempotent_apply": adapter_good["verdict"] == "healthy",
        "unknown_assignee_is_not_runnable": capability_unknown["verdict"] == "critical"
        and capability_unknown["runnable"] is False
        and "UNKNOWN_ASSIGNEE" in capability_unknown["reason_codes"],
        "valid_capability_assignment_is_runnable": capability_valid["verdict"] == "healthy"
        and capability_valid["runnable"] is True,
        "empty_done_is_not_material_progress": completion_empty_done["verdict"] == "critical"
        and completion_empty_done["is_material_progress"] is False,
        "sufficient_completion_proof_is_material_progress": completion_sufficient["verdict"] == "healthy"
        and completion_sufficient["is_material_progress"] is True,
        "fanout_without_fanin_is_critical": work_graph_missing_fanin["verdict"] == "critical"
        and "FANOUT_WITHOUT_FANIN" in work_graph_missing_fanin["reason_codes"],
        "valid_work_graph_has_actionable_frontier": work_graph_valid["verdict"] == "healthy"
        and work_graph_valid["actionable_frontier_count"] == 1,
        "trace_missing_evidence_is_rejected": trace_missing_evidence["verdict"] == "critical",
        "trace_replay_suppresses_duplicate_and_preserves_human_gate": trace_replay["duplicate_event_count"] == 1
        and trace_replay["verdict"] == "waiting_for_human",
        "trace_replay_summary_is_bounded": trace_summary["rendered_length"] < 1200
        and "private" not in json.dumps(trace_summary, ensure_ascii=True).lower(),
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
        "scenario_decisions": {key: item["decision"] for key, item in scenarios.items()},
        "scenario_verdicts": {key: item["verdict"] for key, item in scenarios.items()},
        "replay": replay,
        "runtime_adapter_verdicts": {
            "bad": adapter_bad["verdict"],
            "good": adapter_good["verdict"],
        },
        "capability_verdicts": {
            "unknown": capability_unknown["verdict"],
            "valid": capability_valid["verdict"],
        },
        "completion_verdicts": {
            "empty_done": completion_empty_done["verdict"],
            "sufficient": completion_sufficient["verdict"],
        },
        "work_graph_verdicts": {
            "missing_fanin": work_graph_missing_fanin["verdict"],
            "valid": work_graph_valid["verdict"],
        },
        "trace_replay": {
            "verdict": trace_replay["verdict"],
            "duplicate_event_count": trace_replay["duplicate_event_count"],
            "summary_rendered_length": trace_summary["rendered_length"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify autonomy continuation engine.")
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
