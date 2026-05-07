from __future__ import annotations

from typing import Any, Mapping


RETRIEVAL_CHANNEL_DEADLINE_SCHEMA_VERSION = "brainstack.retrieval_channel_deadlines.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _tuple_text(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _external_corpus_backend_active(store: Any) -> bool:
    return getattr(store, "_corpus_backend", None) is not None


def _external_graph_backend_active(store: Any) -> bool:
    return getattr(store, "_graph_backend", None) is not None


def _status(
    *,
    channel: str,
    plan_id: str,
    deadline_ms: int,
    allowed: bool,
    support_status: str,
    enforcement: str,
    reason: str,
) -> dict[str, Any]:
    if not allowed:
        support_status = "skipped_by_plan"
        enforcement = "not_called"
        reason = "channel_not_allowed_by_retrieval_control_plan"
    return {
        "schema": RETRIEVAL_CHANNEL_DEADLINE_SCHEMA_VERSION,
        "channel": channel,
        "plan_id": plan_id,
        "deadline_ms": deadline_ms,
        "support_status": support_status,
        "enforcement": enforcement,
        "reason": reason,
        "hidden_work_after_return": False if support_status != "cancellation_unsupported" else None,
    }


def build_channel_deadline_statuses(
    store: Any,
    *,
    retrieval_control_plan: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    plan = _mapping(retrieval_control_plan)
    plan_id = str(plan.get("plan_id") or "")
    deadlines = _mapping(plan.get("channel_deadlines_ms"))
    shelf_limits = _mapping(plan.get("shelf_limits"))
    semantic_allowed = set(_tuple_text(plan.get("semantic_allowed_shelves")))
    semantic_enabled = bool(plan.get("semantic_enabled"))
    corpus_external = _external_corpus_backend_active(store)
    graph_external = _external_graph_backend_active(store)

    profile_allowed = _int(shelf_limits.get("profile")) > 0
    continuity_allowed = _int(shelf_limits.get("continuity_match")) > 0 or _int(shelf_limits.get("continuity_recent")) > 0
    transcript_allowed = _int(shelf_limits.get("transcript")) > 0
    operating_allowed = _int(shelf_limits.get("operating")) > 0
    corpus_allowed = _int(shelf_limits.get("corpus")) > 0
    graph_allowed = _int(shelf_limits.get("graph")) > 0
    keyword_allowed = any((profile_allowed, continuity_allowed, transcript_allowed, operating_allowed, corpus_allowed))

    semantic_uses_external_corpus = semantic_enabled and corpus_external and bool(
        {"corpus", "continuity", "continuity_match", "transcript", "tank"}.intersection(semantic_allowed)
    )
    semantic_support = "cancellation_unsupported" if semantic_uses_external_corpus else "bounded_sync"
    semantic_enforcement = "explicit_unsupported_status" if semantic_uses_external_corpus else "query_limit_bounded_same_thread"
    semantic_reason = (
        "external_corpus_semantic_backend_has_no_safe_cancel_seam"
        if semantic_uses_external_corpus
        else "semantic_index_path_is_bounded_by_route_limit"
    )

    graph_uses_external = graph_allowed and graph_external
    graph_support = "cancellation_unsupported" if graph_uses_external else "bounded_sync"
    graph_enforcement = "explicit_unsupported_status" if graph_uses_external else "query_limit_bounded_same_thread"
    graph_reason = (
        "external_graph_backend_has_no_safe_cancel_seam"
        if graph_uses_external
        else "graph_path_is_bounded_by_route_limit_or_skipped"
    )

    return {
        "task_memory": _status(
            channel="task_memory",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("operating")),
            allowed=True,
            support_status="bounded_sync",
            enforcement="query_limit_bounded_same_thread",
            reason="task_lookup_is_bounded_and_does_not_spawn_hidden_work",
        ),
        "operating_truth": _status(
            channel="operating_truth",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("operating")),
            allowed=operating_allowed,
            support_status="bounded_sync",
            enforcement="query_limit_bounded_same_thread",
            reason="operating_lookup_is_bounded_by_route_limit",
        ),
        "keyword": _status(
            channel="keyword",
            plan_id=plan_id,
            deadline_ms=max(_int(deadlines.get("profile")), _int(deadlines.get("corpus")), _int(deadlines.get("transcript"))),
            allowed=keyword_allowed,
            support_status="bounded_sync",
            enforcement="query_limit_bounded_same_thread",
            reason="keyword_channels_are_bounded_by_route_limits",
        ),
        "semantic": _status(
            channel="semantic",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("semantic")),
            allowed=semantic_enabled,
            support_status=semantic_support,
            enforcement=semantic_enforcement,
            reason=semantic_reason,
        ),
        "graph": _status(
            channel="graph",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("graph")),
            allowed=graph_allowed,
            support_status=graph_support,
            enforcement=graph_enforcement,
            reason=graph_reason,
        ),
        "graph_recall": _status(
            channel="graph_recall",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("graph")),
            allowed=graph_allowed or "graph" in semantic_allowed,
            support_status=graph_support,
            enforcement=graph_enforcement,
            reason=graph_reason,
        ),
        "associative_expansion": _status(
            channel="associative_expansion",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("graph")),
            allowed=graph_allowed,
            support_status=graph_support,
            enforcement=graph_enforcement,
            reason=graph_reason,
        ),
        "temporal": _status(
            channel="temporal",
            plan_id=plan_id,
            deadline_ms=_int(deadlines.get("temporal")),
            allowed=continuity_allowed or transcript_allowed or graph_allowed,
            support_status=graph_support if graph_allowed else "bounded_sync",
            enforcement=graph_enforcement if graph_allowed else "query_limit_bounded_same_thread",
            reason=graph_reason if graph_allowed else "temporal_support_is_bounded_by_route_limits",
        ),
    }
