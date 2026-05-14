"""Continuation decision trace and replay recovery contracts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


DECISION_TRACE_SCHEMA = "hermes_continuation.decision_trace.v1"
REPLAY_CHECKPOINT_SCHEMA = "hermes_continuation.replay_checkpoint.v1"
REPLAY_REPORT_SCHEMA = "hermes_continuation.replay_report.v1"

DECISIONS = {
    "continue",
    "split",
    "verify",
    "repair",
    "learn",
    "wait",
    "human_needed",
    "intentional_stop",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _trace_id(event: Mapping[str, Any]) -> str:
    return _text(event.get("trace_id") or event.get("id") or event.get("idempotency_key"))


def validate_decision_trace(event: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a single append-only decision trace event."""

    decision = _text(event.get("decision"))
    trace_id = _trace_id(event)
    reason_codes = _refs(event.get("reason_codes"))
    input_refs = _refs(event.get("input_event_refs"))
    work_graph_refs = _refs(event.get("work_graph_refs"))
    kanban_task_refs = _refs(event.get("kanban_task_refs"))
    artifact_refs = _refs(event.get("artifact_refs"))
    postcondition = _text(event.get("postcondition"))
    private_payload_present = _bool(event.get("private_payload_present")) or bool(event.get("private_payload"))
    issues: list[str] = []

    if not trace_id:
        issues.append("TRACE_ID_MISSING")
    if decision not in DECISIONS:
        issues.append("TRACE_DECISION_INVALID")
    if not reason_codes:
        issues.append("TRACE_REASON_CODES_MISSING")
    if not postcondition or not (input_refs or work_graph_refs or kanban_task_refs or artifact_refs):
        issues.append("TRACE_EVIDENCE_OR_POSTCONDITION_MISSING")
    if private_payload_present:
        issues.append("PRIVATE_PAYLOAD_PRESENT")

    verdict = "healthy" if not issues else "critical"
    return {
        "schema": DECISION_TRACE_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": not private_payload_present,
        "verdict": verdict,
        "trace_id": trace_id or "unknown",
        "decision": decision or "unknown",
        "postcondition": postcondition,
        "reason_codes": sorted(set(issues or ["DECISION_TRACE_VALID"])),
    }


def _event_verdict(decision: str, postcondition: str) -> str:
    if decision == "human_needed":
        return "waiting_for_human"
    if decision == "intentional_stop":
        return "stopped_intentionally"
    if decision == "repair" or postcondition == "recovery_needed":
        return "recovery_needed"
    if decision == "wait":
        return "waiting_for_signal"
    return "healthy"


def build_checkpoint(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the latest compact checkpoint from decision trace events."""

    replay = replay_decision_trace(events)
    return {
        "schema": REPLAY_CHECKPOINT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": True,
        "checkpoint_id": f"checkpoint:{replay['last_trace_id']}",
        "workstream_id": replay["workstream_id"],
        "verdict": replay["verdict"],
        "last_decision": replay["last_decision"],
        "last_material_decision_ref": replay["last_trace_id"],
        "open_frontier_node_ids": replay["open_frontier_node_ids"],
        "running_task_refs": replay["running_task_refs"],
        "blocked_task_refs": replay["blocked_task_refs"],
        "fan_in_wait_nodes": replay["fan_in_wait_nodes"],
        "recovery_needed_reason": replay["recovery_needed_reason"],
        "replay_idempotency_key": replay["replay_idempotency_key"],
    }


def replay_decision_trace(
    events: Iterable[Mapping[str, Any]],
    *,
    checkpoint: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay decision trace events into compact continuation recovery state."""

    seen: set[str] = set()
    accepted: list[Mapping[str, Any]] = []
    invalid_count = 0
    duplicate_count = 0
    private_payload_count = 0
    reason_codes: list[str] = []

    for event in events:
        validation = validate_decision_trace(event)
        if validation["verdict"] != "healthy":
            invalid_count += 1
            reason_codes.extend(validation["reason_codes"])
            if validation["public_safe"] is False:
                private_payload_count += 1
            continue
        trace_id = validation["trace_id"]
        if trace_id in seen:
            duplicate_count += 1
            continue
        seen.add(trace_id)
        accepted.append(event)

    last = accepted[-1] if accepted else {}
    last_trace_id = _trace_id(last) if last else _text((checkpoint or {}).get("last_material_decision_ref"))
    last_decision = _text(last.get("decision")) if last else _text((checkpoint or {}).get("last_decision") or "none")
    postcondition = _text(last.get("postcondition")) if last else ""
    verdict = _event_verdict(last_decision, postcondition) if last else _text((checkpoint or {}).get("verdict") or "insufficient_evidence")
    checkpoint_verdict = _text((checkpoint or {}).get("verdict"))
    if checkpoint and accepted:
        if checkpoint_verdict and checkpoint_verdict != verdict:
            reason_codes.append("CHECKPOINT_SUPERSEDED_BY_TRACE")

    open_frontier = _refs(last.get("open_frontier_node_ids")) or _refs((checkpoint or {}).get("open_frontier_node_ids"))
    running_tasks = _refs(last.get("running_task_refs")) or _refs((checkpoint or {}).get("running_task_refs"))
    blocked_tasks = _refs(last.get("blocked_task_refs")) or _refs((checkpoint or {}).get("blocked_task_refs"))
    fan_in_wait_nodes = _refs(last.get("fan_in_wait_nodes")) or _refs((checkpoint or {}).get("fan_in_wait_nodes"))
    kanban_refs = _refs(last.get("kanban_task_refs"))
    if last_decision in {"split", "continue", "verify", "repair"} and kanban_refs and not running_tasks:
        running_tasks = kanban_refs

    if invalid_count:
        verdict = "critical"
    if private_payload_count:
        reason_codes.append("PRIVATE_PAYLOAD_PRESENT")
    if duplicate_count:
        reason_codes.append("DUPLICATE_TRACE_EVENT_IGNORED")

    return {
        "schema": REPLAY_REPORT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": private_payload_count == 0,
        "verdict": verdict,
        "workstream_id": _text(last.get("workstream_id")) or _text((checkpoint or {}).get("workstream_id")) or "unknown",
        "decision_count": len(accepted),
        "invalid_event_count": invalid_count,
        "duplicate_event_count": duplicate_count,
        "trace_event_count": len(accepted) + duplicate_count + invalid_count,
        "last_trace_id": last_trace_id or "none",
        "last_decision": last_decision,
        "open_frontier_node_ids": open_frontier[:20],
        "running_task_refs": running_tasks[:20],
        "blocked_task_refs": blocked_tasks[:20],
        "fan_in_wait_nodes": fan_in_wait_nodes[:20],
        "recovery_needed_reason": "repair_decision" if verdict == "recovery_needed" else "",
        "replay_idempotency_key": f"replay:{last_trace_id or 'none'}",
        "reason_codes": sorted(set(reason_codes or ["TRACE_REPLAY_OK"])),
        "agent_claim": f"trace_replay_{verdict}",
    }


def render_replay_summary(replay: Mapping[str, Any], *, max_reason_codes: int = 8) -> dict[str, Any]:
    """Render a bounded model-facing recovery summary."""

    reason_codes = _refs(replay.get("reason_codes"))[:max_reason_codes]
    summary = {
        "schema": "hermes_continuation.replay_summary.v1",
        "verdict": _text(replay.get("verdict")),
        "workstream_id": _text(replay.get("workstream_id")),
        "last_decision": _text(replay.get("last_decision")),
        "last_trace_id": _text(replay.get("last_trace_id")),
        "trace_event_count": int(replay.get("trace_event_count") or 0),
        "duplicate_event_count": int(replay.get("duplicate_event_count") or 0),
        "open_frontier_count": len(replay.get("open_frontier_node_ids") or []),
        "running_task_count": len(replay.get("running_task_refs") or []),
        "blocked_task_count": len(replay.get("blocked_task_refs") or []),
        "fan_in_wait_count": len(replay.get("fan_in_wait_nodes") or []),
        "reason_codes": reason_codes,
        "inspect_handle": _text(replay.get("last_trace_id")) or "none",
    }
    rendered_length = len(str(summary))
    summary["rendered_length"] = rendered_length
    return summary


__all__ = [
    "DECISION_TRACE_SCHEMA",
    "REPLAY_CHECKPOINT_SCHEMA",
    "REPLAY_REPORT_SCHEMA",
    "build_checkpoint",
    "render_replay_summary",
    "replay_decision_trace",
    "validate_decision_trace",
]

