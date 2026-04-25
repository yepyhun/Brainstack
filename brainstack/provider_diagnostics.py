from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from .diagnostics import build_memory_kernel_doctor, build_query_inspect


def _normalize_compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def build_provider_lifecycle_status(
    *,
    store: Any,
    tier2_running: bool,
    pending_explicit_write_count: int,
    session_id: str,
    principal_scope_key: str,
    pending_tier2_turns: int,
    tool_schemas: list[dict[str, Any]],
    operator_only_tools: list[dict[str, Any]],
    disabled_memory_write_tools: list[str],
    last_maintenance_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    store_active = store is not None
    explicit_write_barrier = pending_explicit_write_count > 0
    if not store_active:
        status = "unavailable"
        reason = "Brainstack provider has not been initialized or has been shut down."
    elif explicit_write_barrier:
        status = "degraded"
        reason = "An explicit write barrier is pending; shutdown/session maintenance must wait."
    else:
        status = "active"
        reason = "Brainstack provider is initialized and lifecycle hooks are available."

    exported_tools = [
        {
            "name": str(schema.get("name") or ""),
            "tool_class": str(schema.get("x_brainstack_tool_class") or ""),
            "model_callable": bool(schema.get("x_brainstack_model_callable", True)),
        }
        for schema in tool_schemas
    ]
    hook_status = "active" if store_active else "unavailable"
    return {
        "schema": "brainstack.provider_lifecycle.v1",
        "status": status,
        "reason": reason,
        "session_id": session_id,
        "principal_scope_key": principal_scope_key,
        "store_initialized": store_active,
        "tier2_worker_running": bool(tier2_running),
        "pending_tier2_turns": pending_tier2_turns,
        "pending_explicit_write_count": pending_explicit_write_count,
        "hooks": [
            {"name": "initialize", "status": "active" if store_active else "available", "side_effect": "opens Brainstack store"},
            {"name": "system_prompt_block", "status": hook_status, "side_effect": "read-only projection"},
            {"name": "prefetch", "status": hook_status, "side_effect": "read-only recall"},
            {"name": "sync_turn", "status": hook_status, "side_effect": "post-turn transcript and typed extraction"},
            {"name": "on_pre_compress", "status": hook_status, "side_effect": "bounded continuity snapshot"},
            {"name": "on_session_end", "status": hook_status, "side_effect": "bounded maintenance and session finalization"},
            {"name": "shutdown", "status": "available", "side_effect": "closes store after barriers clear"},
            {"name": "get_tool_schemas", "status": "available", "side_effect": "read-only schema export"},
            {"name": "handle_tool_call", "status": "available", "side_effect": "tool-specific; memory tools are read-only in Phase 70"},
        ],
        "exported_tools": exported_tools,
        "operator_only_tools": operator_only_tools,
        "disabled_memory_write_tools": sorted(disabled_memory_write_tools),
        "last_maintenance": dict(last_maintenance_receipt or {}),
        "shared_state_safety": {
            "brainstack_authority": "Brainstack owns memory state and policy truth.",
            "runtime_authority": "Hermes owns scheduling, execution, and approval enforcement.",
            "operator_mcp_stance": "Optional operator access must use Brainstack APIs, not direct DB mutation.",
            "concurrency_rule": "Shared store operations are serialized through BrainstackStore locked methods.",
        },
    }


def build_provider_memory_kernel_doctor(
    *,
    store: Any,
    strict: bool,
    tier2_session_end_flush_enabled: bool,
    tier2_running: bool,
    pending_tier2_turns: int,
    last_tier2_schedule: Mapping[str, Any] | None,
    last_tier2_batch_result: Mapping[str, Any] | None,
    tier2_batch_history_count: int,
) -> dict[str, Any]:
    if store is None:
        return {
            "schema": "brainstack.memory_kernel_doctor.v1",
            "strict": bool(strict),
            "verdict": "fail" if strict else "unavailable",
            "issues": [
                {
                    "capability": "store",
                    "status": "unavailable",
                    "reason": "Brainstack store is not initialized.",
                }
            ],
        }
    return build_memory_kernel_doctor(
        store,
        strict=strict,
        tier2_state={
            "enabled": tier2_session_end_flush_enabled,
            "running": tier2_running,
            "pending_turns": pending_tier2_turns,
            "last_schedule": dict(last_tier2_schedule or {}),
            "last_result": dict(last_tier2_batch_result or {}),
            "history_count": tier2_batch_history_count,
        },
    )


def build_provider_query_inspect(
    *,
    store: Any,
    query: str,
    session_id: str,
    principal_scope_key: str,
    timezone_name: str,
    route_resolver: Any,
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    evidence_item_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    operating_match_limit: int,
    render_ordinary_contract: bool,
) -> dict[str, Any]:
    if store is None:
        return {
            "schema": "brainstack.query_inspect.v1",
            "error": "Brainstack store is not initialized.",
        }
    return build_query_inspect(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        timezone_name=timezone_name,
        route_resolver=route_resolver,
        profile_match_limit=profile_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        evidence_item_budget=evidence_item_budget,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
        operating_match_limit=operating_match_limit,
        render_ordinary_contract=render_ordinary_contract,
    )


def handle_brainstack_recall(
    *,
    args: Mapping[str, Any],
    principal_scope_key: str,
    session_id: str,
    query_inspect: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    query = _normalize_compact_text(args.get("query") if isinstance(args, Mapping) else "")
    if not query:
        return {
            "schema": "brainstack.tool_error.v1",
            "tool_name": "brainstack_recall",
            "error_code": "invalid_query",
            "error": "brainstack_recall requires a non-empty query.",
            "read_only": True,
        }
    report = query_inspect(
        query=query,
        session_id=str(args.get("session_id") or session_id) if isinstance(args, Mapping) else session_id,
    )
    raw_selected = report.get("selected_evidence")
    selected: Mapping[str, Any] = raw_selected if isinstance(raw_selected, Mapping) else {}
    evidence_count = sum(len(rows or []) for rows in selected.values()) if isinstance(selected, Mapping) else 0
    raw_packet = report.get("final_packet")
    packet: Mapping[str, Any] = raw_packet if isinstance(raw_packet, Mapping) else {}
    return {
        "schema": "brainstack.tool_recall.v1",
        "tool_name": "brainstack_recall",
        "read_only": True,
        "principal_scope_key": principal_scope_key,
        "query": query,
        "routing": dict(report.get("routing") or {}),
        "channels": list(report.get("channels") or []),
        "selected_evidence": dict(selected),
        "evidence_count": evidence_count,
        "final_packet": {
            "sections": list(packet.get("sections") or []),
            "char_count": int(packet.get("char_count") or 0),
            "preview": str(packet.get("preview") or ""),
        },
    }


def handle_brainstack_inspect(
    *,
    args: Mapping[str, Any],
    principal_scope_key: str,
    session_id: str,
    query_inspect: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    query = _normalize_compact_text(args.get("query") if isinstance(args, Mapping) else "")
    if not query:
        return {
            "schema": "brainstack.tool_error.v1",
            "tool_name": "brainstack_inspect",
            "error_code": "invalid_query",
            "error": "brainstack_inspect requires a non-empty query.",
            "read_only": True,
        }
    report = query_inspect(
        query=query,
        session_id=str(args.get("session_id") or session_id) if isinstance(args, Mapping) else session_id,
    )
    return {
        "schema": "brainstack.tool_inspect.v1",
        "tool_name": "brainstack_inspect",
        "read_only": True,
        "principal_scope_key": principal_scope_key,
        "report": report,
    }


def handle_brainstack_stats(
    *,
    args: Mapping[str, Any],
    principal_scope_key: str,
    lifecycle_status: Callable[[], dict[str, Any]],
    memory_kernel_doctor: Callable[..., dict[str, Any]],
    last_maintenance_receipt: Mapping[str, Any] | None,
) -> dict[str, Any]:
    strict_value = args.get("strict", False) if isinstance(args, Mapping) else False
    strict = strict_value if isinstance(strict_value, bool) else str(strict_value).strip().lower() in {"1", "true", "yes"}
    return {
        "schema": "brainstack.tool_stats.v1",
        "tool_name": "brainstack_stats",
        "read_only": True,
        "principal_scope_key": principal_scope_key,
        "lifecycle": lifecycle_status(),
        "maintenance": dict(last_maintenance_receipt or {}),
        "report": memory_kernel_doctor(strict=strict),
    }
