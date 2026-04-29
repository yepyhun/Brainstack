"""Agent-facing contract for Brainstack proactive state.

This module exposes proactive memory as explicit status and control data.
It does not schedule, notify, execute, approve actions, or rewrite output.
"""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
from typing import Any, Mapping

from .core.proactive import ProactiveEventState, ProactiveReasonCode


PROACTIVE_AGENT_CONTRACT_SCHEMA = "brainstack.proactive_agent_surface.v1"
PROACTIVE_AGENT_CONTROL_SCHEMA = "brainstack.proactive_agent_control.v1"

PROACTIVE_ALLOWED_READ_ACTIONS = ("status", "doctor", "list", "inspect")
PROACTIVE_ALLOWED_CONTROL_ACTIONS = ("set_item_state", "set_kill_switch")
PROACTIVE_BLOCKED_ACTIONS = (
    "send_notification",
    "start_scheduler",
    "install_evolver",
    "execute_task",
    "create_current_assignment",
)
PROACTIVE_MODE_VALUES = ("disabled", "dry_run", "automatic", "live")


def proactive_capability_card() -> dict[str, Any]:
    return {
        "schema": "brainstack.proactive_capability_card.v1",
        "summary": (
            "Brainstack proactive state is an inspectable memory-kernel surface. "
            "Use proactive status/list/inspect tools for facts. Control is limited "
            "to explicit user-requested state changes."
        ),
        "allowed_read_actions": list(PROACTIVE_ALLOWED_READ_ACTIONS),
        "allowed_control_actions": list(PROACTIVE_ALLOWED_CONTROL_ACTIONS),
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_hermes_home(config: Mapping[str, Any] | None = None) -> Path | None:
    raw = ""
    if isinstance(config, Mapping):
        raw = str(config.get("hermes_home") or config.get("_hermes_home") or "").strip()
    if not raw:
        raw = os.getenv("HERMES_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    try:
        from hermes_constants import get_hermes_home  # type: ignore[import-not-found]

        return Path(get_hermes_home()).expanduser()
    except Exception:
        return None


def _resolve_hermes_root_from_package() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "brainstack" and parent.parent.name == "memory" and parent.parent.parent.name == "plugins":
            return parent.parent.parent.parent
    return None


def _config_path_from_home(hermes_home: Path | None) -> Path | None:
    if hermes_home is None:
        return None
    return hermes_home / "config.yaml"


def _load_yaml(path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        return {}, {"status": "unavailable", "reason_code": "HERMES_HOME_UNRESOLVED"}
    if not path.exists():
        return {}, {"status": "missing", "config_path": str(path), "reason_code": "CONFIG_FILE_MISSING"}
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "PYYAML_UNAVAILABLE"}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "CONFIG_READ_FAILED", "error": str(exc)}
    if not isinstance(data, dict):
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "CONFIG_NOT_OBJECT"}
    return data, {"status": "loaded", "config_path": str(path), "reason_code": "CONFIG_LOADED"}


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    import yaml  # type: ignore[import-untyped]

    path.write_text(
        yaml.safe_dump(dict(data), default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _runtime_config_summary(config_data: Mapping[str, Any], load_status: Mapping[str, Any]) -> dict[str, Any]:
    plugins = config_data.get("plugins") if isinstance(config_data, Mapping) else {}
    plugin_cfg = {}
    brainstack_cfg = {}
    if isinstance(plugins, Mapping):
        raw = plugins.get("hermes_proactive") or plugins.get("proactive") or {}
        if isinstance(raw, Mapping):
            plugin_cfg = dict(raw)
        raw_brainstack = plugins.get("brainstack") or {}
        if isinstance(raw_brainstack, Mapping):
            brainstack_cfg = dict(raw_brainstack)
    proactive_block = config_data.get("proactive")
    proactive_cfg = dict(proactive_block) if isinstance(proactive_block, Mapping) else {}
    kernel_memory_block = config_data.get("kernel_memory")
    kernel_memory_cfg = dict(kernel_memory_block) if isinstance(kernel_memory_block, Mapping) else {}
    mode = (
        config_data.get("proactive_mode")
        or kernel_memory_cfg.get("proactive_mode")
        or brainstack_cfg.get("proactive_mode")
        or plugin_cfg.get("mode")
        or proactive_cfg.get("mode")
    )
    kill_switch = config_data.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = kernel_memory_cfg.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = brainstack_cfg.get("proactive_kill_switch")
    cooldown = config_data.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = kernel_memory_cfg.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = brainstack_cfg.get("proactive_cooldown_seconds")
    return {
        "status": str(load_status.get("status") or "unknown"),
        "reason_code": str(load_status.get("reason_code") or ""),
        "config_path": str(load_status.get("config_path") or ""),
        "mode": str(mode or "unknown"),
        "kill_switch": bool(kill_switch) if kill_switch is not None else False,
        "cooldown_seconds": _safe_int(cooldown, 0),
        "kernel_memory_mode": str(kernel_memory_cfg.get("proactive_mode") or ""),
        "brainstack_plugin_mode": str(brainstack_cfg.get("proactive_mode") or ""),
        "plugin_mode": str(plugin_cfg.get("mode") or ""),
        "source": "hermes_config_yaml",
    }


def _write_kill_switch_to_config(data: dict[str, Any], kill_switch: bool, reason_code: str) -> None:
    plugins = data.get("plugins")
    brainstack_cfg = {}
    if isinstance(plugins, Mapping):
        raw_brainstack = plugins.get("brainstack") or {}
        if isinstance(raw_brainstack, Mapping):
            brainstack_cfg = raw_brainstack
    if "proactive_kill_switch" in data:
        data["proactive_kill_switch"] = bool(kill_switch)
        data["proactive_control_last_reason"] = reason_code
        return
    kernel_memory_cfg = data.get("kernel_memory")
    if isinstance(kernel_memory_cfg, dict) and (
        "proactive_kill_switch" in kernel_memory_cfg or "proactive_mode" in kernel_memory_cfg
    ):
        kernel_memory_cfg["proactive_kill_switch"] = bool(kill_switch)
        kernel_memory_cfg["proactive_control_last_reason"] = reason_code
        return
    if isinstance(brainstack_cfg, dict) and (
        "proactive_kill_switch" in brainstack_cfg or "proactive_mode" in brainstack_cfg
    ):
        brainstack_cfg["proactive_kill_switch"] = bool(kill_switch)
        brainstack_cfg["proactive_control_last_reason"] = reason_code
        return
    data["proactive_kill_switch"] = bool(kill_switch)
    data["proactive_control_last_reason"] = reason_code


def _extension_status() -> dict[str, Any]:
    root = _resolve_hermes_root_from_package()
    if root is None:
        return {
            "installed": False,
            "status": "unknown",
            "reason_code": "HERMES_ROOT_UNRESOLVED",
            "source": "brainstack_package_path",
        }
    extension_path = root / "extensions" / "hermes_proactive"
    return {
        "installed": extension_path.exists(),
        "status": "installed" if extension_path.exists() else "missing",
        "path": str(extension_path),
        "reason_code": "EXTENSION_PATH_EXISTS" if extension_path.exists() else "EXTENSION_PATH_MISSING",
        "source": "brainstack_package_path",
    }


def _store_counts(store: Any, principal_scope_key: str) -> dict[str, Any]:
    items = store.list_proactive_items(principal_scope_key=principal_scope_key, limit=200)
    state_counts = Counter(str(item.get("state") or "") for item in items)
    pending_outbox = store.list_pending_proactive_outbox(limit=200)
    return {
        "total_items_sampled": len(items),
        "state_counts": dict(sorted(state_counts.items())),
        "pending_outbox_count": len(pending_outbox),
        "recent_cost": store.proactive_recent_cost(limit=100),
    }


def build_proactive_status(
    *,
    store: Any,
    principal_scope_key: str,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    hermes_home = _resolve_hermes_home(config)
    config_data, load_status = _load_yaml(_config_path_from_home(hermes_home))
    return {
        "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
        "operation": "status",
        "read_only": True,
        "side_effect": False,
        "status_source": "brainstack_store_and_hermes_config",
        "principal_scope_key": str(principal_scope_key or ""),
        "capability_card": proactive_capability_card(),
        "extension": _extension_status(),
        "config": _runtime_config_summary(config_data, load_status),
        "counts": _store_counts(store, principal_scope_key),
        "allowed_actions": list(PROACTIVE_ALLOWED_READ_ACTIONS + PROACTIVE_ALLOWED_CONTROL_ACTIONS),
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
        "model_use_contract": {
            "answer_source": "this_tool_result",
            "do_not_infer_current_assignment": True,
            "do_not_claim_notifications_are_enabled_from_memory": True,
        },
        "reason_code": "PROACTIVE_STATUS_TOOL_BACKED",
    }


def list_proactive_agent_items(
    *,
    store: Any,
    principal_scope_key: str,
    state: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    items = store.list_proactive_items(
        principal_scope_key=principal_scope_key,
        state=str(state or ""),
        limit=max(1, min(int(limit or 20), 50)),
    )
    summaries = []
    for item in items:
        summaries.append(
            {
                "event_id": str(item.get("event_id") or ""),
                "kind": str(item.get("kind") or ""),
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or "")[:500],
                "priority": str(item.get("priority") or ""),
                "state": str(item.get("state") or ""),
                "intended_next_action": str(item.get("intended_next_action") or ""),
                "evidence_count": len(item.get("evidence_ids") or []),
                "updated_at": str(item.get("updated_at") or ""),
                "current_assignment_authority": False,
            }
        )
    return {
        "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
        "operation": "list",
        "read_only": True,
        "side_effect": False,
        "principal_scope_key": str(principal_scope_key or ""),
        "state_filter": str(state or ""),
        "limit": max(1, min(int(limit or 20), 50)),
        "items": summaries,
        "item_count": len(summaries),
        "current_assignment_authority": False,
        "reason_code": "PROACTIVE_LIST_TOOL_BACKED",
    }


def inspect_proactive_agent_item(
    *,
    store: Any,
    principal_scope_key: str,
    event_id: str,
) -> dict[str, Any]:
    try:
        payload = store.inspect_proactive_item(event_id=str(event_id or ""))
    except KeyError:
        return {
            "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
            "operation": "inspect",
            "status": "not_found",
            "read_only": True,
            "side_effect": False,
            "event_id": str(event_id or ""),
            "reason_code": "PROACTIVE_ITEM_NOT_FOUND",
        }
    item = payload.get("item") or {}
    if str(item.get("principal_scope_key") or "") != str(principal_scope_key or ""):
        return {
            "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
            "operation": "inspect",
            "status": "rejected",
            "read_only": True,
            "side_effect": False,
            "event_id": str(event_id or ""),
            "reason_code": "PROACTIVE_ITEM_SCOPE_MISMATCH",
        }
    payload["schema"] = PROACTIVE_AGENT_CONTRACT_SCHEMA
    payload["operation"] = "inspect"
    payload["read_only"] = True
    payload["side_effect"] = False
    payload["current_assignment_authority"] = False
    payload["reason_code"] = "PROACTIVE_INSPECT_TOOL_BACKED"
    return payload


def _require_explicit_request(args: Mapping[str, Any]) -> dict[str, Any] | None:
    if bool(args.get("explicit_user_request")):
        return None
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "status": "rejected",
        "read_only": False,
        "side_effect": False,
        "reason_code": "EXPLICIT_USER_REQUEST_REQUIRED",
        "error": "Proactive control requires explicit_user_request=true.",
    }


def _set_kill_switch(
    *,
    config: Mapping[str, Any] | None,
    kill_switch: bool,
    reason_code: str,
) -> dict[str, Any]:
    hermes_home = _resolve_hermes_home(config)
    config_path = _config_path_from_home(hermes_home)
    data, load_status = _load_yaml(config_path)
    if str(load_status.get("status") or "") != "loaded" or config_path is None:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_kill_switch",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": str(load_status.get("reason_code") or "CONFIG_UNAVAILABLE"),
            "config": _runtime_config_summary(data, load_status),
        }
    _write_kill_switch_to_config(data, bool(kill_switch), reason_code)
    _write_yaml(config_path, data)
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": "set_kill_switch",
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "config_path": str(config_path),
        "kill_switch": bool(kill_switch),
        "reason_code": "PROACTIVE_KILL_SWITCH_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
    }


def control_proactive_agent_surface(
    *,
    store: Any,
    principal_scope_key: str,
    args: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rejection = _require_explicit_request(args)
    if rejection is not None:
        return rejection
    action = str(args.get("action") or "").strip()
    reason_code = str(args.get("reason_code") or ProactiveReasonCode.BLOCKED.value).strip()
    if action == "set_kill_switch":
        return _set_kill_switch(
            config=config,
            kill_switch=bool(args.get("kill_switch")),
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action != "set_item_state":
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "UNSUPPORTED_PROACTIVE_CONTROL_ACTION",
            "allowed_actions": list(PROACTIVE_ALLOWED_CONTROL_ACTIONS),
            "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        }
    event_id = str(args.get("event_id") or "").strip()
    state = str(args.get("state") or "").strip()
    valid_states = {item.value for item in ProactiveEventState}
    if state not in valid_states:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_item_state",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "event_id": event_id,
            "reason_code": "INVALID_PROACTIVE_ITEM_STATE",
            "allowed_states": sorted(valid_states),
        }
    inspected = inspect_proactive_agent_item(store=store, principal_scope_key=principal_scope_key, event_id=event_id)
    if inspected.get("reason_code") != "PROACTIVE_INSPECT_TOOL_BACKED":
        inspected["schema"] = PROACTIVE_AGENT_CONTROL_SCHEMA
        inspected["operation"] = "control"
        inspected["action"] = "set_item_state"
        inspected["read_only"] = False
        inspected["side_effect"] = False
        return inspected
    payload = store.set_proactive_item_state(
        event_id=event_id,
        state=state,
        reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        actor="agent_explicit_user_request",
        trace_id=str(args.get("trace_id") or ""),
        metadata={"explicit_user_request": True},
    )
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": "set_item_state",
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "event_id": event_id,
        "state": state,
        "result": payload,
        "reason_code": "PROACTIVE_ITEM_STATE_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
    }
