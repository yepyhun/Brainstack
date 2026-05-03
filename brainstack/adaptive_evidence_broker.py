"""Read-only adaptive evidence candidate broker contract.

The broker normalizes existing candidate surfaces into one public-safe diagnostic
shape. It is not a retrieval engine, allocator, storage writer, provider router,
or durable truth authority.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from typing import Any, Mapping, Sequence

CANDIDATE_SCHEMA = "brainstack.adaptive_evidence_candidate.v1"
BROKER_TRACE_SCHEMA = "brainstack.adaptive_evidence_broker.v1"

_FORBIDDEN_PUBLIC_KEYS = {
    "raw_text",
    "raw_private_text",
    "private_value",
    "full_prompt",
    "prompt_text",
    "message_text",
    "full_text",
    "raw_output",
    "block",
    "content",
    "query",
    "query_text",
    "transcript_text",
    "raw_transcript",
}

_SECRET_VALUE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "sk-",
    "ghp_",
    "github_pat_",
    "private-token-should-not-leak-from-broker",
)

_PROTECTED_AUTHORITIES = {"durable_truth", "receipt_backed", "cited_corpus"}
_UNSAFE_AUTHORITIES = {"support_only", "inspect_only", "corrected_false", "conflict", "malformed"}

_SHELVES = {
    "profile",
    "task",
    "operating",
    "continuity_match",
    "continuity_recent",
    "transcript",
    "graph",
    "corpus",
}


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


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


def _fingerprint(value: object) -> str:
    text = str(value or "")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if is_dataclass(value) and not isinstance(value, type):
        data = asdict(value)
        return dict(data) if isinstance(data, Mapping) else {}
    return {}


def _nested(mapping: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _candidate_base(candidate: Any) -> tuple[dict[str, Any], dict[str, Any], str, str, dict[str, int], float]:
    """Return structural candidate data for Mapping or EvidenceCandidate-like dataclass."""

    if is_dataclass(candidate) and not isinstance(candidate, type):
        data = asdict(candidate)
        row = dict(data.get("row") or {}) if isinstance(data.get("row"), Mapping) else {}
        key = _text(data.get("key"))
        shelf = _text(data.get("shelf"))
        channel_ranks = {
            _text(channel): _integer(rank)
            for channel, rank in dict(data.get("channel_ranks") or {}).items()
            if _text(channel)
        }
        return data, row, key, shelf, channel_ranks, _number(data.get("rrf_score"))
    data = _mapping(candidate)
    row = data
    key = _text(data.get("evidence_key") or data.get("key") or data.get("candidate_id") or data.get("evidence_id"))
    shelf = _text(data.get("shelf")) or _shelf_from_identifier(key) or _shelf_from_identifier(_text(data.get("candidate_id")))
    channel_ranks = dict(data.get("channel_ranks") or data.get("_brainstack_channel_ranks") or {})
    return data, row, key, shelf, {_text(k): _integer(v) for k, v in channel_ranks.items() if _text(k)}, _number(data.get("rrf_score"))


def _shelf_from_identifier(value: str) -> str:
    prefix = _text(value).split(":", 1)[0]
    aliases = {
        "profile_items": "profile",
        "task_rows": "task",
        "operating_rows": "operating",
        "matched": "continuity_match",
        "recent": "continuity_recent",
        "transcript_rows": "transcript",
        "graph_rows": "graph",
        "corpus_rows": "corpus",
    }
    if prefix in _SHELVES:
        return prefix
    return aliases.get(prefix, "")


def _channels(data: Mapping[str, Any], row: Mapping[str, Any], channel_ranks: Mapping[str, int]) -> list[str]:
    raw_channels = data.get("channels")
    if raw_channels is None:
        raw_channels = row.get("_brainstack_channels")
    if raw_channels is None:
        raw_source = _nested(data, "source")
        raw_channels = raw_source.get("channels")
    channels: set[str] = set()
    if isinstance(raw_channels, (list, tuple)):
        channels.update(_text(item) for item in raw_channels if _text(item))
    channels.update(_text(channel) for channel in channel_ranks if _text(channel))
    channel = _text(data.get("channel"))
    if channel:
        channels.add(channel)
    return sorted(channels)


def _selection_status(data: Mapping[str, Any], *, explicit_status: str | None, malformed: bool) -> str:
    if malformed:
        return "malformed"
    if explicit_status:
        return _text(explicit_status)
    nested_selection = _nested(data, "selection")
    status = _text(nested_selection.get("status")) or _text(data.get("selection_status"))
    if status:
        if status == "not_selected":
            return "suppressed"
        return status
    decision = _text(data.get("decision"))
    if decision == "selected":
        return "selected"
    if decision in {"dropped", "demoted"}:
        return "suppressed"
    return "candidate"


def _authority_class(data: Mapping[str, Any], row: Mapping[str, Any]) -> str:
    nested_authority = _nested(data, "authority")
    support_visibility = _text(data.get("support_visibility") or row.get("support_visibility"))
    row_type = _text(data.get("row_type") or row.get("row_type"))
    freshness = _text(data.get("freshness") or data.get("temporal_status") or row.get("temporal_status")).casefold()
    source_role = _text(data.get("source_role") or row.get("source_role")).casefold()
    if row_type == "conflict" or support_visibility in {"contradiction_only", "conflict"}:
        return "conflict"
    if support_visibility in {"inspect_only", "history_only"}:
        return "inspect_only"
    if source_role == "assistant":
        return "inspect_only"
    authority = (
        _text(data.get("authority"))
        or _text(row.get("authority"))
        or _text(nested_authority.get("class"))
        or _text(nested_authority.get("level"))
    )
    if authority == "canonical":
        return "durable_truth"
    if authority in _PROTECTED_AUTHORITIES | _UNSAFE_AUTHORITIES:
        return authority
    if _text(data.get("receipt_id") or row.get("receipt_id")):
        return "receipt_backed"
    if bool(data.get("truth_eligible") or row.get("truth_eligible")):
        return "durable_truth"
    if freshness in {"prior", "stale", "expired"}:
        return "inspect_only"
    return authority or "support_only"


def _freshness(data: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    raw = _text(
        data.get("freshness")
        or data.get("temporal_status")
        or row.get("temporal_status")
        or row.get("record_temporal_status")
    ).casefold()
    stale = bool(data.get("stale") or row.get("stale"))
    valid_to_present = bool(_text(data.get("valid_to") or row.get("valid_to")))
    if stale:
        klass = "stale"
    elif raw in {"prior", "expired", "stale"}:
        klass = raw
    elif valid_to_present:
        klass = "prior"
    else:
        klass = raw or "current"
    return {
        "class": klass,
        "stale": klass in {"prior", "expired", "stale"},
        "valid_to_present": valid_to_present,
        "happened_at_present": bool(_text(data.get("happened_at") or row.get("happened_at"))),
    }


def _source_present(data: Mapping[str, Any], row: Mapping[str, Any], key: str) -> bool:
    nested_source = _nested(data, "source")
    donor_metadata = _nested(data, "donor_metadata")
    return any(
        _text(value)
        for value in (
            data.get("source_event_id"),
            data.get("source_span_id"),
            row.get("source_event_id"),
            row.get("source_span_id"),
            data.get("source"),
            row.get("source"),
            data.get("citation_id"),
            row.get("citation_id"),
            data.get("document_hash"),
            row.get("document_hash"),
            nested_source.get("retrieval_source"),
            key,
            _text(donor_metadata),
        )
    )


def _source_chain_complete(data: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    source_event = _text(data.get("source_event_id") or row.get("source_event_id"))
    source_span = _text(data.get("source_span_id") or row.get("source_span_id"))
    citation = _text(data.get("citation_id") or row.get("citation_id") or data.get("document_hash") or row.get("document_hash"))
    return bool((source_event and source_span) or citation)


def _receipt_chain_complete(data: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    receipt = _text(data.get("receipt_id") or row.get("receipt_id"))
    if not receipt:
        return True
    admission = _text(data.get("admission_id") or row.get("admission_id"))
    return bool(admission and _source_chain_complete(data, row))


def _truth_eligible(data: Mapping[str, Any], row: Mapping[str, Any], nested_authority: Mapping[str, Any]) -> bool:
    if "truth_eligible" in data:
        return bool(data.get("truth_eligible"))
    if "truth_eligible" in row:
        return bool(row.get("truth_eligible"))
    if "truth_eligible" in nested_authority:
        return bool(nested_authority.get("truth_eligible"))
    return False


def _answer_signal(data: Mapping[str, Any], row: Mapping[str, Any]) -> bool:
    return bool(
        data.get("answer_evidence_allowed")
        or data.get("answer_evidence")
        or row.get("answer_evidence_allowed")
        or row.get("answer_evidence")
    )


def _failure_reasons(
    *,
    malformed: bool,
    authority_class: str,
    selection_status: str,
    source_role: str,
    truth_eligible: bool,
    answer_signal: bool,
    source_present: bool,
    source_chain_complete: bool,
    receipt_chain_complete: bool,
    freshness: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if malformed:
        reasons.append("malformed_candidate")
    if not source_present:
        reasons.append("missing_source")
    if selection_status == "selected" and not source_chain_complete:
        reasons.append("selected_missing_source_chain")
    if not receipt_chain_complete:
        reasons.append("fake_or_incomplete_receipt_chain")
    if source_role == "assistant":
        reasons.append("assistant_authored_candidate")
    if authority_class in _UNSAFE_AUTHORITIES:
        reasons.append(f"unsafe_authority:{authority_class}")
    if freshness.get("stale"):
        reasons.append(f"non_current_freshness:{freshness.get('class')}")
    if selection_status == "selected" and not truth_eligible:
        reasons.append("selected_not_truth_eligible")
    if selection_status == "selected" and not answer_signal:
        reasons.append("selected_not_answer_evidence_allowed")
    return sorted(set(reasons))


def normalize_broker_candidate(
    candidate: Any,
    *,
    selection_status: str | None = None,
    selection_reason: str = "",
) -> dict[str, Any]:
    data, row, key, shelf, channel_ranks, dataclass_rrf = _candidate_base(candidate)
    malformed = not bool(shelf and key)
    status = _selection_status(data, explicit_status=selection_status, malformed=malformed)
    nested_selection = _nested(data, "selection")
    nested_authority = _nested(data, "authority")
    authority_class = _authority_class(data, row) if not malformed else "malformed"
    source_role = _text(data.get("source_role") or row.get("source_role") or "memory").casefold()
    freshness = _freshness(data, row)
    source_present = _source_present(data, row, key)
    source_chain_complete = _source_chain_complete(data, row)
    receipt_chain_complete = _receipt_chain_complete(data, row)
    truth_eligible = _truth_eligible(data, row, nested_authority)
    answer_signal = _answer_signal(data, row)
    reasons = _failure_reasons(
        malformed=malformed,
        authority_class=authority_class,
        selection_status=status,
        source_role=source_role,
        truth_eligible=truth_eligible,
        answer_signal=answer_signal,
        source_present=source_present,
        source_chain_complete=source_chain_complete,
        receipt_chain_complete=receipt_chain_complete,
        freshness=freshness,
    )
    answer_truth_allowed = (
        status == "selected"
        and not reasons
        and authority_class in _PROTECTED_AUTHORITIES
        and truth_eligible
        and answer_signal
        and source_present
        and source_chain_complete
        and receipt_chain_complete
    )
    source = _nested(data, "source")
    cost = _nested(data, "cost")
    score = _nested(data, "score")
    raw_id = key or _text(data.get("candidate_id") or data.get("evidence_id")) or repr(type(candidate).__name__)
    channels = _channels(data, row, channel_ranks)
    reason = _text(selection_reason) or _text(nested_selection.get("reason")) or _text(data.get("selection_reason"))
    if not reason and status == "selected":
        reason = "selected_by_existing_runtime"
    if not reason and status in {"suppressed", "dropped", "demoted"}:
        reason = _text(data.get("reason_code")) or "not_selected"
    return {
        "schema": CANDIDATE_SCHEMA,
        "candidate_id": _fingerprint(f"{CANDIDATE_SCHEMA}|{shelf}|{raw_id}"),
        "evidence_fingerprint": _fingerprint(raw_id),
        "shelf": shelf,
        "channels": channels,
        "authority": {
            "class": authority_class,
            "truth_eligible": truth_eligible,
            "answer_evidence_requested": answer_signal,
            "answer_truth_allowed": answer_truth_allowed,
            "protected": bool(data.get("protected") or row.get("protected") or authority_class in _PROTECTED_AUTHORITIES),
            "receipt_present": bool(_text(data.get("receipt_id") or row.get("receipt_id"))),
            "admission_present": bool(_text(data.get("admission_id") or row.get("admission_id"))),
            "source_role": source_role,
        },
        "relevance": {
            "rrf_score": dataclass_rrf or _number(data.get("rrf_score") or score.get("rrf")),
            "keyword_score": _number(data.get("keyword_score") or score.get("keyword")),
            "semantic_score": _number(data.get("semantic_score") or score.get("semantic")),
            "query_token_overlap": _integer(data.get("query_token_overlap") or score.get("query_token_overlap")),
            "channel_count": len(channels),
            "final_rank": _integer(data.get("final_rank") or score.get("final_rank")),
        },
        "freshness": freshness,
        "cost": {
            "token_estimate": _integer(
                data.get("token_estimate")
                or row.get("token_estimate")
                or cost.get("preview_token_estimate")
                or cost.get("token_estimate")
            ),
            "preview_char_count": _integer(cost.get("preview_char_count")),
        },
        "provenance": {
            "source_present": source_present,
            "source_chain_complete": source_chain_complete,
            "receipt_chain_complete": receipt_chain_complete,
            "source_event_present": bool(_text(data.get("source_event_id") or row.get("source_event_id"))),
            "source_span_present": bool(_text(data.get("source_span_id") or row.get("source_span_id"))),
            "retrieval_source": _text(data.get("retrieval_source") or source.get("retrieval_source")),
            "match_mode": _text(data.get("match_mode") or source.get("match_mode")),
            "row_type": _text(data.get("row_type") or row.get("row_type")),
            "stable_key_fingerprint": _fingerprint(data.get("stable_key") or row.get("stable_key"))
            if _text(data.get("stable_key") or row.get("stable_key"))
            else "",
        },
        "selection": {
            "status": status,
            "reason_code": _text(data.get("reason_code")),
            "reason_fingerprint": _fingerprint(reason) if reason else "",
            "drop_reason": _text(data.get("reason_code"))
            or _text(nested_selection.get("suppression_reason"))
            or (_text(nested_selection.get("reason")) if status != "selected" else "")
            or (reasons[0] if reasons and status != "selected" else ""),
        },
        "failure_bundle": {
            "present": bool(reasons),
            "reason_codes": reasons,
        },
        "broker_boundaries": {
            "read_only_projection": True,
            "durable_truth_write": False,
            "provider_choice": False,
            "storage_mutation": False,
        },
        "public_safety": {
            "raw_text_included": False,
            "raw_key_included": False,
            "private_value_included": False,
        },
    }


def _normalize_group(items: Sequence[Any], *, selection_status: str) -> list[dict[str, Any]]:
    return [normalize_broker_candidate(item, selection_status=selection_status) for item in items]


def build_broker_trace(
    *,
    retrieval_trace: Mapping[str, Any] | None = None,
    candidates: Sequence[Any] | None = None,
) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    if retrieval_trace is not None:
        selected.extend(_normalize_group(_sequence(retrieval_trace.get("selected")), selection_status="selected"))
        suppressed.extend(_normalize_group(_sequence(retrieval_trace.get("suppressed")), selection_status="suppressed"))
    if candidates is not None:
        for item in candidates:
            normalized = normalize_broker_candidate(item)
            if normalized["selection"]["status"] == "selected":
                selected.append(normalized)
            else:
                suppressed.append(normalized)
    all_candidates = [*selected, *suppressed]
    trace = {
        "schema": BROKER_TRACE_SCHEMA,
        "mode": "read_only_projection",
        "public_safe": True,
        "broker_boundaries": {
            "read_only_projection": True,
            "durable_truth_write": False,
            "admission_bypass": False,
            "provider_choice": False,
            "storage_mutation": False,
        },
        "selected_count": len(selected),
        "suppressed_count": len(suppressed),
        "candidate_count": len(all_candidates),
        "unsafe_answer_truth_upgrade_count": sum(
            1
            for item in all_candidates
            if item["authority"]["answer_truth_allowed"] is True and item["failure_bundle"]["present"] is True
        ),
        "failure_bundle_count": sum(1 for item in all_candidates if item["failure_bundle"]["present"]),
        "authority_class_counts": _authority_class_counts(all_candidates),
        "selected": selected,
        "suppressed": suppressed,
    }
    errors = validate_broker_trace(trace)
    if errors:
        trace["public_safe"] = False
        trace["validation_errors"] = errors
    return trace


def _authority_class_counts(candidates: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        authority = _nested(candidate, "authority")
        klass = _text(authority.get("class")) or "unknown"
        counts[klass] = counts.get(klass, 0) + 1
    return dict(sorted(counts.items()))


def build_broker_trace_from_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    packet_budget = _nested(packet, "packet_budget")
    decisions = _sequence(packet_budget.get("budget_decisions"))
    candidates: list[dict[str, Any]] = []
    for item in decisions:
        data = _mapping(item)
        decision = _text(data.get("decision"))
        if decision == "selected":
            status = "selected"
        elif decision in {"dropped", "demoted"}:
            status = "suppressed"
        else:
            status = "candidate"
        updated = dict(data)
        updated["selection_status"] = status
        candidates.append(updated)
    return build_broker_trace(candidates=candidates)


def _scan_public_safety(value: Any, *, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}" if path else key_text
            if key_text.lower() in _FORBIDDEN_PUBLIC_KEYS:
                errors.append(f"public_safe_forbidden_key:{child_path}")
            errors.extend(_scan_public_safety(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            errors.extend(_scan_public_safety(child, path=child_path))
    elif isinstance(value, str):
        for marker in _SECRET_VALUE_MARKERS:
            if marker and marker in value:
                errors.append(f"public_safe_forbidden_value:{path}")
                break
    return errors


def validate_broker_trace(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if trace.get("schema") != BROKER_TRACE_SCHEMA:
        errors.append("invalid_broker_trace_schema")
    if trace.get("mode") != "read_only_projection":
        errors.append("broker_not_read_only_projection")
    boundaries = _nested(trace, "broker_boundaries")
    for key in ("durable_truth_write", "admission_bypass", "provider_choice", "storage_mutation"):
        if boundaries.get(key) is not False:
            errors.append(f"broker_boundary_not_false:{key}")
    candidates = [*_sequence(trace.get("selected")), *_sequence(trace.get("suppressed"))]
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            errors.append(f"broker_candidate_not_mapping:{index}")
            continue
        if candidate.get("schema") != CANDIDATE_SCHEMA:
            errors.append(f"invalid_candidate_schema:{index}")
        authority = _nested(candidate, "authority")
        failure = _nested(candidate, "failure_bundle")
        if authority.get("answer_truth_allowed") is True and failure.get("present") is True:
            errors.append(f"unsafe_candidate_answer_truth_upgrade:{index}")
        public_safety = _nested(candidate, "public_safety")
        for key in ("raw_text_included", "raw_key_included", "private_value_included"):
            if public_safety.get(key) is not False:
                errors.append(f"candidate_public_safety_flag_not_false:{index}:{key}")
    if int(trace.get("unsafe_answer_truth_upgrade_count") or 0) != 0:
        errors.append("unsafe_answer_truth_upgrade_count_nonzero")
    errors.extend(_scan_public_safety(trace))
    return sorted(errors)


__all__ = [
    "BROKER_TRACE_SCHEMA",
    "CANDIDATE_SCHEMA",
    "build_broker_trace",
    "build_broker_trace_from_packet",
    "normalize_broker_candidate",
    "validate_broker_trace",
]
