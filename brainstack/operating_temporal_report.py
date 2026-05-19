from __future__ import annotations

from collections import Counter
import hashlib
import sqlite3
from typing import Any, Mapping

from .operating_temporal import (
    VOLATILE_OPERATING_RECORD_TYPES,
    operating_temporal_status,
    suggest_operating_expiry_from_text,
)
from .storage.store_runtime import _decode_json_object


REPORT_SCHEMA = "brainstack.operating_temporal_hygiene_report.v1"


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:12]


def _row_to_dict(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    item = dict(row)
    if "metadata_json" in item:
        item["metadata"] = _decode_json_object(item.pop("metadata_json"))
    return item


def _age_bucket(age_seconds: Any) -> str:
    if not isinstance(age_seconds, int):
        return "unknown"
    if age_seconds < 3600:
        return "lt_1h"
    if age_seconds < 86400:
        return "lt_1d"
    if age_seconds < 604800:
        return "lt_7d"
    return "gte_7d"


def build_operating_temporal_hygiene_report(conn: sqlite3.Connection, *, limit: int = 20) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT id, stable_key, principal_scope_key, record_type, content, metadata_json, created_at, updated_at
        FROM operating_records
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()

    status_counts: Counter[str] = Counter()
    age_buckets: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []

    for raw in rows:
        row = _row_to_dict(raw)
        status = operating_temporal_status(row)
        state = str(status.get("status") or "unknown")
        status_counts[state] += 1
        if str(row.get("record_type") or "") in VOLATILE_OPERATING_RECORD_TYPES:
            age_buckets[_age_bucket(status.get("age_seconds"))] += 1
        if state == "unknown_expiry" and len(candidates) < max(int(limit or 0), 0):
            suggestion = suggest_operating_expiry_from_text(
                str(row.get("content") or ""),
                created_at=str(row.get("created_at") or ""),
            )
            candidates.append(
                {
                    "id": int(row.get("id") or 0),
                    "stable_key_hash": _stable_hash(row.get("stable_key")),
                    "record_type": str(row.get("record_type") or ""),
                    "status": state,
                    "age_bucket": _age_bucket(status.get("age_seconds")),
                    "text_helper_suggestion_present": suggestion is not None,
                    "mutation": "none",
                }
            )

    return {
        "schema": REPORT_SCHEMA,
        "read_only": True,
        "raw_content_included": False,
        "row_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "volatile_age_buckets": dict(sorted(age_buckets.items())),
        "unknown_expiry_candidate_count": int(status_counts.get("unknown_expiry", 0)),
        "dry_run_candidates": candidates,
    }
