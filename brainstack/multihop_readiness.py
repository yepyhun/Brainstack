from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from .graphiti_projection import project_canonical_events_to_graphiti

MULTIHOP_READINESS_SCHEMA_VERSION = "brainstack.multihop_readiness.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: Any, *, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _trace_hook(edge: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "path_trace_id": _hash(
            [
                edge.get("edge_id"),
                edge.get("event_id"),
                edge.get("source_event_id"),
                edge.get("source_span_id"),
            ]
        ),
        "edge_id": _text(edge.get("edge_id")),
        "event_id": _text(edge.get("event_id")),
        "source_event_id": _text(edge.get("source_event_id")),
        "source_span_id": _text(edge.get("source_span_id")),
    }


def _readiness_edge(edge: Mapping[str, Any], *, traversal_allowed: bool, reason_code: str) -> dict[str, Any]:
    return {
        "relation_id": _text(edge.get("edge_id")),
        "stable_fact_id": _text(edge.get("stable_fact_id")),
        "subject_ref": _text(edge.get("subject_ref")),
        "predicate": _text(edge.get("predicate")),
        "object_ref": _text(edge.get("object_ref")),
        "direction": "subject_to_object",
        "source_event_id": _text(edge.get("source_event_id")),
        "source_span_id": _text(edge.get("source_span_id")),
        "source_quote_hash": _text(edge.get("source_quote_hash")),
        "scope": dict(edge.get("scope") if isinstance(edge.get("scope"), Mapping) else {}),
        "valid_from": _text(edge.get("valid_from")),
        "valid_to": _text(edge.get("valid_to")),
        "truth_eligible": bool(edge.get("truth_eligible")),
        "support_visibility": _text(edge.get("support_visibility")),
        "conflicted": bool(edge.get("conflicted")),
        "traversal_allowed": traversal_allowed,
        "reason_code": reason_code,
        "retrieval_trace": _trace_hook(edge),
    }


def build_multihop_readiness_projection(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    graph = project_canonical_events_to_graphiti(events)
    counters = {
        "graph_projection_failed": 0,
        "missing_relation_id": 0,
        "missing_source_path": 0,
        "missing_scope": 0,
        "missing_temporal_validity": 0,
        "support_only_traversable": 0,
        "conflict_traversable": 0,
        "summary_only_traversable": 0,
    }
    traversal_edges: list[dict[str, Any]] = []
    blocked_edges: list[dict[str, Any]] = []

    if graph.get("status") != "pass":
        counters["graph_projection_failed"] += 1

    for edge in graph.get("current_edges", []):
        readiness = _readiness_edge(edge, traversal_allowed=True, reason_code="TRAVERSABLE_TRUTH_EDGE")
        traversal_edges.append(readiness)

    for edge in [*graph.get("prior_edges", []), *graph.get("inspect_only_edges", [])]:
        reason = "BLOCKED_NON_CURRENT_OR_INSPECT_ONLY"
        if edge.get("conflicted"):
            reason = "BLOCKED_CONFLICT_OR_CONTRADICTION"
        elif edge.get("support_visibility") != "answer_evidence":
            reason = "BLOCKED_NOT_ANSWER_EVIDENCE"
        blocked_edges.append(_readiness_edge(edge, traversal_allowed=False, reason_code=reason))

    for edge in [*traversal_edges, *blocked_edges]:
        if not edge["relation_id"]:
            counters["missing_relation_id"] += 1
        if not edge["source_event_id"] or not edge["source_span_id"] or not edge["source_quote_hash"]:
            counters["missing_source_path"] += 1
        if not edge["scope"].get("principal_scope_key"):
            counters["missing_scope"] += 1
        if not edge["valid_from"]:
            counters["missing_temporal_validity"] += 1
        if edge["traversal_allowed"] and edge["support_visibility"] != "answer_evidence":
            counters["support_only_traversable"] += 1
        if edge["traversal_allowed"] and edge["conflicted"]:
            counters["conflict_traversable"] += 1
        if edge["traversal_allowed"] and (not edge["subject_ref"] or not edge["predicate"] or not edge["object_ref"]):
            counters["summary_only_traversable"] += 1

    status = "pass" if sum(counters.values()) == 0 else "fail"
    return {
        "schema": MULTIHOP_READINESS_SCHEMA_VERSION,
        "status": status,
        "future_engine_readiness": {
            "catrag_query_aware_traversal_ready": status == "pass",
            "hipporag_personalized_pagerank_ready": status == "pass",
            "engine_implementation_recommended_now": False,
            "reason": "readiness metadata is present; no measured retrieval weakness requires engine work yet",
        },
        "critical_counters": counters,
        "traversal_edges": sorted(traversal_edges, key=lambda item: item["relation_id"]),
        "blocked_edges": sorted(blocked_edges, key=lambda item: item["relation_id"]),
        "graph_projection_status": graph.get("status"),
    }
