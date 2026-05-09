"""Runtime config helpers for the optional Hermes proactive extension."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def _nested_config(data: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    raw = data.get(name)
    return raw if isinstance(raw, Mapping) else {}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _line_config_fallback(text: str) -> dict[str, Any]:
    """Dependency-free parser for the simple top-level proactive flags."""

    parsed: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line or line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key == "proactive_mode" and value:
            parsed["proactive_mode"] = value
        elif key == "proactive_kill_switch" and value:
            parsed["proactive_kill_switch"] = _parse_bool(value)
        elif key == "proactive_cooldown_seconds" and value:
            parsed["proactive_cooldown_seconds"] = value
    return parsed


def load_config_with_fallback(hermes_home: Path) -> tuple[dict[str, Any], dict[str, str]]:
    path = hermes_home / "config.yaml"
    if not path.exists():
        return {}, {"status": "missing", "reason_code": "CONFIG_FILE_MISSING", "config_path": str(path)}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}, {"status": "unavailable", "reason_code": "CONFIG_READ_FAILED", "config_path": str(path)}
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(text) or {}
    except Exception:
        fallback = _line_config_fallback(text)
        if fallback:
            return fallback, {"status": "fallback_loaded", "reason_code": "CONFIG_LINE_FALLBACK_LOADED", "config_path": str(path)}
        return {}, {"status": "unavailable", "reason_code": "CONFIG_READ_FAILED", "config_path": str(path)}
    if isinstance(data, dict):
        return data, {"status": "loaded", "reason_code": "CONFIG_LOADED", "config_path": str(path)}
    fallback = _line_config_fallback(text)
    if fallback:
        return fallback, {"status": "fallback_loaded", "reason_code": "CONFIG_LINE_FALLBACK_LOADED", "config_path": str(path)}
    return {}, {"status": "unavailable", "reason_code": "CONFIG_NOT_OBJECT", "config_path": str(path)}


def runtime_config_from_data(data: Mapping[str, Any], load_status: Mapping[str, str]) -> dict[str, Any]:
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
        "kill_switch": _parse_bool(kill_switch) if kill_switch is not None else False,
        "cooldown_seconds": int(cooldown or 0) if str(cooldown or "").isdigit() else 0,
    }


def load_runtime_config(hermes_home: Path) -> dict[str, Any]:
    data, status = load_config_with_fallback(hermes_home)
    return runtime_config_from_data(data, status)
