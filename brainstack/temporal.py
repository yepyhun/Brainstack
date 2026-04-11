from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def _parse_iso(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_iso(parsed: datetime | None) -> str | None:
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat()


def normalize_temporal_fields(
    *,
    observed_at: str | None = None,
    valid_at: str | None = None,
    valid_from: str | None = None,
    valid_to: str | None = None,
    supersedes: str | None = None,
    superseded_by: str | None = None,
    episode_id: str | None = None,
) -> dict[str, Any]:
    normalized_observed_at = _to_iso(_parse_iso(observed_at))
    normalized_valid_at = _to_iso(_parse_iso(valid_at))
    normalized_valid_from = _to_iso(_parse_iso(valid_from) or _parse_iso(valid_at) or _parse_iso(observed_at))
    normalized_valid_to = _to_iso(_parse_iso(valid_to))

    normalized: dict[str, Any] = {}
    if normalized_observed_at:
        normalized["observed_at"] = normalized_observed_at
    if normalized_valid_at:
        normalized["valid_at"] = normalized_valid_at
    if normalized_valid_from:
        normalized["valid_from"] = normalized_valid_from
    if normalized_valid_to:
        normalized["valid_to"] = normalized_valid_to

    for key, value in (
        ("supersedes", supersedes),
        ("superseded_by", superseded_by),
        ("episode_id", episode_id),
    ):
        text = str(value or "").strip()
        if text:
            normalized[key] = text
    return normalized


def merge_temporal(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(existing, Mapping):
        payload.update(existing)
    if isinstance(incoming, Mapping):
        payload.update(incoming)
    return normalize_temporal_fields(
        observed_at=payload.get("observed_at"),
        valid_at=payload.get("valid_at"),
        valid_from=payload.get("valid_from"),
        valid_to=payload.get("valid_to"),
        supersedes=payload.get("supersedes"),
        superseded_by=payload.get("superseded_by"),
        episode_id=payload.get("episode_id"),
    )


def record_is_effective_at(record: Mapping[str, Any], as_of: str | None = None) -> bool:
    metadata = record.get("metadata")
    temporal = metadata.get("temporal") if isinstance(metadata, Mapping) else None
    valid_from = _parse_iso(str(record.get("valid_from") or "")) or _parse_iso(
        str((temporal or {}).get("valid_from") or "")
    )
    valid_to = _parse_iso(str(record.get("valid_to") or "")) or _parse_iso(
        str((temporal or {}).get("valid_to") or "")
    )
    point_in_time = _parse_iso(as_of) or datetime.now(timezone.utc)
    if valid_from and point_in_time < valid_from:
        return False
    if valid_to and point_in_time >= valid_to:
        return False
    return True
