from __future__ import annotations

from .channel_collection import collect_candidate_channels
from .fusion_selection import merge_retrieval_candidates, select_route_rows, selected_candidate_keys
from .result_payload import fused_candidate_payload, retrieval_channel_statuses, semantic_retrieval_status
from .route_context import build_route_context
from .runtime import Any, BrainstackStore, Callable, Dict, _build_lookup_semantics, asdict


def retrieve_executive_context(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str = "",
    analysis: Dict[str, Any],
    policy: Dict[str, Any],
    route_resolver: Callable[[str], Dict[str, Any] | str] | None = None,
    timezone_name: str = "UTC",
) -> Dict[str, Any]:
    context = build_route_context(
        store,
        query=query,
        principal_scope_key=principal_scope_key,
        analysis=analysis,
        policy=policy,
        route_resolver=route_resolver,
    )
    route = context["route"]
    limits = context["limits"]
    rows = collect_candidate_channels(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        context=context,
    )
    fused = merge_retrieval_candidates(rows)
    selected = select_route_rows(
        store,
        query=query,
        session_id=session_id,
        route=route,
        limits=limits,
        evidence_item_budget=context["evidence_item_budget"],
        rows=rows,
        fused=fused,
    )
    semantic_status = semantic_retrieval_status(
        store,
        corpus_limit=limits["corpus_limit"],
        keyword_corpus_rows=rows["keyword_corpus_rows"],
        semantic_channels=rows["semantic_channels"],
    )
    lookup_semantics = _build_lookup_semantics(
        query=query,
        task_lookup=context["task_lookup"],
        task_rows=rows["task_rows"],
        operating_lookup=rows["operating_lookup"],
        operating_rows=selected.get("operating_rows") or [],
        selected=selected,
    )
    associative_expansion = rows["graph_channels"]["associative_expansion"]
    return {
        **selected,
        "task_rows": rows["task_rows"],
        "operating_rows": selected.get("operating_rows") or [],
        "channels": retrieval_channel_statuses(context=context, rows=rows, semantic_status=semantic_status),
        "fused_candidates": fused_candidate_payload(fused, selected_candidate_keys=selected_candidate_keys(selected)),
        "decomposition": {
            "used": False,
            "queries": list(context["search_queries"]),
            "legacy_disabled": True,
        },
        "entity_resolution": context["entity_resolution"],
        "lookup_semantics": lookup_semantics,
        "associative_expansion": {key: value for key, value in associative_expansion.items() if key != "candidate_rows"},
        "routing": asdict(route),
    }
