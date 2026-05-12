"""Universal workstream controller decision contract.

This module does not execute work, schedule jobs, notify users, or write Kanban
cards. It produces side-effect-free decisions that other Hermes-owned layers
may consume explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


WORKSTREAM_CONTROLLER_DECISION_SCHEMA = "brainstack.workstream_controller.decision.v1"
WORKSTREAM_CONTROLLER_STATUS_SCHEMA = "brainstack.workstream_controller.status.v1"
WORKSTREAM_CONTROLLER_JOB_CLASSIFICATION_SCHEMA = "brainstack.workstream_controller.job_classification.v1"

CONTROLLER_ACTIONS = ("wait", "stop", "continue", "branch", "ask", "kanban_handoff", "surface")
JOB_CLASSES = ("heartbeat", "recovery", "status_projection", "candidate_producer", "controller_substitute", "domain_experiment")


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(parsed, 1.0))


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _idempotency_key(event: Mapping[str, Any], workstream_id: str) -> str:
    explicit = _text(event.get("idempotency_key"))
    if explicit:
        return explicit
    event_id = _text(event.get("event_id") or event.get("id"))
    kind = _text(event.get("kind"))
    return f"{workstream_id}:{kind}:{event_id}" if event_id or kind else f"{workstream_id}:unknown"


def build_controller_decision(
    *,
    workstream_id: str,
    event: Mapping[str, Any] | None = None,
    state: Mapping[str, Any] | None = None,
    scores: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a side-effect-free controller decision.

    The decision is intentionally conservative: no changed input, duplicate
    event, active lock, exhausted budget, low value, or high risk cannot create
    work.
    """

    event = event if isinstance(event, Mapping) else {}
    state = state if isinstance(state, Mapping) else {}
    scores = scores if isinstance(scores, Mapping) else {}
    workstream = _text(workstream_id) or "unknown"
    key = _idempotency_key(event, workstream)
    seen_keys = {str(item) for item in state.get("seen_idempotency_keys") or []}
    active_locks = {str(item) for item in state.get("active_work_locks") or []}
    event_kind = _text(event.get("kind"))
    trigger_reason = _text(event.get("trigger_reason") or event_kind or "manual")
    changed_inputs = [str(item) for item in event.get("changed_inputs") or [] if str(item).strip()]
    progress_delta = _float(scores.get("progress_delta"))
    expected_value = _float(scores.get("expected_value_next"))
    confidence = _float(scores.get("confidence"))
    intervention_risk = _float(scores.get("intervention_risk"))
    novelty = _float(scores.get("novelty"), 0.5)
    repetition_penalty = _float(scores.get("repetition_penalty"))
    budget_remaining = _int(state.get("budget_remaining"), 1)
    max_fanout = max(1, _int(state.get("max_fanout"), 3))
    current_fanout = _int(state.get("current_fanout"), 0)
    max_depth = max(1, _int(state.get("max_depth"), 4))
    current_depth = _int(state.get("current_depth"), 0)

    action = "wait"
    why_not_now = ""
    why_now = ""
    handoff: dict[str, Any] = {"allowed": False, "target": "", "reason_code": "NO_HANDOFF"}

    if key in seen_keys:
        action = "wait"
        why_not_now = "duplicate_event"
    elif workstream in active_locks:
        action = "wait"
        why_not_now = "active_work_lock"
    elif budget_remaining <= 0:
        action = "stop"
        why_not_now = "budget_exhausted"
    elif current_fanout >= max_fanout:
        action = "wait"
        why_not_now = "fanout_limit_reached"
    elif current_depth >= max_depth:
        action = "stop"
        why_not_now = "depth_limit_reached"
    elif not changed_inputs and event_kind not in {"task_completed", "approval_received", "blocker_cleared"}:
        action = "wait"
        why_not_now = "no_meaningful_change"
    elif intervention_risk >= 0.65:
        action = "ask"
        why_now = "high_intervention_risk_requires_user_decision"
    elif expected_value < 0.45 or confidence < 0.4 or novelty < 0.25 or repetition_penalty >= 0.65:
        action = "wait"
        why_not_now = "low_value_or_low_confidence"
    elif event_kind == "task_completed" and expected_value >= 0.75 and confidence >= 0.6:
        action = "kanban_handoff"
        why_now = "completed_parent_unlocked_high_value_next_step"
        handoff = {
            "allowed": True,
            "target": "hermes_kanban",
            "reason_code": "KANBAN_HANDOFF_ALLOWED",
            "task_title": _text(event.get("next_task_title")) or f"{workstream} next bounded step",
        }
    elif event_kind in {"task_completed", "blocker_cleared", "approval_received"}:
        action = "continue"
        why_now = f"{event_kind}_changed_workstream_state"
    else:
        action = "surface"
        why_now = "meaningful_signal_available"

    continue_score = round((expected_value * confidence) + progress_delta + novelty - intervention_risk - repetition_penalty, 4)
    return {
        "schema": WORKSTREAM_CONTROLLER_DECISION_SCHEMA,
        "side_effect_free": True,
        "workstream_id": workstream,
        "trigger_reason": trigger_reason,
        "idempotency_key": key,
        "changed_inputs": changed_inputs,
        "scores": {
            "progress_delta": progress_delta,
            "expected_value_next": expected_value,
            "confidence": confidence,
            "intervention_risk": intervention_risk,
            "novelty": novelty,
            "repetition_penalty": repetition_penalty,
            "continue_score": continue_score,
        },
        "dampers": {
            "budget_remaining": budget_remaining,
            "max_fanout": max_fanout,
            "current_fanout": current_fanout,
            "max_depth": max_depth,
            "current_depth": current_depth,
            "active_work_lock": workstream in active_locks,
            "duplicate": key in seen_keys,
        },
        "decision": action,
        "why_now": why_now,
        "why_not_now": why_not_now,
        "requires_approval": action == "ask",
        "handoff": handoff,
        "final_state_verifier": "controller_decision_replay_and_status_parity",
    }


def controller_status(decisions: list[Mapping[str, Any]]) -> dict[str, Any]:
    if not decisions:
        return {
            "schema": WORKSTREAM_CONTROLLER_STATUS_SCHEMA,
            "side_effect_free": True,
            "status": "available_no_active_state",
            "agent_claim": "workstream_controller_contract_available_no_active_state",
        }
    active = [item for item in decisions if _text(item.get("decision")) in {"continue", "branch", "kanban_handoff", "ask", "surface"}]
    waiting = [item for item in decisions if _text(item.get("decision")) in {"wait", "stop"}]
    last = decisions[-1] if decisions else {}
    return {
        "schema": WORKSTREAM_CONTROLLER_STATUS_SCHEMA,
        "side_effect_free": True,
        "active_decision_count": len(active),
        "waiting_decision_count": len(waiting),
        "last_decision": _text(last.get("decision")),
        "last_why_now": _text(last.get("why_now")),
        "last_why_not_now": _text(last.get("why_not_now")),
        "next_trigger": "event_or_recovery_tick",
        "agent_claim": (
            "workstream_controller_decisions_available"
            if decisions
            else "workstream_controller_contract_available_no_active_state"
        ),
    }


def replay_controller_events(
    *,
    workstream_id: str,
    events: list[Mapping[str, Any]],
    initial_state: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    state: dict[str, Any] = dict(initial_state or {})
    seen = {str(item) for item in state.get("seen_idempotency_keys") or []}
    decisions: list[dict[str, Any]] = []
    for event in events:
        decision = build_controller_decision(
            workstream_id=workstream_id,
            event=event,
            state={**state, "seen_idempotency_keys": sorted(seen)},
            scores=event.get("scores") if isinstance(event.get("scores"), Mapping) else {},
        )
        decisions.append(decision)
        seen.add(str(decision["idempotency_key"]))
    return decisions


def classify_cadence_job(job: Mapping[str, Any]) -> dict[str, Any]:
    name = _text(job.get("name")).lower()
    kind = _text(job.get("kind")).lower()
    creates_artifact = bool(job.get("creates_artifact"))
    creates_work = bool(job.get("creates_work"))
    reads_events = bool(job.get("reads_events"))
    fixed_schedule = bool(job.get("fixed_schedule", True))
    if kind in {"heartbeat", "health"} or "heartbeat" in name:
        job_class = "heartbeat"
        migration_target = "remain_scheduled_compact"
    elif kind == "recovery" or "recovery" in name:
        job_class = "recovery"
        migration_target = "remain_scheduled_idempotent"
    elif kind == "status_projection" or "status" in name:
        job_class = "status_projection"
        migration_target = "remain_read_only_projection"
    elif creates_work and fixed_schedule and not reads_events:
        job_class = "controller_substitute"
        migration_target = "controller_decision_required"
    elif creates_artifact or reads_events:
        job_class = "candidate_producer"
        migration_target = "event_or_change_gated"
    else:
        job_class = "domain_experiment"
        migration_target = "fixture_or_explicit_owner"
    return {
        "schema": WORKSTREAM_CONTROLLER_JOB_CLASSIFICATION_SCHEMA,
        "job_id": _text(job.get("id") or job.get("name")),
        "job_class": job_class,
        "migration_target": migration_target,
        "fixed_schedule_is_brain": job_class == "controller_substitute",
        "must_not_generate_filler": job_class in {"controller_substitute", "candidate_producer"},
    }
