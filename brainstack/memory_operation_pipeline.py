"""Read-only memory-operation diagnostics.

These helpers borrow only the useful MemU lesson: complex memory operations
should expose bounded stage/projection/route evidence. They do not introduce a
new service, task runner, writable projection, or truth authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


MEMORY_OPERATION_PIPELINE_SCHEMA = "brainstack.memory_operation_pipeline.v1"
REFERENCED_CATEGORY_PROJECTION_SCHEMA = "brainstack.referenced_category_projection.v1"
RETRIEVAL_SUFFICIENCY_TRACE_SCHEMA = "brainstack.retrieval_sufficiency_trace.v1"

FORBIDDEN_PRIVATE_MARKERS = (
    "/private/project/path",
    "private_project_code",
    "private_user_handle",
    "private_runtime_path",
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:16]}"


def _public_safe(value: Mapping[str, Any]) -> bool:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return not any(marker in text for marker in FORBIDDEN_PRIVATE_MARKERS)


def build_memory_operation_pipeline_record(
    *,
    operation: str,
    selected_seam: str,
    stages: Iterable[Mapping[str, Any]],
    final_packet_state: Mapping[str, Any] | None = None,
    unchanged_authority: bool = True,
) -> dict[str, Any]:
    normalized_stages: list[dict[str, Any]] = []
    for index, stage in enumerate(stages, start=1):
        normalized_stages.append(
            {
                "index": index,
                "name": _text(stage.get("name")) or f"stage_{index}",
                "status": _text(stage.get("status")) or "unknown",
                "input_ref": _text(stage.get("input_ref")),
                "output_ref": _text(stage.get("output_ref")),
                "degraded": _bool(stage.get("degraded")),
                "reason_code": _text(stage.get("reason_code")),
            }
        )
    failed = [stage for stage in normalized_stages if stage["status"] in {"failed", "error"} or stage["degraded"]]
    payload = {
        "operation": _text(operation),
        "selected_seam": _text(selected_seam),
        "stage_names": [stage["name"] for stage in normalized_stages],
        "final_packet_state": dict(final_packet_state or {}),
    }
    verdict = "degraded" if failed else "healthy"
    if not unchanged_authority:
        verdict = "critical"
    return {
        "schema": MEMORY_OPERATION_PIPELINE_SCHEMA,
        "pipeline_id": _stable_id("mop", payload),
        "read_only": True,
        "side_effect_free": True,
        "truth_writer": False,
        "operation": payload["operation"],
        "selected_seam": payload["selected_seam"],
        "stage_count": len(normalized_stages),
        "stages": normalized_stages,
        "final_packet_state": payload["final_packet_state"],
        "unchanged_authority": unchanged_authority,
        "verdict": verdict,
        "reason_codes": _pipeline_reason_codes(verdict, failed, unchanged_authority),
        "public_safe": _public_safe(payload),
    }


def _pipeline_reason_codes(verdict: str, failed: list[Mapping[str, Any]], unchanged_authority: bool) -> list[str]:
    if not unchanged_authority:
        return ["PIPELINE_CHANGED_AUTHORITY_FORBIDDEN"]
    if failed:
        return ["PIPELINE_STAGE_DEGRADED"]
    if verdict == "healthy":
        return ["PIPELINE_DIAGNOSTIC_HEALTHY"]
    return ["PIPELINE_DIAGNOSTIC_UNKNOWN"]


def build_referenced_category_projection(
    *,
    category: str,
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    authority_claims: list[dict[str, str]] = []
    support_claims: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []
    for row in rows:
        ref = _text(row.get("source_ref") or row.get("receipt_id") or row.get("source_event_id"))
        claim = _text(row.get("claim") or row.get("content") or row.get("value"))
        if not claim:
            continue
        item = {
            "claim": claim,
            "ref": ref,
            "rendered": f"{claim} [ref:{ref}]" if ref else claim,
        }
        is_current = _bool(row.get("is_current", True))
        truth_eligible = _bool(row.get("truth_eligible"))
        support_only = _bool(row.get("support_only")) or _text(row.get("authority_class")) == "support"
        superseded = bool(_text(row.get("superseded_by")) or _text(row.get("valid_to")))
        if truth_eligible and is_current and not support_only and not superseded:
            authority_claims.append(item)
        elif support_only or not truth_eligible:
            support_claims.append(item)
        else:
            excluded_rows.append({"claim": claim, "ref": ref, "reason_code": "STALE_OR_SUPERSEDED_NOT_AUTHORITY"})
    projection = {
        "category": _text(category),
        "authority_claims": authority_claims,
        "support_claims": support_claims,
        "excluded_rows": excluded_rows,
    }
    return {
        "schema": REFERENCED_CATEGORY_PROJECTION_SCHEMA,
        "projection_id": _stable_id("rcp", projection),
        "read_only": True,
        "side_effect_free": True,
        "truth_writer": False,
        "category": projection["category"],
        "authority_claims": authority_claims,
        "support_claims": support_claims,
        "excluded_rows": excluded_rows,
        "authority_claim_count": len(authority_claims),
        "support_claim_count": len(support_claims),
        "excluded_count": len(excluded_rows),
        "public_safe": _public_safe(projection),
        "agent_claim": "referenced_projection_read_model_not_truth",
    }


def build_retrieval_sufficiency_trace(
    *,
    query_class: str,
    route_class: str,
    evidence_counts: Mapping[str, Any],
    backend_health: Mapping[str, Any] | None = None,
    packet_budget: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    backend = _mapping(backend_health)
    budget = _mapping(packet_budget)
    current_truth = _int(evidence_counts.get("current_truth"))
    profile = _int(evidence_counts.get("profile"))
    corpus = _int(evidence_counts.get("corpus"))
    graph = _int(evidence_counts.get("graph"))
    semantic_available = _bool(backend.get("semantic_available", True))
    semantic_degraded = _bool(backend.get("semantic_degraded")) or _text(backend.get("semantic_status")) in {
        "error",
        "timeout",
        "unavailable",
    }
    budget_exceeded = _text(budget.get("status")) in {"over_budget", "truncated"} or _bool(budget.get("fail_closed"))
    query = _text(query_class) or "unknown"
    route = _text(route_class) or "unknown"

    if semantic_degraded and route in {"semantic", "corpus", "deep"}:
        decision = "degraded_partial"
        reason = "SEMANTIC_BACKEND_DEGRADED_VISIBLE"
    elif query in {"profile", "current_truth", "preference"} and current_truth + profile > 0:
        decision = "stop_fast"
        reason = "FAST_AUTHORITATIVE_CONTEXT_SUFFICIENT"
    elif corpus + graph > 0 or route in {"corpus", "graph", "deep"}:
        decision = "deepen"
        reason = "DEEPER_RETRIEVAL_REQUIRED"
    elif budget_exceeded:
        decision = "degraded_partial"
        reason = "PACKET_BUDGET_DEGRADED_VISIBLE"
    elif not semantic_available and route == "semantic":
        decision = "insufficient"
        reason = "REQUESTED_SEMANTIC_BACKEND_UNAVAILABLE"
    else:
        decision = "insufficient"
        reason = "INSUFFICIENT_RETRIEVAL_EVIDENCE"

    payload = {
        "query_class": query,
        "route_class": route,
        "evidence_counts": {str(key): _int(value) for key, value in evidence_counts.items()},
        "decision": decision,
        "reason_code": reason,
    }
    return {
        "schema": RETRIEVAL_SUFFICIENCY_TRACE_SCHEMA,
        "trace_id": _stable_id("rst", payload),
        "read_only": True,
        "side_effect_free": True,
        "truth_writer": False,
        **payload,
        "semantic_available": semantic_available,
        "semantic_degraded": semantic_degraded,
        "budget_status": _text(budget.get("status")) or "unknown",
        "public_safe": _public_safe(payload),
    }


__all__ = [
    "build_memory_operation_pipeline_record",
    "build_referenced_category_projection",
    "build_retrieval_sufficiency_trace",
]
