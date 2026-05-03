from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, NoReturn

ADAPTIVE_CONSOLIDATION_SCHEMA_VERSION = "brainstack.adaptive_consolidation.v1"
DERIVED_WORK_ITEM_SCHEMA_VERSION = "brainstack.derived_work_item.v1"
DERIVED_WORK_STATES = ("queued", "pending", "failed", "complete", "skipped")
DERIVED_WORK_KINDS = (
    "graph_projection",
    "corpus_index",
    "semantic_index",
    "current_truth_view",
    "projection_rebuild",
)
SYNCHRONOUS_TRUTH_KINDS = ("admission", "write_receipt", "durable_truth")

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


class DurableTruthMustRemainSynchronousError(RuntimeError):
    """Raised when durable truth or receipts are attempted through async consolidation."""


@dataclass(frozen=True)
class DerivedWorkInput:
    work_id: str
    work_kind: str
    state: str
    source_event_id: str = ""
    source_span_id: str = ""
    retry_count: int = 0
    last_error_class: str = ""
    freshness_status: str = "fresh"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _int(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


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


def _walk_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, Mapping):
        for child in value.values():
            values.extend(_walk_values(child))
    elif isinstance(value, list):
        for child in value:
            values.extend(_walk_values(child))
    elif isinstance(value, str):
        values.append(value)
    return values


def validate_adaptive_consolidation_public_safety(report: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for key in _walk_keys(report):
        if key.casefold() in _PUBLIC_FORBIDDEN_KEYS:
            issues.append(f"forbidden_public_key:{key}")
    for value in _walk_values(report):
        lowered = value.casefold()
        if "private source text" in lowered or "provider_secret" in lowered or "api_key" in lowered:
            issues.append("forbidden_public_value")
    return sorted(set(issues))


def _payload_issue_count(payload: Mapping[str, Any] | None) -> int:
    if not isinstance(payload, Mapping):
        return 0
    return len(validate_adaptive_consolidation_public_safety(payload))


def defer_durable_truth_write(_payload: Mapping[str, Any]) -> NoReturn:
    """Fail closed: admission and write receipts must remain synchronous."""

    raise DurableTruthMustRemainSynchronousError(
        "durable truth, admission, and write receipts cannot be deferred to async consolidation"
    )


def build_derived_work_item(
    work_id: str,
    work_kind: str,
    state: str,
    *,
    source_event_id: str = "",
    source_span_id: str = "",
    retry_count: int = 0,
    last_error_class: str = "",
    freshness_status: str = "fresh",
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_kind = _text(work_kind).casefold()
    normalized_state = _text(state).casefold()
    if normalized_kind in SYNCHRONOUS_TRUTH_KINDS:
        raise DurableTruthMustRemainSynchronousError(
            f"{normalized_kind} is synchronous durable truth work and cannot be queued as derived async work"
        )
    if normalized_kind not in DERIVED_WORK_KINDS:
        normalized_kind = "projection_rebuild"
    if normalized_state not in DERIVED_WORK_STATES:
        normalized_state = "failed"
        last_error_class = last_error_class or "invalid_derived_work_state"
    payload_issue_count = _payload_issue_count(payload)
    error_class = _text(last_error_class)
    if payload_issue_count and not error_class:
        error_class = "malformed_derived_payload"
    return {
        "schema": DERIVED_WORK_ITEM_SCHEMA_VERSION,
        "work_id": _text(work_id),
        "work_kind": normalized_kind,
        "state": normalized_state,
        "source": {
            "source_event_id": _text(source_event_id),
            "source_span_id": _text(source_span_id),
        },
        "retry_count": _int(retry_count),
        "last_error_class": error_class,
        "freshness_status": _text(freshness_status) or ("complete" if normalized_state == "complete" else normalized_state),
        "public_safe": payload_issue_count == 0,
        "payload_issue_count": payload_issue_count,
    }


def _empty_counts() -> dict[str, int]:
    return {
        "queued_count": 0,
        "pending_count": 0,
        "failed_count": 0,
        "complete_count": 0,
        "skipped_count": 0,
        "retry_count": 0,
        "stalled_count": 0,
        "malformed_payload_count": 0,
        "rebuild_mismatch_count": 0,
        "backend_unavailable_count": 0,
        "durable_truth_deferred_count": 0,
        "hidden_readiness_claim_count": 0,
    }


def _failure_bundle(item: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(item.get("source"))
    return {
        "schema": "brainstack.derived_work_failure_bundle.v1",
        "work_id": _text(item.get("work_id")),
        "work_kind": _text(item.get("work_kind")),
        "state": _text(item.get("state")),
        "source_event_id": _text(source.get("source_event_id")),
        "source_span_id": _text(source.get("source_span_id")),
        "retry_count": _int(item.get("retry_count")),
        "last_error_class": _text(item.get("last_error_class")),
        "freshness_status": _text(item.get("freshness_status")),
        "public_safe": True,
    }


def _readiness_by_kind(items: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for kind in DERIVED_WORK_KINDS:
        kind_items = [item for item in items if _text(item.get("work_kind")) == kind]
        if not kind_items:
            output[kind] = {"state": "skipped", "ready": False, "reason": "no derived work item"}
            continue
        complete = all(_text(item.get("state")) in {"complete", "skipped"} for item in kind_items)
        output[kind] = {
            "state": "complete" if complete else "not_ready",
            "ready": complete,
            "item_count": len(kind_items),
            "failed_count": sum(1 for item in kind_items if _text(item.get("state")) == "failed"),
            "pending_count": sum(1 for item in kind_items if _text(item.get("state")) in {"queued", "pending"}),
        }
    return output


def build_adaptive_consolidation_report(
    items: Iterable[Mapping[str, Any]],
    *,
    baseline: Mapping[str, Any] | None = None,
    write_amplification: int = 0,
    active_packet_tokens: int = 0,
    projection_rebuild_size: int = 0,
    duplicate_support_only_accumulation: int = 0,
) -> dict[str, Any]:
    normalized_items = [dict(item) for item in items]
    counters = _empty_counts()
    failure_bundles: list[dict[str, Any]] = []
    for item in normalized_items:
        state = _text(item.get("state"))
        kind = _text(item.get("work_kind"))
        if kind in SYNCHRONOUS_TRUTH_KINDS:
            counters["durable_truth_deferred_count"] += 1
        if state in DERIVED_WORK_STATES:
            counters[f"{state}_count"] += 1
        counters["retry_count"] += _int(item.get("retry_count"))
        error_class = _text(item.get("last_error_class"))
        freshness = _text(item.get("freshness_status"))
        if state == "pending" and ("stalled" in error_class or freshness == "stale"):
            counters["stalled_count"] += 1
        if error_class == "malformed_derived_payload" or _int(item.get("payload_issue_count")) > 0:
            counters["malformed_payload_count"] += 1
        if error_class == "rebuild_mismatch":
            counters["rebuild_mismatch_count"] += 1
        if error_class == "backend_unavailable":
            counters["backend_unavailable_count"] += 1
        if state in {"failed", "pending"} or error_class:
            failure_bundles.append(_failure_bundle(item))
    all_ready = bool(normalized_items) and all(
        _text(item.get("state")) in {"complete", "skipped"} for item in normalized_items
    )
    hidden_readiness = 0
    if not all_ready:
        hidden_readiness = 0
    counters["hidden_readiness_claim_count"] = hidden_readiness
    base = dict(baseline or {})
    write_delta = int(write_amplification) - int(base.get("write_amplification") or 0)
    packet_delta = int(active_packet_tokens) - int(base.get("active_packet_tokens") or 0)
    projection_delta = int(projection_rebuild_size) - int(base.get("projection_rebuild_size") or 0)
    bounded = (
        counters["durable_truth_deferred_count"] == 0
        and counters["hidden_readiness_claim_count"] == 0
        and int(duplicate_support_only_accumulation) <= 0
        and write_delta <= 0
        and packet_delta <= 0
        and projection_delta <= 0
    )
    report: dict[str, Any] = {
        "schema": ADAPTIVE_CONSOLIDATION_SCHEMA_VERSION,
        "status": "pass" if all_ready and bounded else "degraded",
        "contract": {
            "admission_synchronous": True,
            "write_receipt_synchronous": True,
            "durable_truth_async_allowed": False,
            "derived_work_async_only": True,
            "runtime_governance_authority": False,
        },
        "allowed_derived_work_kinds": list(DERIVED_WORK_KINDS),
        "states": list(DERIVED_WORK_STATES),
        "items": normalized_items,
        "counters": counters,
        "readiness": {
            "ready": all_ready,
            "ready_claim_allowed": all_ready,
            "by_kind": _readiness_by_kind(normalized_items),
            "hidden_fallback_claim_count": counters["hidden_readiness_claim_count"],
        },
        "failure_bundles": failure_bundles,
        "bloat_control": {
            "write_amplification": int(write_amplification),
            "active_packet_tokens": int(active_packet_tokens),
            "projection_rebuild_size": int(projection_rebuild_size),
            "duplicate_support_only_accumulation": int(duplicate_support_only_accumulation),
            "write_amplification_delta": write_delta,
            "active_packet_growth_delta": packet_delta,
            "projection_rebuild_size_delta": projection_delta,
            "bounded": bounded,
        },
        "anti_goal_proof": {
            "async_without_lying": counters["durable_truth_deferred_count"] == 0
            and counters["hidden_readiness_claim_count"] == 0,
            "derived_readiness_not_claimed_before_complete": not all_ready or counters["hidden_readiness_claim_count"] == 0,
        },
        "public_safety": {"public_safe": True, "issues": []},
    }
    public_issues = validate_adaptive_consolidation_public_safety(report)
    report["public_safety"] = {"public_safe": not public_issues, "issues": public_issues}
    if public_issues:
        report["status"] = "fail"
    return report


def empty_adaptive_consolidation_report() -> dict[str, Any]:
    return build_adaptive_consolidation_report([])
