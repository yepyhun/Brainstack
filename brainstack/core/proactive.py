"""Typed contracts for Brainstack proactive runtime memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


PROACTIVE_EVENT_SCHEMA = "brainstack.proactive_event.v1"
PROACTIVE_OUTBOX_SCHEMA = "brainstack.proactive_outbox.v1"
PROACTIVE_CONTROL_SCHEMA = "brainstack.proactive_control.v1"


class ProactiveEventKind(StrEnum):
    STALE_TASK = "stale_task"
    FOLLOW_UP = "follow_up"
    INBOX_ITEM = "inbox_item"
    EVOLVER_CANDIDATE = "evolver_candidate"
    RISK = "risk"
    BLOCKED = "blocked"
    HEARTBEAT_OK = "heartbeat_ok"


class ProactiveEventState(StrEnum):
    OBSERVED = "observed"
    QUEUED = "queued"
    NOTIFIED = "notified"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPPRESSED = "suppressed"
    BLOCKED = "blocked"


class ProactiveAuthority(StrEnum):
    SUPPORTING_CONTEXT = "supporting_context"
    PROACTIVE_CANDIDATE = "proactive_candidate"
    EXPLICIT_USER_HANDOFF = "explicit_user_handoff"


class ProactiveIntendedNextAction(StrEnum):
    INFORM_USER = "inform_user"
    ASK_PERMISSION = "ask_permission"
    REQUEST_INPUT = "request_input"
    SCHEDULE_CHECK = "schedule_check"
    OPEN_WORK_ITEM = "open_work_item"
    NONE = "none"


class ProactiveReasonCode(StrEnum):
    OBSERVED = "OBSERVED"
    MATERIAL_CHANGE = "MATERIAL_CHANGE"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    OUTBOX_PENDING = "OUTBOX_PENDING"
    NOTIFIED = "NOTIFIED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    SNOOZED = "SNOOZED"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class ProactiveCandidate:
    source: str
    kind: str
    principal_scope_key: str
    workspace_scope_key: str = ""
    workstream_scope_key: str = ""
    title: str = ""
    summary: str = ""
    priority: str = "normal"
    authority: str = ProactiveAuthority.PROACTIVE_CANDIDATE.value
    evidence_ids: tuple[str, ...] = ()
    source_ref: str = ""
    idempotency_key: str = ""
    intended_next_action: str = ProactiveIntendedNextAction.NONE.value
    reason_code: str = ProactiveReasonCode.OBSERVED.value
    state: str = ProactiveEventState.OBSERVED.value
    expires_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
