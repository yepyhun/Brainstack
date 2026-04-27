"""Optional Hermes proactive runtime extension."""

from .heartbeat_wake import (
    HeartbeatWakeDecision,
    HeartbeatWakeReason,
    HeartbeatWakeRequest,
    HeartbeatWakeResult,
    HeartbeatWakeState,
    classify_heartbeat_wake,
)

__all__ = [
    "HeartbeatWakeDecision",
    "HeartbeatWakeReason",
    "HeartbeatWakeRequest",
    "HeartbeatWakeResult",
    "HeartbeatWakeState",
    "classify_heartbeat_wake",
]
