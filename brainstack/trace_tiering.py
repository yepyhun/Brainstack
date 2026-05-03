from __future__ import annotations

from typing import Any, Mapping

TRACE_TIERING_SCHEMA = "brainstack.trace_tiering.v1"
COMPACT_QUERY_TRACE_SCHEMA = "brainstack.compact_query_trace.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _count_selected(report: Mapping[str, Any]) -> dict[str, int]:
    selected = _mapping(report.get("selected_evidence"))
    return {str(shelf): len(_sequence(rows)) for shelf, rows in selected.items()}


def build_compact_query_trace(report: Mapping[str, Any]) -> dict[str, Any]:
    """Return a small public-safe trace for hot-path observability.

    The compact trace deliberately keeps reason/status fields while omitting raw
    packet previews, selected evidence bodies, suppressed excerpts, and model-facing
    text. Full inspect reports remain available for debug/probe/release-gate work.
    """

    route_plan = _mapping(report.get("adaptive_route_plan"))
    route_decision = _mapping(route_plan.get("route_decision"))
    final_packet = _mapping(report.get("final_packet"))
    final_policy = _mapping(final_packet.get("policy"))
    packet_budget = _mapping(final_policy.get("packet_budget"))
    current_truth_view = _mapping(report.get("current_truth_view"))
    capability_health = _mapping(report.get("capability_health"))
    return {
        "schema": COMPACT_QUERY_TRACE_SCHEMA,
        "trace_mode": "compact",
        "full_trace_available": True,
        "route_class": route_plan.get("route_class"),
        "escalated_to_tank": route_decision.get("escalated_to_tank"),
        "escalation_reasons": list(route_decision.get("escalation_reasons") or []),
        "selected_counts": _count_selected(report),
        "suppressed_count": len(_sequence(report.get("suppressed_evidence"))),
        "packet_budget": {
            "mode": packet_budget.get("mode"),
            "status": packet_budget.get("status"),
            "max_tokens": packet_budget.get("max_tokens"),
            "selected_candidate_tokens": packet_budget.get("selected_candidate_tokens"),
            "dropped_candidate_tokens": packet_budget.get("dropped_candidate_tokens"),
            "fail_closed": packet_budget.get("fail_closed"),
        },
        "current_truth_view": {
            "status": current_truth_view.get("status"),
            "current_truth_row_count": current_truth_view.get("current_truth_row_count"),
            "non_answerable_row_count": current_truth_view.get("non_answerable_row_count"),
            "freshness_status": _mapping(current_truth_view.get("rebuild")).get("freshness_status"),
        },
        "capability_health": {
            str(name): _mapping(value).get("status")
            for name, value in capability_health.items()
            if isinstance(value, Mapping)
        },
        "final_packet": {
            "char_count": final_packet.get("char_count"),
            "section_count": final_packet.get("section_count"),
            "diagnostic_evidence_count": final_packet.get("diagnostic_evidence_count"),
            "answerable_evidence_count": final_packet.get("answerable_evidence_count"),
        },
    }


def validate_compact_query_trace_public_safety(trace: Mapping[str, Any]) -> list[str]:
    forbidden_keys = {
        "preview",
        "excerpt",
        "content",
        "raw_text",
        "packet_text",
        "model_output",
        "selected_evidence",
        "suppressed_evidence",
    }
    issues: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if str(key).casefold() in forbidden_keys:
                    issues.append(f"forbidden_key:{key}")
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, str):
            lower = value.casefold()
            if "private source text" in lower or "provider_secret" in lower or "api_key" in lower:
                issues.append("forbidden_value")

    walk(trace)
    return sorted(set(issues))
