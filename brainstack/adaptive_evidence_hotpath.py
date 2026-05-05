"""Public-safe hot-path baseline reporting for adaptive evidence work.

This module is intentionally read-only. It summarizes already-built Brainstack
working-memory packets and existing diagnostic reports; it does not retrieve,
rank, allocate, write storage, or alter runtime behavior.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .adaptive_evidence_broker import build_broker_trace_from_packet, validate_broker_trace

HOTPATH_REPORT_SCHEMA = "brainstack.adaptive_evidence_hotpath_report.v1"

_SHELF_PACKET_KEYS: tuple[tuple[str, str], ...] = (
    ("profile", "profile_items"),
    ("task", "task_rows"),
    ("operating", "operating_rows"),
    ("continuity_match", "matched"),
    ("continuity_recent", "recent"),
    ("transcript", "transcript_rows"),
    ("graph", "graph_rows"),
    ("corpus", "corpus_rows"),
)

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
    "raw_transcript",
    "transcript_text",
    "transcript_payload",
}

_SECRET_VALUE_MARKERS = (
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "sk-",
    "ghp_",
    "github_pat_",
    "Example private raw memory text must never appear",
)

_PROTECTED_PACKET_BUDGET_FLAGS = (
    "answer_evidence_preserved",
    "receipt_coverage_preserved",
    "authority_fields_preserved",
    "scope_fields_preserved",
    "correction_fields_preserved",
)

_DONOR_FIRST_PROOF_MAP = (
    {
        "donor_family": "Graphiti-style temporal graph",
        "brainstack_surface": "routing.temporal + graph_rows",
        "s01_role": "measure_only",
        "truth_mutation": False,
    },
    {
        "donor_family": "MemPalace-style packet budget",
        "brainstack_surface": "packet_budget telemetry",
        "s01_role": "shadow_measurement_only",
        "truth_mutation": False,
    },
    {
        "donor_family": "Hindsight-style source/receipt authority",
        "brainstack_surface": "protected_truth_counters",
        "s01_role": "preservation_counter_only",
        "truth_mutation": False,
    },
    {
        "donor_family": "Corpus retrieval adapter",
        "brainstack_surface": "corpus_rows + channel fanout",
        "s01_role": "measure_only",
        "truth_mutation": False,
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


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


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _round_ms(value: float) -> float:
    return round(max(0.0, float(value or 0.0)), 3)


def _decision_counts(decisions: Sequence[Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in decisions:
        decision = _text(_mapping(item).get("decision")) or "unknown"
        counts[decision] += 1
    return counts


def _reason_counts(decisions: Sequence[Any]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for item in decisions:
        reason = _text(_mapping(item).get("reason_code")) or "<missing>"
        counts[reason] += 1
    return [{"reason_code": reason, "count": count} for reason, count in sorted(counts.items())]


def _public_route_summary(routing: Mapping[str, Any]) -> dict[str, Any]:
    reason = _text(routing.get("reason"))
    error = _text(routing.get("resolution_error"))
    return {
        "requested_mode": _text(routing.get("requested_mode")) or "fact",
        "applied_mode": _text(routing.get("applied_mode")) or "fact",
        "source": _text(routing.get("source")),
        "fallback_used": bool(routing.get("fallback_used")),
        "resolution_status": _text(routing.get("resolution_status")),
        "reason_present": bool(reason),
        "reason_fingerprint": _fingerprint(reason) if reason else "",
        "resolution_error_class": _text(routing.get("resolution_error_class")),
        "resolution_error_fingerprint": _fingerprint(error) if error else "",
    }


def _channel_summary(channels: Sequence[Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in channels:
        channel = _mapping(item)
        output.append(
            {
                "name": _text(channel.get("name")),
                "status": _text(channel.get("status")),
                "reason_present": bool(_text(channel.get("reason"))),
                "reason_fingerprint": _fingerprint(channel.get("reason")) if _text(channel.get("reason")) else "",
                "candidate_count": _integer(channel.get("candidate_count")),
            }
        )
    return output


def _shelf_fanout(packet: Mapping[str, Any]) -> dict[str, int]:
    return {public_name: len(_sequence(packet.get(packet_key))) for public_name, packet_key in _SHELF_PACKET_KEYS}


def _packet_budget_summary(packet_budget: Mapping[str, Any]) -> dict[str, Any]:
    decisions = _sequence(packet_budget.get("budget_decisions"))
    counts = _decision_counts(decisions)
    return {
        "mode": _text(packet_budget.get("mode")),
        "enabled": bool(packet_budget.get("enabled")),
        "applied_to_output": bool(packet_budget.get("applied_to_output")),
        "status": _text(packet_budget.get("status")),
        "max_candidate_tokens": packet_budget.get("max_candidate_tokens"),
        "fail_closed": bool(packet_budget.get("fail_closed")),
        "budget_decision_count": len(decisions),
        "budget_selected": int(counts.get("selected", 0)),
        "budget_dropped": int(counts.get("dropped", 0)),
        "budget_demoted": int(counts.get("demoted", 0)),
        "reason_code_counts": _reason_counts(decisions),
        "budget_reason_code_registry_pass": bool(packet_budget.get("budget_reason_code_registry_pass", True)),
        "raw_text_in_budget_trace": bool(packet_budget.get("raw_text_in_budget_trace", False)),
    }


def _token_estimate(packet_budget: Mapping[str, Any]) -> dict[str, int]:
    return {
        "estimated_tokens_before": _integer(
            packet_budget.get("estimated_tokens_before", packet_budget.get("estimated_tokens"))
        ),
        "selected_candidate_tokens": _integer(packet_budget.get("selected_candidate_tokens")),
        "dropped_candidate_tokens": _integer(packet_budget.get("dropped_candidate_tokens")),
        "authority_minimum_tokens": _integer(packet_budget.get("authority_minimum_tokens")),
    }


def _protected_truth_counters(packet: Mapping[str, Any], packet_budget: Mapping[str, Any]) -> dict[str, Any]:
    protected_shelves = {
        "profile": len(_sequence(packet.get("profile_items"))),
        "task": len(_sequence(packet.get("task_rows"))),
        "operating": len(_sequence(packet.get("operating_rows"))),
        "graph": len(_sequence(packet.get("graph_rows"))),
        "corpus": len(_sequence(packet.get("corpus_rows"))),
    }
    protected_drop_attempts = sum(1 for key in _PROTECTED_PACKET_BUDGET_FLAGS if packet_budget.get(key, True) is False)
    return {
        "protected_shelf_counts": protected_shelves,
        "protected_candidate_count": sum(protected_shelves.values()),
        "protected_drop_attempts": protected_drop_attempts,
        "answer_evidence_preserved": bool(packet_budget.get("answer_evidence_preserved", True)),
        "receipt_coverage_preserved": bool(packet_budget.get("receipt_coverage_preserved", True)),
        "authority_fields_preserved": bool(packet_budget.get("authority_fields_preserved", True)),
        "scope_fields_preserved": bool(packet_budget.get("scope_fields_preserved", True)),
        "correction_fields_preserved": bool(packet_budget.get("correction_fields_preserved", True)),
    }


def _write_amplification_summary(bloat_report: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(bloat_report, Mapping):
        return {
            "available": False,
            "storage_rows": 0,
            "answer_authority_rows": 0,
            "ratio": 0.0,
            "status": "not_available",
            "issue_count": 0,
        }
    metrics = _mapping(bloat_report.get("metrics"))
    amplification = _mapping(metrics.get("write_amplification"))
    statuses = _mapping(bloat_report.get("metric_statuses"))
    amplification_status = _mapping(statuses.get("write_amplification"))
    return {
        "available": True,
        "storage_rows": _integer(amplification.get("storage_rows")),
        "answer_authority_rows": _integer(amplification.get("answer_authority_rows")),
        "ratio": _float(amplification.get("ratio")),
        "status": _text(amplification_status.get("status")) or _text(bloat_report.get("status")),
        "issue_count": _integer(bloat_report.get("issue_count")),
    }


def _failure_bundle(
    *,
    packet: Mapping[str, Any],
    validation_errors: Sequence[str] = (),
    storage_mutation_count: int = 0,
    behavior_changed_from_unbudgeted: bool = False,
) -> dict[str, Any]:
    routing = _mapping(packet.get("routing"))
    packet_budget = _mapping(packet.get("packet_budget"))
    reasons: list[str] = []
    if validation_errors:
        reasons.append("hotpath_report_validation_errors")
    if storage_mutation_count:
        reasons.append("read_only_storage_mutation_detected")
    if behavior_changed_from_unbudgeted:
        reasons.append("measurement_changed_unbudgeted_packet")
    if routing.get("resolution_status") == "failed":
        reasons.append("route_resolution_failed")
    if packet_budget.get("raw_text_in_budget_trace") is True:
        reasons.append("packet_budget_raw_text_trace_detected")
    if packet_budget.get("budget_reason_code_registry_pass") is False:
        reasons.append("packet_budget_reason_registry_failed")
    return {
        "present": bool(reasons),
        "reason_codes": sorted(set(reasons)),
        "route_resolution_error_class": _text(routing.get("resolution_error_class")),
        "packet_budget_fail_closed": bool(packet_budget.get("fail_closed")),
    }


def summarize_hotpath_case(
    *,
    case_id: str,
    query_class: str,
    query_text: str,
    packet: Mapping[str, Any],
    latency_ms: float,
    bloat_report: Mapping[str, Any] | None = None,
    behavior_changed_from_unbudgeted: bool = False,
    storage_mutation_count: int = 0,
    validation_errors: Sequence[str] = (),
) -> dict[str, Any]:
    """Summarize one already-built packet without copying private text fields."""

    packet_budget = _mapping(packet.get("packet_budget"))
    decisions = _sequence(packet_budget.get("budget_decisions"))
    decision_counts = _decision_counts(decisions)
    shelf_fanout = _shelf_fanout(packet)
    adaptive_evidence_broker = build_broker_trace_from_packet(packet)
    broker_errors = validate_broker_trace(adaptive_evidence_broker)
    case = {
        "case_id": _text(case_id),
        "query_class": _text(query_class),
        "query_fingerprint": _fingerprint(query_text),
        "route": _public_route_summary(_mapping(packet.get("routing"))),
        "channels": _channel_summary(_sequence(packet.get("channels"))),
        "shelf_fanout": shelf_fanout,
        "latency_ms": _round_ms(latency_ms),
        "candidate_counts": {
            "shelf_total": sum(shelf_fanout.values()),
            "fused": len(_sequence(packet.get("fused_candidates"))),
            "budget_input": len(decisions),
            "budget_selected": int(decision_counts.get("selected", 0)),
            "budget_dropped": int(decision_counts.get("dropped", 0)),
            "budget_demoted": int(decision_counts.get("demoted", 0)),
        },
        "token_estimate": _token_estimate(packet_budget),
        "packet_budget": _packet_budget_summary(packet_budget),
        "protected_truth_counters": _protected_truth_counters(packet, packet_budget),
        "adaptive_evidence_broker": {
            "schema": adaptive_evidence_broker.get("schema"),
            "mode": adaptive_evidence_broker.get("mode"),
            "public_safe": bool(adaptive_evidence_broker.get("public_safe")),
            "candidate_count": _integer(adaptive_evidence_broker.get("candidate_count")),
            "selected_count": _integer(adaptive_evidence_broker.get("selected_count")),
            "suppressed_count": _integer(adaptive_evidence_broker.get("suppressed_count")),
            "failure_bundle_count": _integer(adaptive_evidence_broker.get("failure_bundle_count")),
            "unsafe_answer_truth_upgrade_count": _integer(
                adaptive_evidence_broker.get("unsafe_answer_truth_upgrade_count")
            ),
            "validation_error_count": len(broker_errors),
            "authority_class_counts": dict(adaptive_evidence_broker.get("authority_class_counts") or {}),
        },
        "write_amplification": _write_amplification_summary(bloat_report),
        "read_only_probe": {
            "behavior_changed_from_unbudgeted": bool(behavior_changed_from_unbudgeted),
            "storage_mutation_count": int(storage_mutation_count),
        },
        "public_safety": {
            "text_payload_included": False,
            "packet_block_included": False,
            "query_text_included": False,
            "route_reason_text_included": False,
        },
    }
    case["failure_bundle"] = _failure_bundle(
        packet=packet,
        validation_errors=[*validation_errors, *broker_errors],
        storage_mutation_count=storage_mutation_count,
        behavior_changed_from_unbudgeted=behavior_changed_from_unbudgeted,
    )
    return case


def _aggregate_cases(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    latency_values = [_float(case.get("latency_ms")) for case in cases]
    token_before = sum(_integer(_mapping(case.get("token_estimate")).get("estimated_tokens_before")) for case in cases)
    token_selected = sum(_integer(_mapping(case.get("token_estimate")).get("selected_candidate_tokens")) for case in cases)
    token_dropped = sum(_integer(_mapping(case.get("token_estimate")).get("dropped_candidate_tokens")) for case in cases)
    shelf_totals: Counter[str] = Counter()
    for case in cases:
        shelf_totals.update({key: _integer(value) for key, value in _mapping(case.get("shelf_fanout")).items()})
    return {
        "case_count": len(cases),
        "query_classes": sorted({_text(case.get("query_class")) for case in cases}),
        "latency_ms_total": round(sum(latency_values), 3),
        "latency_ms_max": round(max(latency_values, default=0.0), 3),
        "candidate_tokens_estimated_before": token_before,
        "candidate_tokens_selected": token_selected,
        "candidate_tokens_dropped": token_dropped,
        "shelf_fanout_totals": dict(sorted(shelf_totals.items())),
        "failure_bundle_count": sum(1 for case in cases if _mapping(case.get("failure_bundle")).get("present")),
        "protected_drop_attempts": sum(
            _integer(_mapping(case.get("protected_truth_counters")).get("protected_drop_attempts"))
            for case in cases
        ),
    }


def build_hotpath_report(
    *,
    cases: Sequence[Mapping[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_cases = [dict(case) for case in cases]
    report = {
        "schema": HOTPATH_REPORT_SCHEMA,
        "generated_at": _text(generated_at) or _utc_now(),
        "public_safe": True,
        "read_only": True,
        "runtime_behavior_changed": False,
        "behavior_delta_count": sum(
            1
            for case in normalized_cases
            if _mapping(case.get("read_only_probe")).get("behavior_changed_from_unbudgeted") is True
        ),
        "storage_mutation_count": sum(
            _integer(_mapping(case.get("read_only_probe")).get("storage_mutation_count"))
            for case in normalized_cases
        ),
        "donor_first_proof_map": [dict(item) for item in _DONOR_FIRST_PROOF_MAP],
        "aggregate": _aggregate_cases(normalized_cases),
        "cases": normalized_cases,
    }
    errors = validate_hotpath_report(report)
    if errors:
        report["public_safe"] = False
        report["validation_errors"] = errors
    return report


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


def validate_hotpath_report(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schema") != HOTPATH_REPORT_SCHEMA:
        errors.append("invalid_schema")
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("missing_cases")
        cases = []
    required_case_keys = {
        "case_id",
        "query_class",
        "query_fingerprint",
        "route",
        "shelf_fanout",
        "latency_ms",
        "candidate_counts",
        "token_estimate",
        "protected_truth_counters",
        "adaptive_evidence_broker",
        "write_amplification",
        "failure_bundle",
        "public_safety",
    }
    for index, case in enumerate(cases):
        if not isinstance(case, Mapping):
            errors.append(f"case_not_mapping:{index}")
            continue
        missing = sorted(required_case_keys - set(case.keys()))
        for key in missing:
            errors.append(f"case_missing_{key}:{index}")
        public_safety = _mapping(case.get("public_safety"))
        for key in (
            "text_payload_included",
            "packet_block_included",
            "query_text_included",
            "route_reason_text_included",
        ):
            if public_safety.get(key) is not False:
                errors.append(f"case_public_safety_flag_not_false:{index}:{key}")
        packet_budget = _mapping(case.get("packet_budget"))
        if packet_budget.get("raw_text_in_budget_trace") is True:
            errors.append(f"case_packet_budget_raw_text_trace:{index}")
        read_only_probe = _mapping(case.get("read_only_probe"))
        if read_only_probe.get("behavior_changed_from_unbudgeted") is True:
            errors.append(f"case_behavior_changed_from_unbudgeted:{index}")
        broker = _mapping(case.get("adaptive_evidence_broker"))
        if _integer(broker.get("unsafe_answer_truth_upgrade_count")) != 0:
            errors.append(f"case_broker_unsafe_answer_truth_upgrade:{index}")
        if _integer(broker.get("validation_error_count")) != 0:
            errors.append(f"case_broker_validation_errors:{index}")
    errors.extend(_scan_public_safety(report))
    # Stable order while preserving duplicates from path-specific failures.
    return sorted(errors)


__all__ = [
    "HOTPATH_REPORT_SCHEMA",
    "build_hotpath_report",
    "summarize_hotpath_case",
    "validate_hotpath_report",
]
