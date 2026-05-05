from __future__ import annotations

from typing import Any, Iterable, Mapping

ADAPTIVE_ROUTE_PLAN_SCHEMA_VERSION = "brainstack.adaptive_route_plan.v1"

ROUTE_NO_MEMORY_MINIMAL = "no_memory_minimal"
ROUTE_PROFILE = "profile"
ROUTE_CURRENT_TRUTH = "current_truth"
ROUTE_OPERATING_STATUS = "operating_status"
ROUTE_TEMPORAL_GRAPH = "temporal_graph"
ROUTE_AGGREGATE = "aggregate"
ROUTE_CORPUS = "corpus"
ROUTE_CONTINUITY = "continuity"
ROUTE_DEEP_MIXED = "deep_mixed"

ROUTE_CLASSES = (
    ROUTE_NO_MEMORY_MINIMAL,
    ROUTE_PROFILE,
    ROUTE_CURRENT_TRUTH,
    ROUTE_OPERATING_STATUS,
    ROUTE_TEMPORAL_GRAPH,
    ROUTE_AGGREGATE,
    ROUTE_CORPUS,
    ROUTE_CONTINUITY,
    ROUTE_DEEP_MIXED,
)

SHELVES = (
    "profile",
    "current_truth",
    "graph",
    "aggregate",
    "corpus",
    "continuity",
    "transcript",
    "operating",
    "tank",
)

ROUTE_ALLOWED_SHELVES: dict[str, tuple[str, ...]] = {
    ROUTE_NO_MEMORY_MINIMAL: (),
    ROUTE_PROFILE: ("profile",),
    ROUTE_CURRENT_TRUTH: ("current_truth", "profile"),
    ROUTE_OPERATING_STATUS: ("operating",),
    ROUTE_TEMPORAL_GRAPH: ("graph", "continuity", "transcript"),
    ROUTE_AGGREGATE: ("aggregate", "graph", "corpus", "continuity", "transcript"),
    ROUTE_CORPUS: ("corpus", "current_truth"),
    ROUTE_CONTINUITY: ("continuity", "transcript", "operating"),
    ROUTE_DEEP_MIXED: SHELVES,
}

ROUTE_TO_RETRIEVAL_MODE: dict[str, str] = {
    ROUTE_NO_MEMORY_MINIMAL: "fact",
    ROUTE_PROFILE: "fact",
    ROUTE_CURRENT_TRUTH: "fact",
    ROUTE_OPERATING_STATUS: "fact",
    ROUTE_TEMPORAL_GRAPH: "temporal",
    ROUTE_AGGREGATE: "aggregate",
    ROUTE_CORPUS: "aggregate",
    ROUTE_CONTINUITY: "temporal",
    ROUTE_DEEP_MIXED: "fact",
}

SEMANTIC_EVIDENCE_ENABLED_ROUTES = {
    ROUTE_TEMPORAL_GRAPH,
    ROUTE_AGGREGATE,
    ROUTE_CORPUS,
    ROUTE_CONTINUITY,
    ROUTE_DEEP_MIXED,
}

EVIDENCE_CLASS_TO_SHELF: dict[str, str] = {
    "profile": "profile",
    "current_truth": "current_truth",
    "temporal_graph": "graph",
    "graph": "graph",
    "relation": "graph",
    "conflict": "graph",
    "aggregate": "aggregate",
    "corpus": "corpus",
    "continuity": "continuity",
    "transcript": "transcript",
    "operating": "operating",
    "operating_status": "operating",
    "operating_memory": "operating",
    "deep_mixed": "tank",
}

ESCALATION_SIGNAL_KEYS = (
    "uncertainty",
    "ambiguous",
    "ambiguity",
    "route_broker_disagreement",
    "broker_disagreement",
    "low_candidate_confidence",
    "low_confidence",
    "protected_evidence_risk",
    "protected_truth_risk",
    "candidate_conflict",
)

_PUBLIC_FORBIDDEN_KEYS = {
    "raw_text",
    "raw_private_text",
    "raw_value",
    "secret",
    "provider_secret",
    "provider_api_key",
    "embedding",
    "embedding_vector",
    "prompt",
    "model_output",
    "packet_text",
}


class AdaptiveRoutePlanError(ValueError):
    """Raised for invalid adaptive route planning inputs."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_evidence_class(value: Any) -> str:
    return _text(value).casefold().replace("-", "_").replace(" ", "_")


def _normalized_required_classes(values: Iterable[Any]) -> tuple[str, ...]:
    normalized = [_normalize_evidence_class(value) for value in values]
    return tuple(dict.fromkeys(item for item in normalized if item))


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def _walk_text_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, Mapping):
        for child in value.values():
            values.extend(_walk_text_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_text_values(child))
    elif isinstance(value, str):
        values.append(value)
    return values


def validate_route_plan_public_safety(plan: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in _walk_keys(plan):
        if key.casefold() in _PUBLIC_FORBIDDEN_KEYS:
            issues.append(f"forbidden_public_key:{key}")
    for value in _walk_text_values(plan):
        lower = value.casefold()
        if "private source text" in lower or "provider_secret" in lower or "api_key" in lower:
            issues.append("forbidden_public_value")
    return sorted(set(issues))


def _current_truth_available(current_truth_view: Mapping[str, Any] | None) -> bool:
    view = _mapping(current_truth_view)
    if view.get("status") != "pass":
        return False
    rows = view.get("current_truth_rows")
    return any(isinstance(row, Mapping) and row.get("answerable_current_truth") is True for row in _list(rows))


def _route_from_payload(query_understanding: Mapping[str, Any]) -> str:
    route_payload = _mapping(query_understanding.get("route_payload"))
    requested = _normalize_evidence_class(route_payload.get("route_class") or route_payload.get("mode"))
    if requested in ROUTE_CLASSES:
        return requested
    if requested == "fact":
        return ROUTE_CURRENT_TRUTH if "current_truth" in _normalized_required_classes(query_understanding.get("required_evidence_classes") or []) else ROUTE_PROFILE
    if requested == "temporal":
        return ROUTE_TEMPORAL_GRAPH
    if requested == "style_contract":
        return ROUTE_PROFILE
    if requested == "aggregate":
        return ROUTE_AGGREGATE
    return ""


def _has_deep_mix(required: tuple[str, ...]) -> bool:
    shelves = {EVIDENCE_CLASS_TO_SHELF.get(item, item) for item in required}
    deep_shelves = shelves.intersection({"graph", "corpus", "continuity", "aggregate", "transcript"})
    return len(deep_shelves) >= 2 or "deep_mixed" in required


def _choose_route(
    *,
    query: str,
    query_understanding: Mapping[str, Any],
    required: tuple[str, ...],
    current_truth_available: bool,
) -> tuple[str, list[str]]:
    memory_intent = _normalize_evidence_class(query_understanding.get("memory_intent"))
    if memory_intent in {"none", "no_memory", "minimal"} or (not _text(query) and not required):
        return ROUTE_NO_MEMORY_MINIMAL, ["structured_memory_intent:none"]

    payload_route = _route_from_payload(query_understanding)
    if payload_route:
        return payload_route, ["structured_route_payload"]

    if _has_deep_mix(required):
        return ROUTE_DEEP_MIXED, ["multiple_deep_evidence_classes_required"]
    if any(item in required for item in ("temporal_graph", "graph", "relation", "conflict")):
        return ROUTE_TEMPORAL_GRAPH, ["structured_temporal_or_graph_need"]
    if "aggregate" in required:
        return ROUTE_AGGREGATE, ["structured_aggregate_need"]
    if "corpus" in required:
        return ROUTE_CORPUS, ["structured_corpus_need"]
    if "continuity" in required or "transcript" in required:
        return ROUTE_CONTINUITY, ["structured_continuity_need"]
    if "operating" in required or "operating_status" in required or "operating_memory" in required:
        return ROUTE_OPERATING_STATUS, ["structured_operating_status_need"]
    if "current_truth" in required and current_truth_available:
        return ROUTE_CURRENT_TRUTH, ["fresh_current_truth_view_available"]
    if query_understanding.get("profile_slot_targets") or "profile" in required:
        return ROUTE_PROFILE, ["structured_profile_slot_target"]

    return ROUTE_DEEP_MIXED, ["insufficient_structured_route_signal"]


def _backend_degraded_reasons(
    *,
    route_class: str,
    backend_health: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    allowed = set(ROUTE_ALLOWED_SHELVES[route_class])
    if "graph" in allowed and _text(backend_health.get("graph")).casefold() in {"degraded", "failed", "unavailable"}:
        reasons.append("degraded_graph_backend")
    if "corpus" in allowed and _text(backend_health.get("corpus")).casefold() in {"degraded", "failed", "unavailable"}:
        reasons.append("degraded_corpus_backend")
    return reasons


def _escalation_reasons(
    *,
    query_understanding: Mapping[str, Any],
    route_class: str,
    backend_health: Mapping[str, Any],
    current_truth_view: Mapping[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    for key in ESCALATION_SIGNAL_KEYS:
        if _bool(query_understanding.get(key)):
            reasons.append(key)
    required = _normalized_required_classes(query_understanding.get("required_evidence_classes") or [])
    if _has_deep_mix(required):
        reasons.append("deep_mixed_required")
    if "conflict" in required:
        reasons.append("conflict_requires_tank")
    if "current_truth" in required and not _current_truth_available(current_truth_view):
        reasons.append("current_truth_view_unavailable_or_stale")
    reasons.extend(_backend_degraded_reasons(route_class=route_class, backend_health=backend_health))
    return list(dict.fromkeys(reasons))


def _decision_for_shelf(*, shelf: str, route_class: str, allowed: set[str], escalation_reasons: list[str]) -> dict[str, Any]:
    if shelf in allowed:
        return {
            "shelf": shelf,
            "status": "activated",
            "reason": f"route_class:{route_class}",
        }
    return {
        "shelf": shelf,
        "status": "skipped",
        "reason": "not_required_by_structured_route_signal" if not escalation_reasons else "tank_escalation_handles_depth",
    }


def build_adaptive_route_plan(
    query: str,
    *,
    query_understanding: Mapping[str, Any] | None = None,
    current_truth_view: Mapping[str, Any] | None = None,
    backend_health: Mapping[str, Any] | None = None,
    broker_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan hot/cold retrieval from structured signals without language keyword farms."""

    understanding = dict(query_understanding or {})
    if broker_summary:
        broker = _mapping(broker_summary)
        if broker.get("unsafe_answer_truth_upgrade_count"):
            understanding["broker_disagreement"] = True
        if broker.get("protected_evidence_risk"):
            understanding["protected_evidence_risk"] = True
    backend = dict(backend_health or {})
    required = _normalized_required_classes(understanding.get("required_evidence_classes") or [])
    current_available = _current_truth_available(current_truth_view)
    route_class, route_reasons = _choose_route(
        query=query,
        query_understanding=understanding,
        required=required,
        current_truth_available=current_available,
    )
    escalation_reasons = _escalation_reasons(
        query_understanding=understanding,
        route_class=route_class,
        backend_health=backend,
        current_truth_view=current_truth_view,
    )
    escalated = bool(escalation_reasons) or route_class == ROUTE_DEEP_MIXED
    effective_route_class = ROUTE_DEEP_MIXED if escalated else route_class
    allowed = set(ROUTE_ALLOWED_SHELVES[effective_route_class])
    activated = [shelf for shelf in SHELVES if shelf in allowed]
    skipped = [shelf for shelf in SHELVES if shelf not in allowed]
    shelf_decisions = [
        _decision_for_shelf(
            shelf=shelf,
            route_class=effective_route_class,
            allowed=allowed,
            escalation_reasons=escalation_reasons,
        )
        for shelf in SHELVES
    ]
    semantic_enabled = effective_route_class in SEMANTIC_EVIDENCE_ENABLED_ROUTES
    limit_overrides = route_plan_limit_overrides({"route_class": effective_route_class})
    semantic_limit = max(int(limit_overrides.get("evidence_item_budget") or 0) * 4, 16) if semantic_enabled else 0
    shelf_limits = {
        "profile": int(limit_overrides.get("profile_limit") or 0),
        "current_truth": 0,
        "continuity_match": int(limit_overrides.get("continuity_match_limit") or 0),
        "continuity_recent": int(limit_overrides.get("continuity_recent_limit") or 0),
        "transcript": int(limit_overrides.get("transcript_limit") or 0),
        "operating": int(limit_overrides.get("operating_limit") or 0),
        "graph": int(limit_overrides.get("graph_limit") or 0),
        "corpus": int(limit_overrides.get("corpus_limit") or 0),
        "semantic_evidence": semantic_limit,
    }
    backend_call_budget = {
        "profile": 1 if shelf_limits["profile"] > 0 else 0,
        "continuity": 2 if shelf_limits["continuity_match"] > 0 or shelf_limits["continuity_recent"] > 0 else 0,
        "transcript": 2 if shelf_limits["transcript"] > 0 else 0,
        "operating": 1 if shelf_limits["operating"] > 0 else 0,
        "graph": 2 if shelf_limits["graph"] > 0 else 0,
        "corpus": 2 if shelf_limits["corpus"] > 0 else 0,
        "semantic_evidence": 1 if semantic_enabled else 0,
    }
    plan: dict[str, Any] = {
        "schema": ADAPTIVE_ROUTE_PLAN_SCHEMA_VERSION,
        "status": "pass",
        "route_class": effective_route_class,
        "requested_route_class": route_class,
        "retrieval_mode": ROUTE_TO_RETRIEVAL_MODE[effective_route_class],
        "contract": {
            "structured_signal_routing": True,
            "keyword_farm_routing": False,
            "second_truth_authority": False,
            "current_truth_view_is_read_only_input": True,
            "safe_failure_mode": "over_escalate_to_tank",
        },
        "guardrails": {
            "keyword_sprawl_guard": True,
            "language_specific_keyword_count": 0,
            "multilingual_by_design": True,
            "signal_sources": [
                "structured_query_understanding",
                "current_truth_view",
                "backend_health",
                "broker_summary",
            ],
        },
        "route_decision": {
            "full_depth_escalation_considered": True,
            "escalated_to_tank": escalated,
            "route_reasons": route_reasons,
            "escalation_reasons": escalation_reasons,
            "required_evidence_classes": list(required),
            "retrieval_mode": ROUTE_TO_RETRIEVAL_MODE[effective_route_class],
        },
        "activated_shelves": activated,
        "skipped_shelves": skipped,
        "shelf_decisions": shelf_decisions,
        "semantic_retrieval": {
            "enabled": semantic_enabled,
            "reason": f"route_class:{effective_route_class}"
            if semantic_enabled
            else "not_required_by_structured_route_signal",
            "allowed_shelves": [
                shelf
                for shelf in activated
                if shelf in {"graph", "corpus", "continuity", "transcript", "operating", "tank"}
            ]
            if semantic_enabled
            else [],
            "backend_call_policy": "route_gated",
        },
        "shelf_budget": {
            "applied_before_packet_render_budget": True,
            "shelf_limits": shelf_limits,
            "backend_call_budget": backend_call_budget,
            "backend_call_budget_total": sum(backend_call_budget.values()),
            "latency_budget_ms": 5000 if effective_route_class in {ROUTE_NO_MEMORY_MINIMAL, ROUTE_PROFILE, ROUTE_CURRENT_TRUTH, ROUTE_OPERATING_STATUS} else 10000,
            "protected_truth_policy": "PacketRenderBudget preserves authority-critical selected truth after pre-retrieval limits.",
            "skipped_shelves": skipped,
        },
        "fallback": {
            "fallback_used": bool(escalation_reasons),
            "fallback_mode": "tank" if escalated else "none",
            "degraded_backend_states": backend,
        },
        "current_truth_view": {
            "available": current_available,
            "status": _mapping(current_truth_view).get("status") or "missing",
            "row_count": len(_list(_mapping(current_truth_view).get("current_truth_rows"))),
            "freshness_status": _mapping(_mapping(current_truth_view).get("rebuild")).get("freshness_status"),
        },
        "broker": {
            "used": bool(broker_summary),
            "disagreement": bool(understanding.get("broker_disagreement")),
            "protected_evidence_risk": bool(understanding.get("protected_evidence_risk")),
        },
        "public_safety": {"public_safe": True, "issues": []},
    }
    public_issues = validate_route_plan_public_safety(plan)
    plan["public_safety"] = {"public_safe": not public_issues, "issues": public_issues}
    plan["status"] = "pass" if not public_issues else "fail"
    return plan


def route_plan_limit_overrides(plan: Mapping[str, Any]) -> dict[str, int]:
    route_class = _text(plan.get("route_class")) or ROUTE_DEEP_MIXED
    if route_class == ROUTE_NO_MEMORY_MINIMAL:
        return {
            "profile_limit": 0,
            "continuity_recent_limit": 0,
            "continuity_match_limit": 0,
            "transcript_limit": 0,
            "transcript_char_budget": 0,
            "operating_limit": 0,
            "graph_limit": 0,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 1,
        }
    if route_class == ROUTE_PROFILE:
        return {
            "profile_limit": 4,
            "continuity_recent_limit": 0,
            "continuity_match_limit": 0,
            "transcript_limit": 0,
            "transcript_char_budget": 0,
            "operating_limit": 0,
            "graph_limit": 0,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 4,
        }
    if route_class == ROUTE_CURRENT_TRUTH:
        return {
            "profile_limit": 1,
            "continuity_recent_limit": 0,
            "continuity_match_limit": 0,
            "transcript_limit": 0,
            "transcript_char_budget": 0,
            "operating_limit": 0,
            "graph_limit": 0,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 3,
        }
    if route_class == ROUTE_OPERATING_STATUS:
        return {
            "profile_limit": 0,
            "continuity_recent_limit": 0,
            "continuity_match_limit": 0,
            "transcript_limit": 0,
            "transcript_char_budget": 0,
            "operating_limit": 3,
            "graph_limit": 0,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 3,
        }
    if route_class == ROUTE_TEMPORAL_GRAPH:
        return {
            "profile_limit": 1,
            "continuity_recent_limit": 3,
            "continuity_match_limit": 3,
            "transcript_limit": 3,
            "transcript_char_budget": 720,
            "operating_limit": 1,
            "graph_limit": 4,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 8,
        }
    if route_class == ROUTE_AGGREGATE:
        return {
            "profile_limit": 2,
            "continuity_recent_limit": 3,
            "continuity_match_limit": 4,
            "transcript_limit": 4,
            "transcript_char_budget": 960,
            "operating_limit": 2,
            "graph_limit": 3,
            "corpus_limit": 3,
            "corpus_char_budget": 650,
            "evidence_item_budget": 9,
        }
    if route_class == ROUTE_CORPUS:
        return {
            "profile_limit": 1,
            "continuity_recent_limit": 1,
            "continuity_match_limit": 1,
            "transcript_limit": 1,
            "transcript_char_budget": 320,
            "operating_limit": 0,
            "graph_limit": 0,
            "corpus_limit": 4,
            "corpus_char_budget": 900,
            "evidence_item_budget": 6,
        }
    if route_class == ROUTE_CONTINUITY:
        return {
            "profile_limit": 1,
            "continuity_recent_limit": 4,
            "continuity_match_limit": 4,
            "transcript_limit": 3,
            "transcript_char_budget": 720,
            "operating_limit": 2,
            "graph_limit": 1,
            "corpus_limit": 0,
            "corpus_char_budget": 0,
            "evidence_item_budget": 7,
        }
    return {
        "profile_limit": 4,
        "continuity_recent_limit": 4,
        "continuity_match_limit": 4,
        "transcript_limit": 4,
        "transcript_char_budget": 960,
        "operating_limit": 3,
        "graph_limit": 4,
        "corpus_limit": 4,
        "corpus_char_budget": 900,
        "evidence_item_budget": 10,
    }


def route_plan_resolver_payload(plan: Mapping[str, Any]) -> dict[str, str]:
    return {
        "mode": _text(plan.get("retrieval_mode")) or "fact",
        "reason": "; ".join(_list(_mapping(plan.get("route_decision")).get("route_reasons")))
        or f"adaptive route: {_text(plan.get('route_class'))}",
        "source": "adaptive_route_plan",
    }


def _required_shelves(required: Iterable[Any]) -> set[str]:
    shelves: set[str] = set()
    for item in _normalized_required_classes(required):
        shelves.add(EVIDENCE_CLASS_TO_SHELF.get(item, item))
    shelves.discard("")
    return shelves


def evaluate_tank_shadow_oracle(
    cases: Iterable[Mapping[str, Any]],
    *,
    current_truth_view: Mapping[str, Any] | None = None,
    backend_health: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    false_negative_count = 0
    for index, case in enumerate(cases):
        case_id = _text(case.get("case_id")) or f"case_{index}"
        query_understanding = _mapping(case.get("query_understanding"))
        required = _required_shelves(case.get("required_evidence_classes") or query_understanding.get("required_evidence_classes") or [])
        plan = build_adaptive_route_plan(
            _text(case.get("query")) or case_id,
            query_understanding=query_understanding,
            current_truth_view=current_truth_view,
            backend_health=_mapping(case.get("backend_health")) or backend_health,
            broker_summary=_mapping(case.get("broker_summary")),
        )
        activated = set(_list(plan.get("activated_shelves")))
        escalated = bool(_mapping(plan.get("route_decision")).get("escalated_to_tank"))
        missing = sorted(required - activated)
        false_negative = bool(missing and not escalated)
        if false_negative:
            false_negative_count += 1
        rows.append(
            {
                "case_id": case_id,
                "route_class": plan.get("route_class"),
                "required_shelves": sorted(required),
                "activated_shelves": sorted(activated),
                "escalated_to_tank": escalated,
                "missing_required_shelves": missing,
                "false_negative_tank_miss": false_negative,
                "sufficiency_status": "false_negative_tank_miss"
                if false_negative
                else "escalated_to_tank"
                if escalated
                else "sufficient",
                "sufficiency_explanation": "tank path covers required evidence"
                if escalated
                else "activated shelves cover required evidence classes",
            }
        )
    return {
        "schema": "brainstack.tank_shadow_oracle.v1",
        "status": "pass" if false_negative_count == 0 else "fail",
        "case_count": len(rows),
        "false_negative_tank_miss_count": false_negative_count,
        "cases": rows,
    }
