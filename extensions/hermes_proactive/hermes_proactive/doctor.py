"""Doctor checks for the optional Hermes proactive extension."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .heartbeat_wake import HeartbeatWakeState
from .pulse_producer import classify_pulse_wake, produce_pulse


def _load_config(hermes_home: Path) -> tuple[dict[str, Any], dict[str, str]]:
    path = hermes_home / "config.yaml"
    if not path.exists():
        return {}, {"status": "missing", "reason_code": "CONFIG_FILE_MISSING", "config_path": str(path)}
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}, {"status": "unavailable", "reason_code": "PYYAML_UNAVAILABLE", "config_path": str(path)}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}, {"status": "unavailable", "reason_code": "CONFIG_READ_FAILED", "config_path": str(path)}
    if not isinstance(data, dict):
        return {}, {"status": "unavailable", "reason_code": "CONFIG_NOT_OBJECT", "config_path": str(path)}
    return data, {"status": "loaded", "reason_code": "CONFIG_LOADED", "config_path": str(path)}


def _nested_config(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    raw = data.get(name)
    return raw if isinstance(raw, Mapping) else {}


def _runtime_config(data: Mapping[str, Any], load_status: Mapping[str, str]) -> dict[str, Any]:
    kernel_memory = _nested_config(data, "kernel_memory")
    plugins = _nested_config(data, "plugins")
    brainstack = _nested_config(plugins, "brainstack") if isinstance(plugins, Mapping) else {}
    mode = data.get("proactive_mode") or kernel_memory.get("proactive_mode") or brainstack.get("proactive_mode") or "dry_run"
    kill_switch = data.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = kernel_memory.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = brainstack.get("proactive_kill_switch")
    cooldown = data.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = kernel_memory.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = brainstack.get("proactive_cooldown_seconds")
    return {
        "status": str(load_status.get("status") or "unknown"),
        "reason_code": str(load_status.get("reason_code") or ""),
        "config_path": str(load_status.get("config_path") or ""),
        "mode": str(mode or "unknown"),
        "kill_switch": bool(kill_switch) if kill_switch is not None else False,
        "cooldown_seconds": int(cooldown or 0) if str(cooldown or "").isdigit() else 0,
    }


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
    config_data, config_load = _load_config(hermes_home)
    runtime_config = _runtime_config(config_data, config_load)
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
