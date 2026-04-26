from __future__ import annotations

from .runtime import (
    Any,
    BrainstackStore,
    Dict,
    EvidenceCandidate,
    List,
    Mapping,
    _agreement_bonus,
    _candidate_authority_floor,
    _candidate_has_authority_floor,
    _candidate_priority_bonus,
    _candidate_text,
    _channel_status,
)


def semantic_retrieval_status(
    store: BrainstackStore,
    *,
    corpus_limit: int,
    keyword_corpus_rows: List[Dict[str, Any]],
    semantic_channels: Mapping[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    corpus_semantic_status = (
        store.corpus_semantic_channel_status()
        if corpus_limit > 0 or keyword_corpus_rows or semantic_channels["corpus"]
        else {
            "status": "idle",
            "reason": "Corpus semantic retrieval was intentionally skipped for this query shape.",
        }
    )
    semantic_index_status = store.semantic_evidence_channel_status()
    semantic_channel_rows = semantic_channels["conversation"] + semantic_channels["corpus"] + semantic_channels["evidence"]
    reason = (
        f"Derived index: {semantic_index_status.get('reason') or ''} "
        f"Corpus backend: {corpus_semantic_status.get('reason') or ''}"
    ).strip()
    if str(semantic_index_status.get("status") or "") == "degraded":
        return {
            "status": "degraded",
            "reason": str(semantic_index_status.get("reason") or ""),
            "rows": semantic_channel_rows,
        }
    if semantic_channel_rows:
        return {"status": "active", "reason": reason, "rows": semantic_channel_rows}
    return {
        "status": str(corpus_semantic_status.get("status") or semantic_index_status.get("status") or "idle"),
        "reason": reason,
        "rows": semantic_channel_rows,
    }


def retrieval_channel_statuses(
    *,
    context: Mapping[str, Any],
    rows: Mapping[str, Any],
    semantic_status: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    operating_channels = rows["operating_channels"]
    graph_channels = rows["graph_channels"]
    graph_recall_status = graph_channels["graph_recall_status"]
    return [
        _channel_status(
            "task_memory",
            rows["task_rows"],
            reason="structured task truth",
            status="active" if context["task_lookup"] is not None else "idle",
        ),
        _channel_status(
            "operating_truth",
            operating_channels["keyword"] + operating_channels["recent_work"] + operating_channels["current"],
            reason="first-class operating truth",
            status="active" if rows["operating_lookup"] is not None or bool(operating_channels["recent_work"]) else "idle",
        ),
        _channel_status(
            "semantic",
            semantic_status["rows"],
            reason=str(semantic_status.get("reason") or ""),
            status=str(semantic_status.get("status") or "degraded"),
        ),
        _channel_status("keyword", rows["keyword_rows"]),
        _channel_status(
            "graph",
            graph_channels["graph_rows"],
            reason=str(graph_channels["graph_status"].get("reason") or ""),
            status=str(graph_channels["graph_status"].get("status") or "degraded"),
        ),
        _channel_status(
            "graph_recall",
            graph_channels["graph_rows"] + rows["semantic_channels"]["graph"] + graph_channels["associative_graph_rows"],
            reason=f"{graph_recall_status.get('recall_mode')}: {graph_recall_status.get('reason')}",
            status=str(graph_recall_status.get("status") or "idle"),
        ),
        _channel_status(
            "associative_expansion",
            graph_channels["associative_graph_rows"],
            reason=str(graph_channels["associative_expansion"].get("reason") or ""),
            status=str(graph_channels["associative_expansion"].get("status") or "idle"),
        ),
        _channel_status("temporal", rows["temporal_channels"]["merged"]),
    ]


def row_text(row: Mapping[str, Any], key: str) -> str:
    return str(row.get(key) or "")


def row_int(row: Mapping[str, Any], key: str) -> int:
    return int(row.get(key) or 0)


def row_float(row: Mapping[str, Any], key: str) -> float:
    return float(row.get(key) or 0.0)


def row_bool(row: Mapping[str, Any], key: str) -> bool:
    return bool(row.get(key))


def candidate_metadata_text(candidate: EvidenceCandidate, key: str) -> str:
    metadata = candidate.row.get("metadata")
    return str(metadata.get(key) or "") if isinstance(metadata, dict) else ""


def candidate_selection_reason(candidate: EvidenceCandidate, selected_candidate_keys: set[str]) -> str:
    if candidate.key in selected_candidate_keys:
        return "selected_by_fusion_and_budget"
    return row_text(candidate.row, "_brainstack_suppression_reason") or "not_selected_by_route_authority_dedupe_or_budget"


def candidate_payload(candidate: EvidenceCandidate, *, selected_candidate_keys: set[str]) -> Dict[str, Any]:
    row = candidate.row
    return {
        "key": candidate.key,
        "shelf": candidate.shelf,
        "rrf_score": candidate.rrf_score,
        "agreement_bonus": _agreement_bonus(candidate),
        "priority_bonus": _candidate_priority_bonus(candidate),
        "authority_floor": _candidate_authority_floor(candidate),
        "authority_floor_applied": _candidate_has_authority_floor(candidate),
        "channel_ranks": dict(candidate.channel_ranks),
        "selection_status": "selected" if candidate.key in selected_candidate_keys else "not_selected",
        "selection_reason": candidate_selection_reason(candidate, selected_candidate_keys),
        "id": row_int(row, "id"),
        "row_id": row_int(row, "row_id"),
        "turn_number": row_int(row, "turn_number"),
        "document_id": row_int(row, "document_id"),
        "section_index": row_int(row, "section_index"),
        "created_at": row_text(row, "created_at"),
        "keyword_score": row_float(row, "keyword_score"),
        "semantic_score": row_float(row, "semantic_score"),
        "retrieval_source": row_text(row, "retrieval_source"),
        "match_mode": row_text(row, "match_mode"),
        "row_type": row_text(row, "row_type"),
        "fact_class": row_text(row, "fact_class"),
        "matched_alias": row_text(row, "matched_alias"),
        "entity_resolution_source": row_text(row, "entity_resolution_source"),
        "entity_resolution_reason": row_text(row, "entity_resolution_reason"),
        "entity_resolution_confidence": row_float(row, "entity_resolution_confidence"),
        "entity_resolution_merge_eligible": row_bool(row, "entity_resolution_merge_eligible"),
        "graph_backend_status": row_text(row, "graph_backend_status"),
        "graph_backend_requested": row_text(row, "graph_backend_requested"),
        "graph_fallback_reason": row_text(row, "graph_fallback_reason"),
        "query_token_overlap": row_int(row, "_brainstack_query_token_overlap"),
        "query_token_count": row_int(row, "_brainstack_query_token_count"),
        "same_session": row_bool(row, "same_session"),
        "recap_surface": row_bool(row, "_brainstack_recap_surface"),
        "supporting_evidence_only": row_bool(row, "_brainstack_supporting_evidence_only"),
        "runtime_state_only": row_bool(row, "_brainstack_runtime_state_only"),
        "workstream_recap_reason": row_text(row, "_brainstack_workstream_recap_reason"),
        "operating_authority_level": candidate_metadata_text(candidate, "authority_level"),
        "operating_owner_role": candidate_metadata_text(candidate, "owner_role"),
        "workstream_id": candidate_metadata_text(candidate, "workstream_id"),
        "suppression_reason": row_text(row, "_brainstack_suppression_reason"),
        "content_excerpt": _candidate_text(candidate)[:220],
    }


def fused_candidate_payload(
    fused: List[EvidenceCandidate],
    *,
    selected_candidate_keys: set[str],
) -> List[Dict[str, Any]]:
    return [candidate_payload(candidate, selected_candidate_keys=selected_candidate_keys) for candidate in fused]
