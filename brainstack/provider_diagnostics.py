from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .answerability import build_memory_answerability
from .authority_policy import is_current_assignment_authority
from .diagnostics import build_memory_kernel_doctor, build_query_inspect
from .persistent_bloat import PERSISTENT_BLOAT_REPORT_SCHEMA
from .tier2_runtime_spine import build_tier2_runtime_route_status

@dataclass(frozen=True)
class RecallDetailBudget:
    """Agent-facing recall contract; inspect keeps the full diagnostic payload."""

    detail_level: str
    budget_basis: str
    preview_char_limit: int
    evidence_excerpt_char_limit: int
    semantic_anchor_char_limit: int
    evidence_per_shelf_limit: int
    inspect_tool: str


MODEL_FACING_RECALL_BUDGET = RecallDetailBudget(
    detail_level="compact",
    budget_basis="existing_recall_preview_compatibility_default",
    preview_char_limit=1200,
    evidence_excerpt_char_limit=180,
    semantic_anchor_char_limit=120,
    evidence_per_shelf_limit=2,
    inspect_tool="brainstack_inspect",
)

_INSPECT_GRADE_EVIDENCE_KEYS = frozenset(
    {
        "literal_tokens",
        "explicit_truth_parity",
        "source_envelope",
        "raw_source_envelope",
        "retrieval_candidates",
        "candidate_trace",
        "raw_metadata",
        "metadata_json",
        "full_text",
        "raw_text",
    }
)


def _normalize_compact_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _trim_compact_text(value: Any, *, limit: int = 180) -> str:
    text = _normalize_compact_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _omit_empty_compact_values(data: Mapping[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in data.items():
        if value in ("", None, [], {}):
            continue
        compact[str(key)] = value
    return compact


def _compact_channel_cards(channels: list[Any], *, limit: int = 8) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for raw in channels[: max(0, limit)]:
        if not isinstance(raw, Mapping):
            continue
        cards.append(
            {
                "name": _normalize_compact_text(raw.get("name")),
                "status": _normalize_compact_text(raw.get("status")),
                "candidate_count": int(raw.get("candidate_count") or 0),
                "reason": _trim_compact_text(raw.get("reason"), limit=120),
            }
        )
    return cards


def _is_current_assignment_authority(item: Mapping[str, Any]) -> bool:
    return is_current_assignment_authority(item)


def _compact_inspect_handle(item: Mapping[str, Any]) -> str:
    for key in ("evidence_key", "citation_id", "stable_key", "id", "event_id"):
        value = _normalize_compact_text(item.get(key))
        if value:
            return value
    shelf = _normalize_compact_text(item.get("shelf"))
    row_type = _normalize_compact_text(item.get("row_type") or item.get("record_type"))
    return ":".join(part for part in (shelf, row_type, "unkeyed") if part)


def _compact_evidence_identity_values(item: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("evidence_key", "citation_id", "stable_key", "id", "event_id"):
        value = _normalize_compact_text(item.get(key))
        if value:
            values.add(value)
    return values


def _compact_source_status(item: Mapping[str, Any]) -> dict[str, Any]:
    parity = item.get("explicit_truth_parity") if isinstance(item.get("explicit_truth_parity"), Mapping) else {}
    status = {
        "projection_status": _normalize_compact_text(item.get("projection_status") or parity.get("projection_status")),
        "divergence_status": _normalize_compact_text(item.get("divergence_status") or parity.get("divergence_status")),
        "parity_observable": _normalize_compact_text(item.get("parity_observable") or parity.get("parity_observable")),
        "event_type": _normalize_compact_text(item.get("event_type") or parity.get("event_type")),
        "parity_detail_available": bool(parity),
    }
    return _omit_empty_compact_values(status)


def _has_inspect_grade_evidence_detail(item: Mapping[str, Any]) -> bool:
    for key in _INSPECT_GRADE_EVIDENCE_KEYS:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return True
    return (
        len(_normalize_compact_text(item.get("semantic_anchor_text")))
        > MODEL_FACING_RECALL_BUDGET.semantic_anchor_char_limit
    )


def _compact_evidence_card(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return model-facing recall evidence, not inspect-grade diagnostics."""
    runtime_state_only = bool(item.get("runtime_state_only"))
    supporting_evidence_only = bool(item.get("supporting_evidence_only")) or runtime_state_only
    current_assignment_authority = _is_current_assignment_authority(
        {**dict(item), "supporting_evidence_only": supporting_evidence_only}
    )
    card = {
        "evidence_key": _normalize_compact_text(item.get("evidence_key")),
        "shelf": _normalize_compact_text(item.get("shelf")),
        "row_type": _normalize_compact_text(item.get("row_type") or item.get("record_type")),
        "stable_key": _trim_compact_text(item.get("stable_key"), limit=120),
        "source": _trim_compact_text(item.get("source"), limit=100),
        "authority_level": _normalize_compact_text(item.get("authority_level")),
        "owner_role": _normalize_compact_text(item.get("owner_role")),
        "workstream_id": _normalize_compact_text(item.get("workstream_id")),
        "runtime_state_only": runtime_state_only,
        "supporting_evidence_only": supporting_evidence_only,
        "current_assignment_authority": current_assignment_authority,
        "current_assignment_authority_schema": _normalize_compact_text(
            item.get("current_assignment_authority_schema")
        ),
        "citation_id": _normalize_compact_text(item.get("citation_id")),
        "created_at": _normalize_compact_text(item.get("created_at")),
        "excerpt": _trim_compact_text(item.get("excerpt"), limit=MODEL_FACING_RECALL_BUDGET.evidence_excerpt_char_limit),
        "semantic_anchor_preview": _trim_compact_text(
            item.get("semantic_anchor_text"), limit=MODEL_FACING_RECALL_BUDGET.semantic_anchor_char_limit
        ),
        "projection_status": _normalize_compact_text(item.get("projection_status")),
        "divergence_status": _normalize_compact_text(item.get("divergence_status")),
        "parity_observable": _normalize_compact_text(item.get("parity_observable")),
        "event_type": _normalize_compact_text(item.get("event_type")),
        "bounded_scope_only": bool(item.get("bounded_scope_only")),
        "source_status": _compact_source_status(item),
        "inspect": {
            "tool": MODEL_FACING_RECALL_BUDGET.inspect_tool,
            "handle": _compact_inspect_handle(item),
            "detail_omitted": _has_inspect_grade_evidence_detail(item),
        },
    }
    return _omit_empty_compact_values(card)


def _compact_selected_evidence(
    selected: Mapping[str, Any],
    *,
    answer_evidence_ids: set[str] | None = None,
    per_shelf_limit: int = MODEL_FACING_RECALL_BUDGET.evidence_per_shelf_limit,
) -> dict[str, list[dict[str, Any]]]:
    protected_answer_ids = set(answer_evidence_ids or set())
    compact: dict[str, list[dict[str, Any]]] = {}
    for shelf, raw_rows in selected.items():
        rows = raw_rows if isinstance(raw_rows, list) else []
        chosen: list[Mapping[str, Any]] = []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            if protected_answer_ids & _compact_evidence_identity_values(row):
                chosen.append(row)
        for row in rows:
            if len(chosen) >= max(0, per_shelf_limit):
                break
            if isinstance(row, Mapping) and row not in chosen:
                chosen.append(row)
        compact[str(shelf)] = [_compact_evidence_card(row) for row in chosen]
    return compact


def _tier2_runtime_route_status(config: Mapping[str, Any] | None) -> dict[str, Any]:
    return build_tier2_runtime_route_status(config)


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
    config: Mapping[str, Any] | None = None,
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
        "tier2_runtime_route": _tier2_runtime_route_status(config),
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
    config: Mapping[str, Any] | None = None,
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
            "runtime_route": _tier2_runtime_route_status(config),
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
    system_substrate: Mapping[str, Any] | None = None,
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
        system_substrate=system_substrate,
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
    diagnostic_evidence_count = sum(len(rows or []) for rows in selected.values()) if isinstance(selected, Mapping) else 0
    raw_packet = report.get("final_packet")
    packet: Mapping[str, Any] = raw_packet if isinstance(raw_packet, Mapping) else {}
    raw_answerability = report.get("memory_answerability")
    answerability: Mapping[str, Any] = (
        raw_answerability
        if isinstance(raw_answerability, Mapping)
        else build_memory_answerability(
            query=query,
            analysis=report.get("analysis") if isinstance(report.get("analysis"), Mapping) else {},
            selected_by_shelf=selected,
            packet_text=str(packet.get("preview") or ""),
        )
    )
    answer_evidence_ids = {str(value) for value in list(answerability.get("answer_evidence_ids") or []) if value}
    compact_selected = _compact_selected_evidence(selected, answer_evidence_ids=answer_evidence_ids)
    answerable_evidence_count = len(list(answerability.get("answer_evidence_ids") or []))
    return {
        "schema": "brainstack.tool_recall.v1",
        "tool_name": "brainstack_recall",
        "read_only": True,
        "bounded_model_facing": True,
        "detail_level": MODEL_FACING_RECALL_BUDGET.detail_level,
        "budget_contract": {
            "schema": "brainstack.recall_detail_budget.v1",
            "detail_level": MODEL_FACING_RECALL_BUDGET.detail_level,
            "budget_basis": MODEL_FACING_RECALL_BUDGET.budget_basis,
            "preview_char_limit": MODEL_FACING_RECALL_BUDGET.preview_char_limit,
            "evidence_excerpt_char_limit": MODEL_FACING_RECALL_BUDGET.evidence_excerpt_char_limit,
            "semantic_anchor_char_limit": MODEL_FACING_RECALL_BUDGET.semantic_anchor_char_limit,
            "evidence_per_shelf_limit": MODEL_FACING_RECALL_BUDGET.evidence_per_shelf_limit,
            "inspect_tool": MODEL_FACING_RECALL_BUDGET.inspect_tool,
            "rationale": "normal recall is answer context; explicit inspect owns raw diagnostic detail",
        },
        "model_use_contract": {
            "primary_answer_source": "final_packet.preview",
            "selected_evidence_use": "diagnostic support only; do not override final_packet authority notes",
            "current_assignment_rule": (
                "Treat current work, assignment, or workstream as recorded only when a selected task card exists "
                "or an operating card has typed current_assignment_authority=true."
            ),
            "current_assignment_negative_rule": (
                "Do not determine active work from continuity, transcript/session history, profile shared_work, "
                "graph/background facts, runtime scheduler state, or Pulse evidence unless it is selected task "
                "evidence or selected operating evidence with typed current_assignment_authority=true. "
                "Pulse output may describe background observations or candidate task rows, but it does not assign current work by itself."
            ),
            "non_authority_sources": [
                "profile shared_work",
                "continuity/transcript/session summaries",
                "graph/background facts without current_assignment_authority",
                "runtime_state_only scheduler or pulse rows",
                "external/session-search summaries",
            ],
            "answerability_rule": (
                "Use memory_answerability for memory claims. Diagnostic selected evidence is not answer truth "
                "unless listed in answer_evidence_ids."
            ),
        },
        "principal_scope_key": principal_scope_key,
        "query": query,
        "routing": dict(report.get("routing") or {}),
        "channels": _compact_channel_cards(list(report.get("channels") or [])),
        "final_packet": {
            "sections": list(packet.get("sections") or []),
            "char_count": int(packet.get("char_count") or 0),
            "preview": _trim_compact_text(packet.get("preview"), limit=MODEL_FACING_RECALL_BUDGET.preview_char_limit),
            "preview_char_limit": MODEL_FACING_RECALL_BUDGET.preview_char_limit,
            "detail_omitted": bool(packet.get("explicit_truth_parity")),
        },
        "memory_answerability": dict(answerability),
        "selected_evidence": compact_selected,
        "diagnostic_evidence_count": diagnostic_evidence_count,
        "answerable_evidence_count": answerable_evidence_count,
        "evidence_card_count": sum(len(rows) for rows in compact_selected.values()),
        "diagnostic_detail_tool": MODEL_FACING_RECALL_BUDGET.inspect_tool,
        "inspect_route": {
            "tool": MODEL_FACING_RECALL_BUDGET.inspect_tool,
            "query": query,
            "detail_level": "diagnostic",
            "returns": "full query_inspect report for this scoped query",
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


def _persistent_bloat_unavailable(
    *,
    principal_scope_key: str,
    status: str,
    issue_code: str,
) -> dict[str, Any]:
    return {
        "schema": PERSISTENT_BLOAT_REPORT_SCHEMA,
        "status": status,
        "read_only": True,
        "public_safe": True,
        "scope": {
            "principal_scope_key": principal_scope_key,
            "scope_filter_applied": bool(principal_scope_key),
            "scope_note": "Persistent bloat report is unavailable; no storage mutation was attempted.",
        },
        "lanes": {},
        "metrics": {},
        "metric_statuses": {},
        "policy_preview": [],
        "issues": [issue_code],
        "issue_count": 1,
        "critical_counters": {
            "raw_private_text_leak": 0,
            "truth_cleanup_apply_supported": 0,
            "receipt_preservation_missing": 0,
            "projection_rebuild_counters_nonzero": 0,
        },
    }


def _safe_persistent_bloat_report(
    *,
    principal_scope_key: str,
    persistent_bloat_report: Callable[[], dict[str, Any]] | None,
) -> dict[str, Any]:
    if persistent_bloat_report is None:
        return _persistent_bloat_unavailable(
            principal_scope_key=principal_scope_key,
            status="unavailable",
            issue_code="PERSISTENT_BLOAT_STORE_UNAVAILABLE",
        )
    try:
        raw_report = persistent_bloat_report()
    except Exception:
        return _persistent_bloat_unavailable(
            principal_scope_key=principal_scope_key,
            status="fail",
            issue_code="PERSISTENT_BLOAT_REPORT_ERROR",
        )
    if not isinstance(raw_report, Mapping):
        return _persistent_bloat_unavailable(
            principal_scope_key=principal_scope_key,
            status="fail",
            issue_code="PERSISTENT_BLOAT_REPORT_MALFORMED",
        )
    report = dict(raw_report)
    report.setdefault("schema", PERSISTENT_BLOAT_REPORT_SCHEMA)
    report.setdefault("read_only", True)
    report.setdefault("public_safe", True)
    return report


def _bool_arg(args: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = args.get(name, default) if isinstance(args, Mapping) else default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _compact_tier2_route(route: Any) -> dict[str, Any]:
    if not isinstance(route, Mapping):
        return {}
    background_task_status = route.get("background_task_status")
    compact_background_tasks: dict[str, Any] = {}
    if isinstance(background_task_status, Mapping):
        summary = background_task_status.get("summary")
        compact_background_tasks = {
            "schema": _normalize_compact_text(background_task_status.get("schema")),
            "tier2_write_allowed": bool(background_task_status.get("tier2_write_allowed")),
            "route_counts": {
                key: int(summary.get(key) or 0)
                for key in ("active", "configured_unavailable", "experimental", "blocked")
            }
            if isinstance(summary, Mapping)
            else {},
        }
    return {
        "runtime": _normalize_compact_text(route.get("runtime")),
        "binding_status": _normalize_compact_text(route.get("binding_status")),
        "binding_reason_code": _normalize_compact_text(route.get("binding_reason_code")),
        "mode": _normalize_compact_text(route.get("mode")),
        "llm_provider": _normalize_compact_text(route.get("llm_provider")),
        "effective_model": _normalize_compact_text(route.get("effective_model")),
        "background_task_status": compact_background_tasks,
    }


def _compact_lifecycle_status(lifecycle: Any) -> dict[str, Any]:
    if not isinstance(lifecycle, Mapping):
        return {"status": "unknown"}
    exported_tools = lifecycle.get("exported_tools") if isinstance(lifecycle.get("exported_tools"), list) else []
    return {
        "schema": _normalize_compact_text(lifecycle.get("schema")),
        "status": _normalize_compact_text(lifecycle.get("status")),
        "store_initialized": bool(lifecycle.get("store_initialized")),
        "tier2_worker_running": bool(lifecycle.get("tier2_worker_running")),
        "pending_tier2_turns": int(lifecycle.get("pending_tier2_turns") or 0),
        "tier2_runtime_route": _compact_tier2_route(lifecycle.get("tier2_runtime_route")),
        "exported_tools": [
            {"name": _normalize_compact_text(tool.get("name")) if isinstance(tool, Mapping) else ""}
            for tool in exported_tools[:20]
            if isinstance(tool, Mapping)
        ],
    }


def _compact_backend_health(raw_backend_health: Any) -> dict[str, Any]:
    if not isinstance(raw_backend_health, Mapping):
        return {}
    backends: dict[str, Any] = {}
    raw_backends = raw_backend_health.get("backends")
    if isinstance(raw_backends, Mapping):
        for name, raw in raw_backends.items():
            if not isinstance(raw, Mapping):
                continue
            backends[str(name)] = {
                "kind": _normalize_compact_text(raw.get("kind") or name),
                "status": _normalize_compact_text(raw.get("status")),
                "active": bool(raw.get("active")),
                "requested": bool(raw.get("requested")),
                "reason": _trim_compact_text(raw.get("reason"), limit=160),
                "reason_code": _normalize_compact_text(raw.get("reason_code")),
                "safe_reason": _trim_compact_text(raw.get("safe_reason"), limit=160),
            }
    return {
        "schema": _normalize_compact_text(raw_backend_health.get("schema")),
        "status": _normalize_compact_text(raw_backend_health.get("status")),
        "issue_count": int(raw_backend_health.get("issue_count") or 0),
        "agent_summary": _trim_compact_text(raw_backend_health.get("agent_summary"), limit=240),
        "backends": backends,
    }


def _compact_doctor_report(report: Any, *, strict_requested: bool) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        return {"schema": "brainstack.memory_kernel_doctor.v1", "verdict": "unknown"}
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    capabilities: dict[str, Any] = {}
    raw_capabilities = report.get("capabilities")
    if isinstance(raw_capabilities, Mapping):
        for name, raw in raw_capabilities.items():
            if not isinstance(raw, Mapping):
                continue
            capabilities[str(name)] = {
                "status": _normalize_compact_text(raw.get("status")),
                "active": bool(raw.get("active")),
                "requested": bool(raw.get("requested")),
                "reason_code": _normalize_compact_text(raw.get("reason_code")),
            }
    return {
        "schema": _normalize_compact_text(report.get("schema")),
        "strict": bool(report.get("strict")),
        "strict_requested": bool(strict_requested),
        "verdict": _normalize_compact_text(report.get("verdict")),
        "issue_count": len(issues),
        "issues": [
            {
                "capability": _normalize_compact_text(issue.get("capability")) if isinstance(issue, Mapping) else "",
                "status": _normalize_compact_text(issue.get("status")) if isinstance(issue, Mapping) else "",
                "severity": _normalize_compact_text(issue.get("severity")) if isinstance(issue, Mapping) else "",
                "reason": _trim_compact_text(issue.get("reason"), limit=160) if isinstance(issue, Mapping) else "",
                "reason_code": _normalize_compact_text(issue.get("reason_code")) if isinstance(issue, Mapping) else "",
            }
            for issue in issues[:5]
        ],
        "capabilities": capabilities,
    }


def _compact_persistent_bloat(report: Any) -> dict[str, Any]:
    if not isinstance(report, Mapping):
        return {"schema": PERSISTENT_BLOAT_REPORT_SCHEMA, "status": "unknown", "issue_count": 1}
    metrics = report.get("metrics") if isinstance(report.get("metrics"), Mapping) else {}
    issues = report.get("issues") if isinstance(report.get("issues"), list) else []
    return {
        "schema": _normalize_compact_text(report.get("schema") or PERSISTENT_BLOAT_REPORT_SCHEMA),
        "status": _normalize_compact_text(report.get("status")),
        "read_only": bool(report.get("read_only", True)),
        "public_safe": bool(report.get("public_safe", True)),
        "issue_count": int(report.get("issue_count") or 0),
        "issues": [_normalize_compact_text(issue) for issue in issues[:8] if _normalize_compact_text(issue)],
        "metric_statuses": dict(report.get("metric_statuses") or {})
        if isinstance(report.get("metric_statuses"), Mapping)
        else {},
        "critical_counters": dict(report.get("critical_counters") or {})
        if isinstance(report.get("critical_counters"), Mapping)
        else {},
        "metric_names": sorted(str(name) for name in metrics.keys()),
        "policy_preview_count": len(report.get("policy_preview") or []),
    }


def _compact_maintenance_receipt(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(receipt, Mapping) or not receipt:
        return {}
    return {
        "schema": _normalize_compact_text(receipt.get("schema")),
        "status": _normalize_compact_text(receipt.get("status")),
        "maintenance_class": _normalize_compact_text(receipt.get("maintenance_class")),
        "change_count": int(receipt.get("change_count") or 0),
        "issue_count": int(receipt.get("issue_count") or 0),
    }


def handle_brainstack_stats(
    *,
    args: Mapping[str, Any],
    principal_scope_key: str,
    lifecycle_status: Callable[[], dict[str, Any]],
    memory_kernel_doctor: Callable[..., dict[str, Any]],
    last_maintenance_receipt: Mapping[str, Any] | None,
    persistent_bloat_report: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    strict = _bool_arg(args, "strict") if isinstance(args, Mapping) else False
    report = memory_kernel_doctor(strict=strict)
    raw_backend_health = report.get("backend_health") if isinstance(report, Mapping) else None
    persistent_bloat = _safe_persistent_bloat_report(
        principal_scope_key=principal_scope_key,
        persistent_bloat_report=persistent_bloat_report,
    )
    lifecycle = _compact_lifecycle_status(lifecycle_status())
    doctor = _compact_doctor_report(report, strict_requested=strict)
    return {
        "schema": "brainstack.tool_stats.v1",
        "tool_name": "brainstack_stats",
        "read_only": True,
        "bounded_model_facing": True,
        "principal_scope_key": principal_scope_key,
        "status": doctor.get("verdict") or lifecycle.get("status") or "unknown",
        "strict_requested": strict,
        "model_use_contract": {
            "answer_source": "this_compact_summary",
            "full_internal_report_omitted": True,
            "do_not_call_search_files_for_brainstack_config": True,
            "detail_route": "Use brainstack_inspect for query-specific retrieval traces; operator/release diagnostics own full doctor reports.",
        },
        "lifecycle": lifecycle,
        "maintenance": _compact_maintenance_receipt(last_maintenance_receipt),
        "backend_health": _compact_backend_health(raw_backend_health),
        "persistent_bloat": _compact_persistent_bloat(persistent_bloat),
        "doctor": doctor,
        "omitted_fields": ["report.capabilities.raw", "report.backend_health.raw", "persistent_bloat.metrics.raw", "persistent_bloat.policy_preview.raw"],
        "reason_code": "MODEL_FACING_STATS_COMPACT",
    }


def handle_brainstack_latency_status(
    *,
    args: Mapping[str, Any],
    principal_scope_key: str,
    lifecycle_status: Callable[[], dict[str, Any]],
    memory_kernel_doctor: Callable[..., dict[str, Any]],
    last_maintenance_receipt: Mapping[str, Any] | None,
    persistent_bloat_report: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stats = handle_brainstack_stats(
        args={"strict": False},
        principal_scope_key=principal_scope_key,
        lifecycle_status=lifecycle_status,
        memory_kernel_doctor=memory_kernel_doctor,
        last_maintenance_receipt=last_maintenance_receipt,
        persistent_bloat_report=persistent_bloat_report,
    )
    return {
        "schema": "brainstack.tool_latency_status.v1",
        "tool_name": "brainstack_latency_status",
        "read_only": True,
        "bounded_model_facing": True,
        "status": stats.get("status"),
        "brainstack_summary": {
            "lifecycle_status": stats.get("lifecycle", {}).get("status"),
            "tier2_route": stats.get("lifecycle", {}).get("tier2_runtime_route", {}),
            "backend_health_status": stats.get("backend_health", {}).get("status"),
            "doctor_verdict": stats.get("doctor", {}).get("verdict"),
            "persistent_bloat_status": stats.get("persistent_bloat", {}).get("status"),
        },
        "latency_contract": {
            "hotpath_target_seconds": 5,
            "heavy_path_target_seconds": 10,
            "brainstack_tool_output": "compact_bounded_summary",
            "does_not_benchmark_provider_api": True,
            "does_not_require_file_search": True,
        },
        "likely_slow_component_if_turn_exceeds_target": "provider_or_gateway_or_unbounded_non_brainstack_tool; verify with gateway timing logs before blaming Brainstack memory.",
        "model_use_contract": {
            "answer_source": "this_compact_latency_summary",
            "do_not_call_search_files_for_brainstack_config": True,
            "if_more_detail_needed": "Ask for explicit deep diagnostics or use operator/release tooling, not normal chat file search.",
        },
        "reason_code": "MODEL_FACING_LATENCY_STATUS_COMPACT",
    }
