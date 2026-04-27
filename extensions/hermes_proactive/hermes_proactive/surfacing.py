"""Pure surfacing policy for Hermes proactive items."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


PROACTIVE_SURFACING_SCHEMA = "hermes_proactive.surfacing.v1"


class ProactiveSurfacingDecision(StrEnum):
    SILENT_NOOP = "silent_noop"
    STORE_BACKGROUND = "store_background"
    QUEUE_INTERNAL_TASK = "queue_internal_task"
    NOTIFY_USER = "notify_user"
    NEEDS_APPROVAL = "needs_approval"
    BLOCKED = "blocked"


class ProactiveSurfacingReason(StrEnum):
    HEARTBEAT_ONLY = "HEARTBEAT_ONLY"
    DUPLICATE_NO_MATERIAL_CHANGE = "DUPLICATE_NO_MATERIAL_CHANGE"
    OPEN_ASK_EXISTS = "OPEN_ASK_EXISTS"
    READY_TO_NOTIFY = "READY_TO_NOTIFY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"


@dataclass(frozen=True)
class SurfacingContext:
    material_change: bool = True
    duplicate: bool = False
    open_proactive_asks: int = 0
    quiet_hours: bool = False
    allow_notify: bool = True


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def render_proactive_message(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "title": _text(item.get("title")) or "Proactive item",
        "why_now": _text(item.get("summary")) or "A proactive runtime signal exists.",
        "evidence_basis": ", ".join(str(value) for value in item.get("evidence_ids") or []) or "structured proactive evidence",
        "requested_next_action": _text(item.get("intended_next_action")) or "none",
    }


def decide_proactive_surfacing(item: Mapping[str, Any], context: SurfacingContext | None = None) -> dict[str, Any]:
    ctx = context or SurfacingContext()
    kind = _text(item.get("kind"))
    intended_next_action = _text(item.get("intended_next_action"))
    message = render_proactive_message(item)

    if kind == "heartbeat_ok":
        decision = ProactiveSurfacingDecision.SILENT_NOOP
        reason = ProactiveSurfacingReason.HEARTBEAT_ONLY
        should_notify = False
        requires_approval = False
    elif ctx.duplicate and not ctx.material_change:
        decision = ProactiveSurfacingDecision.STORE_BACKGROUND
        reason = ProactiveSurfacingReason.DUPLICATE_NO_MATERIAL_CHANGE
        should_notify = False
        requires_approval = False
    elif ctx.open_proactive_asks > 0:
        decision = ProactiveSurfacingDecision.QUEUE_INTERNAL_TASK
        reason = ProactiveSurfacingReason.OPEN_ASK_EXISTS
        should_notify = False
        requires_approval = False
    elif not ctx.allow_notify or ctx.quiet_hours:
        decision = ProactiveSurfacingDecision.QUEUE_INTERNAL_TASK
        reason = ProactiveSurfacingReason.BLOCKED_BY_POLICY
        should_notify = False
        requires_approval = False
    else:
        requires_approval = intended_next_action in {"ask_permission", "open_work_item", "request_input"}
        decision = ProactiveSurfacingDecision.NEEDS_APPROVAL if requires_approval else ProactiveSurfacingDecision.NOTIFY_USER
        reason = ProactiveSurfacingReason.APPROVAL_REQUIRED if requires_approval else ProactiveSurfacingReason.READY_TO_NOTIFY
        should_notify = True

    return {
        "schema": PROACTIVE_SURFACING_SCHEMA,
        "decision": decision.value,
        "reason_code": reason.value,
        "should_notify": should_notify,
        "requires_approval": requires_approval,
        "message": message,
    }
