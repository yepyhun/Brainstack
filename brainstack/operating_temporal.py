from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping


OPERATING_TEMPORAL_SCHEMA = "brainstack.operating_temporal.v1"

VOLATILE_OPERATING_RECORD_TYPES = {
    "active_work",
    "current_commitment",
    "next_step",
    "session_state",
}

WARNING_ONLY_OPERATING_RECORD_TYPES = {
    "recent_work_summary",
}

_STRICT_EN_RELATIVE_DURATION_RE = re.compile(
    r"\b(?:within|in|for)\s+(?P<amount>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>second|seconds|minute|minutes|hour|hours|day|days|week|weeks)\b",
    re.IGNORECASE,
)


def _parse_iso(value: Any) -> datetime | None:
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


def _to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _positive_seconds(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        seconds = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return seconds


def _duration_to_seconds(amount_text: str, unit: str) -> int | None:
    try:
        amount = float(amount_text)
    except ValueError:
        return None
    if amount <= 0:
        return None
    multiplier = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800,
    }.get(unit.lower())
    if multiplier is None:
        return None
    return int(amount * multiplier)


def suggest_operating_expiry_from_text(
    content: str,
    *,
    created_at: str,
    locale_hint: str | None = None,
) -> dict[str, Any] | None:
    """Return a non-authoritative expiry suggestion for narrow known text.

    This helper is deliberately not called by the operating write path. The
    Brainstack core authority path is structured temporal metadata; text
    parsing is only an adapter/helper surface.
    """

    match = _STRICT_EN_RELATIVE_DURATION_RE.search(str(content or ""))
    if not match:
        return None
    base = _parse_iso(created_at)
    seconds = _duration_to_seconds(match.group("amount"), match.group("unit"))
    if base is None or seconds is None:
        return None
    return {
        "schema": OPERATING_TEMPORAL_SCHEMA,
        "authority": "suggestion_only",
        "locale_hint": str(locale_hint or "").strip(),
        "expires_after_seconds": seconds,
        "valid_from": _to_iso(base),
        "valid_to": _to_iso(base + timedelta(seconds=seconds)),
        "source": "strict_text_helper",
    }


def normalize_operating_temporal_metadata(
    *,
    record_type: str,
    created_at: str,
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = _mapping(metadata)
    record_kind = str(record_type or "").strip()
    temporal = _mapping(payload.get("temporal"))
    validity = _mapping(payload.get("operating_temporal"))

    valid_from = _parse_iso(temporal.get("valid_from")) or _parse_iso(created_at)
    valid_to = _parse_iso(temporal.get("valid_to"))
    expires_after_seconds = _positive_seconds(temporal.get("expires_after_seconds"))
    if expires_after_seconds is None:
        expires_after_seconds = _positive_seconds(payload.get("expires_after_seconds"))

    if valid_to is None and expires_after_seconds is not None and valid_from is not None:
        valid_to = valid_from + timedelta(seconds=expires_after_seconds)
        temporal["valid_to"] = _to_iso(valid_to)

    if valid_from is not None and record_kind in VOLATILE_OPERATING_RECORD_TYPES and (valid_to or expires_after_seconds):
        temporal.setdefault("valid_from", _to_iso(valid_from))

    if expires_after_seconds is not None:
        temporal["expires_after_seconds"] = expires_after_seconds

    if temporal:
        payload["temporal"] = temporal

    if record_kind in VOLATILE_OPERATING_RECORD_TYPES:
        validity.update(
            {
                "schema": OPERATING_TEMPORAL_SCHEMA,
                "record_class": "volatile_operating_truth",
                "authority": "structured_temporal_metadata" if valid_to else "unknown_expiry",
                "expiry_policy": "structured_validity_window" if valid_to else "unknown_expiry",
            }
        )
        if valid_to:
            validity["valid_to"] = _to_iso(valid_to)
        elif created_at:
            validity["created_at"] = str(created_at)
        payload["operating_temporal"] = validity
    elif record_kind in WARNING_ONLY_OPERATING_RECORD_TYPES and not valid_to:
        validity.update(
            {
                "schema": OPERATING_TEMPORAL_SCHEMA,
                "record_class": "warning_only_operating_truth",
                "authority": "unknown_expiry",
                "expiry_policy": "unknown_expiry",
            }
        )
        payload["operating_temporal"] = validity

    return payload


def operating_temporal_status(row: Mapping[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    metadata = _mapping(row.get("metadata"))
    temporal = _mapping(metadata.get("temporal"))
    record_kind = str(row.get("record_type") or "").strip()
    now = _parse_iso(as_of) or datetime.now(timezone.utc)

    valid_from = _parse_iso(temporal.get("valid_from")) or _parse_iso(row.get("created_at"))
    valid_to = _parse_iso(temporal.get("valid_to"))
    if valid_to is None:
        seconds = _positive_seconds(temporal.get("expires_after_seconds"))
        if seconds is not None and valid_from is not None:
            valid_to = valid_from + timedelta(seconds=seconds)

    if record_kind not in VOLATILE_OPERATING_RECORD_TYPES | WARNING_ONLY_OPERATING_RECORD_TYPES:
        status = "not_time_sensitive"
    elif valid_from is not None and now < valid_from:
        status = "not_yet_valid"
    elif valid_to is not None and now >= valid_to:
        status = "expired"
    elif valid_to is not None:
        status = "current"
    else:
        status = "unknown_expiry"

    age_seconds = None
    if valid_from is not None:
        age_seconds = max(int((now - valid_from).total_seconds()), 0)

    return {
        "schema": OPERATING_TEMPORAL_SCHEMA,
        "status": status,
        "record_type": record_kind,
        "valid_from": _to_iso(valid_from),
        "valid_to": _to_iso(valid_to),
        "age_seconds": age_seconds,
    }


def operating_temporal_warning(row: Mapping[str, Any], *, as_of: str | None = None) -> str:
    status = operating_temporal_status(row, as_of=as_of)
    state = str(status.get("status") or "")
    if state == "not_time_sensitive":
        return ""
    age = status.get("age_seconds")
    age_part = f"; age={age}s" if isinstance(age, int) else ""
    valid_to = str(status.get("valid_to") or "")
    if state == "current" and valid_to:
        return f"freshness: current until {valid_to}{age_part}"
    if state == "expired":
        return f"freshness: expired at {valid_to or 'unknown'}{age_part}"
    if state == "not_yet_valid":
        return f"freshness: not yet valid{age_part}"
    if state == "unknown_expiry":
        return f"freshness: volatile record with unknown expiry{age_part}"
    return ""
