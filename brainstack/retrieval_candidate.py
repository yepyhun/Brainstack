from __future__ import annotations

import hashlib
from typing import Any, Mapping, Sequence


CANDIDATE_SCHEMA = "brainstack.retrieval_candidate.v1"
TRACE_SCHEMA = "brainstack.retrieval_candidate_trace.v1"

_HINDSIGHT_SHELVES = {
    "profile",
    "task",
    "operating",
    "continuity_match",
    "continuity_recent",
    "transcript",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _candidate_id(*, shelf: str, evidence_key: str) -> str:
    # ID is stable and redaction-safe: it hashes structural identity, not row text.
    payload = f"{CANDIDATE_SCHEMA}|{shelf}|{evidence_key}".encode("utf-8", "surrogatepass")
    return hashlib.sha256(payload).hexdigest()[:24]


def _channels(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("channels")
    if raw is None:
        raw = row.get("_brainstack_channels")
    if isinstance(raw, (list, tuple)):
        return sorted({_text(item) for item in raw if _text(item)})
    ranks = row.get("channel_ranks")
    if ranks is None:
        ranks = row.get("_brainstack_channel_ranks")
    if isinstance(ranks, Mapping):
        return sorted({_text(key) for key in ranks if _text(key)})
    return []


def _channel_ranks(row: Mapping[str, Any]) -> dict[str, int]:
    raw = row.get("channel_ranks")
    if raw is None:
        raw = row.get("_brainstack_channel_ranks")
    if not isinstance(raw, Mapping):
        return {}
    return {_text(key): _integer(value) for key, value in raw.items() if _text(key)}


def _cost(row: Mapping[str, Any]) -> dict[str, int]:
    excerpt = _text(row.get("excerpt") or row.get("content_excerpt"))
    char_count = len(excerpt)
    return {
        "preview_char_count": char_count,
        "preview_token_estimate": max(1, char_count // 4) if char_count else 0,
    }


def _brainstack_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {
        "row_type": _text(row.get("row_type")),
        "record_type": _text(row.get("record_type")),
        "stable_key": _text(row.get("stable_key")),
        "source_kind": _text(row.get("source_kind")),
    }
    return {key: value for key, value in metadata.items() if value}


def _graphiti_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {
        "fact_class": _text(row.get("fact_class")),
        "matched_alias": _text(row.get("matched_alias")),
        "entity_resolution_source": _text(row.get("entity_resolution_source")),
        "entity_resolution_reason": _text(row.get("entity_resolution_reason")),
        "entity_resolution_confidence": _number(row.get("entity_resolution_confidence")),
        "entity_resolution_merge_eligible": bool(row.get("entity_resolution_merge_eligible")),
        "graph_backend_requested": _text(row.get("graph_backend_requested")),
        "graph_backend_status": _text(row.get("graph_backend_status")),
        "graph_fallback_reason": _text(row.get("graph_fallback_reason")),
        "graph_authority_status": _text(row.get("graph_authority_status")),
    }
    lineage = row.get("graph_source_lineage")
    if isinstance(lineage, Mapping) and lineage:
        metadata["graph_source_lineage"] = dict(lineage)
    return {key: value for key, value in metadata.items() if value not in ("", 0.0, False)}


def _hindsight_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata = {
        "happened_at": _text(row.get("happened_at")),
        "valid_to": _text(row.get("valid_to")),
        "same_session": bool(row.get("same_session")),
        "same_principal": bool(row.get("same_principal")),
        "workstream_id": _text(row.get("workstream_id")),
        "owner_role": _text(row.get("owner_role")),
        "recap_surface": bool(row.get("recap_surface")),
        "supporting_evidence_only": bool(row.get("supporting_evidence_only")),
        "runtime_state_only": bool(row.get("runtime_state_only")),
        "workstream_recap_reason": _text(row.get("workstream_recap_reason")),
    }
    return {key: value for key, value in metadata.items() if value not in ("", False)}


def _mempalace_metadata(row: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "citation_id": _text(row.get("citation_id")),
        "document_hash": _text(row.get("document_hash")),
        "section_hash": _text(row.get("section_hash")),
        "source_display_id": _text(row.get("source_display_id")),
        "public_source_uri": _text(row.get("public_source_uri")),
    }
    taxonomy = row.get("corpus_taxonomy")
    if isinstance(taxonomy, Mapping) and taxonomy:
        metadata["corpus_taxonomy"] = dict(taxonomy)
    trace = row.get("corpus_retrieval_trace")
    if isinstance(trace, Mapping) and trace:
        metadata["corpus_retrieval_trace"] = dict(trace)
    return {key: value for key, value in metadata.items() if value}


def _donor_metadata(shelf: str, row: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {"brainstack": _brainstack_metadata(row)}
    if shelf == "graph":
        metadata["graphiti"] = _graphiti_metadata(row)
    if shelf == "corpus":
        metadata["mempalace"] = _mempalace_metadata(row)
    if shelf in _HINDSIGHT_SHELVES:
        metadata["hindsight"] = _hindsight_metadata(row)
    return {key: value for key, value in metadata.items() if value}


def project_retrieval_candidate(
    row: Mapping[str, Any],
    *,
    shelf: str,
    evidence_key: str,
    selection_status: str,
    selection_reason: str,
) -> dict[str, Any]:
    """Project existing inspect rows into typed candidate metadata without changing recall."""
    normalized_shelf = _text(shelf)
    normalized_key = _text(evidence_key)
    reason = _text(selection_reason)
    return {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": _candidate_id(shelf=normalized_shelf, evidence_key=normalized_key),
        "evidence_key": normalized_key,
        "shelf": normalized_shelf,
        "selection": {
            "status": _text(selection_status),
            "reason": reason,
            "suppression_reason": _text(row.get("suppression_reason")) if selection_status != "selected" else "",
        },
        "source": {
            "retrieval_source": _text(row.get("retrieval_source")),
            "match_mode": _text(row.get("match_mode")),
            "channels": _channels(row),
            "channel_ranks": _channel_ranks(row),
        },
        "authority": {
            "floor": _integer(row.get("authority_floor")),
            "floor_applied": bool(row.get("authority_floor_applied")),
            "level": _text(row.get("authority_level") or row.get("operating_authority_level")),
        },
        "score": {
            "rrf": _number(row.get("rrf_score")),
            "keyword": _number(row.get("keyword_score")),
            "semantic": _number(row.get("semantic_score")),
            "query_token_overlap": _integer(row.get("query_token_overlap")),
            "query_token_count": _integer(row.get("query_token_count")),
        },
        "cost": _cost(row),
        "modality": {
            "primary": "text",
            "metadata_ready": True,
        },
        "donor_metadata": _donor_metadata(normalized_shelf, row),
    }


def build_candidate_trace(
    *,
    selected_by_shelf: Mapping[str, Sequence[Mapping[str, Any]]],
    suppressed_rows: Sequence[Mapping[str, Any]],
    suppressed_limit: int = 40,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    for shelf, rows in selected_by_shelf.items():
        for row in rows:
            evidence_key = _text(row.get("evidence_key"))
            if not evidence_key:
                continue
            selected.append(
                project_retrieval_candidate(
                    row,
                    shelf=shelf,
                    evidence_key=evidence_key,
                    selection_status="selected",
                    selection_reason=_text(row.get("selection_reason")) or "selected_by_final_packet",
                )
            )

    bounded_suppressed = list(suppressed_rows)[: max(0, int(suppressed_limit))]
    suppressed: list[dict[str, Any]] = []
    for row in bounded_suppressed:
        shelf = _text(row.get("shelf"))
        evidence_key = _text(row.get("evidence_key"))
        if not shelf or not evidence_key:
            continue
        suppressed.append(
            project_retrieval_candidate(
                row,
                shelf=shelf,
                evidence_key=evidence_key,
                selection_status="suppressed",
                selection_reason=_text(row.get("selection_reason"))
                or _text(row.get("reason"))
                or "not_selected",
            )
        )

    return {
        "schema": TRACE_SCHEMA,
        "mode": "shadow_read_only",
        "selected_count": len(selected),
        "suppressed_count": len(suppressed),
        "suppressed_limit": max(0, int(suppressed_limit)),
        "selected": selected,
        "suppressed": suppressed,
    }
