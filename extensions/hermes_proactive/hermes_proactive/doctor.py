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


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _proactive_state_report(*, hermes_home: Path, runtime_config: Mapping[str, Any], config_data: Mapping[str, Any]) -> dict[str, Any]:
    state_base = Path(str(runtime_config.get("state_base_dir") or hermes_home / "home" / "brainstack"))
    plugins = config_data.get("plugins") if isinstance(config_data.get("plugins"), Mapping) else {}
    brainstack = plugins.get("brainstack") if isinstance(plugins.get("brainstack"), Mapping) else {}
    flat_paths = [
        str(brainstack.get(key) or "")
        for key in ("db_path", "graph_db_path", "corpus_db_path")
    ]
    has_path_override = any(path and "$HERMES_HOME" not in path and "${HERMES_HOME}" not in path for path in flat_paths)
    explicit_state_base = str(runtime_config.get("state_base_source") or "") != "default"
    partial = has_path_override and not explicit_state_base
    status = "partial_isolation_shared_proactive_runtime" if partial else "pass"
    return {
        "schema": "hermes_proactive.state_base.v1",
        "status": status,
        "state_base_dir": str(state_base),
        "state_base_source": str(runtime_config.get("state_base_source") or ""),
        "default_state_base_dir": str(runtime_config.get("default_state_base_dir") or hermes_home / "home" / "brainstack"),
        "exists": state_base.exists(),
        "under_hermes_home": _is_relative_to(state_base, hermes_home),
        "explicit_state_base": explicit_state_base,
        "path_override_detected": has_path_override,
        "full_isolation_certified": not partial,
    }


def proactive_extension_doctor(
    *,
    hermes_home: Path,
    evolver_health_file: Path | None = None,
    wake_state: HeartbeatWakeState | None = None,
) -> dict[str, Any]:
    config_data, config_load = load_config_with_fallback(hermes_home)
    runtime_config = runtime_config_from_data(config_data, config_load, hermes_home=hermes_home)
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
    state_base = _proactive_state_report(hermes_home=hermes_home, runtime_config=runtime_config, config_data=config_data)
    issues: list[str] = []
    if pulse_summary["provider_calls"] or pulse_summary["prompt_tokens"] or pulse_summary["completion_tokens"]:
        issues.append("PULSE_USED_PROVIDER_OR_TOKENS")
    if int(wake.get("provider_calls") or 0) or int(wake.get("transcript_writes") or 0):
        issues.append("WAKE_USED_PROVIDER_OR_TRANSCRIPT")
    issues.extend([str(reason) for reason in pulse_summary.get("signal_reason_codes") or [] if str(reason) == "EVOLVER_SIGNAL_MALFORMED"])
    if state_base["status"] == "partial_isolation_shared_proactive_runtime":
        issues.append("PARTIAL_ISOLATION_SHARED_PROACTIVE_RUNTIME")
    status = "degraded" if issues and "EVOLVER_SIGNAL_MALFORMED" in issues else "pass"
    if "PARTIAL_ISOLATION_SHARED_PROACTIVE_RUNTIME" in issues:
        status = "degraded"
    return {
        "schema": "hermes_proactive.doctor.v1",
        "status": status,
        "proactive_status": proactive_status,
        "config": runtime_config,
        "state_base": state_base,
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
