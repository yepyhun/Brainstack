from __future__ import annotations

from .runtime import (
    Any,
    AssociativeExpansionBounds,
    BrainstackStore,
    Callable,
    Dict,
    EvidenceCandidate,
    List,
    Mapping,
    OPERATING_RECORD_TYPES,
    RECENT_WORK_RECAP_RECORD_TYPES,
    ROUTE_AGGREGATE,
    ROUTE_FACT,
    ROUTE_STYLE_CONTRACT,
    ROUTE_TEMPORAL,
    STYLE_CONTRACT_SLOT,
    TEMPORAL_RECENT_CAP,
    TEMPORAL_TRANSCRIPT_CAP,
    _agreement_bonus,
    _annotate_query_flags,
    _build_cross_session_search_queries,
    _build_lookup_semantics,
    _candidate_authority_floor,
    _candidate_has_authority_floor,
    _candidate_key,
    _candidate_priority_bonus,
    _candidate_text,
    _channel_status,
    _collect_query_rows,
    _current_assignment_lookup_requested,
    _dedupe_rows,
    _fact_sort_key,
    _fact_transcript_rows,
    _graph_channel_rows,
    _has_meaningful_transcript_signal,
    _is_native_profile_mirror_receipt,
    _keep_temporal_transcript_rows_with_anchor_support,
    _merge_channel,
    _missing_style_contract_row,
    _native_aggregate_rows,
    _normalize_text,
    _operating_channel_rows,
    _profile_keyword_rows,
    _resolve_route,
    _round_robin,
    _route_has_support,
    _route_limits,
    _same_principal_session_support_rows,
    _select_aggregate_rows,
    _select_rows,
    _select_temporal_rows,
    _sort_rows_chronologically,
    _temporal_graph_rows,
    annotate_corpus_retrieval_trace,
    annotate_graph_rows_with_entity_resolution,
    asdict,
    build_associative_expansion,
    filter_graph_rows_to_entity_resolution_candidates,
    is_native_explicit_style_item,
    resolve_entity_candidates,
)

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
    profile_limit = max(int(policy.get("profile_limit", 0)), 0)
    continuity_match_limit = max(int(policy.get("continuity_match_limit", 0)), 0)
    continuity_recent_limit = max(int(policy.get("continuity_recent_limit", 0)), 0)
    transcript_limit = max(int(policy.get("transcript_limit", 0)), 0)
    evidence_item_budget = max(int(policy.get("evidence_item_budget", 0)), 0)
    operating_limit = max(int(policy.get("operating_limit", 0)), 0)
    graph_limit = max(int(policy.get("graph_limit", 0)), 0)
    corpus_limit = max(int(policy.get("corpus_limit", 0)), 0)
    native_explicit_style_rows = [
        row
        for row in store.list_profile_items(limit=24, principal_scope_key=principal_scope_key)
        if is_native_explicit_style_item(row)
    ]
    analysis_route_payload = analysis.get("route_payload")
    effective_route_resolver = route_resolver
    if effective_route_resolver is None and isinstance(analysis_route_payload, Mapping):
        payload = dict(analysis_route_payload)

        def effective_route_resolver(_query: str, _payload: Mapping[str, Any] = payload) -> Dict[str, Any]:
            return dict(_payload)

    route = _resolve_route(
        query,
        route_resolver=effective_route_resolver,
    )
    limits = _route_limits(
        route=route,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        operating_limit=operating_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
    )
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
    graph_search_queries = list(dict.fromkeys(search_queries + resolver_query_variants))
    continuity_queries = _build_cross_session_search_queries(query)
    task_lookup = analysis.get("task_lookup") if isinstance(analysis.get("task_lookup"), Mapping) else None
    operating_lookup = analysis.get("operating_lookup") if isinstance(analysis.get("operating_lookup"), Mapping) else None
    task_lookup_rows = (
        [dict(row) for row in (task_lookup.get("matched_rows") or []) if isinstance(row, Mapping)]
        if isinstance(task_lookup, Mapping)
        else []
    )
    operating_lookup_rows = (
        [dict(row) for row in (operating_lookup.get("matched_rows") or []) if isinstance(row, Mapping)]
        if isinstance(operating_lookup, Mapping)
        else []
    )
    task_rows = (
        _dedupe_rows(task_lookup_rows)
        if task_lookup_rows
        else store.list_task_items(
            principal_scope_key=principal_scope_key,
            due_date=str(task_lookup.get("due_date") or "").strip(),
            item_type=str(task_lookup.get("item_type") or "").strip(),
            statuses=("open",),
            limit=24,
        )
        if isinstance(task_lookup, Mapping)
        else []
    )
    task_rows = _annotate_query_flags(task_rows, query=query)
    operating_target_types = (
        [
            str(value or "").strip()
            for value in (operating_lookup.get("record_types") or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        if isinstance(operating_lookup, Mapping)
        else []
    )
    explicit_operating_lookup = isinstance(operating_lookup, Mapping) and not operating_lookup_rows
    profile_limit = limits["profile_limit"]
    continuity_match_limit = limits["continuity_match_limit"]
    continuity_recent_limit = limits["continuity_recent_limit"]
    transcript_limit = limits["transcript_limit"]
    operating_limit = limits["operating_limit"]
    graph_limit = limits["graph_limit"]
    corpus_limit = limits["corpus_limit"]

    profile_target_slots = tuple(str(slot) for slot in analysis.get("profile_slot_targets") or ())
    preserve_authoritative_contract = bool(policy.get("show_authoritative_contract"))
    if route.applied_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract:
        profile_target_slots = tuple({*profile_target_slots, STYLE_CONTRACT_SLOT})
    excluded_profile_slots = () if route.applied_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract else (STYLE_CONTRACT_SLOT,)

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
    if route.applied_mode == ROUTE_STYLE_CONTRACT:
        keyword_profile_rows = [
            row
            for row in keyword_profile_rows
            if str(row.get("stable_key") or "").strip() == STYLE_CONTRACT_SLOT or is_native_explicit_style_item(row)
        ]
        if not keyword_profile_rows:
            if native_explicit_style_rows:
                keyword_profile_rows = list(native_explicit_style_rows)
            else:
                keyword_profile_rows = [_missing_style_contract_row(principal_scope_key=principal_scope_key)]
    keyword_continuity_rows = (
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
    keyword_continuity_rows = _annotate_query_flags(keyword_continuity_rows, query=query)
    keyword_transcript_session_rows = (
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
    keyword_transcript_session_rows = _annotate_query_flags(keyword_transcript_session_rows, query=query)
    keyword_transcript_global_rows = (
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
    keyword_transcript_global_rows = _annotate_query_flags(keyword_transcript_global_rows, query=query)
    keyword_transcript_rows = _round_robin(
        keyword_transcript_session_rows,
        keyword_transcript_global_rows,
    )
    keyword_operating_source_rows = (
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
    keyword_operating_rows = (
        _operating_channel_rows(
            keyword_operating_source_rows,
            limit=max(operating_limit * 3, 8),
        )
        if operating_limit > 0
        else []
    )
    keyword_operating_rows = _annotate_query_flags(keyword_operating_rows, query=query)
    recent_work_operating_source_rows: List[Dict[str, Any]] = []
    if operating_limit > 0:
        recent_work_operating_source_rows = store.search_operating_records(
            query=query,
            principal_scope_key=principal_scope_key,
            record_types=RECENT_WORK_RECAP_RECORD_TYPES,
            limit=max(operating_limit * 4, 8),
        )
        if not recent_work_operating_source_rows and _current_assignment_lookup_requested(query):
            recent_work_operating_source_rows = [
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
    recent_work_operating_rows = (
        _operating_channel_rows(
            recent_work_operating_source_rows,
            limit=max(operating_limit * 3, 8),
        )
        if operating_limit > 0
        else []
    )
    recent_work_operating_rows = _annotate_query_flags(recent_work_operating_rows, query=query)
    current_operating_rows = (
        store.list_operating_records(
            principal_scope_key=principal_scope_key,
            record_types=operating_target_types or None,
            limit=max(operating_limit * 2, 6),
        )
        if operating_limit > 0 and explicit_operating_lookup
        else []
    )
    current_operating_rows = _annotate_query_flags(current_operating_rows, query=query)
    keyword_corpus_rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus(
                query=variant,
                limit=max(corpus_limit * 4, 8),
            ),
        )
        if corpus_limit > 0
        else []
    )
    keyword_corpus_rows = _annotate_query_flags(keyword_corpus_rows, query=query)
    keyword_corpus_rows = annotate_corpus_retrieval_trace(
        keyword_corpus_rows,
        query=query,
        candidate_limit=max(corpus_limit * 4, 8),
    )
    semantic_conversation_rows = (
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
    semantic_conversation_rows = _annotate_query_flags(semantic_conversation_rows, query=query)
    semantic_corpus_rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus_semantic(
                query=variant,
                limit=max(corpus_limit * 4, 8),
            ),
        )
        if corpus_limit > 0
        else []
    )
    semantic_corpus_rows = _annotate_query_flags(semantic_corpus_rows, query=query)
    semantic_corpus_rows = annotate_corpus_retrieval_trace(
        semantic_corpus_rows,
        query=query,
        candidate_limit=max(corpus_limit * 4, 8),
    )
    semantic_evidence_rows = store.search_semantic_evidence(
        query=query,
        principal_scope_key=principal_scope_key,
        limit=max(evidence_item_budget * 4, 16),
    )
    semantic_evidence_rows = _annotate_query_flags(semantic_evidence_rows, query=query)
    semantic_profile_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "profile"]
    semantic_task_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "task"]
    semantic_operating_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "operating"]
    semantic_continuity_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "continuity_match"]
    semantic_graph_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "graph"]
    semantic_graph_rows = filter_graph_rows_to_entity_resolution_candidates(semantic_graph_rows, entity_resolution)
    semantic_graph_rows = annotate_graph_rows_with_entity_resolution(semantic_graph_rows, entity_resolution)
    semantic_index_corpus_rows = [row for row in semantic_evidence_rows if str(row.get("semantic_shelf") or "") == "corpus"]
    semantic_index_corpus_rows = annotate_corpus_retrieval_trace(
        semantic_index_corpus_rows,
        query=query,
        candidate_limit=max(evidence_item_budget * 4, 16),
    )
    if semantic_task_rows:
        task_rows = _dedupe_rows(_round_robin(task_rows, semantic_task_rows))[:24]
    task_structured_authority = isinstance(task_lookup, Mapping) and route.applied_mode != ROUTE_TEMPORAL
    if task_structured_authority:
        keyword_continuity_rows = []
        keyword_transcript_session_rows = []
        keyword_transcript_global_rows = []
        keyword_transcript_rows = []
        semantic_conversation_rows = []
        semantic_continuity_rows = []
    keyword_rows = _round_robin(
        keyword_profile_rows,
        keyword_operating_rows,
        recent_work_operating_rows,
        keyword_continuity_rows,
        keyword_transcript_rows,
        keyword_corpus_rows,
    )

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
    graph_rows = _annotate_query_flags(graph_rows, query=query)
    graph_rows = annotate_graph_rows_with_entity_resolution(graph_rows, entity_resolution)
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
        if continuity_recent_limit > 0
        and route.applied_mode == ROUTE_TEMPORAL
        and callable(temporal_continuity_search)
        else []
    )
    temporal_continuity_rows = _annotate_query_flags(temporal_continuity_rows, query=query)
    recent_rows = _annotate_query_flags(recent_rows, query=query)
    if task_structured_authority:
        recent_rows = []
        temporal_continuity_rows = []
    temporal_support_requested = route.applied_mode == ROUTE_TEMPORAL or route.requested_mode == ROUTE_TEMPORAL

    temporal_graph_rows = []
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

    temporal_transcript_rows = []
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

    temporal_rows = _round_robin(
        temporal_continuity_rows,
        recent_rows,
        temporal_transcript_rows,
        temporal_graph_rows,
    )
    native_aggregate_rows = (
        _native_aggregate_rows(
            store,
            query=query,
            session_id=session_id,
        )
        if route.applied_mode == ROUTE_AGGREGATE
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

    merged: Dict[str, EvidenceCandidate] = {}
    _merge_channel(merged, channel_name="keyword", rows=keyword_profile_rows, shelf="profile")
    _merge_channel(merged, channel_name="semantic", rows=semantic_profile_rows, shelf="profile")
    _merge_channel(merged, channel_name="operating", rows=keyword_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=recent_work_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=current_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="semantic", rows=semantic_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="keyword", rows=keyword_continuity_rows, shelf="continuity_match")
    _merge_channel(merged, channel_name="semantic", rows=semantic_continuity_rows, shelf="continuity_match")
    _merge_channel(merged, channel_name="keyword", rows=keyword_transcript_rows, shelf="transcript")
    _merge_channel(merged, channel_name="keyword", rows=keyword_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_conversation_rows, shelf="transcript")
    _merge_channel(merged, channel_name="semantic", rows=semantic_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_index_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="graph", rows=graph_rows, shelf="graph")
    _merge_channel(merged, channel_name="semantic", rows=semantic_graph_rows, shelf="graph")
    _merge_channel(merged, channel_name="associative", rows=associative_graph_rows, shelf="graph")
    _merge_channel(merged, channel_name="temporal", rows=temporal_continuity_rows, shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=recent_rows, shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=temporal_transcript_rows, shelf="transcript")
    _merge_channel(merged, channel_name="temporal", rows=temporal_graph_rows, shelf="graph")

    fused = sorted(merged.values(), key=_fact_sort_key, reverse=True)

    fact_selected = _select_rows(
        fused,
        query=query,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        operating_limit=operating_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        evidence_item_budget=evidence_item_budget,
    )
    fused_transcript_rows = [candidate.row for candidate in fused if candidate.shelf == "transcript"]
    fact_selected["transcript_rows"] = _fact_transcript_rows(
        store=store,
        current_session_id=session_id,
        fused_transcript_rows=fused_transcript_rows,
        keyword_transcript_rows=keyword_transcript_rows,
        semantic_conversation_rows=semantic_conversation_rows,
        matched_rows=fact_selected["matched"],
        limit=limits["transcript_limit"],
    )
    fact_selected["transcript_rows"] = [
        row for row in fact_selected["transcript_rows"] if not str(row.get("_brainstack_suppression_reason") or "")
    ]
    selected = fact_selected
    if route.applied_mode == ROUTE_TEMPORAL:
        selected = _select_temporal_rows(
            keyword_continuity_rows=keyword_continuity_rows,
            recent_rows=recent_rows,
            temporal_continuity_rows=temporal_continuity_rows,
            temporal_transcript_rows=temporal_transcript_rows,
            graph_rows=temporal_graph_rows,
            limits=limits,
        )
    elif route.applied_mode == ROUTE_AGGREGATE:
        selected = _select_aggregate_rows(
            native_aggregate_rows=native_aggregate_rows,
            keyword_continuity_rows=keyword_continuity_rows,
            keyword_transcript_rows=keyword_transcript_rows,
            semantic_conversation_rows=semantic_conversation_rows,
            keyword_corpus_rows=keyword_corpus_rows,
            semantic_corpus_rows=semantic_corpus_rows,
            graph_rows=graph_rows,
            limits=limits,
        )

    transcript_rows = selected["transcript_rows"]
    if transcript_rows and not _has_meaningful_transcript_signal(transcript_rows):
        if route.applied_mode == ROUTE_TEMPORAL and _keep_temporal_transcript_rows_with_anchor_support(selected):
            pass
        else:
            selected["transcript_rows"] = []
    if route.applied_mode != ROUTE_FACT and not _route_has_support(route, selected):
        route.fallback_used = True
        route.applied_mode = ROUTE_FACT
        selected = fact_selected

    selected_candidate_keys = {
        _candidate_key(shelf, row)
        for shelf, rows in (
            ("profile", selected.get("profile_items") or []),
            ("operating", selected.get("operating_rows") or []),
            ("continuity_match", selected.get("matched") or []),
            ("continuity_recent", selected.get("recent") or []),
            ("transcript", selected.get("transcript_rows") or []),
            ("graph", selected.get("graph_rows") or []),
            ("corpus", selected.get("corpus_rows") or []),
        )
        for row in rows
    }

    corpus_semantic_status = (
        store.corpus_semantic_channel_status()
        if corpus_limit > 0 or keyword_corpus_rows or semantic_corpus_rows
        else {
            "status": "idle",
            "reason": "Corpus semantic retrieval was intentionally skipped for this query shape.",
        }
    )
    semantic_index_status = store.semantic_evidence_channel_status()
    semantic_channel_rows = semantic_conversation_rows + semantic_corpus_rows + semantic_evidence_rows
    if str(semantic_index_status.get("status") or "") == "degraded":
        semantic_status = {
            "status": "degraded",
            "reason": str(semantic_index_status.get("reason") or ""),
        }
    elif semantic_channel_rows:
        semantic_status = {
            "status": "active",
            "reason": (
                f"Derived index: {semantic_index_status.get('reason') or ''} "
                f"Corpus backend: {corpus_semantic_status.get('reason') or ''}"
            ).strip(),
        }
    else:
        semantic_status = {
            "status": str(corpus_semantic_status.get("status") or semantic_index_status.get("status") or "idle"),
            "reason": (
                f"Derived index: {semantic_index_status.get('reason') or ''} "
                f"Corpus backend: {corpus_semantic_status.get('reason') or ''}"
            ).strip(),
        }
    channels = [
        _channel_status(
            "task_memory",
            task_rows,
            reason="structured task truth",
            status="active" if task_lookup is not None else "idle",
        ),
        _channel_status(
            "operating_truth",
            keyword_operating_rows + recent_work_operating_rows + current_operating_rows,
            reason="first-class operating truth",
            status="active" if operating_lookup is not None or bool(recent_work_operating_rows) else "idle",
        ),
        _channel_status(
            "semantic",
            semantic_channel_rows,
            reason=str(semantic_status.get("reason") or ""),
            status=str(semantic_status.get("status") or "degraded"),
        ),
        _channel_status("keyword", keyword_rows),
        _channel_status(
            "graph",
            graph_rows,
            reason=str(graph_status.get("reason") or ""),
            status=str(graph_status.get("status") or "degraded"),
        ),
        _channel_status(
            "graph_recall",
            graph_rows + semantic_graph_rows + associative_graph_rows,
            reason=f"{graph_recall_status.get('recall_mode')}: {graph_recall_status.get('reason')}",
            status=str(graph_recall_status.get("status") or "idle"),
        ),
        _channel_status(
            "associative_expansion",
            associative_graph_rows,
            reason=str(associative_expansion.get("reason") or ""),
            status=str(associative_expansion.get("status") or "idle"),
        ),
        _channel_status("temporal", temporal_rows),
    ]
    lookup_semantics = _build_lookup_semantics(
        query=query,
        task_lookup=task_lookup,
        task_rows=task_rows,
        operating_lookup=operating_lookup,
        operating_rows=selected.get("operating_rows") or [],
        selected=selected,
    )

    return {
        **selected,
        "task_rows": task_rows,
        "operating_rows": selected.get("operating_rows") or [],
        "channels": channels,
        "fused_candidates": [
            {
                "key": candidate.key,
                "shelf": candidate.shelf,
                "rrf_score": candidate.rrf_score,
                "agreement_bonus": _agreement_bonus(candidate),
                "priority_bonus": _candidate_priority_bonus(candidate),
                "authority_floor": _candidate_authority_floor(candidate),
                "authority_floor_applied": _candidate_has_authority_floor(candidate),
                "channel_ranks": dict(candidate.channel_ranks),
                "selection_status": "selected" if candidate.key in selected_candidate_keys else "not_selected",
                "selection_reason": (
                    "selected_by_fusion_and_budget"
                    if candidate.key in selected_candidate_keys
                    else str(candidate.row.get("_brainstack_suppression_reason") or "not_selected_by_route_authority_dedupe_or_budget")
                ),
                "id": int(candidate.row.get("id") or 0),
                "row_id": int(candidate.row.get("row_id") or 0),
                "turn_number": int(candidate.row.get("turn_number") or 0),
                "document_id": int(candidate.row.get("document_id") or 0),
                "section_index": int(candidate.row.get("section_index") or 0),
                "created_at": str(candidate.row.get("created_at") or ""),
                "keyword_score": float(candidate.row.get("keyword_score") or 0.0),
                "semantic_score": float(candidate.row.get("semantic_score") or 0.0),
                "retrieval_source": str(candidate.row.get("retrieval_source") or ""),
                "match_mode": str(candidate.row.get("match_mode") or ""),
                "row_type": str(candidate.row.get("row_type") or ""),
                "fact_class": str(candidate.row.get("fact_class") or ""),
                "matched_alias": str(candidate.row.get("matched_alias") or ""),
                "entity_resolution_source": str(candidate.row.get("entity_resolution_source") or ""),
                "entity_resolution_reason": str(candidate.row.get("entity_resolution_reason") or ""),
                "entity_resolution_confidence": float(candidate.row.get("entity_resolution_confidence") or 0.0),
                "entity_resolution_merge_eligible": bool(candidate.row.get("entity_resolution_merge_eligible")),
                "graph_backend_status": str(candidate.row.get("graph_backend_status") or ""),
                "graph_backend_requested": str(candidate.row.get("graph_backend_requested") or ""),
                "graph_fallback_reason": str(candidate.row.get("graph_fallback_reason") or ""),
                "query_token_overlap": int(candidate.row.get("_brainstack_query_token_overlap") or 0),
                "query_token_count": int(candidate.row.get("_brainstack_query_token_count") or 0),
                "same_session": bool(candidate.row.get("same_session")),
                "recap_surface": bool(candidate.row.get("_brainstack_recap_surface")),
                "supporting_evidence_only": bool(candidate.row.get("_brainstack_supporting_evidence_only")),
                "runtime_state_only": bool(candidate.row.get("_brainstack_runtime_state_only")),
                "workstream_recap_reason": str(candidate.row.get("_brainstack_workstream_recap_reason") or ""),
                "operating_authority_level": str(
                    (candidate.row.get("metadata") or {}).get("authority_level")
                    if isinstance(candidate.row.get("metadata"), dict)
                    else ""
                ),
                "operating_owner_role": str(
                    (candidate.row.get("metadata") or {}).get("owner_role")
                    if isinstance(candidate.row.get("metadata"), dict)
                    else ""
                ),
                "workstream_id": str(
                    (candidate.row.get("metadata") or {}).get("workstream_id")
                    if isinstance(candidate.row.get("metadata"), dict)
                    else ""
                ),
                "suppression_reason": str(candidate.row.get("_brainstack_suppression_reason") or ""),
                "content_excerpt": _candidate_text(candidate)[:220],
            }
            for candidate in fused
        ],
        "decomposition": {
            "used": False,
            "queries": list(search_queries),
            "legacy_disabled": True,
        },
        "entity_resolution": entity_resolution,
        "lookup_semantics": lookup_semantics,
        "associative_expansion": {
            key: value
            for key, value in associative_expansion.items()
            if key != "candidate_rows"
        },
        "routing": asdict(route),
    }
