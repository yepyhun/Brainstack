"""Doctor checks for the optional Hermes proactive extension."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .heartbeat_wake import HeartbeatWakeRequest, HeartbeatWakeState, classify_heartbeat_wake
from .pulse_producer import produce_pulse


def proactive_extension_doctor(*, hermes_home: Path) -> dict[str, Any]:
    wake = classify_heartbeat_wake(HeartbeatWakeRequest(target="doctor"), HeartbeatWakeState()).to_dict()
    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="doctor",
        workspace_scope_key="doctor",
        stale_inbox_threshold=999,
    )
    return {
        "schema": "hermes_proactive.doctor.v1",
        "status": "pass" if wake["provider_calls"] == 0 and pulse["provider_calls"] == 0 else "fail",
        "heartbeat": wake,
        "pulse_idle": {
            "provider_calls": pulse["provider_calls"],
            "prompt_tokens": pulse["prompt_tokens"],
            "completion_tokens": pulse["completion_tokens"],
            "delivery_requested": pulse["delivery_requested"],
            "no_op": pulse["no_op"],
        },
    }
