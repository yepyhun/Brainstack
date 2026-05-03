from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Iterable, Mapping, NoReturn

from .canonical_memory_event import CANONICAL_MEMORY_EVENT_CORE_GROUPS, validate_canonical_memory_event
from .graphiti_projection import project_canonical_events_to_graphiti
from .projection_semantics import classify_projection_semantics

CURRENT_TRUTH_VIEW_SCHEMA_VERSION = "brainstack.current_truth_view.v1"
CURRENT_TRUTH_VIEW_PROJECTION_VERSION = "brainstack.current_truth_view.rebuild.v1"
DEFAULT_CACHE_MAX_AGE_SECONDS = 300

_PUBLIC_FORBIDDEN_KEYS = {
    "raw_text",
    "raw_private_text",
    "raw_value",
    "secret",
    "provider_secret",
    "provider_api_key",
    "embedding",
    "embedding_vector",
    "embedding_vectors",
    "full_prompt",
    "prompt",
    "model_output",
    "raw_donor_json",
    "packet_text",
}


class CurrentTruthViewWriteError(RuntimeError):
    """Raised when code tries to write directly into the current-truth view."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "stale"}
    return bool(value)


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _age_seconds(*, rebuilt_at: str, checked_at: str) -> int | None:
    rebuilt = _parse_iso(rebuilt_at)
    checked = _parse_iso(checked_at)
    if rebuilt is None or checked is None:
        return None
    return max(0, int((checked - rebuilt).total_seconds()))


def _hash(value: Any, *, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _canonical_event(row_or_event: Mapping[str, Any]) -> Mapping[str, Any]:
    if all(isinstance(row_or_event.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return row_or_event
    nested = _mapping(row_or_event.get("event"))
    if all(isinstance(nested.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return nested
    return {}


def _event_sort_key(event: Mapping[str, Any]) -> tuple[str, str]:
    temporal = _mapping(event.get("temporal"))
    event_group = _mapping(event.get("event"))
    return (_text(temporal.get("transaction_time")), _text(event_group.get("event_id")))


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


def validate_current_truth_view_public_safety(view: Mapping[str, Any]) -> list[str]:
    """Return public-safety findings for a materialized view payload."""

    issues: list[str] = []
    for key in _walk_keys(view):
        if key.casefold() in _PUBLIC_FORBIDDEN_KEYS:
            issues.append(f"forbidden_public_key:{key}")
    for value in _walk_text_values(view):
        value_lower = value.casefold()
        if "private source text" in value_lower:
            issues.append("forbidden_public_value:private_source_text")
        if "provider_secret" in value_lower or "api_key" in value_lower:
            issues.append("forbidden_public_value:secret_marker")
    return sorted(set(issues))


def write_current_truth_view(_row: Mapping[str, Any]) -> NoReturn:
    """Fail closed: the current-truth view is rebuild-only, never directly writable."""

    raise CurrentTruthViewWriteError(
        "current-truth view is a rebuildable projection only; durable truth must flow through admission receipts"
    )


def _projection_stale_source(event: Mapping[str, Any]) -> bool:
    projection = _mapping(event.get("projection"))
    return (
        _flag(projection.get("stale"))
        or _flag(projection.get("is_stale"))
        or _text(projection.get("freshness_status")).casefold() in {"stale", "stale_source", "expired"}
        or _text(projection.get("cache_status")).casefold() in {"stale", "stale_source", "expired"}
    )


def _malformed_projection(event: Mapping[str, Any]) -> bool:
    projection = event.get("projection")
    return not isinstance(projection, Mapping) or not isinstance(_mapping(projection).get("projection_hints"), Mapping)


def _row_from_event(
    event: Mapping[str, Any],
    *,
    answerable_current_truth: bool,
    extra_reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    event_group = _mapping(event.get("event"))
    source = _mapping(event.get("source"))
    scope = _mapping(event.get("scope"))
    claim = _mapping(event.get("claim"))
    authority = _mapping(event.get("authority"))
    temporal = _mapping(event.get("temporal"))
    projection = _mapping(event.get("projection"))
    semantics = classify_projection_semantics(event)
    reason_codes = [reason.value for reason in semantics.reason_codes]
    for reason in extra_reason_codes or []:
        if reason not in reason_codes:
            reason_codes.append(reason)
    event_id = _text(event_group.get("event_id"))
    stable_fact_id = _text(claim.get("stable_fact_id"))
    return {
        "view_id": _hash([CURRENT_TRUTH_VIEW_PROJECTION_VERSION, event_id, stable_fact_id]),
        "event_id": event_id,
        "stable_fact_id": stable_fact_id,
        "target_slot": _text(claim.get("target_slot")),
        "memory_kind": _text(claim.get("memory_kind")),
        "normalized_value_hash": _text(claim.get("normalized_value_hash")),
        "subject_ref": _text(claim.get("subject_ref")),
        "predicate": _text(claim.get("predicate")),
        "object_ref": _text(claim.get("object_ref")),
        "scope": {
            "tenant_id": _text(scope.get("tenant_id")),
            "principal_scope_key": _text(scope.get("principal_scope_key")),
            "workspace_scope_key": _text(scope.get("workspace_scope_key")),
            "session_id": _text(scope.get("session_id")),
            "project_id": _text(scope.get("project_id")),
        },
        "source_event_id": _text(source.get("source_event_id")),
        "source_span_id": _text(source.get("source_span_id")),
        "source_quote_hash": _text(source.get("source_quote_hash")),
        "receipt_id": _text(authority.get("receipt_id")),
        "authority_class": _text(authority.get("authority_class")),
        "truth_eligible": bool(authority.get("truth_eligible")),
        "support_visibility": _text(authority.get("support_visibility")),
        "valid_from": _text(temporal.get("valid_from")),
        "valid_to": _text(temporal.get("valid_to")),
        "transaction_time": _text(temporal.get("transaction_time")),
        "superseded_by": _text(temporal.get("superseded_by")),
        "projection_version": CURRENT_TRUTH_VIEW_PROJECTION_VERSION,
        "projection_budget_class": _text(projection.get("budget_class")),
        "answerable_current_truth": bool(answerable_current_truth),
        "is_current": semantics.is_current,
        "is_prior": semantics.is_prior,
        "is_conflicted": semantics.is_conflicted,
        "is_support_only": semantics.is_support_only,
        "is_retrieval_only": semantics.is_retrieval_only,
        "is_hidden": semantics.is_hidden,
        "is_authority_critical": semantics.is_authority_critical,
        "projection_reason_codes": reason_codes,
    }


def _source_event_span(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    rows: list[tuple[str, str, str]] = []
    for event in events:
        event_group = _mapping(event.get("event"))
        temporal = _mapping(event.get("temporal"))
        rows.append(
            (
                _text(temporal.get("transaction_time")),
                _text(event_group.get("event_id")),
                _text(_mapping(event.get("source")).get("source_event_id")),
            )
        )
    rows = sorted(row for row in rows if row[1] or row[2])
    if not rows:
        return {
            "source_event_count": 0,
            "first_event_id": "",
            "last_event_id": "",
            "min_transaction_time": "",
            "max_transaction_time": "",
            "source_event_ids": [],
        }
    source_event_ids = sorted({row[2] for row in rows if row[2]})
    return {
        "source_event_count": len(source_event_ids),
        "first_event_id": rows[0][1],
        "last_event_id": rows[-1][1],
        "min_transaction_time": rows[0][0],
        "max_transaction_time": rows[-1][0],
        "source_event_ids": source_event_ids,
    }


def _receipt_coverage(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    receipt_ids: list[str] = []
    missing = 0
    answer_truth_rows = 0
    for event in events:
        authority = _mapping(event.get("authority"))
        support_visibility = _text(authority.get("support_visibility"))
        truth_eligible = bool(authority.get("truth_eligible"))
        receipt_id = _text(authority.get("receipt_id"))
        if truth_eligible and support_visibility == "answer_evidence":
            answer_truth_rows += 1
            if receipt_id:
                receipt_ids.append(receipt_id)
            else:
                missing += 1
    return {
        "answer_truth_row_count": answer_truth_rows,
        "receipt_count": len(set(receipt_ids)),
        "missing_receipt_count": missing,
        "receipt_ids": sorted(set(receipt_ids)),
    }


def _deep_graph_path(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    graph = project_canonical_events_to_graphiti(events)
    prior_count = len(_list(graph.get("prior_edges")))
    inspect_count = len(_list(graph.get("inspect_only_edges")))
    current_count = len(_list(graph.get("current_edges")))
    edge_path_available = bool(current_count or prior_count or inspect_count)
    return {
        "available": edge_path_available and bool(graph.get("graphiti_contract")),
        "graph_projection_schema": graph.get("schema"),
        "graph_projection_status": graph.get("status"),
        "current_edge_count": current_count,
        "prior_edge_count": prior_count,
        "inspect_only_edge_count": inspect_count,
        "temporal_or_conflict_path_available": bool(prior_count or inspect_count),
        "current_truth_view_is_graph_authority": False,
    }


def _snapshot_hash(view: Mapping[str, Any]) -> str:
    snapshot = {
        "schema": view.get("schema"),
        "contract": view.get("contract"),
        "source_event_span": view.get("source_event_span"),
        "receipt_coverage": view.get("receipt_coverage"),
        "current_truth_rows": view.get("current_truth_rows"),
        "non_answerable_rows": view.get("non_answerable_rows"),
        "issues": view.get("issues"),
        "counters": view.get("counters"),
        "deep_graph_path": view.get("deep_graph_path"),
    }
    return _hash(snapshot, length=32)


def rebuild_current_truth_view(
    events: Iterable[Mapping[str, Any]],
    *,
    rebuilt_at: str | None = None,
    checked_at: str | None = None,
    cache_max_age_seconds: int = DEFAULT_CACHE_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Build a public-safe current-truth read view from canonical events.

    The view has no write path and no authority of its own. It only mirrors
    already-admitted canonical/projection semantics into a fast, inspectable,
    rebuildable shape. Unsafe evidence remains visible as non-answerable rows or
    issues, but never upgrades into current answer truth.
    """

    rebuild_timestamp = _text(rebuilt_at) or _now_iso()
    check_timestamp = _text(checked_at) or rebuild_timestamp
    age = _age_seconds(rebuilt_at=rebuild_timestamp, checked_at=check_timestamp)
    cache_fresh = age is not None and age <= int(cache_max_age_seconds)
    freshness_status = "fresh" if cache_fresh else "stale_cache"

    normalized_events = [_canonical_event(event) for event in events]
    normalized_events = [event for event in normalized_events if event]
    normalized_events = sorted(normalized_events, key=_event_sort_key)

    current_rows: list[dict[str, Any]] = []
    non_answerable_rows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    counters = {
        "input_event_count": len(normalized_events),
        "current_answerable_count": 0,
        "non_answerable_count": 0,
        "invalid_canonical_event_count": 0,
        "prior_count": 0,
        "conflict_count": 0,
        "missing_source_count": 0,
        "missing_receipt_count": 0,
        "support_only_count": 0,
        "stale_projection_source_count": 0,
        "malformed_projection_count": 0,
        "unsafe_answer_truth_projection_count": 0,
        "stale_cache_serving_block_count": 0,
        "second_write_authority_count": 0,
        "raw_truth_write_attempt_count": 0,
        "raw_text_leak_count": 0,
    }

    for event in normalized_events:
        event_id = _text(_mapping(event.get("event")).get("event_id"))
        validation_issues = validate_canonical_memory_event(event)
        malformed_projection = _malformed_projection(event)
        if malformed_projection:
            counters["malformed_projection_count"] += 1
        if validation_issues:
            counters["invalid_canonical_event_count"] += 1
            if any("source" in issue for issue in validation_issues):
                counters["missing_source_count"] += 1
            if any("receipt" in issue for issue in validation_issues):
                counters["missing_receipt_count"] += 1
            issues.append({"event_id": event_id, "issues": validation_issues})
            extra = [f"current_truth_view_invalid_canonical_event:{issue}" for issue in validation_issues]
            if malformed_projection:
                extra.append("current_truth_view_malformed_projection")
            non_answerable_rows.append(
                _row_from_event(
                    event,
                    answerable_current_truth=False,
                    extra_reason_codes=extra,
                )
            )
            counters["non_answerable_count"] += 1
            continue

        semantics = classify_projection_semantics(event)
        stale_projection = _projection_stale_source(event)
        extra_reasons: list[str] = []
        if stale_projection:
            counters["stale_projection_source_count"] += 1
            extra_reasons.append("current_truth_view_stale_projection_source")
        if not cache_fresh:
            extra_reasons.append("current_truth_view_cache_stale")
        if semantics.is_prior:
            counters["prior_count"] += 1
        if semantics.is_conflicted:
            counters["conflict_count"] += 1
        if not semantics.source_event_id or not semantics.source_span_id or not semantics.source_quote_hash:
            counters["missing_source_count"] += 1
        if any(reason.value == "projection_missing_receipt_ref" for reason in semantics.reason_codes):
            counters["missing_receipt_count"] += 1
        if semantics.is_support_only:
            counters["support_only_count"] += 1

        answerable_current_truth = semantics.is_answer_safe and not stale_projection and cache_fresh and not malformed_projection
        row = _row_from_event(
            event,
            answerable_current_truth=answerable_current_truth,
            extra_reason_codes=extra_reasons,
        )
        if answerable_current_truth:
            current_rows.append(row)
            counters["current_answerable_count"] += 1
        else:
            non_answerable_rows.append(row)
            counters["non_answerable_count"] += 1
            if not cache_fresh and semantics.is_answer_safe:
                counters["stale_cache_serving_block_count"] += 1

        if row["answerable_current_truth"] and (
            row["is_prior"]
            or row["is_conflicted"]
            or row["is_support_only"]
            or not row["source_event_id"]
            or not row["source_span_id"]
            or not row["source_quote_hash"]
            or not row["receipt_id"]
            or stale_projection
        ):
            counters["unsafe_answer_truth_projection_count"] += 1

    for row_list in (current_rows, non_answerable_rows):
        row_list.sort(
            key=lambda item: (
                item["scope"].get("principal_scope_key", ""),
                item.get("stable_fact_id", ""),
                item.get("event_id", ""),
            )
        )
    issues.sort(key=lambda item: item.get("event_id", ""))

    view: dict[str, Any] = {
        "schema": CURRENT_TRUTH_VIEW_SCHEMA_VERSION,
        "status": "pass",
        "contract": {
            "rebuildable_from_canonical_events": True,
            "second_write_authority": False,
            "durable_truth_writes": False,
            "admission_receipt_override": False,
            "raw_truth_write_api": False,
        },
        "rebuild": {
            "projection_version": CURRENT_TRUTH_VIEW_PROJECTION_VERSION,
            "rebuilt_at": rebuild_timestamp,
            "checked_at": check_timestamp,
            "cache_max_age_seconds": int(cache_max_age_seconds),
            "cache_age_seconds": age,
            "freshness_status": freshness_status,
            "freshness_diagnostics_present": True,
        },
        "source_event_span": _source_event_span(normalized_events),
        "receipt_coverage": _receipt_coverage(normalized_events),
        "current_truth_rows": current_rows,
        "non_answerable_rows": non_answerable_rows,
        "issues": issues,
        "counters": counters,
        "deep_graph_path": _deep_graph_path(normalized_events),
    }
    public_safety_issues = validate_current_truth_view_public_safety(view)
    counters["raw_text_leak_count"] = len(public_safety_issues)
    view["public_safety"] = {
        "public_safe": not public_safety_issues,
        "issues": public_safety_issues,
    }
    safety_failed = (
        counters["unsafe_answer_truth_projection_count"]
        or counters["second_write_authority_count"]
        or counters["raw_truth_write_attempt_count"]
        or counters["raw_text_leak_count"]
        or not cache_fresh
    )
    view["status"] = "fail" if safety_failed else "pass"
    view["deterministic_snapshot_hash"] = _snapshot_hash(view)
    return view
