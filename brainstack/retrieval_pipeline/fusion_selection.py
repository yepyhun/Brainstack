from __future__ import annotations

from .runtime import (
    Any,
    BrainstackStore,
    Dict,
    EvidenceCandidate,
    List,
    Mapping,
    ROUTE_AGGREGATE,
    ROUTE_FACT,
    ROUTE_TEMPORAL,
    _candidate_key,
    _fact_sort_key,
    _fact_transcript_rows,
    _has_meaningful_transcript_signal,
    _keep_temporal_transcript_rows_with_anchor_support,
    _merge_channel,
    _route_has_support,
    _select_aggregate_rows,
    _select_rows,
    _select_temporal_rows,
)


def merge_retrieval_candidates(rows: Mapping[str, Any]) -> List[EvidenceCandidate]:
    semantic_channels = rows["semantic_channels"]
    operating_channels = rows["operating_channels"]
    graph_channels = rows["graph_channels"]
    temporal_channels = rows["temporal_channels"]
    merged: Dict[str, EvidenceCandidate] = {}
    _merge_channel(merged, channel_name="keyword", rows=rows["keyword_profile_rows"], shelf="profile")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["profile"], shelf="profile")
    _merge_channel(merged, channel_name="operating", rows=operating_channels["keyword"], shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=operating_channels["recent_work"], shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=operating_channels["current"], shelf="operating")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["operating"], shelf="operating")
    _merge_channel(merged, channel_name="keyword", rows=rows["keyword_continuity_rows"], shelf="continuity_match")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["continuity"], shelf="continuity_match")
    _merge_channel(merged, channel_name="keyword", rows=rows["keyword_transcript_rows"], shelf="transcript")
    _merge_channel(merged, channel_name="keyword", rows=rows["keyword_corpus_rows"], shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["conversation"], shelf="transcript")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["corpus"], shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["index_corpus"], shelf="corpus")
    _merge_channel(merged, channel_name="graph", rows=graph_channels["graph_rows"], shelf="graph")
    _merge_channel(merged, channel_name="semantic", rows=semantic_channels["graph"], shelf="graph")
    _merge_channel(merged, channel_name="associative", rows=graph_channels["associative_graph_rows"], shelf="graph")
    _merge_channel(merged, channel_name="temporal", rows=temporal_channels["continuity"], shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=temporal_channels["recent"], shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=temporal_channels["transcript"], shelf="transcript")
    _merge_channel(merged, channel_name="temporal", rows=temporal_channels["graph"], shelf="graph")
    return sorted(merged.values(), key=_fact_sort_key, reverse=True)


def select_route_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    route: Any,
    limits: Dict[str, int],
    evidence_item_budget: int,
    rows: Mapping[str, Any],
    fused: List[EvidenceCandidate],
) -> Dict[str, Any]:
    fact_selected = _select_rows(
        fused,
        query=query,
        profile_limit=limits["profile_limit"],
        continuity_match_limit=limits["continuity_match_limit"],
        continuity_recent_limit=limits["continuity_recent_limit"],
        transcript_limit=limits["transcript_limit"],
        operating_limit=limits["operating_limit"],
        graph_limit=limits["graph_limit"],
        corpus_limit=limits["corpus_limit"],
        evidence_item_budget=evidence_item_budget,
    )
    fact_selected["transcript_rows"] = _fact_transcript_rows(
        store=store,
        current_session_id=session_id,
        fused_transcript_rows=[candidate.row for candidate in fused if candidate.shelf == "transcript"],
        keyword_transcript_rows=rows["keyword_transcript_rows"],
        semantic_conversation_rows=rows["semantic_channels"]["conversation"],
        matched_rows=fact_selected["matched"],
        limit=limits["transcript_limit"],
    )
    fact_selected["transcript_rows"] = [
        row for row in fact_selected["transcript_rows"] if not str(row.get("_brainstack_suppression_reason") or "")
    ]
    selected = fact_selected
    if route.applied_mode == ROUTE_TEMPORAL:
        selected = _select_temporal_rows(
            keyword_continuity_rows=rows["keyword_continuity_rows"],
            recent_rows=rows["temporal_channels"]["recent"],
            temporal_continuity_rows=rows["temporal_channels"]["continuity"],
            temporal_transcript_rows=rows["temporal_channels"]["transcript"],
            graph_rows=rows["temporal_channels"]["graph"],
            limits=limits,
        )
    elif route.applied_mode == ROUTE_AGGREGATE:
        selected = _select_aggregate_rows(
            native_aggregate_rows=rows["native_aggregate_rows"],
            keyword_continuity_rows=rows["keyword_continuity_rows"],
            keyword_transcript_rows=rows["keyword_transcript_rows"],
            semantic_conversation_rows=rows["semantic_channels"]["conversation"],
            keyword_corpus_rows=rows["keyword_corpus_rows"],
            semantic_corpus_rows=rows["semantic_channels"]["corpus"],
            graph_rows=rows["graph_channels"]["graph_rows"],
            limits=limits,
        )
    if selected["transcript_rows"] and not _has_meaningful_transcript_signal(selected["transcript_rows"]):
        if route.applied_mode != ROUTE_TEMPORAL or not _keep_temporal_transcript_rows_with_anchor_support(selected):
            selected["transcript_rows"] = []
    if route.applied_mode != ROUTE_FACT and not _route_has_support(route, selected):
        route.fallback_used = True
        route.applied_mode = ROUTE_FACT
        selected = fact_selected
    return selected


def selected_candidate_keys(selected: Mapping[str, Any]) -> set[str]:
    return {
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
