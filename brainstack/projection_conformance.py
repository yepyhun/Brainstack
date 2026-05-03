"""Cross-surface projection semantics conformance proof.

The conformance layer is read-only: it runs existing projection/read paths and
checks that they agree on shared safety semantics. It never writes durable
memory, retrieves new evidence, calls a model, or assembles a final answer.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .graphiti_projection import project_canonical_events_to_graphiti
from .mempalace_budget_projection import project_canonical_events_to_mempalace_budget
from .multihop_readiness import build_multihop_readiness_projection
from .projection_semantics import ProjectionSemanticsDecision, classify_projection_semantics
from .core.packet_budget import PacketBudgetPolicy, apply_packet_budget, validate_packet_budget_trace
from .core.reason_codes import ReasonCode
from .core.trace import (
    AUTHORITY_INSPECT_ONLY,
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_SUPPORT_ONLY,
    DECISION_DROPPED,
    DECISION_SELECTED,
    make_evidence_candidate,
)

PROJECTION_CONFORMANCE_SCHEMA_VERSION = "brainstack.projection_conformance.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _event_id(event: Mapping[str, Any]) -> str:
    return _text(_mapping(event.get("event")).get("event_id"))


def _claim(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(event.get("claim"))


def _source(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(event.get("source"))


def _authority(event: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(event.get("authority"))


def _candidate_authority(decision: ProjectionSemanticsDecision) -> str:
    if decision.is_answer_safe:
        return AUTHORITY_RECEIPT_BACKED
    if decision.is_support_only:
        return AUTHORITY_SUPPORT_ONLY
    return AUTHORITY_INSPECT_ONLY


def _candidate_reason(decision: ProjectionSemanticsDecision) -> str:
    if decision.is_answer_safe:
        return ReasonCode.SELECTED_RECEIPT_BACKED_FACT.value
    if decision.is_support_only:
        return ReasonCode.DROPPED_BUDGET_SUPPORT_ONLY.value
    return ReasonCode.DROPPED_BUDGET_LOW_AUTHORITY.value


def _packet_candidate_from_event(event: Mapping[str, Any], decision: ProjectionSemanticsDecision) -> dict[str, Any]:
    claim = _claim(event)
    source = _source(event)
    authority = _authority(event)
    candidate = make_evidence_candidate(
        candidate_id=decision.event_id,
        shelf=_text(claim.get("memory_kind")) or "support_only",
        target_slot=_text(claim.get("target_slot")),
        source_role=_text(source.get("speaker")) or "user",
        authority=_candidate_authority(decision),
        decision=DECISION_SELECTED if decision.is_answer_safe else DECISION_DROPPED,
        reason_code=_candidate_reason(decision),
        source_event_id=decision.source_event_id,
        source_span_id=decision.source_span_id,
        proposal_id=_text(authority.get("admission_decision_id")),
        admission_id=_text(authority.get("admission_decision_id")),
        receipt_id=decision.receipt_id or None,
        truth_eligible=decision.is_answer_safe,
        model_facing_allowed=decision.is_answer_safe,
        answer_evidence_allowed=decision.is_answer_safe,
        raw_value=_text(claim.get("normalized_value_hash")) or decision.stable_fact_id,
        token_estimate=18 if decision.is_answer_safe and decision.is_authority_critical else 10,
    )
    candidate["event_id"] = decision.event_id
    candidate["projection_reason_codes"] = [reason.value for reason in decision.reason_codes]
    candidate["projection_semantics"] = decision.to_public_dict()
    return candidate


def _index_by_event(items: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    indexed: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        event_id = _text(item.get("event_id"))
        if event_id:
            indexed.setdefault(event_id, []).append(item)
    return indexed


def _issue(event_id: str, surface: str, code: str, detail: str = "") -> dict[str, str]:
    return {
        "event_id": event_id,
        "surface": surface,
        "code": code,
        "detail": detail,
    }


def _contains_forbidden_raw_text(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return any(marker in payload for marker in ("private source text", '"raw_text"', '"raw_private_text"', '"packet_text"'))


def build_projection_conformance_report(
    events: Iterable[Mapping[str, Any]],
    *,
    max_active_tokens: int = 24,
    max_packet_tokens: int = 12,
) -> dict[str, Any]:
    """Run graph/budget/multi-hop/packet paths and check shared semantics.

    The returned report is public-safe: it contains IDs, hashes, counters, flags,
    and reason codes only.
    """

    canonical_events = [dict(event) for event in events]
    semantics_by_event = {
        _event_id(event): classify_projection_semantics(event)
        for event in canonical_events
        if _event_id(event)
    }
    graph = project_canonical_events_to_graphiti(canonical_events)
    budget = project_canonical_events_to_mempalace_budget(canonical_events, max_active_tokens=max_active_tokens)
    multihop = build_multihop_readiness_projection(canonical_events)
    packet_candidates = [
        _packet_candidate_from_event(event, semantics_by_event[_event_id(event)])
        for event in canonical_events
        if _event_id(event) in semantics_by_event
    ]
    packet_result = apply_packet_budget(packet_candidates, PacketBudgetPolicy(max_candidate_tokens=max_packet_tokens))
    packet_trace = {
        "candidates": packet_result.candidates,
        "packet_budget": packet_result.to_trace_packet_budget(),
    }

    graph_edges = _index_by_event(
        [
            *graph.get("current_edges", []),
            *graph.get("prior_edges", []),
            *graph.get("inspect_only_edges", []),
        ]
    )
    budget_cards = _index_by_event(
        [
            *budget.get("active_cards", []),
            *budget.get("retrieval_only", []),
            *budget.get("support_only", []),
            *budget.get("archived", []),
        ]
    )
    traversal_edges = _index_by_event(multihop.get("traversal_edges", []))
    blocked_edges = _index_by_event(multihop.get("blocked_edges", []))
    packet_items = _index_by_event(packet_result.candidates)

    issues: list[dict[str, str]] = []
    for surface, output in (("graph", graph), ("budget", budget), ("multihop", multihop)):
        if output.get("status") != "pass":
            issues.append(_issue("", surface, "surface_status_failed", _text(output.get("status"))))
    for event_id, semantics in semantics_by_event.items():
        for edge in graph_edges.get(event_id, []):
            if bool(edge.get("answerable")) != semantics.is_answer_safe:
                issues.append(
                    _issue(
                        event_id,
                        "graph",
                        "graph_answerability_mismatch",
                        f"answerable={bool(edge.get('answerable'))} shared={semantics.is_answer_safe}",
                    )
                )
            if bool(edge.get("answerable")) and not semantics.is_answer_safe:
                issues.append(_issue(event_id, "graph", "unsafe_graph_answerable"))
        if not semantics.is_answer_safe:
            for edge in traversal_edges.get(event_id, []):
                if bool(edge.get("traversal_allowed")):
                    issues.append(_issue(event_id, "multihop", "unsafe_traversal_allowed"))
        for card in budget_cards.get(event_id, []):
            if bool(card.get("answer_safe")) != semantics.is_answer_safe:
                issues.append(
                    _issue(
                        event_id,
                        "budget",
                        "budget_answer_safety_mismatch",
                        f"answer_safe={bool(card.get('answer_safe'))} shared={semantics.is_answer_safe}",
                    )
                )
            if bool(card.get("answer_safe")) and not semantics.is_answer_safe:
                issues.append(_issue(event_id, "budget", "unsafe_budget_answer_safe"))
        for candidate in packet_items.get(event_id, []):
            selected = _text(candidate.get("decision")) == "selected"
            if selected and not semantics.is_answer_safe:
                issues.append(_issue(event_id, "packet", "unsafe_packet_selected"))
            if (
                semantics.is_authority_critical
                and semantics.is_answer_safe
                and _text(candidate.get("decision")) == "dropped"
            ):
                issues.append(_issue(event_id, "packet", "authority_critical_dropped"))
        if semantics.is_answer_safe and not packet_items.get(event_id):
            issues.append(_issue(event_id, "packet", "answer_safe_missing_packet_candidate"))
        if not semantics.is_answer_safe and not (graph_edges.get(event_id) or blocked_edges.get(event_id) or budget_cards.get(event_id) or packet_items.get(event_id)):
            issues.append(_issue(event_id, "conformance", "unsafe_event_unobserved"))

    for error in validate_packet_budget_trace(packet_trace):
        issues.append(_issue("", "packet", error))

    report = {
        "schema": PROJECTION_CONFORMANCE_SCHEMA_VERSION,
        "status": "pass",
        "surface_status": {
            "graph": graph.get("status"),
            "budget": budget.get("status"),
            "multihop": multihop.get("status"),
            "packet_budget": packet_result.status,
            "packet_fail_closed": packet_result.fail_closed,
        },
        "critical_counters": {
            "graph_unsafe_answerable": sum(1 for issue in issues if issue["code"] == "unsafe_graph_answerable"),
            "multihop_unsafe_traversal": sum(1 for issue in issues if issue["code"] == "unsafe_traversal_allowed"),
            "budget_unsafe_answer_safe": sum(1 for issue in issues if issue["code"] == "unsafe_budget_answer_safe"),
            "packet_unsafe_selected": sum(1 for issue in issues if issue["code"] == "unsafe_packet_selected"),
            "packet_authority_critical_dropped": sum(1 for issue in issues if issue["code"] == "authority_critical_dropped"),
            "raw_text_in_report": 0,
        },
        "event_semantics": [
            semantics_by_event[event_id].to_public_dict()
            for event_id in sorted(semantics_by_event)
        ],
        "graph": {
            "current_edge_ids": [_text(edge.get("event_id")) for edge in graph.get("current_edges", [])],
            "prior_edge_ids": [_text(edge.get("event_id")) for edge in graph.get("prior_edges", [])],
            "inspect_only_edge_ids": [_text(edge.get("event_id")) for edge in graph.get("inspect_only_edges", [])],
            "critical_counters": dict(_mapping(graph.get("critical_counters"))),
        },
        "budget": {
            "active_event_ids": [_text(card.get("event_id")) for card in budget.get("active_cards", [])],
            "retrieval_only_event_ids": [_text(card.get("event_id")) for card in budget.get("retrieval_only", [])],
            "support_only_event_ids": [_text(card.get("event_id")) for card in budget.get("support_only", [])],
            "archived_event_ids": [_text(card.get("event_id")) for card in budget.get("archived", [])],
            "fail_closed": bool(budget.get("fail_closed")),
            "critical_counters": dict(_mapping(budget.get("critical_counters"))),
        },
        "multihop": {
            "traversal_event_ids": [_text(edge.get("event_id")) for edge in multihop.get("traversal_edges", [])],
            "blocked_event_ids": [_text(edge.get("event_id")) for edge in multihop.get("blocked_edges", [])],
            "critical_counters": dict(_mapping(multihop.get("critical_counters"))),
        },
        "packet": {
            "selected_event_ids": [
                _text(item.get("event_id"))
                for item in packet_result.candidates
                if _text(item.get("decision")) == "selected"
            ],
            "dropped_event_ids": [
                _text(item.get("event_id"))
                for item in packet_result.candidates
                if _text(item.get("decision")) == "dropped"
            ],
            "packet_budget": packet_result.to_trace_packet_budget(),
        },
        "issues": issues,
    }
    if _contains_forbidden_raw_text(report):
        report["critical_counters"]["raw_text_in_report"] = 1
        report["issues"].append(_issue("", "conformance", "raw_text_in_report"))
    if report["issues"]:
        report["status"] = "fail"
    return report
