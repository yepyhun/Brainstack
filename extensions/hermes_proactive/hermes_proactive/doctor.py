"""Doctor checks for the optional Hermes proactive extension."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import load_config_with_fallback, runtime_config_from_data
from .heartbeat_wake import HeartbeatWakeState
from .pulse_producer import classify_pulse_wake, produce_pulse


def _pulse_summary(pulse: Mapping[str, Any]) -> dict[str, Any]:
    tasks = [item for item in pulse.get("tasks") or [] if isinstance(item, Mapping)]
    events = [item for item in pulse.get("events") or [] if isinstance(item, Mapping)]
    signal_reasons: list[str] = []
    signal_statuses: list[str] = []
    for item in tasks:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        signal = metadata.get("evolver_signal") if isinstance(metadata, Mapping) else None
        if isinstance(signal, Mapping):
            reason = str(signal.get("reason_code") or "")
            status = str(signal.get("status") or "")
            if reason:
                signal_reasons.append(reason)
            if status:
                signal_statuses.append(status)
    return {
        "status": str(pulse.get("status") or ""),
        "no_op": bool(pulse.get("no_op")),
        "task_count": len(tasks),
        "event_count": len(events),
        "candidate_count": int(pulse.get("candidate_count") or 0),
        "signal_reason_codes": signal_reasons,
        "signal_statuses": signal_statuses,
        "provider_calls": int(pulse.get("provider_calls") or 0),
        "prompt_tokens": int(pulse.get("prompt_tokens") or 0),
        "completion_tokens": int(pulse.get("completion_tokens") or 0),
    }


def _proactive_status(*, runtime_config: Mapping[str, Any], pulse: Mapping[str, Any], wake: Mapping[str, Any]) -> str:
    if runtime_config.get("kill_switch"):
        return "killed"
    if str(runtime_config.get("mode") or "") == "disabled":
        return "paused"
    summary = _pulse_summary(pulse)
    if "malformed" in set(summary.get("signal_statuses") or []):
        return "degraded"
    if bool(wake.get("delivery_requested")):
        return "active"
    if bool(pulse.get("no_op")):
        return "idle"
    return "observed"


def proactive_extension_doctor(
    *,
    hermes_home: Path,
    evolver_health_file: Path | None = None,
    wake_state: HeartbeatWakeState | None = None,
) -> dict[str, Any]:
    config_data, config_load = load_config_with_fallback(hermes_home)
    runtime_config = runtime_config_from_data(config_data, config_load)
    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="doctor",
        workspace_scope_key="doctor",
        evolver_health_file=evolver_health_file,
        stale_inbox_threshold=999,
    )
    killed = bool(runtime_config.get("kill_switch"))
    paused = str(runtime_config.get("mode") or "") == "disabled"
    live_mode = str(runtime_config.get("mode") or "") == "live"
    create_outbox = live_mode and not paused
    effective_wake_state = HeartbeatWakeState(enabled=False) if killed else wake_state
    wake = classify_pulse_wake(
        pulse,
        create_outbox=create_outbox,
        wake_state=effective_wake_state,
    )
    pulse_summary = _pulse_summary(pulse)
    proactive_status = _proactive_status(runtime_config=runtime_config, pulse=pulse, wake=wake)
    issues: list[str] = []
    if pulse_summary["provider_calls"] or pulse_summary["prompt_tokens"] or pulse_summary["completion_tokens"]:
        issues.append("PULSE_USED_PROVIDER_OR_TOKENS")
    if int(wake.get("provider_calls") or 0) or int(wake.get("transcript_writes") or 0):
        issues.append("WAKE_USED_PROVIDER_OR_TRANSCRIPT")
    issues.extend([str(reason) for reason in pulse_summary.get("signal_reason_codes") or [] if str(reason) == "EVOLVER_SIGNAL_MALFORMED"])
    status = "degraded" if issues and "EVOLVER_SIGNAL_MALFORMED" in issues else "pass"
    return {
        "schema": "hermes_proactive.doctor.v1",
        "status": status,
        "proactive_status": proactive_status,
        "config": runtime_config,
        "pulse": pulse_summary,
        "wake": wake,
        "issues": issues,
        "provider_calls": pulse_summary["provider_calls"],
        "prompt_tokens": pulse_summary["prompt_tokens"],
        "completion_tokens": pulse_summary["completion_tokens"],
        "heartbeat": wake,
        "pulse_idle": {
            "provider_calls": pulse_summary["provider_calls"],
            "prompt_tokens": pulse_summary["prompt_tokens"],
            "completion_tokens": pulse_summary["completion_tokens"],
            "delivery_requested": wake["delivery_requested"],
            "no_op": pulse_summary["no_op"],
        },
    }
