from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


TELEMETRY_KEY = "retrieval_telemetry"
PROTECTED_PROFILE_CATEGORIES = {"identity", "preference", "shared_work"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_retrieval_telemetry(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(metadata or {})
    telemetry = payload.get(TELEMETRY_KEY)
    if not isinstance(telemetry, dict):
        telemetry = {}
    return {
        "served_count": max(0, int(telemetry.get("served_count") or 0)),
        "match_served_count": max(0, int(telemetry.get("match_served_count") or 0)),
        "fallback_served_count": max(0, int(telemetry.get("fallback_served_count") or 0)),
        "last_served_at": str(telemetry.get("last_served_at") or "").strip(),
    }


def apply_retrieval_telemetry(
    metadata: Dict[str, Any] | None,
    *,
    matched: bool,
    fallback: bool,
    served_at: str | None = None,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    telemetry = read_retrieval_telemetry(payload)
    telemetry["served_count"] += 1
    if matched:
        telemetry["match_served_count"] += 1
    if fallback:
        telemetry["fallback_served_count"] += 1
    telemetry["last_served_at"] = str(served_at or _utc_now_iso())
    payload[TELEMETRY_KEY] = telemetry
    return payload


def is_protected_profile_row(row: Dict[str, Any]) -> bool:
    category = str(row.get("category") or "").strip().lower()
    if category in PROTECTED_PROFILE_CATEGORIES:
        return True
    stable_key = str(row.get("stable_key") or "").strip().lower()
    return stable_key.startswith("identity:") or stable_key.startswith("preference:") or stable_key.startswith("shared_work:")


def profile_priority_adjustment(row: Dict[str, Any]) -> float:
    telemetry = read_retrieval_telemetry(row.get("metadata") if isinstance(row.get("metadata"), dict) else {})
    match_count = telemetry["match_served_count"]
    fallback_count = telemetry["fallback_served_count"]

    adjustment = 0.0
    if match_count > 0:
        adjustment += min(0.12, 0.03 * match_count)
    if not is_protected_profile_row(row) and fallback_count >= 3 and match_count == 0:
        adjustment -= min(0.18, 0.04 * (fallback_count - 2))
    return adjustment


def graph_priority_adjustment(row: Dict[str, Any]) -> float:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if str(row.get("row_type") or "") == "conflict" and isinstance(row.get("conflict_metadata"), dict):
        metadata = row.get("conflict_metadata") or metadata
    telemetry = read_retrieval_telemetry(metadata)
    match_count = telemetry["match_served_count"]
    adjustment = min(0.1, 0.025 * match_count)
    if str(row.get("row_type") or "") == "conflict":
        adjustment += 0.04
    elif str(row.get("row_type") or "") == "state" and bool(row.get("is_current")):
        adjustment += 0.02
    return adjustment
