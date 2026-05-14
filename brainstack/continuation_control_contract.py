"""Side-effect-free continuation-control contract.

This module belongs to the autonomy/proactive extension boundary, not to
Brainstack's memory storage core. It classifies controller evidence so a caller
can tell event-primary deterministic continuation from prompt/cadence autonomy
theatre.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CONTINUATION_CONTROL_CONTRACT_SCHEMA = "brainstack.continuation_control.contract.v1"
FRONTIER_CONTINUATION_CONTRACT_SCHEMA = CONTINUATION_CONTROL_CONTRACT_SCHEMA


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _record_event_keys(records: list[Mapping[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        for field in ("event_id", "source_event_id", "terminal_event_id", "idempotency_key"):
            value = _text(record.get(field))
            if value:
                keys.add(value)
    return keys


def build_continuation_control_contract(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify whether continuation control is event-first and deterministic.

    This contract is intentionally read-only. It does not create tasks, trigger
    schedulers, notify users, or mutate Kanban state. It only makes the control
    shape inspectable so agents cannot call prompt/cadence autonomy theatre
    healthy.
    """

    controller = _mapping(evidence.get("controller"))
    allocator = _mapping(evidence.get("allocator") or controller.get("allocator"))
    cursor = _mapping(evidence.get("event_cursor") or controller.get("event_cursor"))
    frontier = _mapping(evidence.get("frontier") or evidence.get("kanban_runtime_snapshot") or controller.get("frontier"))
    token_evidence = _mapping(evidence.get("token_policy") or evidence.get("control_plane_token_policy") or controller.get("token_policy"))
    terminal_events = _list_of_mappings(evidence.get("terminal_events"))
    continuation_records = _list_of_mappings(evidence.get("continuation_records"))
    seen_continuations = _record_event_keys(continuation_records)
    explicit_stop = _bool(evidence.get("explicit_stop")) or _text(evidence.get("state")) == "stopped_intentionally"

    declared_mode = _text(evidence.get("controller_mode") or controller.get("controller_mode") or controller.get("mode"))
    event_bridge_enabled = (
        _bool(controller.get("event_bridge_enabled"))
        or _bool(controller.get("event_primary"))
        or _bool(evidence.get("event_bridge_enabled"))
        or declared_mode in {"event_primary", "event_driven", "event_plus_watchdog"}
    )
    event_bridge_stale = _bool(controller.get("event_bridge_stale")) or _bool(evidence.get("event_bridge_stale"))
    watchdog_enabled = _bool(controller.get("watchdog_enabled")) or _bool(evidence.get("watchdog_enabled"))
    allocator_exists = bool(allocator)
    allocator_fixed = _bool(allocator.get("fixed_schedule", allocator_exists))
    allocator_creates_work = _bool(allocator.get("creates_work")) or _bool(controller.get("allocator_creates_work"))
    allocator_reads_events = _bool(allocator.get("reads_events")) or _bool(controller.get("allocator_reads_events"))
    allocator_watchdog_only = _bool(allocator.get("watchdog_only")) or _text(allocator.get("kind")) in {
        "watchdog",
        "recovery",
        "heartbeat",
    }
    prompt_primary = (
        declared_mode == "prompt_primary"
        or _bool(controller.get("prompt_primary"))
        or _bool(allocator.get("prompt_primary"))
        or (
            allocator_creates_work
            and not allocator_watchdog_only
            and (_bool(allocator.get("uses_llm")) or _bool(controller.get("normal_path_uses_llm")))
            and not allocator_reads_events
        )
    )

    dry_run_presented_as_live = (
        _bool(evidence.get("dry_run_presented_as_live"))
        or _bool(controller.get("dry_run_presented_as_live"))
        or (_bool(controller.get("dry_run")) and _bool(controller.get("presented_as_live")))
        or (_text(controller.get("artifact_kind")) == "dry_run" and _bool(controller.get("used_as_live_state")))
    )

    cursor_lag = _safe_int(cursor.get("cursor_lag"), 0)
    terminal_cursor_lag = _safe_int(cursor.get("terminal_cursor_lag"), cursor_lag)
    if "last_event_id" in cursor and "max_event_id" in cursor:
        cursor_lag = max(cursor_lag, _safe_int(cursor.get("max_event_id")) - _safe_int(cursor.get("last_event_id")))
    if "last_event_id" in cursor and "max_terminal_event_id" in cursor:
        terminal_cursor_lag = max(
            terminal_cursor_lag,
            _safe_int(cursor.get("max_terminal_event_id")) - _safe_int(cursor.get("last_event_id")),
        )
    event_cursor_stale = _bool(cursor.get("stale")) or cursor_lag > 0 or terminal_cursor_lag > 0

    if prompt_primary:
        controller_mode = "prompt_primary"
    elif event_bridge_enabled and not event_bridge_stale and not event_cursor_stale:
        controller_mode = "event_primary"
    elif event_bridge_enabled and (event_bridge_stale or event_cursor_stale):
        controller_mode = "event_primary_stale"
    elif allocator_creates_work and allocator_fixed and not allocator_reads_events:
        controller_mode = "cadence_primary"
    elif watchdog_enabled or allocator_watchdog_only:
        controller_mode = "watchdog_only"
    elif not (controller or allocator or terminal_events or continuation_records):
        controller_mode = "insufficient_evidence"
    else:
        controller_mode = "unavailable"

    primary_control = controller_mode in {"event_primary", "event_primary_stale", "prompt_primary", "cadence_primary"}
    model_calls = _safe_int(token_evidence.get("model_calls") or token_evidence.get("control_plane_model_calls"), 0)
    max_input_tokens = _safe_int(token_evidence.get("max_input_tokens"), 0)
    max_payload_chars = _safe_int(
        token_evidence.get("max_model_facing_payload_chars")
        or token_evidence.get("max_tool_result_chars")
        or token_evidence.get("large_tool_result_chars"),
        0,
    )
    normal_path_uses_llm = _bool(token_evidence.get("normal_path_uses_llm")) or _bool(controller.get("normal_path_uses_llm"))
    llm_advisory = _bool(token_evidence.get("llm_advisory_only")) or _text(token_evidence.get("role")) == "advisory"
    llm_worker = _bool(token_evidence.get("llm_worker_allowed")) or _text(token_evidence.get("role")) in {"worker", "reviewer", "verifier"}
    token_violation = (
        prompt_primary
        or normal_path_uses_llm
        or (primary_control and model_calls > 0 and not (llm_advisory or llm_worker))
        or max_input_tokens >= 30000
        or max_payload_chars >= 12000
    )
    if token_violation:
        token_policy = "violation"
    elif llm_advisory:
        token_policy = "llm_advisory_only"
    elif llm_worker:
        token_policy = "llm_worker_allowed"
    else:
        token_policy = "deterministic_normal_path"

    terminal_kinds = {
        "task_completed",
        "completed",
        "done",
        "blocked",
        "crashed",
        "failed",
        "timed_out",
        "timeout",
    }
    allowed_decisions = {
        "next_frontier_created",
        "wait_for_parent_or_dependency",
        "human_gate",
        "intentional_stop",
        "recovery_candidate",
        "wait",
        "stop",
        "ask",
        "kanban_handoff",
    }
    continuation_gaps: list[dict[str, Any]] = []
    for event in terminal_events:
        event_kind = _text(event.get("kind"))
        if event_kind not in terminal_kinds:
            continue
        event_id = _text(event.get("event_id") or event.get("id") or event.get("idempotency_key"))
        decision = _text(event.get("continuation_decision") or event.get("decision"))
        has_continuation = (
            _bool(event.get("has_continuation"))
            or decision in allowed_decisions
            or (event_id and event_id in seen_continuations)
        )
        if not has_continuation and not explicit_stop:
            continuation_gaps.append(
                {
                    "event_id": event_id or "unknown-event",
                    "task_id": _text(event.get("task_id")) or "unknown-task",
                    "kind": event_kind,
                    "reason_code": "terminal_event_without_continuation",
                }
            )

    reason_codes: list[str] = []
    if continuation_gaps:
        reason_codes.append("FRONTIER_CONTINUATION_GAP")
    if controller_mode == "prompt_primary":
        reason_codes.append("PROMPT_ALLOCATOR_PRIMARY")
    elif controller_mode == "cadence_primary":
        reason_codes.append("CADENCE_PRIMARY_NOT_EVENT_DRIVEN")
    elif controller_mode == "event_primary_stale" or event_cursor_stale:
        reason_codes.append("EVENT_CURSOR_STALE")
    elif controller_mode == "watchdog_only":
        reason_codes.append("FRONTIER_WATCHDOG_ONLY")
    elif controller_mode == "unavailable":
        reason_codes.append("FRONTIER_CONTROLLER_MISSING")
    elif controller_mode == "insufficient_evidence":
        reason_codes.append("FRONTIER_CONTINUATION_INSUFFICIENT_EVIDENCE")
    if dry_run_presented_as_live:
        reason_codes.append("DRY_RUN_PRESENTED_AS_LIVE")
    if token_policy == "violation":
        reason_codes.append("CONTROL_PLANE_LLM_TOKEN_VIOLATION")

    target_frontier = _safe_int(frontier.get("target_frontier"), 0)
    target_running = _safe_int(frontier.get("target_running"), 0)
    actionable_frontier = _safe_int(frontier.get("actionable_frontier_count"), 0)
    ready_count = _safe_int(frontier.get("ready_task_count"), 0)
    running_count = _safe_int(frontier.get("running_worker_count"), 0)
    blocked_residue_count = _safe_int(frontier.get("blocked_residue_count") or frontier.get("blocked_task_count"), 0)
    completed_fanin_stuck_count = _safe_int(frontier.get("completed_fanin_stuck_count"), 0)
    invalid_assignee_count = _safe_int(frontier.get("invalid_assignee_count") or frontier.get("blocked_unknown_assignee_count"), 0)
    blocked_counted_as_frontier = _bool(frontier.get("blocked_residue_counted_as_frontier"))
    if target_frontier and actionable_frontier < target_frontier:
        reason_codes.append("FRONTIER_BELOW_TARGET")
    if ready_count > 0 and target_running and running_count < target_running:
        reason_codes.append("READY_BACKLOG_LOW_RUNNING")
    if completed_fanin_stuck_count:
        reason_codes.append("COMPLETED_FANIN_STUCK")
    if blocked_residue_count and blocked_counted_as_frontier:
        reason_codes.append("BLOCKED_RESIDUE_NOT_FRONTIER")
    if invalid_assignee_count:
        reason_codes.append("INVALID_ASSIGNEE_ACTIVE")

    if explicit_stop:
        verdict = "stopped_intentionally"
        reason_codes.append("FRONTIER_STOPPED_INTENTIONALLY")
    elif continuation_gaps or prompt_primary or token_policy == "violation" or dry_run_presented_as_live or invalid_assignee_count:
        verdict = "critical"
    elif controller_mode in {"cadence_primary", "event_primary_stale", "unavailable", "watchdog_only"}:
        verdict = "degraded"
    elif completed_fanin_stuck_count or (blocked_residue_count and blocked_counted_as_frontier):
        verdict = "degraded"
    elif (target_frontier and actionable_frontier < target_frontier) or (ready_count > 0 and target_running and running_count < target_running):
        verdict = "degraded"
    elif controller_mode == "insufficient_evidence":
        verdict = "insufficient_evidence"
    else:
        verdict = "healthy"
        reason_codes.append("FRONTIER_CONTINUATION_HEALTHY")

    return {
        "schema": CONTINUATION_CONTROL_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "controller_mode": controller_mode,
        "token_policy": token_policy,
        "event_bridge_enabled": event_bridge_enabled,
        "event_bridge_stale": event_bridge_stale or event_cursor_stale,
        "event_cursor": {
            "cursor_lag": cursor_lag,
            "terminal_cursor_lag": terminal_cursor_lag,
            "stale": event_cursor_stale,
        },
        "dry_run_presented_as_live": dry_run_presented_as_live,
        "cadence_primary_allocator": controller_mode == "cadence_primary",
        "prompt_primary_allocator": controller_mode == "prompt_primary",
        "continuation_gap_count": len(continuation_gaps),
        "terminal_events_without_continuation": continuation_gaps[:20],
        "frontier_pressure": {
            "target_frontier": target_frontier,
            "target_running": target_running,
            "actionable_frontier_count": actionable_frontier,
            "ready_task_count": ready_count,
            "running_worker_count": running_count,
            "blocked_residue_count": blocked_residue_count,
            "completed_fanin_stuck_count": completed_fanin_stuck_count,
            "invalid_assignee_count": invalid_assignee_count,
        },
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": (
            "continuation_control_event_primary"
            if verdict == "healthy"
            else f"continuation_control_{verdict}"
        ),
    }


def build_frontier_continuation_contract(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for older operating-loop callers."""

    return build_continuation_control_contract(evidence)
