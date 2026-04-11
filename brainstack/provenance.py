from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


PROVENANCE_ID_LIST_KEYS = frozenset(
    {
        "resource_ids",
        "extract_ids",
        "claim_ids",
        "entity_ids",
        "relation_ids",
        "source_ids",
        "source_event_ids",
        "merged_record_ids",
    }
)
PROVENANCE_STRING_KEYS = frozenset(
    {
        "event_id",
        "trace_id",
        "correlation_id",
        "origin",
        "status_reason",
        "replacement_record_id",
        "merge_reason",
        "supersedes",
    }
)


def _is_id_list_key(key: str) -> bool:
    return key in PROVENANCE_ID_LIST_KEYS or key.endswith("_ids")


def _normalize_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    return sorted({str(item).strip() for item in items if str(item).strip()})


def normalize_provenance(provenance: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(provenance, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in provenance.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if _is_id_list_key(normalized_key):
            items = _normalize_id_list(value)
            if items:
                normalized[normalized_key] = items
            continue
        if normalized_key in PROVENANCE_STRING_KEYS:
            text = str(value).strip() if value is not None else ""
            if text:
                normalized[normalized_key] = text
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                normalized[normalized_key] = text
            continue
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            normalized[normalized_key] = deepcopy(value)
        else:
            normalized[normalized_key] = value
    return normalized


def merge_provenance(*parts: Mapping[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for part in parts:
        normalized = normalize_provenance(part)
        for key, value in normalized.items():
            if _is_id_list_key(key):
                merged[key] = _normalize_id_list(list(merged.get(key, [])) + list(value))
            else:
                merged[key] = value
    return merged


def summarize_provenance(provenance: Mapping[str, Any] | None, *, max_parts: int = 3) -> str:
    normalized = normalize_provenance(provenance)
    if not normalized:
        return ""
    parts: list[str] = []
    source_ids = normalized.get("source_ids")
    if isinstance(source_ids, list) and source_ids:
        shown = ",".join(str(item) for item in source_ids[:2])
        if len(source_ids) > 2:
            shown = f"{shown}+{len(source_ids) - 2}"
        parts.append(f"sources={shown}")
    for key, label in (
        ("tier", "tier"),
        ("turn_number", "turn"),
        ("origin", "origin"),
        ("admission_reason", "reason"),
        ("status_reason", "status"),
    ):
        value = normalized.get(key)
        if value not in (None, "", []):
            parts.append(f"{label}={value}")
    return " ; ".join(parts[:max_parts])
