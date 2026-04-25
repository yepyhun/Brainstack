from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping

RELATIVE_DURATION_RE = re.compile(
    r"^(?:(?:remaining\s+for)\s+)?(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>second|seconds|minute|minutes|hour|hours|day|days|week|weeks)\s+remaining"
    r"(?:\s+for\s+.+)?$|^remaining\s+for\s+(?P<prefix_amount>\d+(?:\.\d+)?)\s+"
    r"(?P<prefix_unit>second|seconds|minute|minutes|hour|hours|day|days|week|weeks)$",
    re.IGNORECASE,
)
BARE_DURATION_RE = re.compile(
    r"^(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>second|seconds|minute|minutes|hour|hours|day|days|week|weeks)$",
    re.IGNORECASE,
)
NUMERIC_REMAINING_UNIT_RE = re.compile(
    r"(?:^|_)(?P<unit>seconds?|minutes?|hours?|days?|weeks?)(?:$|_)",
    re.IGNORECASE,
)
VOLATILE_BACKGROUND_STATE_TOKENS = {
    "active",
    "assignment",
    "availability",
    "available",
    "current",
    "hours",
    "progress",
    "remaining",
    "role",
    "state",
    "status",
    "task",
    "testing",
    "time",
}
FIELD_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


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


def infer_relative_duration_valid_to(
    *,
    value_text: str,
    temporal: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None = None,
    attribute: str = "",
) -> str | None:
    """Infer expiry for strict relative-duration state values.

    This is not a query heuristic. It is input grammar hygiene for typed graph
    states that carry values such as "15 hours remaining" without an explicit
    `valid_to`.
    """
    value = str(value_text or "").strip()
    attribute_text = str(attribute or "").strip().casefold()
    match = RELATIVE_DURATION_RE.match(value)
    amount_text = ""
    unit = ""
    if not match:
        bare_match = BARE_DURATION_RE.match(value)
        if bare_match and "remaining" in attribute_text:
            amount_text = bare_match.group("amount")
            unit = bare_match.group("unit").lower()
        else:
            numeric_unit_match = NUMERIC_REMAINING_UNIT_RE.search(attribute_text)
            if not numeric_unit_match or "remaining" not in attribute_text:
                return None
            try:
                float(value)
            except ValueError:
                return None
            amount_text = value
            unit = numeric_unit_match.group("unit").lower()
    else:
        amount_text = match.group("amount") or match.group("prefix_amount") or ""
        unit = (match.group("unit") or match.group("prefix_unit") or "").lower()
    if not amount_text or not unit:
        return None
    amount = float(amount_text)
    if amount <= 0:
        return None
    multiplier = {
        "second": "seconds",
        "seconds": "seconds",
        "minute": "minutes",
        "minutes": "minutes",
        "hour": "hours",
        "hours": "hours",
        "day": "days",
        "days": "days",
        "week": "weeks",
        "weeks": "weeks",
    }[unit]
    base = None
    if isinstance(temporal, Mapping):
        base = _parse_iso(str(temporal.get("observed_at") or "")) or _parse_iso(
            str(temporal.get("valid_from") or "")
        )
    if base is None and isinstance(metadata, Mapping):
        lineage = metadata.get("graph_source_lineage")
        if isinstance(lineage, Mapping):
            base = _parse_iso(str(lineage.get("observed_at") or ""))
    if base is None:
        return None
    delta = timedelta(**{multiplier: amount})
    return _to_iso(base + delta)


def is_background_relative_duration_source(record: Mapping[str, Any]) -> bool:
    metadata = record.get("metadata")
    source = str(record.get("source") or "").strip().casefold()
    if source.startswith("tier2:"):
        return True
    if not isinstance(metadata, Mapping):
        return False
    lineage = metadata.get("graph_source_lineage")
    if isinstance(lineage, Mapping) and str(lineage.get("source_kind") or "").strip().casefold() == "tier2":
        return True
    return str(metadata.get("batch_reason") or "").strip().casefold() in {"idle_window", "batch"}


def _field_tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in FIELD_TOKEN_RE.finditer(str(value or ""))}


def is_unbounded_background_volatile_state(record: Mapping[str, Any]) -> bool:
    """Return true for background graph states that cannot be current authority.

    This is a graph-record authority guard, not a query heuristic. Tier-2 and
    idle-window writes may preserve volatile state as supporting evidence, but
    they must not create unbounded current truth without an explicit validity
    window.
    """
    metadata = record.get("metadata")
    temporal = metadata.get("temporal") if isinstance(metadata, Mapping) else None
    if record.get("valid_to") or (isinstance(temporal, Mapping) and temporal.get("valid_to")):
        return False
    if not is_background_relative_duration_source(record):
        return False
    attribute = str(record.get("attribute") or record.get("predicate") or "")
    tokens = _field_tokens(attribute)
    return bool(tokens.intersection(VOLATILE_BACKGROUND_STATE_TOKENS))


def record_is_effective_at(record: Mapping[str, Any], as_of: str | None = None) -> bool:
    return record_temporal_status(record, as_of=as_of) == "current"


def record_temporal_status(record: Mapping[str, Any], as_of: str | None = None) -> str:
    metadata = record.get("metadata")
    temporal = metadata.get("temporal") if isinstance(metadata, Mapping) else None
    valid_from = _parse_iso(str(record.get("valid_from") or "")) or _parse_iso(
        str((temporal or {}).get("valid_from") or "")
    )
    valid_to = _parse_iso(str(record.get("valid_to") or "")) or _parse_iso(
        str((temporal or {}).get("valid_to") or "")
    )
    if valid_to is None:
        inferred_valid_to = infer_relative_duration_valid_to(
            value_text=str(record.get("value_text") or record.get("object_value") or ""),
            temporal=temporal if isinstance(temporal, Mapping) else None,
            metadata=metadata if isinstance(metadata, Mapping) else None,
            attribute=str(record.get("attribute") or record.get("predicate") or ""),
        )
        if inferred_valid_to and is_background_relative_duration_source(record):
            lineage = metadata.get("graph_source_lineage") if isinstance(metadata, Mapping) else None
            lineage_observed_at = (
                _parse_iso(str(lineage.get("observed_at") or "")) if isinstance(lineage, Mapping) else None
            )
            valid_to = (
                valid_from
                or _parse_iso(str((temporal or {}).get("observed_at") or ""))
                or lineage_observed_at
            )
        else:
            valid_to = _parse_iso(inferred_valid_to)
    if valid_to is None and is_unbounded_background_volatile_state(record):
        return "expired"
    point_in_time = _parse_iso(as_of) or datetime.now(timezone.utc)
    if valid_from and point_in_time < valid_from:
        return "not_yet_valid"
    if valid_to and point_in_time >= valid_to:
        return "expired"
    return "current"
