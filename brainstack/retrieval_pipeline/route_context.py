from __future__ import annotations

from .runtime import (
    Any,
    BrainstackStore,
    Callable,
    Dict,
    List,
    Mapping,
    OPERATING_RECORD_TYPES,
    ROUTE_STYLE_CONTRACT,
    STYLE_CONTRACT_SLOT,
    _annotate_query_flags,
    _build_cross_session_search_queries,
    _dedupe_rows,
    _normalize_text,
    _resolve_route,
    _route_limits,
    is_native_explicit_style_item,
    resolve_entity_candidates,
)


def effective_route_resolver(
    route_resolver: Callable[[str], Dict[str, Any] | str] | None,
    analysis: Mapping[str, Any],
) -> Callable[[str], Dict[str, Any] | str] | None:
    analysis_route_payload = analysis.get("route_payload")
    if route_resolver is not None or not isinstance(analysis_route_payload, Mapping):
        return route_resolver
    payload = dict(analysis_route_payload)

    def resolver(_query: str, _payload: Mapping[str, Any] = payload) -> Dict[str, Any]:
        return dict(_payload)

    return resolver


def policy_limit(policy: Mapping[str, Any], key: str) -> int:
    return max(int(policy.get(key, 0)), 0)


def load_task_rows(
    store: BrainstackStore,
    *,
    task_lookup: Mapping[str, Any] | None,
    principal_scope_key: str,
) -> List[Dict[str, Any]]:
    task_lookup_rows = (
        [dict(row) for row in (task_lookup.get("matched_rows") or []) if isinstance(row, Mapping)]
        if isinstance(task_lookup, Mapping)
        else []
    )
    if task_lookup_rows:
        return _dedupe_rows(task_lookup_rows)
    if not isinstance(task_lookup, Mapping):
        return []
    return store.list_task_items(
        principal_scope_key=principal_scope_key,
        due_date=str(task_lookup.get("due_date") or "").strip(),
        item_type=str(task_lookup.get("item_type") or "").strip(),
        statuses=("open",),
        limit=24,
    )


def operating_lookup_context(analysis: Mapping[str, Any]) -> tuple[Mapping[str, Any] | None, List[Dict[str, Any]], List[str], bool]:
    operating_lookup = analysis.get("operating_lookup") if isinstance(analysis.get("operating_lookup"), Mapping) else None
    operating_lookup_rows = (
        [dict(row) for row in (operating_lookup.get("matched_rows") or []) if isinstance(row, Mapping)]
        if isinstance(operating_lookup, Mapping)
        else []
    )
    operating_target_types = (
        [
            str(value or "").strip()
            for value in (operating_lookup.get("record_types") or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        if isinstance(operating_lookup, Mapping)
        else []
    )
    return operating_lookup, operating_lookup_rows, operating_target_types, isinstance(operating_lookup, Mapping) and not operating_lookup_rows


def profile_target_context(
    *,
    analysis: Mapping[str, Any],
    route_mode: str,
    preserve_authoritative_contract: bool,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    profile_target_slots = tuple(str(slot) for slot in analysis.get("profile_slot_targets") or ())
    if route_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract:
        profile_target_slots = tuple({*profile_target_slots, STYLE_CONTRACT_SLOT})
    excluded_profile_slots = () if route_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract else (STYLE_CONTRACT_SLOT,)
    return profile_target_slots, excluded_profile_slots


def build_route_context(
    store: BrainstackStore,
    *,
    query: str,
    principal_scope_key: str,
    analysis: Mapping[str, Any],
    policy: Mapping[str, Any],
    route_resolver: Callable[[str], Dict[str, Any] | str] | None,
) -> Dict[str, Any]:
    base_limits = {
        "profile_limit": policy_limit(policy, "profile_limit"),
        "continuity_match_limit": policy_limit(policy, "continuity_match_limit"),
        "continuity_recent_limit": policy_limit(policy, "continuity_recent_limit"),
        "transcript_limit": policy_limit(policy, "transcript_limit"),
        "operating_limit": policy_limit(policy, "operating_limit"),
        "graph_limit": policy_limit(policy, "graph_limit"),
        "corpus_limit": policy_limit(policy, "corpus_limit"),
    }
    native_explicit_style_rows = [
        row
        for row in store.list_profile_items(limit=24, principal_scope_key=principal_scope_key)
        if is_native_explicit_style_item(row)
    ]
    route = _resolve_route(query, route_resolver=effective_route_resolver(route_resolver, analysis))
    search_queries = [_normalize_text(query)]
    entity_resolution = resolve_entity_candidates(
        store,
        query=query,
        principal_scope_key=principal_scope_key,
        limit=4,
    )
    resolver_query_variants = [
        _normalize_text(f"{candidate.get('canonical_name', '')} {query}")
        for candidate in entity_resolution.get("candidates", [])
        if isinstance(candidate, Mapping) and str(candidate.get("canonical_name") or "").strip()
    ]
    task_lookup = analysis.get("task_lookup") if isinstance(analysis.get("task_lookup"), Mapping) else None
    profile_target_slots, excluded_profile_slots = profile_target_context(
        analysis=analysis,
        route_mode=route.applied_mode,
        preserve_authoritative_contract=bool(policy.get("show_authoritative_contract")),
    )
    return {
        "route": route,
        "limits": _route_limits(route=route, **base_limits),
        "evidence_item_budget": policy_limit(policy, "evidence_item_budget"),
        "search_queries": search_queries,
        "graph_search_queries": list(dict.fromkeys(search_queries + resolver_query_variants)),
        "continuity_queries": _build_cross_session_search_queries(query),
        "entity_resolution": entity_resolution,
        "task_lookup": task_lookup,
        "task_rows": _annotate_query_flags(
            load_task_rows(store, task_lookup=task_lookup, principal_scope_key=principal_scope_key),
            query=query,
        ),
        "operating_context": operating_lookup_context(analysis),
        "profile_target_slots": profile_target_slots,
        "excluded_profile_slots": excluded_profile_slots,
        "native_explicit_style_rows": native_explicit_style_rows,
    }
