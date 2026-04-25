from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, Mapping


CONSOLIDATION_SOURCE_SCHEMA_VERSION = "brainstack.consolidation_source.v1"


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _content_hash(value: Any) -> str:
    text = _compact(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


def _row_id(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def build_consolidation_source(
    rows: Iterable[Mapping[str, Any]],
    *,
    source_kind: str,
) -> Dict[str, Any]:
    normalized_rows = []
    source_ids = []
    prefix = _compact(source_kind) or "source"
    for row in rows:
        row_id = _row_id(row)
        if row_id <= 0:
            continue
        source_id = f"{prefix}:{row_id}"
        source_ids.append(source_id)
        normalized_rows.append(
            {
                "source_id": source_id,
                "kind": _compact(row.get("kind")),
                "turn_number": int(row.get("turn_number") or 0),
                "content_hash": _content_hash(row.get("content")),
                "created_at": _compact(row.get("created_at")),
            }
        )
    normalized_rows.sort(key=lambda item: str(item["source_id"]))
    fingerprint_payload = json.dumps(normalized_rows, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {
        "schema": CONSOLIDATION_SOURCE_SCHEMA_VERSION,
        "source_kind": prefix,
        "source_ids": source_ids,
        "source_count": len(source_ids),
        "source_fingerprint": hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:24]
        if normalized_rows
        else "",
    }


def consolidation_source_status(
    metadata: Mapping[str, Any] | None,
    *,
    source_rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    payload = metadata if isinstance(metadata, Mapping) else {}
    source = payload.get("consolidation_source")
    if not isinstance(source, Mapping):
        return {"status": "untracked", "source_kind": "", "source_count": 0}
    expected_ids = [str(item) for item in list(source.get("source_ids") or []) if str(item or "").strip()]
    source_kind = _compact(source.get("source_kind"))
    if not expected_ids or not source_kind:
        return {"status": "degraded_missing_source", "source_kind": source_kind, "source_count": 0}

    rows_by_source_id = {f"{source_kind}:{_row_id(row)}": dict(row) for row in source_rows if _row_id(row) > 0}
    matched_rows = [rows_by_source_id[source_id] for source_id in expected_ids if source_id in rows_by_source_id]
    if len(matched_rows) != len(expected_ids):
        return {
            "status": "degraded_missing_source",
            "source_kind": source_kind,
            "source_count": len(expected_ids),
            "matched_source_count": len(matched_rows),
        }

    current = build_consolidation_source(matched_rows, source_kind=source_kind)
    status = "current" if current.get("source_fingerprint") == source.get("source_fingerprint") else "stale_source_changed"
    return {
        "status": status,
        "source_kind": source_kind,
        "source_count": len(expected_ids),
        "matched_source_count": len(matched_rows),
        "source_fingerprint": str(source.get("source_fingerprint") or ""),
    }
