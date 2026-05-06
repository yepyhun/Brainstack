from __future__ import annotations

from typing import Any, Mapping


BACKGROUND_TASK_STATUS_SCHEMA = "brainstack.background_task_status.v1"

BACKGROUND_CONSOLIDATION_TASK_ID = "brainstack.background_consolidation"
CAPTURE_UNDERSTANDING_TASK_ID = "brainstack.capture_understanding"
QUERY_UNDERSTANDING_TASK_ID = "brainstack.query_understanding"

BACKGROUND_CONSOLIDATION_HERMES_TASK_SLOT = "flush_memories"
CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT = "brainstack_capture_understanding"
QUERY_UNDERSTANDING_HERMES_TASK_SLOT = "brainstack_query_understanding"

REQUIRED_BACKGROUND_TASK_BINDINGS: tuple[dict[str, str], ...] = (
    {
        "task_id": BACKGROUND_CONSOLIDATION_TASK_ID,
        "hermes_task_slot": BACKGROUND_CONSOLIDATION_HERMES_TASK_SLOT,
        "purpose": "tier2_candidate_consolidation",
    },
    {
        "task_id": CAPTURE_UNDERSTANDING_TASK_ID,
        "hermes_task_slot": CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT,
        "purpose": "structured_capture_understanding",
    },
    {
        "task_id": QUERY_UNDERSTANDING_TASK_ID,
        "hermes_task_slot": QUERY_UNDERSTANDING_HERMES_TASK_SLOT,
        "purpose": "structured_query_understanding",
    },
)

BACKGROUND_TASK_IDS = tuple(binding["task_id"] for binding in REQUIRED_BACKGROUND_TASK_BINDINGS)
BACKGROUND_TASK_SLOT_BY_ID = {
    binding["task_id"]: binding["hermes_task_slot"] for binding in REQUIRED_BACKGROUND_TASK_BINDINGS
}

VALID_BACKGROUND_TASK_STATUSES = {"active", "configured_unavailable", "experimental", "blocked"}

READY_ROUTE_STATUS = "ready"
UNAVAILABLE_ROUTE_STATUS = "unavailable"
BLOCKED_ROUTE_STATUS = "blocked"

REASON_ROUTE_READY = "AUXILIARY_ROUTE_READY"
REASON_MISSING_ROUTE = "AUXILIARY_ROUTE_MISSING"
REASON_AUTO_PROVIDER_BLOCKED = "AUXILIARY_AUTO_PROVIDER_BLOCKED"
REASON_MAIN_MODEL_UNRESOLVED = "AUXILIARY_MAIN_MODEL_UNRESOLVED"
REASON_UNSUPPORTED_MODEL_FOR_PROVIDER = "AUXILIARY_MODEL_UNSUPPORTED_FOR_PROVIDER"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _task_config(config: Mapping[str, Any], task_id: str) -> Mapping[str, Any]:
    tasks = _background_tasks_config(config)
    return _mapping(tasks.get(task_id))


def _background_tasks_config(config: Mapping[str, Any]) -> Mapping[str, Any]:
    tasks = _mapping(config.get("background_tasks"))
    if tasks:
        return tasks
    plugins = _mapping(config.get("plugins"))
    brainstack = _mapping(plugins.get("brainstack"))
    return _mapping(brainstack.get("background_tasks"))


def _main_provider(config: Mapping[str, Any]) -> str:
    model_config = config.get("model")
    if isinstance(model_config, Mapping):
        return _text(model_config.get("provider")).lower()
    return ""


def _main_model(config: Mapping[str, Any]) -> str:
    model_config = config.get("model")
    if isinstance(model_config, str):
        return _text(model_config)
    if isinstance(model_config, Mapping):
        return _text(model_config.get("default"))
    return ""


def _model_supported_by_provider(*, provider: str, model: str) -> tuple[bool, str]:
    provider = _text(provider).lower()
    model = _text(model)
    if not provider or not model:
        return True, ""
    if provider == "openai-codex" and "/" in model:
        return False, REASON_UNSUPPORTED_MODEL_FOR_PROVIDER
    return True, ""


def resolve_auxiliary_route_readiness(
    *,
    task_slot: str,
    provider_label: str,
    model_label: str,
    main_provider_label: str = "",
    main_model_label: str = "",
) -> dict[str, Any]:
    """Classify a Hermes-owned auxiliary route without doing an LLM call.

    Brainstack does not choose providers here. It only validates whether the
    configured Hermes route is specific enough to claim readiness.
    """
    provider = _text(provider_label).lower()
    configured_model = _text(model_label)
    main_provider = _text(main_provider_label).lower()
    main_model = _text(main_model_label)

    if not provider:
        return {
            "status": UNAVAILABLE_ROUTE_STATUS,
            "reason_code": REASON_MISSING_ROUTE,
            "task_slot": task_slot,
            "provider_label": "",
            "model_label": configured_model,
            "effective_provider_label": "",
            "effective_model_label": "",
            "public_safe": True,
            "secret_redacted": True,
        }
    if provider == "auto":
        return {
            "status": BLOCKED_ROUTE_STATUS,
            "reason_code": REASON_AUTO_PROVIDER_BLOCKED,
            "task_slot": task_slot,
            "provider_label": provider,
            "model_label": configured_model,
            "effective_provider_label": "",
            "effective_model_label": "",
            "public_safe": True,
            "secret_redacted": True,
        }

    effective_provider = provider
    effective_model = configured_model
    if provider == "main":
        effective_provider = main_provider
        effective_model = configured_model or main_model
        if not effective_model:
            return {
                "status": BLOCKED_ROUTE_STATUS,
                "reason_code": REASON_MAIN_MODEL_UNRESOLVED,
                "task_slot": task_slot,
                "provider_label": provider,
                "model_label": configured_model,
                "effective_provider_label": effective_provider,
                "effective_model_label": "",
                "public_safe": True,
                "secret_redacted": True,
            }

    supported, reason_code = _model_supported_by_provider(provider=effective_provider, model=effective_model)
    if not supported:
        return {
            "status": BLOCKED_ROUTE_STATUS,
            "reason_code": reason_code,
            "task_slot": task_slot,
            "provider_label": provider,
            "model_label": configured_model,
            "effective_provider_label": effective_provider,
            "effective_model_label": effective_model,
            "public_safe": True,
            "secret_redacted": True,
        }

    return {
        "status": READY_ROUTE_STATUS,
        "reason_code": REASON_ROUTE_READY,
        "task_slot": task_slot,
        "provider_label": provider,
        "model_label": configured_model,
        "effective_provider_label": effective_provider,
        "effective_model_label": effective_model,
        "public_safe": True,
        "secret_redacted": True,
    }


def _normalized_task_status(raw: Mapping[str, Any], *, has_explicit_route: bool) -> str:
    status = _text(raw.get("status")).lower()
    if not status:
        return "active" if has_explicit_route else "configured_unavailable"
    if status not in VALID_BACKGROUND_TASK_STATUSES:
        return "blocked"
    return status


def _background_task_card(config: Mapping[str, Any], binding: Mapping[str, str]) -> dict[str, Any]:
    task_id = binding["task_id"]
    hermes_task_slot = binding["hermes_task_slot"]
    raw = _task_config(config, task_id)
    provider_label = _text(raw.get("provider_label") or raw.get("provider")).lower()
    model_label = _text(raw.get("model_label") or raw.get("model"))
    readiness = dict(raw.get("route_readiness") or {})
    if not readiness:
        readiness = resolve_auxiliary_route_readiness(
            task_slot=hermes_task_slot,
            provider_label=provider_label,
            model_label=model_label,
            main_provider_label=_text(raw.get("main_provider_label")),
            main_model_label=_text(raw.get("main_model_label")),
        )
    readiness_status = _text(readiness.get("status")).lower()
    readiness_reason_code = _text(readiness.get("reason_code")) or REASON_MISSING_ROUTE
    fallback_policy = _text(raw.get("fallback_policy") or "none").lower() or "none"
    route_source = _text(raw.get("route_source") or "brainstack.background_tasks")
    has_explicit_route = bool(provider_label and provider_label != "auto")
    status = _normalized_task_status(raw, has_explicit_route=has_explicit_route)
    issues: list[str] = []
    if status == "active" and not has_explicit_route:
        status = "blocked"
        issues.append("missing_explicit_hermes_task_route")
    if provider_label == "auto":
        status = "blocked"
        issues.append("ambient_auto_fallback_not_allowed")
    if fallback_policy != "none":
        status = "blocked"
        issues.append("unnamed_fallback_policy_not_allowed")

    if status == "active" and readiness_status != READY_ROUTE_STATUS:
        status = "blocked" if readiness_status == BLOCKED_ROUTE_STATUS else "configured_unavailable"
        issues.append(readiness_reason_code)

    task_use_allowed = status == "active" and readiness_status == READY_ROUTE_STATUS
    tier2_write_allowed = task_id == BACKGROUND_CONSOLIDATION_TASK_ID and task_use_allowed
    reason = _text(raw.get("reason"))
    if not reason:
        if status == "active":
            reason = "explicit Hermes-owned task route is configured and ready"
        elif status == "configured_unavailable":
            reason = "no explicit Hermes-owned task route is configured"
        elif status == "experimental":
            reason = "route is measurement-only and cannot produce durable writes"
        else:
            reason = ";".join(issues) or "background task route is blocked by policy"
    return {
        "task_id": task_id,
        "hermes_task_slot": hermes_task_slot,
        "purpose": binding.get("purpose", ""),
        "status": status,
        "provider_label": provider_label,
        "model_label": model_label,
        "effective_provider_label": _text(readiness.get("effective_provider_label")).lower(),
        "effective_model_label": _text(readiness.get("effective_model_label")),
        "route_readiness": readiness,
        "route_readiness_status": readiness_status,
        "route_readiness_reason_code": readiness_reason_code,
        "route_source": route_source,
        "fallback_policy": fallback_policy,
        "secret_redacted": True,
        "task_use_allowed": task_use_allowed,
        "tier2_write_allowed": tier2_write_allowed,
        "execution_authority": "hermes",
        "brainstack_authority": "memory_semantics_admission_receipts_trace",
        "reason": reason,
        "issues": issues,
    }


def build_background_task_status(config: Mapping[str, Any] | None) -> dict[str, Any]:
    cfg = _mapping(config)
    tasks = [_background_task_card(cfg, binding) for binding in REQUIRED_BACKGROUND_TASK_BINDINGS]
    counts = {
        "active": sum(1 for task in tasks if task["status"] == "active"),
        "configured_unavailable": sum(1 for task in tasks if task["status"] == "configured_unavailable"),
        "experimental": sum(1 for task in tasks if task["status"] == "experimental"),
        "blocked": sum(1 for task in tasks if task["status"] == "blocked"),
    }
    tier2_write_allowed = any(bool(task["tier2_write_allowed"]) for task in tasks)
    return {
        "schema": BACKGROUND_TASK_STATUS_SCHEMA,
        "public_safe": True,
        "read_only": True,
        "execution_authority": "hermes",
        "brainstack_authority": "memory_semantics_admission_receipts_trace",
        "fallback_policy": "none",
        "tier2_write_allowed": tier2_write_allowed,
        "tasks": tasks,
        "summary": {
            **counts,
            "required_task_count": len(tasks),
            "tier2_write_allowed": tier2_write_allowed,
            "all_required_routes_explicit": all(task["provider_label"] and task["provider_label"] != "auto" for task in tasks),
            "all_required_routes_ready": all(task["status"] == "active" and task["route_readiness_status"] == "ready" for task in tasks),
        },
    }


def install_default_background_task_bindings(config: dict[str, Any]) -> dict[str, Any]:
    config.setdefault("auxiliary", {})
    if not isinstance(config["auxiliary"], dict):
        raise RuntimeError("config.yaml has non-object `auxiliary` section")
    config.setdefault("plugins", {})
    if not isinstance(config["plugins"], dict):
        raise RuntimeError("config.yaml has non-object `plugins` section")
    brainstack = config["plugins"].setdefault("brainstack", {})
    if not isinstance(brainstack, dict):
        brainstack = {}
        config["plugins"]["brainstack"] = brainstack
    background_tasks = brainstack.setdefault("background_tasks", {})
    if not isinstance(background_tasks, dict):
        background_tasks = {}
        brainstack["background_tasks"] = background_tasks

    for binding in REQUIRED_BACKGROUND_TASK_BINDINGS:
        task_id = binding["task_id"]
        hermes_task_slot = binding["hermes_task_slot"]
        aux_entry = _mapping(config["auxiliary"].get(hermes_task_slot))
        provider = _text(aux_entry.get("provider")).lower()
        model = _text(aux_entry.get("model"))
        readiness = resolve_auxiliary_route_readiness(
            task_slot=hermes_task_slot,
            provider_label=provider,
            model_label=model,
            main_provider_label=_main_provider(config),
            main_model_label=_main_model(config),
        )
        has_explicit_route = bool(provider and provider != "auto")
        task_entry = background_tasks.setdefault(task_id, {})
        if not isinstance(task_entry, dict):
            task_entry = {}
            background_tasks[task_id] = task_entry
        task_entry["hermes_task_slot"] = hermes_task_slot
        task_entry["status"] = "active" if readiness["status"] == READY_ROUTE_STATUS else "configured_unavailable"
        task_entry["provider_label"] = provider if has_explicit_route else ""
        task_entry["model_label"] = model
        task_entry["effective_provider_label"] = _text(readiness.get("effective_provider_label")).lower()
        task_entry["effective_model_label"] = _text(readiness.get("effective_model_label"))
        task_entry["main_provider_label"] = _main_provider(config)
        task_entry["main_model_label"] = _main_model(config)
        task_entry["route_readiness"] = readiness
        task_entry["fallback_policy"] = "none"
        task_entry["secret_redacted"] = True
        task_entry["route_source"] = f"auxiliary.{hermes_task_slot}"
        task_entry["reason"] = (
            "explicit Hermes-owned task route is configured and ready"
            if readiness["status"] == READY_ROUTE_STATUS
            else "no explicit Hermes-owned task route is configured"
        )
    return build_background_task_status(brainstack)


def require_explicit_hermes_auxiliary_route(task_slot: str) -> None:
    try:
        from agent.auxiliary_client import _get_auxiliary_task_config  # type: ignore[import-not-found,import-untyped]
    except Exception as exc:
        raise RuntimeError("Hermes auxiliary task config is not importable") from exc
    task_config = _get_auxiliary_task_config(task_slot)
    provider = _text(_mapping(task_config).get("provider")).lower()
    if not provider or provider == "auto":
        raise RuntimeError(f"Brainstack background task {task_slot!r} requires an explicit Hermes auxiliary route")
    model = _text(_mapping(task_config).get("model"))
    readiness = resolve_auxiliary_route_readiness(
        task_slot=task_slot,
        provider_label=provider,
        model_label=model,
    )
    if readiness["status"] != READY_ROUTE_STATUS:
        raise RuntimeError(
            f"Brainstack background task {task_slot!r} route is not ready: {readiness['reason_code']}"
        )
