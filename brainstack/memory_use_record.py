"""Public-safe telemetry for whether memory was actually used.

Memory-use records are operating/eval telemetry. They are never user truth,
profile memory, current truth, or model-facing recall material.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


MEMORY_USE_RECORD_SCHEMA = "brainstack.memory_use_record.v1"
STORAGE_LANE = "operating_telemetry"

FORBIDDEN_RAW_FIELDS = {
    "answer",
    "answer_text",
    "packet",
    "packet_text",
    "raw_answer",
    "raw_context",
    "raw_packet",
    "raw_transcript",
    "transcript",
    "transcript_text",
}

PRIVATE_RUNTIME_MARKERS = (
    "/private/runtime/path",
    "private_user_handle",
    "private_agent_name",
    "private_project_code",
    "private_chat_platform",
    "private_container_name",
)


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    if values is None:
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _public_metric(value: Any) -> Any:
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _public_metric(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_public_metric(item) for item in value]
    return str(value)


def _stable_record_id(payload: Mapping[str, Any]) -> str:
    source = {
        "consumer_id": payload.get("consumer_id"),
        "task_id": payload.get("task_id"),
        "source_packet_id": payload.get("source_packet_id"),
        "selected_memory_ids": payload.get("selected_memory_ids"),
        "used_memory_ids": payload.get("used_memory_ids"),
        "ignored_memory_ids": payload.get("ignored_memory_ids"),
        "provenance_refs": payload.get("provenance_refs"),
        "outcome_metrics": payload.get("outcome_metrics"),
    }
    encoded = json.dumps(source, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return f"mur_{digest}"


def build_memory_use_record(
    *,
    consumer_id: str,
    task_id: str,
    source_packet_id: str,
    selected_memory_ids: Iterable[Any] | None = None,
    used_memory_ids: Iterable[Any] | None = None,
    ignored_memory_ids: Iterable[Any] | None = None,
    provenance_refs: Iterable[Any] | None = None,
    outcome_metrics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    selected = _clean_list(selected_memory_ids)
    used = _clean_list(used_memory_ids)
    ignored = _clean_list(ignored_memory_ids)
    record: dict[str, Any] = {
        "schema": MEMORY_USE_RECORD_SCHEMA,
        "truth_eligible": False,
        "model_facing_default": False,
        "storage_lane": STORAGE_LANE,
        "consumer_id": str(consumer_id).strip(),
        "task_id": str(task_id).strip(),
        "source_packet_id": str(source_packet_id).strip(),
        "selected_memory_ids": selected,
        "used_memory_ids": used,
        "ignored_memory_ids": ignored,
        "provenance_refs": _clean_list(provenance_refs),
        "outcome_metrics": _public_metric(dict(outcome_metrics or {})),
        "selected_count": len(selected),
        "used_count": len(used),
        "ignored_count": len(ignored),
    }
    record["record_id"] = _stable_record_id(record)
    return record


def validate_memory_use_record(record: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if record.get("schema") != MEMORY_USE_RECORD_SCHEMA:
        issues.append("invalid_schema")
    if record.get("truth_eligible") is not False:
        issues.append("truth_eligible_must_be_false")
    if record.get("model_facing_default") is not False:
        issues.append("model_facing_default_must_be_false")
    if record.get("storage_lane") != STORAGE_LANE:
        issues.append("storage_lane_must_be_operating_telemetry")
    for field in sorted(FORBIDDEN_RAW_FIELDS):
        if field in record:
            issues.append(f"forbidden_raw_field:{field}")
    text = json.dumps(record, ensure_ascii=True, sort_keys=True, default=str)
    for marker in PRIVATE_RUNTIME_MARKERS:
        if marker in text:
            issues.append(f"private_marker_leak:{marker}")
    for field in ("consumer_id", "task_id", "source_packet_id", "record_id"):
        if not str(record.get(field) or "").strip():
            issues.append(f"missing_{field}")
    selected = set(_clean_list(record.get("selected_memory_ids") if isinstance(record.get("selected_memory_ids"), list) else []))
    used = set(_clean_list(record.get("used_memory_ids") if isinstance(record.get("used_memory_ids"), list) else []))
    if used and not used.issubset(selected):
        issues.append("used_ids_must_be_subset_of_selected_ids")
    return sorted(set(issues))


def summarize_memory_use_records(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    records_list = list(records)
    selected_ids: set[str] = set()
    used_ids: set[str] = set()
    invalid_count = 0
    for record in records_list:
        if validate_memory_use_record(record):
            invalid_count += 1
        selected_ids.update(_clean_list(record.get("selected_memory_ids") if isinstance(record.get("selected_memory_ids"), list) else []))
        used_ids.update(_clean_list(record.get("used_memory_ids") if isinstance(record.get("used_memory_ids"), list) else []))
    usage_rate = (len(used_ids) / len(selected_ids)) if selected_ids else 0.0
    return {
        "schema": "brainstack.memory_use_record_summary.v1",
        "record_count": len(records_list),
        "invalid_record_count": invalid_count,
        "selected_memory_id_count": len(selected_ids),
        "used_memory_id_count": len(used_ids),
        "usage_rate": usage_rate,
        "truth_eligible": False,
        "model_facing_default": False,
        "storage_lane": STORAGE_LANE,
    }


__all__ = [
    "MEMORY_USE_RECORD_SCHEMA",
    "build_memory_use_record",
    "summarize_memory_use_records",
    "validate_memory_use_record",
]
