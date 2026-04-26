from __future__ import annotations

from .runtime import (
    Any,
    AssociativeExpansionBounds,
    BrainstackStore,
    Dict,
    List,
    Mapping,
    RECENT_WORK_RECAP_RECORD_TYPES,
    ROUTE_AGGREGATE,
    ROUTE_STYLE_CONTRACT,
    ROUTE_TEMPORAL,
    STYLE_CONTRACT_SLOT,
    TEMPORAL_RECENT_CAP,
    TEMPORAL_TRANSCRIPT_CAP,
    _annotate_query_flags,
    _collect_query_rows,
    _current_assignment_lookup_requested,
    _dedupe_rows,
    _graph_channel_rows,
    _is_native_profile_mirror_receipt,
    _missing_style_contract_row,
    _native_aggregate_rows,
    _operating_channel_rows,
    _profile_keyword_rows,
    _round_robin,
    _same_principal_session_support_rows,
    _sort_rows_chronologically,
    _temporal_graph_rows,
    annotate_corpus_retrieval_trace,
    annotate_graph_rows_with_entity_resolution,
    build_associative_expansion,
    filter_graph_rows_to_entity_resolution_candidates,
    is_native_explicit_style_item,
)


def collect_profile_rows(
    store: BrainstackStore,
    *,
    query: str,
    principal_scope_key: str,
    profile_limit: int,
    profile_target_slots: tuple[str, ...],
    excluded_profile_slots: tuple[str, ...],
    route_mode: str,
    native_explicit_style_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    keyword_profile_rows = (
        _profile_keyword_rows(
            store.search_profile(
                query=query,
                limit=max(profile_limit * 4, 8),
                principal_scope_key=principal_scope_key,
                target_slots=profile_target_slots,
                excluded_slots=excluded_profile_slots,
            ),
            limit=max(profile_limit * 2, 6),
        )
        if profile_limit > 0
        else []
    )
    keyword_profile_rows = _annotate_query_flags(keyword_profile_rows, query=query)
    keyword_profile_rows = [row for row in keyword_profile_rows if not _is_native_profile_mirror_receipt(row)]
    if route_mode != ROUTE_STYLE_CONTRACT:
        return keyword_profile_rows
    keyword_profile_rows = [
        row
        for row in keyword_profile_rows
        if str(row.get("stable_key") or "").strip() == STYLE_CONTRACT_SLOT or is_native_explicit_style_item(row)
    ]
    if keyword_profile_rows:
        return keyword_profile_rows
    if native_explicit_style_rows:
        return list(native_explicit_style_rows)
    return [_missing_style_contract_row(principal_scope_key=principal_scope_key)]


def collect_continuity_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    continuity_queries: List[str],
    continuity_match_limit: int,
) -> List[Dict[str, Any]]:
    rows = (
        _collect_query_rows(
            shelf="continuity_match",
            queries=continuity_queries,
            searcher=lambda variant: store.search_continuity(
                query=variant,
                session_id=session_id,
                principal_scope_key=principal_scope_key,
                limit=max(continuity_match_limit * 4, 8),
            ),
        )
        if continuity_match_limit > 0
        else []
    )
    return _annotate_query_flags(rows, query=query)


def collect_transcript_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    continuity_queries: List[str],
    transcript_limit: int,
) -> dict[str, List[Dict[str, Any]]]:
    session_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=continuity_queries,
            searcher=lambda variant: store.search_transcript(
                query=variant,
                session_id=session_id,
                limit=max(transcript_limit * 4, 6),
            ),
        )
        if transcript_limit > 0
        else []
    )
    global_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=continuity_queries,
            searcher=lambda variant: store.search_transcript_global(
                query=variant,
                session_id=session_id,
                principal_scope_key=principal_scope_key,
                limit=max(transcript_limit * 6, 12),
            ),
        )
        if transcript_limit > 0
        else []
    )
    session_rows = _annotate_query_flags(session_rows, query=query)
    global_rows = _annotate_query_flags(global_rows, query=query)
    return {
        "session": session_rows,
        "global": global_rows,
        "merged": _round_robin(session_rows, global_rows),
    }


def collect_operating_rows(
    store: BrainstackStore,
    *,
    query: str,
    principal_scope_key: str,
    operating_limit: int,
    operating_lookup_rows: List[Dict[str, Any]],
    operating_target_types: List[str],
    explicit_operating_lookup: bool,
) -> dict[str, List[Dict[str, Any]]]:
    keyword_source_rows = (
        operating_lookup_rows
        if operating_lookup_rows
        else store.search_operating_records(
            query=query,
            principal_scope_key=principal_scope_key,
            record_types=operating_target_types or None,
            limit=max(operating_limit * 4, 8),
        )
        if operating_limit > 0
        else []
    )
    recent_work_source_rows: List[Dict[str, Any]] = []
    if operating_limit > 0:
        recent_work_source_rows = store.search_operating_records(
            query=query,
            principal_scope_key=principal_scope_key,
            record_types=RECENT_WORK_RECAP_RECORD_TYPES,
            limit=max(operating_limit * 4, 8),
        )
        if not recent_work_source_rows and _current_assignment_lookup_requested(query):
            recent_work_source_rows = [
                {
                    **dict(row),
                    "retrieval_source": str(row.get("retrieval_source") or "operating.recent_work_current"),
                    "match_mode": str(row.get("match_mode") or "authority"),
                }
                for row in store.list_operating_records(
                    principal_scope_key=principal_scope_key,
                    record_types=RECENT_WORK_RECAP_RECORD_TYPES,
                    limit=max(operating_limit * 2, 4),
                )
            ]
    return {
        "keyword": _annotate_query_flags(
            _operating_channel_rows(keyword_source_rows, limit=max(operating_limit * 3, 8))
            if operating_limit > 0
            else [],
            query=query,
        ),
        "recent_work": _annotate_query_flags(
            _operating_channel_rows(recent_work_source_rows, limit=max(operating_limit * 3, 8))
            if operating_limit > 0
            else [],
            query=query,
        ),
        "current": _annotate_query_flags(
            store.list_operating_records(
                principal_scope_key=principal_scope_key,
                record_types=operating_target_types or None,
                limit=max(operating_limit * 2, 6),
            )
            if operating_limit > 0 and explicit_operating_lookup
            else [],
            query=query,
        ),
    }


def collect_keyword_corpus_rows(
    store: BrainstackStore,
    *,
    query: str,
    search_queries: List[str],
    corpus_limit: int,
) -> List[Dict[str, Any]]:
    rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus(query=variant, limit=max(corpus_limit * 4, 8)),
        )
        if corpus_limit > 0
        else []
    )
    rows = _annotate_query_flags(rows, query=query)
    return annotate_corpus_retrieval_trace(rows, query=query, candidate_limit=max(corpus_limit * 4, 8))


def collect_semantic_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    search_queries: List[str],
    transcript_limit: int,
    corpus_limit: int,
    evidence_item_budget: int,
    entity_resolution: Mapping[str, Any],
) -> dict[str, List[Dict[str, Any]]]:
    conversation_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=search_queries,
            searcher=lambda variant: store.search_conversation_semantic(
                query=variant,
                session_id=session_id,
                limit=max(transcript_limit * 4, 8),
                principal_scope_key=principal_scope_key,
            ),
        )
        if transcript_limit > 0
        else []
    )
    corpus_rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus_semantic(query=variant, limit=max(corpus_limit * 4, 8)),
        )
        if corpus_limit > 0
        else []
    )
    semantic_evidence_rows = _annotate_query_flags(
        store.search_semantic_evidence(
            query=query,
            principal_scope_key=principal_scope_key,
            limit=max(evidence_item_budget * 4, 16),
        ),
        query=query,
    )
    semantic_graph_rows = [
        row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "graph"
    ]
    semantic_graph_rows = filter_graph_rows_to_entity_resolution_candidates(semantic_graph_rows, entity_resolution)
    semantic_graph_rows = annotate_graph_rows_with_entity_resolution(semantic_graph_rows, entity_resolution)
    semantic_index_corpus_rows = [
        row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "corpus"
    ]
    semantic_index_corpus_rows = annotate_corpus_retrieval_trace(
        semantic_index_corpus_rows,
        query=query,
        candidate_limit=max(evidence_item_budget * 4, 16),
    )
    return {
        "conversation": _annotate_query_flags(conversation_rows, query=query),
        "corpus": annotate_corpus_retrieval_trace(
            _annotate_query_flags(corpus_rows, query=query),
            query=query,
            candidate_limit=max(corpus_limit * 4, 8),
        ),
        "evidence": semantic_evidence_rows,
        "profile": [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "profile"],
        "task": [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "task"],
        "operating": [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "operating"],
        "continuity": [
            row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "continuity_match"
        ],
        "graph": semantic_graph_rows,
        "index_corpus": semantic_index_corpus_rows,
    }


def collect_graph_rows(
    store: BrainstackStore,
    *,
    query: str,
    principal_scope_key: str,
    graph_search_queries: List[str],
    graph_limit: int,
    semantic_graph_rows: List[Dict[str, Any]],
    entity_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    graph_rows = (
        _graph_channel_rows(
            _collect_query_rows(
                shelf="graph",
                queries=graph_search_queries,
                searcher=lambda variant: store.search_graph(
                    query=variant,
                    limit=max(graph_limit * 4, 12),
                    principal_scope_key=principal_scope_key,
                ),
            ),
            limit=max(graph_limit * 3, 8),
        )
        if graph_limit > 0
        else []
    )
    graph_rows = annotate_graph_rows_with_entity_resolution(_annotate_query_flags(graph_rows, query=query), entity_resolution)
    associative_expansion = build_associative_expansion(
        store,
        query=query,
        principal_scope_key=principal_scope_key,
        seed_rows=_dedupe_rows(_round_robin(graph_rows, semantic_graph_rows)),
        bounds=AssociativeExpansionBounds(
            max_seed_count=4,
            max_depth=1,
            max_candidate_count=max(min(graph_limit * 2, 8), 0),
            max_search_count=12,
            allowed_shelves=("graph",),
        ),
    )
    associative_graph_rows = (
        _graph_channel_rows(
            annotate_graph_rows_with_entity_resolution(
                _annotate_query_flags(list(associative_expansion.get("candidate_rows") or []), query=query),
                entity_resolution,
            ),
            limit=max(graph_limit * 2, 4),
        )
        if graph_limit > 0
        else []
    )
    graph_status = store.graph_backend_channel_status()
    if graph_rows and semantic_graph_rows:
        graph_recall_status = {
            "status": "active",
            "reason": "Query used lexical graph rows and typed semantic_seeded graph seeds.",
            "recall_mode": "hybrid_seeded",
        }
    elif semantic_graph_rows:
        graph_recall_status = {
            "status": "active",
            "reason": "Query used typed semantic graph seeds.",
            "recall_mode": "semantic_seeded",
        }
    elif graph_rows:
        graph_recall_status = {
            "status": "active",
            "reason": "Query used lexical graph search seeds.",
            "recall_mode": "lexical_seeded",
        }
    else:
        graph_recall_status = store.graph_recall_channel_status()
    return {
        "graph_rows": graph_rows,
        "associative_expansion": associative_expansion,
        "associative_graph_rows": associative_graph_rows,
        "graph_status": graph_status,
        "graph_recall_status": graph_recall_status,
    }


def collect_temporal_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    route: Any,
    continuity_recent_limit: int,
    transcript_limit: int,
    graph_limit: int,
    graph_search_queries: List[str],
    keyword_transcript_rows: List[Dict[str, Any]],
    semantic_conversation_rows: List[Dict[str, Any]],
    task_structured_authority: bool,
    entity_resolution: Mapping[str, Any],
) -> dict[str, List[Dict[str, Any]]]:
    recent_rows = (
        store.recent_continuity(session_id=session_id, limit=max(continuity_recent_limit * 4, 6))
        if continuity_recent_limit > 0
        else []
    )
    temporal_continuity_search = getattr(store, "search_temporal_continuity", None)
    temporal_continuity_rows = (
        temporal_continuity_search(
            query=query,
            session_id=session_id,
            principal_scope_key=principal_scope_key,
            limit=max(continuity_recent_limit * 4, TEMPORAL_RECENT_CAP),
        )
        if continuity_recent_limit > 0 and route.applied_mode == ROUTE_TEMPORAL and callable(temporal_continuity_search)
        else []
    )
    temporal_continuity_rows = _annotate_query_flags(temporal_continuity_rows, query=query)
    recent_rows = _annotate_query_flags(recent_rows, query=query)
    if task_structured_authority:
        recent_rows = []
        temporal_continuity_rows = []
    temporal_support_requested = route.applied_mode == ROUTE_TEMPORAL or route.requested_mode == ROUTE_TEMPORAL
    temporal_graph_rows: List[Dict[str, Any]] = []
    if graph_limit > 0 and temporal_support_requested:
        temporal_graph_rows = _temporal_graph_rows(
            _collect_query_rows(
                shelf="graph",
                queries=graph_search_queries,
                searcher=lambda variant: store.search_graph(
                    query=variant,
                    limit=max(graph_limit * 6, 12),
                    principal_scope_key=principal_scope_key,
                ),
            ),
            limit=max(graph_limit * 2, 6),
        )
        temporal_graph_rows = annotate_graph_rows_with_entity_resolution(temporal_graph_rows, entity_resolution)
    temporal_transcript_rows: List[Dict[str, Any]] = []
    if transcript_limit > 0 and temporal_support_requested:
        temporal_support_rows = _same_principal_session_support_rows(
            store,
            _dedupe_rows(_round_robin(temporal_continuity_rows, recent_rows)),
            current_session_id=session_id,
        )
        temporal_transcript_rows = _sort_rows_chronologically(
            _round_robin(keyword_transcript_rows, semantic_conversation_rows, temporal_support_rows),
            limit=max(TEMPORAL_TRANSCRIPT_CAP * 2, transcript_limit * 2),
        )
    return {
        "recent": recent_rows,
        "continuity": temporal_continuity_rows,
        "graph": temporal_graph_rows,
        "transcript": temporal_transcript_rows,
        "merged": _round_robin(temporal_continuity_rows, recent_rows, temporal_transcript_rows, temporal_graph_rows),
    }


def collect_lexical_channels(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    route = context["route"]
    limits = context["limits"]
    operating_lookup, operating_lookup_rows, operating_target_types, explicit_operating_lookup = context["operating_context"]
    transcript_channels = collect_transcript_rows(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        continuity_queries=context["continuity_queries"],
        transcript_limit=limits["transcript_limit"],
    )
    return {
        "operating_lookup": operating_lookup,
        "profile": collect_profile_rows(
            store,
            query=query,
            principal_scope_key=principal_scope_key,
            profile_limit=limits["profile_limit"],
            profile_target_slots=context["profile_target_slots"],
            excluded_profile_slots=context["excluded_profile_slots"],
            route_mode=route.applied_mode,
            native_explicit_style_rows=context["native_explicit_style_rows"],
        ),
        "continuity": collect_continuity_rows(
            store,
            query=query,
            session_id=session_id,
            principal_scope_key=principal_scope_key,
            continuity_queries=context["continuity_queries"],
            continuity_match_limit=limits["continuity_match_limit"],
        ),
        "transcript": transcript_channels["merged"],
        "operating": collect_operating_rows(
            store,
            query=query,
            principal_scope_key=principal_scope_key,
            operating_limit=limits["operating_limit"],
            operating_lookup_rows=operating_lookup_rows,
            operating_target_types=operating_target_types,
            explicit_operating_lookup=explicit_operating_lookup,
        ),
    }


def collect_semantic_and_task_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    context: Mapping[str, Any],
) -> tuple[dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    limits = context["limits"]
    semantic_channels = collect_semantic_rows(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        search_queries=context["search_queries"],
        transcript_limit=limits["transcript_limit"],
        corpus_limit=limits["corpus_limit"],
        evidence_item_budget=context["evidence_item_budget"],
        entity_resolution=context["entity_resolution"],
    )
    task_rows = list(context["task_rows"])
    if semantic_channels["task"]:
        task_rows = _dedupe_rows(_round_robin(task_rows, semantic_channels["task"]))[:24]
    return semantic_channels, task_rows


def apply_task_authority_suppression(
    *,
    route: Any,
    task_lookup: Any,
    keyword_continuity_rows: List[Dict[str, Any]],
    keyword_transcript_rows: List[Dict[str, Any]],
    semantic_channels: dict[str, List[Dict[str, Any]]],
) -> tuple[bool, List[Dict[str, Any]], List[Dict[str, Any]]]:
    task_structured_authority = isinstance(task_lookup, Mapping) and route.applied_mode != ROUTE_TEMPORAL
    if not task_structured_authority:
        return False, keyword_continuity_rows, keyword_transcript_rows
    semantic_channels["conversation"] = []
    semantic_channels["continuity"] = []
    return True, [], []


def collect_graph_temporal_channels(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    context: Mapping[str, Any],
    keyword_transcript_rows: List[Dict[str, Any]],
    semantic_channels: Mapping[str, List[Dict[str, Any]]],
    task_structured_authority: bool,
) -> tuple[dict[str, Any], dict[str, List[Dict[str, Any]]]]:
    route = context["route"]
    limits = context["limits"]
    graph_channels = collect_graph_rows(
        store,
        query=query,
        principal_scope_key=principal_scope_key,
        graph_search_queries=context["graph_search_queries"],
        graph_limit=limits["graph_limit"],
        semantic_graph_rows=semantic_channels["graph"],
        entity_resolution=context["entity_resolution"],
    )
    temporal_channels = collect_temporal_rows(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        route=route,
        continuity_recent_limit=limits["continuity_recent_limit"],
        transcript_limit=limits["transcript_limit"],
        graph_limit=limits["graph_limit"],
        graph_search_queries=context["graph_search_queries"],
        keyword_transcript_rows=keyword_transcript_rows,
        semantic_conversation_rows=semantic_channels["conversation"],
        task_structured_authority=task_structured_authority,
        entity_resolution=context["entity_resolution"],
    )
    return graph_channels, temporal_channels


def collect_candidate_channels(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str,
    context: Mapping[str, Any],
) -> Dict[str, Any]:
    route = context["route"]
    limits = context["limits"]
    lexical_channels = collect_lexical_channels(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        context=context,
    )
    semantic_channels, task_rows = collect_semantic_and_task_rows(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        context=context,
    )
    task_structured_authority, keyword_continuity_rows, keyword_transcript_rows = apply_task_authority_suppression(
        route=route,
        task_lookup=context["task_lookup"],
        keyword_continuity_rows=lexical_channels["continuity"],
        keyword_transcript_rows=lexical_channels["transcript"],
        semantic_channels=semantic_channels,
    )
    keyword_corpus_rows = collect_keyword_corpus_rows(
        store,
        query=query,
        search_queries=context["search_queries"],
        corpus_limit=limits["corpus_limit"],
    )
    graph_channels, temporal_channels = collect_graph_temporal_channels(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        context=context,
        keyword_transcript_rows=keyword_transcript_rows,
        semantic_channels=semantic_channels,
        task_structured_authority=task_structured_authority,
    )
    return {
        "task_rows": task_rows,
        "task_structured_authority": task_structured_authority,
        "operating_lookup": lexical_channels["operating_lookup"],
        "keyword_profile_rows": lexical_channels["profile"],
        "keyword_continuity_rows": keyword_continuity_rows,
        "keyword_transcript_rows": keyword_transcript_rows,
        "keyword_corpus_rows": keyword_corpus_rows,
        "keyword_rows": _round_robin(
            lexical_channels["profile"],
            lexical_channels["operating"]["keyword"],
            lexical_channels["operating"]["recent_work"],
            keyword_continuity_rows,
            keyword_transcript_rows,
            keyword_corpus_rows,
        ),
        "operating_channels": lexical_channels["operating"],
        "semantic_channels": semantic_channels,
        "graph_channels": graph_channels,
        "temporal_channels": temporal_channels,
        "native_aggregate_rows": (
            _native_aggregate_rows(store, query=query, session_id=session_id)
            if route.applied_mode == ROUTE_AGGREGATE
            else []
        ),
    }
