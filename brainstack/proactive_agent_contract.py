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
ACTIONABLE_SUBSTRATE_SCHEMA = "brainstack.actionable_substrate.v1"

PROACTIVE_ALLOWED_READ_ACTIONS = ("status", "doctor", "list", "inspect")
PROACTIVE_ALLOWED_CONTROL_ACTIONS = (
    "set_item_state",
    "snooze_item",
    "mute_item",
    "set_mode",
    "set_kill_switch",
    "pause_proactive",
    "resume_proactive",
    "set_cooldown_seconds",
)
PROACTIVE_BLOCKED_ACTIONS = (
    "send_notification",
    "start_scheduler",
    "install_evolver",
    "execute_task",
    "create_current_assignment",
)
PROACTIVE_MODE_VALUES = ("disabled", "dry_run", "live")


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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _brainstack_plugin_config(data: Mapping[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins") if isinstance(data, Mapping) else None
    if not isinstance(plugins, dict):
        return {}
    raw = plugins.get("brainstack") or {}
    return raw if isinstance(raw, dict) else {}


def _runtime_config_target(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key in data or "proactive_mode" in data or "proactive_kill_switch" in data or "proactive_cooldown_seconds" in data:
        return data
    kernel_memory_cfg = data.get("kernel_memory")
    if isinstance(kernel_memory_cfg, dict) and (
        key in kernel_memory_cfg
        or "proactive_mode" in kernel_memory_cfg
        or "proactive_kill_switch" in kernel_memory_cfg
        or "proactive_cooldown_seconds" in kernel_memory_cfg
    ):
        return kernel_memory_cfg
    brainstack_cfg = _brainstack_plugin_config(data)
    if isinstance(brainstack_cfg, dict) and (
        key in brainstack_cfg
        or "proactive_mode" in brainstack_cfg
        or "proactive_kill_switch" in brainstack_cfg
        or "proactive_cooldown_seconds" in brainstack_cfg
    ):
        return brainstack_cfg
    return data


def _write_runtime_config_value(data: dict[str, Any], key: str, value: Any, reason_code: str) -> None:
    target = _runtime_config_target(data, key)
    target[key] = value
    target["proactive_control_last_reason"] = reason_code


def _write_kill_switch_to_config(data: dict[str, Any], kill_switch: bool, reason_code: str) -> None:
    _write_runtime_config_value(data, "proactive_kill_switch", bool(kill_switch), reason_code)


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


def _agent_item_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item, Mapping) else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}
    signal = metadata.get("evolver_signal") if isinstance(metadata, Mapping) else None
    wake = metadata.get("wake") if isinstance(metadata, Mapping) else None
    signal_summary: dict[str, Any] = {}
    if isinstance(signal, Mapping):
        signal_summary = {
            "status": str(signal.get("status") or ""),
            "reason_code": str(signal.get("reason_code") or ""),
            "actionable": bool(signal.get("actionable")),
            "directive_count": _safe_int(signal.get("directive_count"), 0),
            "directive_kinds": [str(value) for value in signal.get("directive_kinds") or []],
            "directive_execution": str(signal.get("directive_execution") or ""),
            "raw_output_present": bool(signal.get("raw_output_present")),
        }
    wake_summary: dict[str, Any] = {}
    if isinstance(wake, Mapping):
        wake_summary = {
            "decision": str(wake.get("decision") or ""),
            "reason_code": str(wake.get("reason_code") or ""),
            "delivery_requested": bool(wake.get("delivery_requested")),
        }
    pending_or_failing_reason = ""
    if signal_summary.get("reason_code"):
        pending_or_failing_reason = str(signal_summary["reason_code"])
    elif wake_summary.get("reason_code"):
        pending_or_failing_reason = str(wake_summary["reason_code"])
    else:
        pending_or_failing_reason = str(item.get("reason_code") or "")
    return {
        "source": str(item.get("source") or ""),
        "kind": str(item.get("kind") or ""),
        "state": str(item.get("state") or ""),
        "priority": str(item.get("priority") or ""),
        "intended_next_action": str(item.get("intended_next_action") or ""),
        "pending_or_failing_reason": pending_or_failing_reason,
        "evolver_signal": signal_summary,
        "wake": wake_summary,
        "current_assignment_authority": False,
    }


def _outbox_summary(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "outbox_id": str(item.get("outbox_id") or ""),
            "event_id": str(item.get("event_id") or ""),
            "delivery_target": str(item.get("delivery_target") or ""),
            "delivery_state": str(item.get("delivery_state") or ""),
            "attempt_count": _safe_int(item.get("attempt_count"), 0),
            "intended_next_action": str(item.get("intended_next_action") or ""),
            "last_error_present": bool(str(item.get("last_error") or "")),
            "kind": str(item.get("kind") or ""),
            "priority": str(item.get("priority") or ""),
            "title": str(item.get("title") or "")[:160],
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        }
        for item in items
    ]


def _canonical_receipts_by_task_source(store: Any, principal_scope_key: str) -> dict[tuple[str, str], str]:
    if not hasattr(store, "list_canonical_memory_events"):
        return {}
    receipts: dict[tuple[str, str], str] = {}
    for row in store.list_canonical_memory_events(limit=500):
        event = _mapping(row.get("event"))
        scope = _mapping(event.get("scope"))
        claim = _mapping(event.get("claim"))
        authority = _mapping(event.get("authority"))
        source = _mapping(event.get("source"))
        if str(scope.get("principal_scope_key") or "") != str(principal_scope_key or ""):
            continue
        if str(claim.get("target_slot") or "") != "task.actionable":
            continue
        stable_fact_id = str(claim.get("stable_fact_id") or "")
        source_event_id = str(source.get("source_event_id") or "")
        receipt_id = str(authority.get("receipt_id") or "")
        if stable_fact_id and source_event_id and receipt_id:
            receipts[(stable_fact_id, source_event_id)] = receipt_id
    return receipts


def _actionable_substrate_summary(store: Any, principal_scope_key: str) -> dict[str, Any]:
    if not hasattr(store, "list_task_items"):
        return {
            "schema": ACTIONABLE_SUBSTRATE_SCHEMA,
            "source": "task_items",
            "available": False,
            "reason_code": "TASK_STORE_UNAVAILABLE",
            "pending_count": 0,
            "sampled_items": [],
        }
    receipt_index = _canonical_receipts_by_task_source(store, principal_scope_key)
    rows = store.list_task_items(
        principal_scope_key=principal_scope_key,
        item_type="task",
        statuses=("open",),
        limit=50,
    )
    sampled: list[dict[str, Any]] = []
    rejected_or_degraded = 0
    for row in rows:
        metadata = _mapping(row.get("metadata"))
        admission = _mapping(metadata.get("admission"))
        source_event_id = str(metadata.get("source_event_id") or admission.get("source_event_id") or "")
        source_span_id = str(metadata.get("source_span_id") or admission.get("source_span_id") or "")
        stable_key = str(row.get("stable_key") or admission.get("stable_key") or "")
        receipt_id = receipt_index.get((stable_key, source_event_id), "")
        is_actionable = (
            str(admission.get("target_slot") or "") == "task.actionable"
            and str(admission.get("decision") or "") in {"ACCEPT_DURABLE", "ACCEPT_WITH_SUPERSESSION"}
            and bool(metadata.get("truth_eligible"))
            and str(metadata.get("support_visibility") or "") == "answer_evidence"
            and bool(source_event_id and source_span_id and receipt_id)
        )
        if not is_actionable:
            rejected_or_degraded += 1
            continue
        sampled.append(
            {
                "stable_key": stable_key,
                "status": str(row.get("status") or ""),
                "title": str(row.get("title") or "")[:160],
                "source_event_id": source_event_id,
                "source_span_id": source_span_id,
                "receipt_id": receipt_id,
                "admission_reason_code": str(metadata.get("admission_reason_code") or admission.get("reason_code") or ""),
                "actionable_reason_code": "SOURCE_BACKED_ACTIONABLE_ADMITTED",
                "intended_next_action": "agent_may_consider_when_user_context_requires",
                "execution_payload_present": False,
                "current_assignment_authority": False,
            }
        )
    return {
        "schema": ACTIONABLE_SUBSTRATE_SCHEMA,
        "source": "task_items",
        "available": True,
        "read_only": True,
        "side_effect": False,
        "pending_count": len(sampled),
        "rejected_or_degraded_count": rejected_or_degraded,
        "sampled_items": sampled[:5],
        "model_use_contract": {
            "may_surface_as_pending_work": True,
            "must_not_send_notification": True,
            "must_not_execute_task": True,
            "must_not_schedule_task": True,
        },
        "reason_code": "SOURCE_BACKED_ACTIONABLE_SUBSTRATE_COMPACT",
    }


def _store_counts(store: Any, principal_scope_key: str) -> dict[str, Any]:
    items = store.list_proactive_items(principal_scope_key=principal_scope_key, limit=200)
    state_counts = Counter(str(item.get("state") or "") for item in items)
    pending_outbox = store.list_pending_proactive_outbox(limit=200)
    latest = items[0] if items else {}
    actionable_substrate = _actionable_substrate_summary(store, principal_scope_key)
    return {
        "total_items_sampled": len(items),
        "state_counts": dict(sorted(state_counts.items())),
        "pending_outbox_count": len(pending_outbox),
        "pending_outbox_sample": _outbox_summary(pending_outbox[:5]),
        "actionable_substrate": actionable_substrate,
        "pending_actionable_substrate_count": actionable_substrate.get("pending_count", 0),
        "latest_item_summary": {
            "event_id": str(latest.get("event_id") or ""),
            "updated_at": str(latest.get("updated_at") or ""),
            "agent_summary": _agent_item_summary(latest),
        }
        if latest
        else {},
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
    runtime_config = _runtime_config_summary(config_data, load_status)
    counts = _store_counts(store, principal_scope_key)
    return {
        "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
        "operation": "status",
        "read_only": True,
        "side_effect": False,
        "bounded_model_facing": True,
        "status_source": "brainstack_store_and_hermes_config",
        "principal_scope_key": str(principal_scope_key or ""),
        "capability_summary": "Inspectable proactive state; control is limited to explicit user-requested mode/item changes.",
        "extension": _extension_status(),
        "config": runtime_config,
        "counts": counts,
        "allowed_actions": list(PROACTIVE_ALLOWED_READ_ACTIONS + PROACTIVE_ALLOWED_CONTROL_ACTIONS),
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
        "model_use_contract": {
            "answer_source": "this_compact_status",
            "do_not_infer_current_assignment": True,
            "do_not_claim_notifications_are_enabled_from_memory": True,
            "do_not_call_search_files_for_proactive_config": True,
        },
        "reason_code": "PROACTIVE_STATUS_TOOL_BACKED_COMPACT",
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
                "source": str(item.get("source") or ""),
                "source_ref": str(item.get("source_ref") or ""),
                "kind": str(item.get("kind") or ""),
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or "")[:500],
                "priority": str(item.get("priority") or ""),
                "state": str(item.get("state") or ""),
                "reason_code": str(item.get("reason_code") or ""),
                "intended_next_action": str(item.get("intended_next_action") or ""),
                "evidence_count": len(item.get("evidence_ids") or []),
                "updated_at": str(item.get("updated_at") or ""),
                "agent_summary": _agent_item_summary(item),
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
    payload["agent_summary"] = _agent_item_summary(item)
    payload["outbox_summary"] = _outbox_summary([entry for entry in payload.get("outbox") or [] if isinstance(entry, Mapping)])
    payload["reason_code"] = "PROACTIVE_INSPECT_TOOL_BACKED"
    return payload


def _require_explicit_request(args: Mapping[str, Any]) -> dict[str, Any] | None:
    if not str(args.get("_trusted_operator_origin") or "").strip():
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "TRUSTED_OPERATOR_APPROVAL_REQUIRED",
            "error": "Proactive control requires a host-supplied trusted operator approval origin.",
        }
    if args.get("explicit_user_request") is True:
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


def _update_runtime_config(
    *,
    config: Mapping[str, Any] | None,
    action: str,
    key: str,
    value: Any,
    reason_code: str,
) -> dict[str, Any]:
    hermes_home = _resolve_hermes_home(config)
    config_path = _config_path_from_home(hermes_home)
    data, load_status = _load_yaml(config_path)
    if str(load_status.get("status") or "") != "loaded" or config_path is None:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": str(load_status.get("reason_code") or "CONFIG_UNAVAILABLE"),
            "config": _runtime_config_summary(data, load_status),
        }
    _write_runtime_config_value(data, key, value, reason_code)
    _write_yaml(config_path, data)
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": action,
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "config_path": str(config_path),
        key: value,
        "reason_code": "PROACTIVE_RUNTIME_CONFIG_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
        "effective_without_container_restart": True,
        "effective_scope": "config_backed_status_and_next_proactive_pulse",
    }


def _normalize_proactive_mode(value: Any) -> str:
    return str(value or "").strip().lower()


def _set_proactive_mode(
    *,
    config: Mapping[str, Any] | None,
    mode: str,
    action: str,
    reason_code: str,
) -> dict[str, Any]:
    normalized_mode = _normalize_proactive_mode(mode)
    if normalized_mode not in PROACTIVE_MODE_VALUES:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "mode": normalized_mode,
            "allowed_modes": list(PROACTIVE_MODE_VALUES),
            "reason_code": "INVALID_PROACTIVE_MODE",
            "current_assignment_authority": False,
        }
    return _update_runtime_config(
        config=config,
        action=action,
        key="proactive_mode",
        value=normalized_mode,
        reason_code=reason_code or "EXPLICIT_USER_REQUEST",
    )


def set_proactive_mode_from_explicit_request(
    *,
    args: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if args.get("explicit_user_request") is not True:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_mode",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "EXPLICIT_USER_REQUEST_REQUIRED",
            "error": "Changing proactive mode requires explicit_user_request=true.",
            "current_assignment_authority": False,
        }
    return _set_proactive_mode(
        config=config,
        mode=str(args.get("mode") or ""),
        action="set_mode",
        reason_code=str(args.get("reason_code") or "EXPLICIT_USER_REQUEST"),
    )


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
    if action == "set_mode":
        return _set_proactive_mode(
            config=config,
            mode=str(args.get("mode") or ""),
            action=action,
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "set_kill_switch":
        return _set_kill_switch(
            config=config,
            kill_switch=bool(args.get("kill_switch")),
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "pause_proactive":
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_mode",
            value="disabled",
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "resume_proactive":
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_mode",
            value="live",
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "set_cooldown_seconds":
        cooldown = max(0, min(_safe_int(args.get("cooldown_seconds"), 0), 604800))
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_cooldown_seconds",
            value=cooldown,
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action in {"snooze_item", "mute_item"}:
        event_id = str(args.get("event_id") or "").strip()
        inspected = inspect_proactive_agent_item(store=store, principal_scope_key=principal_scope_key, event_id=event_id)
        if inspected.get("reason_code") != "PROACTIVE_INSPECT_TOOL_BACKED":
            inspected["schema"] = PROACTIVE_AGENT_CONTROL_SCHEMA
            inspected["operation"] = "control"
            inspected["action"] = action
            inspected["read_only"] = False
            inspected["side_effect"] = False
            return inspected
        metadata = {"explicit_user_request": True}
        if action == "snooze_item":
            metadata["snooze_until"] = str(args.get("snooze_until") or "")
            metadata["control"] = "snoozed"
        else:
            metadata["muted"] = True
            metadata["control"] = "muted"
        payload = store.set_proactive_item_state(
            event_id=event_id,
            state=ProactiveEventState.SUPPRESSED.value,
            reason_code=reason_code or (ProactiveReasonCode.SNOOZED.value if action == "snooze_item" else "MUTED"),
            actor="agent_explicit_user_request",
            trace_id=str(args.get("trace_id") or ""),
            metadata=metadata,
        )
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "committed",
            "read_only": False,
            "side_effect": True,
            "event_id": event_id,
            "state": ProactiveEventState.SUPPRESSED.value,
            "result": payload,
            "reason_code": "PROACTIVE_ITEM_STATE_UPDATED",
            "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
            "current_assignment_authority": False,
        }
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
