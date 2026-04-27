"""Hermes-owned heartbeat wake lane contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Mapping


HEARTBEAT_WAKE_SCHEMA = "hermes_proactive.heartbeat_wake.v1"


class HeartbeatWakeDecision(StrEnum):
    READY = "ready"
    COALESCED = "coalesced"
    RETRY_LATER = "retry_later"
    STALE_CANCELLED = "stale_cancelled"
    DISABLED = "disabled"


class HeartbeatWakeReason(StrEnum):
    READY_TO_RUN = "READY_TO_RUN"
    DUPLICATE_IN_FLIGHT = "DUPLICATE_IN_FLIGHT"
    MAIN_LANE_BUSY = "MAIN_LANE_BUSY"
    STALE_RUNNING_LOCK = "STALE_RUNNING_LOCK"
    HEARTBEAT_DISABLED = "HEARTBEAT_DISABLED"


@dataclass(frozen=True)
class HeartbeatWakeRequest:
    target: str
    source: str = "heartbeat"
    run_id: str | None = None
    idempotency_key: str | None = None
    requested_at: datetime | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def effective_idempotency_key(self) -> str:
        if self.idempotency_key:
            return self.idempotency_key
        if self.run_id:
            return f"{self.source}:{self.target}:{self.run_id}"
        day_bucket = (self.requested_at or datetime.now(UTC)).strftime("%Y%m%d%H%M")
        return f"{self.source}:{self.target}:{day_bucket}"


@dataclass(frozen=True)
class HeartbeatWakeState:
    enabled: bool = True
    main_lane_busy: bool = False
    running_idempotency_key: str | None = None
    running_since: datetime | None = None
    stale_after_seconds: int = 900


@dataclass(frozen=True)
class HeartbeatWakeResult:
    schema: str
    decision: HeartbeatWakeDecision
    reason_code: HeartbeatWakeReason
    idempotency_key: str
    target: str
    provider_calls: int = 0
    transcript_writes: int = 0
    delivery_requested: bool = False
    retry_after_seconds: int | None = None
    stale_lock_cancelled: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "decision": self.decision.value,
            "reason_code": self.reason_code.value,
            "idempotency_key": self.idempotency_key,
            "target": self.target,
            "provider_calls": self.provider_calls,
            "transcript_writes": self.transcript_writes,
            "delivery_requested": self.delivery_requested,
            "retry_after_seconds": self.retry_after_seconds,
            "stale_lock_cancelled": self.stale_lock_cancelled,
        }


def classify_heartbeat_wake(
    request: HeartbeatWakeRequest,
    state: HeartbeatWakeState,
    *,
    now: datetime | None = None,
) -> HeartbeatWakeResult:
    timestamp = now or datetime.now(UTC)
    key = request.effective_idempotency_key()
    if not state.enabled:
        return HeartbeatWakeResult(HEARTBEAT_WAKE_SCHEMA, HeartbeatWakeDecision.DISABLED, HeartbeatWakeReason.HEARTBEAT_DISABLED, key, request.target)
    if state.running_idempotency_key == key:
        return HeartbeatWakeResult(HEARTBEAT_WAKE_SCHEMA, HeartbeatWakeDecision.COALESCED, HeartbeatWakeReason.DUPLICATE_IN_FLIGHT, key, request.target)
    if state.running_idempotency_key and state.running_since:
        if timestamp - state.running_since > timedelta(seconds=max(state.stale_after_seconds, 1)):
            return HeartbeatWakeResult(
                HEARTBEAT_WAKE_SCHEMA,
                HeartbeatWakeDecision.STALE_CANCELLED,
                HeartbeatWakeReason.STALE_RUNNING_LOCK,
                key,
                request.target,
                stale_lock_cancelled=True,
            )
    if state.main_lane_busy:
        return HeartbeatWakeResult(
            HEARTBEAT_WAKE_SCHEMA,
            HeartbeatWakeDecision.RETRY_LATER,
            HeartbeatWakeReason.MAIN_LANE_BUSY,
            key,
            request.target,
            retry_after_seconds=30,
        )
    return HeartbeatWakeResult(HEARTBEAT_WAKE_SCHEMA, HeartbeatWakeDecision.READY, HeartbeatWakeReason.READY_TO_RUN, key, request.target)
