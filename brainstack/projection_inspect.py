"""Public-safe projection inspect/doctor explanations.

This module renders the shared projection semantics and cross-surface conformance
report into agent-facing explanations. It is read-only and deliberately avoids
raw memory payloads.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from .projection_conformance import build_projection_conformance_report

PROJECTION_INSPECT_SCHEMA_VERSION = "brainstack.projection_inspect.v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ids(report: Mapping[str, Any], surface: str, key: str) -> set[str]:
    section = _mapping(report.get(surface))
    return {_text(item) for item in _list(section.get(key)) if _text(item)}


def _contains_forbidden_raw_text(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return any(marker in payload for marker in ("private source text", '"raw_text"', '"raw_private_text"', '"packet_text"'))


def _semantic_labels(semantics: Mapping[str, Any]) -> list[str]:
    labels: list[str] = []
    if semantics.get("is_current"):
        labels.append("current")
    if semantics.get("is_prior"):
        labels.append("prior")
    if semantics.get("is_conflicted"):
        labels.append("conflicted")
    if semantics.get("is_support_only"):
        labels.append("support-only")
    if semantics.get("is_answer_safe"):
        labels.append("answer-safe")
    if semantics.get("is_retrieval_only"):
        labels.append("retrieval-only")
    if semantics.get("is_hidden"):
        labels.append("hidden")
    if semantics.get("is_authority_critical"):
        labels.append("authority-critical")
    return labels


def _surface_actions(event_id: str, report: Mapping[str, Any]) -> dict[str, str]:
    graph_current = _ids(report, "graph", "current_edge_ids")
    graph_prior = _ids(report, "graph", "prior_edge_ids")
    graph_inspect = _ids(report, "graph", "inspect_only_edge_ids")
    budget_active = _ids(report, "budget", "active_event_ids")
    budget_retrieval = _ids(report, "budget", "retrieval_only_event_ids")
    budget_support = _ids(report, "budget", "support_only_event_ids")
    budget_archived = _ids(report, "budget", "archived_event_ids")
    multihop_traversal = _ids(report, "multihop", "traversal_event_ids")
    multihop_blocked = _ids(report, "multihop", "blocked_event_ids")
    packet_selected = _ids(report, "packet", "selected_event_ids")
    packet_dropped = _ids(report, "packet", "dropped_event_ids")

    graph_action = "not_projected"
    if event_id in graph_current:
        graph_action = "answerable_current_edge"
    elif event_id in graph_prior:
        graph_action = "prior_edge"
    elif event_id in graph_inspect:
        graph_action = "inspect_only_edge"

    budget_action = "not_projected"
    if event_id in budget_active:
        budget_action = "active"
    elif event_id in budget_retrieval:
        budget_action = "retrieval_only"
    elif event_id in budget_support:
        budget_action = "support_only"
    elif event_id in budget_archived:
        budget_action = "archived"

    multihop_action = "not_projected"
    if event_id in multihop_traversal:
        multihop_action = "traversable"
    elif event_id in multihop_blocked:
        multihop_action = "blocked"

    packet_action = "not_projected"
    if event_id in packet_selected:
        packet_action = "selected"
    elif event_id in packet_dropped:
        packet_action = "dropped"

    return {
        "graph": graph_action,
        "budget": budget_action,
        "multihop": multihop_action,
        "packet": packet_action,
    }


def _event_issues(event_id: str, report: Mapping[str, Any]) -> list[dict[str, str]]:
    issues = []
    for issue in _list(report.get("issues")):
        if not isinstance(issue, Mapping):
            continue
        if _text(issue.get("event_id")) == event_id or (not event_id and not _text(issue.get("event_id"))):
            issues.append(
                {
                    "surface": _text(issue.get("surface")),
                    "code": _text(issue.get("code")),
                    "detail": _text(issue.get("detail")),
                }
            )
    return issues


def _explanation_text(semantics: Mapping[str, Any], actions: Mapping[str, str]) -> str:
    event_id = _text(semantics.get("event_id"))
    reason_codes = [_text(reason) for reason in _list(semantics.get("reason_codes")) if _text(reason)]
    if semantics.get("is_answer_safe"):
        base = "Memory is current, source-backed, receipt-backed, non-conflicted answer evidence."
    elif semantics.get("is_hidden"):
        base = "Memory is hidden by policy and cannot be answer truth."
    elif semantics.get("is_conflicted"):
        base = "Memory is conflicted or contradiction-only and cannot be answer truth."
    elif semantics.get("is_prior"):
        base = "Memory is prior/expired/superseded and cannot be current answer truth."
    elif semantics.get("is_support_only"):
        base = "Memory is support-only/background and cannot be answer truth."
    elif semantics.get("is_retrieval_only"):
        base = "Memory is retrieval-only and is not directly answer-safe."
    else:
        base = "Memory is not answer-safe under the shared projection contract."
    if semantics.get("is_authority_critical"):
        base += " Authority-critical evidence must be kept or fail visibly, but this does not upgrade answer safety."
    return (
        f"{event_id}: {base} "
        f"Graph={actions.get('graph')}; budget={actions.get('budget')}; "
        f"multi-hop={actions.get('multihop')}; packet={actions.get('packet')}. "
        f"Reasons={','.join(reason_codes)}."
    )


def build_projection_inspect_report(
    events: Iterable[Mapping[str, Any]] | None = None,
    *,
    conformance_report: Mapping[str, Any] | None = None,
    max_active_tokens: int = 24,
    max_packet_tokens: int = 12,
) -> dict[str, Any]:
    """Build a public-safe inspect report from events or an existing conformance report."""

    report = dict(conformance_report or {})
    if not report:
        report = build_projection_conformance_report(
            list(events or []),
            max_active_tokens=max_active_tokens,
            max_packet_tokens=max_packet_tokens,
        )

    event_explanations: list[dict[str, Any]] = []
    for raw_semantics in _list(report.get("event_semantics")):
        if not isinstance(raw_semantics, Mapping):
            continue
        semantics = dict(raw_semantics)
        event_id = _text(semantics.get("event_id"))
        actions = _surface_actions(event_id, report)
        event_explanations.append(
            {
                "event_id": event_id,
                "stable_fact_id": _text(semantics.get("stable_fact_id")),
                "labels": _semantic_labels(semantics),
                "answer_decision": "answer_safe" if semantics.get("is_answer_safe") else "not_answer_safe",
                "surface_actions": actions,
                "reason_codes": [
                    _text(reason)
                    for reason in _list(semantics.get("reason_codes"))
                    if _text(reason)
                ],
                "issues": _event_issues(event_id, report),
                "explanation": _explanation_text(semantics, actions),
            }
        )

    issue_count = len(_list(report.get("issues")))
    conformance_status = _text(report.get("status")) or "unknown"
    verdict = "pass" if conformance_status == "pass" and issue_count == 0 else "needs_attention"
    inspect = {
        "schema": PROJECTION_INSPECT_SCHEMA_VERSION,
        "verdict": verdict,
        "conformance_status": conformance_status,
        "surface_status": dict(_mapping(report.get("surface_status"))),
        "critical_counters": dict(_mapping(report.get("critical_counters"))),
        "terms": {
            "answer_safe": "May be used as answer evidence by read/projection surfaces.",
            "not_answer_safe": "May be inspectable or retrievable, but cannot be answer truth.",
            "support_only": "Background/support context only; cannot become answer truth.",
            "prior": "Old/expired/superseded memory; not current answer truth.",
            "conflicted": "Disputed or contradiction-only memory; blocked from answer truth.",
            "authority_critical": "Evidence that must be preserved or fail visibly; not an answer-safety upgrade.",
            "hidden": "Policy-hidden memory; excluded from answer truth.",
        },
        "event_explanations": event_explanations,
        "issues": [
            {
                "event_id": _text(issue.get("event_id")) if isinstance(issue, Mapping) else "",
                "surface": _text(issue.get("surface")) if isinstance(issue, Mapping) else "",
                "code": _text(issue.get("code")) if isinstance(issue, Mapping) else "",
                "detail": _text(issue.get("detail")) if isinstance(issue, Mapping) else "",
            }
            for issue in _list(report.get("issues"))
            if isinstance(issue, Mapping)
        ],
    }
    if _contains_forbidden_raw_text(inspect):
        inspect["verdict"] = "fail"
        inspect.setdefault("issues", []).append(
            {"event_id": "", "surface": "inspect", "code": "raw_text_in_projection_inspect", "detail": ""}
        )
    return inspect


def build_projection_doctor_section(conformance_report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact doctor-compatible section for projection semantics."""

    inspect = build_projection_inspect_report(conformance_report=conformance_report)
    return {
        "kind": "projection_semantics",
        "status": "active" if inspect.get("verdict") == "pass" else "degraded",
        "verdict": inspect.get("verdict"),
        "conformance_status": inspect.get("conformance_status"),
        "surface_status": dict(_mapping(inspect.get("surface_status"))),
        "critical_counters": dict(_mapping(inspect.get("critical_counters"))),
        "event_count": len(_list(inspect.get("event_explanations"))),
        "issue_count": len(_list(inspect.get("issues"))),
        "reason": "Projection semantics conformance is public-safe and inspectable."
        if inspect.get("verdict") == "pass"
        else "Projection semantics conformance needs attention; inspect issues by event_id/surface/code.",
    }
