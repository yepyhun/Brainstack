from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from typing import Any, Mapping


RETRIEVAL_CONTROL_PLAN_SCHEMA_VERSION = "brainstack.retrieval_control_plan.v1"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _dict_int(value: Any) -> dict[str, int]:
    output: dict[str, int] = {}
    for key, item in _mapping(value).items():
        output[str(key)] = max(_int(item), 0)
    return output


def _stable_plan_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"rcp:{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


@dataclass(frozen=True)
class RetrievalControlPlan:
    schema: str
    plan_id: str
    status: str
    route_class: str
    requested_route_class: str
    retrieval_mode: str
    allowed_shelves: tuple[str, ...]
    skipped_shelves: tuple[str, ...]
    shelf_limits: Mapping[str, int] = field(default_factory=dict)
    semantic_enabled: bool = False
    semantic_allowed_shelves: tuple[str, ...] = ()
    semantic_limit: int = 0
    backend_call_budget: Mapping[str, int] = field(default_factory=dict)
    backend_call_budget_total: int = 0
    total_deadline_ms: int = 0
    channel_deadlines_ms: Mapping[str, int] = field(default_factory=dict)
    protected_authorities: tuple[str, ...] = ("durable_truth", "cited_corpus")
    degradation_policy: str = "partial_packet"
    proof_flags: Mapping[str, bool] = field(default_factory=dict)
    route_decision: Mapping[str, Any] = field(default_factory=dict)
    fallback: Mapping[str, Any] = field(default_factory=dict)
    current_truth_view: Mapping[str, Any] = field(default_factory=dict)
    guardrails: Mapping[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


def retrieval_control_plan_from_adaptive_plan(plan: Mapping[str, Any]) -> RetrievalControlPlan:
    semantic = _mapping(plan.get("semantic_retrieval"))
    shelf_budget = _mapping(plan.get("shelf_budget"))
    shelf_limits = _dict_int(shelf_budget.get("shelf_limits"))
    backend_budget = _dict_int(shelf_budget.get("backend_call_budget"))
    total_deadline_ms = max(_int(shelf_budget.get("latency_budget_ms")), 0)
    semantic_allowed = tuple(str(item) for item in _list(semantic.get("allowed_shelves")) if str(item or "").strip())
    semantic_limit = max(_int(shelf_limits.get("semantic_evidence")), 0)
    channel_deadlines = {
        "profile": min(total_deadline_ms, 250) if total_deadline_ms else 0,
        "continuity": min(total_deadline_ms, 400) if total_deadline_ms else 0,
        "transcript": min(total_deadline_ms, 400) if total_deadline_ms else 0,
        "operating": min(total_deadline_ms, 300) if total_deadline_ms else 0,
        "semantic": min(total_deadline_ms, 1200) if total_deadline_ms else 0,
        "graph": min(total_deadline_ms, 1200) if total_deadline_ms else 0,
        "corpus": min(total_deadline_ms, 1200) if total_deadline_ms else 0,
        "temporal": min(total_deadline_ms, 1200) if total_deadline_ms else 0,
        "current_truth_l0": min(total_deadline_ms, 250) if total_deadline_ms else 0,
    }
    id_payload = {
        "route_class": _text(plan.get("route_class")),
        "requested_route_class": _text(plan.get("requested_route_class")),
        "retrieval_mode": _text(plan.get("retrieval_mode")),
        "allowed_shelves": list(_list(plan.get("activated_shelves"))),
        "semantic_enabled": bool(semantic.get("enabled")),
        "semantic_allowed_shelves": list(semantic_allowed),
        "shelf_limits": shelf_limits,
        "backend_call_budget": backend_budget,
        "total_deadline_ms": total_deadline_ms,
    }
    proof_flags = {
        "single_runtime_plan": True,
        "semantic_shelves_bound": bool(not semantic.get("enabled") or semantic_allowed),
        "read_only_retrieval": True,
        "metadata_not_truth_authority": True,
        "packet_trace_requires_plan_id": True,
    }
    return RetrievalControlPlan(
        schema=RETRIEVAL_CONTROL_PLAN_SCHEMA_VERSION,
        plan_id=_stable_plan_id(id_payload),
        status=_text(plan.get("status")) or "unknown",
        route_class=_text(plan.get("route_class")),
        requested_route_class=_text(plan.get("requested_route_class")),
        retrieval_mode=_text(plan.get("retrieval_mode")),
        allowed_shelves=tuple(str(item) for item in _list(plan.get("activated_shelves")) if str(item or "").strip()),
        skipped_shelves=tuple(str(item) for item in _list(plan.get("skipped_shelves")) if str(item or "").strip()),
        shelf_limits=shelf_limits,
        semantic_enabled=bool(semantic.get("enabled")),
        semantic_allowed_shelves=semantic_allowed,
        semantic_limit=semantic_limit,
        backend_call_budget=backend_budget,
        backend_call_budget_total=max(_int(shelf_budget.get("backend_call_budget_total")), sum(backend_budget.values())),
        total_deadline_ms=total_deadline_ms,
        channel_deadlines_ms=channel_deadlines,
        proof_flags=proof_flags,
        route_decision=dict(_mapping(plan.get("route_decision"))),
        fallback=dict(_mapping(plan.get("fallback"))),
        current_truth_view=dict(_mapping(plan.get("current_truth_view"))),
        guardrails=dict(_mapping(plan.get("guardrails"))),
    )
