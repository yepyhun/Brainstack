"""Optional Hermes proactive runtime extension."""

from .evolver_signal import EvolverSignalDecision, classify_evolver_signal, load_evolver_signal_file
from .heartbeat_wake import (
    HeartbeatWakeDecision,
    HeartbeatWakeReason,
    HeartbeatWakeRequest,
    HeartbeatWakeResult,
    HeartbeatWakeState,
    classify_heartbeat_wake,
)
from .pulse_producer import classify_pulse_wake

__all__ = [
    "EvolverSignalDecision",
    "HeartbeatWakeDecision",
    "HeartbeatWakeReason",
    "HeartbeatWakeRequest",
    "HeartbeatWakeResult",
    "HeartbeatWakeState",
    "classify_evolver_signal",
    "classify_heartbeat_wake",
    "classify_pulse_wake",
    "load_evolver_signal_file",
]
