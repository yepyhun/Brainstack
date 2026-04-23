from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Mapping

from .operating_truth import OPERATING_RECORD_TYPES
from .structured_understanding import (
    ROUTE_FACT,
    ROUTE_MODES,
    current_local_date,
    resolve_user_timezone,
)
from .task_memory import ITEM_TYPE_COMMITMENT, ITEM_TYPE_TASK
from .tier2_extractor import _extract_json_object


ITEM_TYPES = {
    ITEM_TYPE_TASK,
    ITEM_TYPE_COMMITMENT,
}

DATE_SCOPE_VALUES = {
    "",
    "none",
    "today",
    "yesterday",
    "day_before_yesterday",
    "tomorrow",
    "explicit_date",
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _extract_mapping_payload(text: str) -> Dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if "{" not in raw or "}" not in raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        payload = _extract_json_object(raw)
    return dict(payload) if isinstance(payload, Mapping) else None


def _normalize_due_date(value: Any) -> str:
    candidate = _normalize_text(value)
    if not candidate:
        return ""
    try:
        return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(candidate.split("T", 1)[0]).date().isoformat()
    except ValueError:
        return ""


def _normalize_date_scope(value: Any, *, due_date: str) -> str:
    scope = _normalize_text(value).lower()
    if scope in DATE_SCOPE_VALUES:
        return scope or ("explicit_date" if due_date else "none")
    return "explicit_date" if due_date else "none"


def _normalize_route_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    mode = _normalize_text(payload.get("mode") or payload.get("route_mode")).lower()
    if mode not in ROUTE_MODES:
        return None
    return {
        "mode": mode,
        "reason": _normalize_text(payload.get("reason") or payload.get("route_reason")) or "typed query envelope",
        "source": "brainstack.local_typed_understanding",
    }


def _normalize_task_lookup_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    item_type = _normalize_text(payload.get("item_type")).lower() or ITEM_TYPE_TASK
    if item_type not in ITEM_TYPES:
        return None
    due_date = _normalize_due_date(payload.get("due_date"))
    date_scope = _normalize_date_scope(payload.get("date_scope"), due_date=due_date)
    return {
        "item_type": item_type,
        "due_date": due_date,
        "date_scope": date_scope,
        "followup_only": bool(payload.get("followup_only")),
    }


def _normalize_operating_lookup_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    record_types = [
        str(value or "").strip()
        for value in (payload.get("record_types") or ())
        if str(value or "").strip() in OPERATING_RECORD_TYPES
    ]
    if not record_types:
        return None
    return {"record_types": list(dict.fromkeys(record_types))}


def _normalize_task_capture_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    item_type = _normalize_text(payload.get("item_type")).lower() or ITEM_TYPE_TASK
    if item_type not in ITEM_TYPES:
        return None
    due_date = _normalize_due_date(payload.get("due_date"))
    date_scope = _normalize_date_scope(payload.get("date_scope"), due_date=due_date)
    items = []
    for raw in payload.get("items") or ():
        if not isinstance(raw, Mapping):
            continue
        title = _normalize_text(raw.get("title"))
        if not title:
            continue
        item_due_date = _normalize_due_date(raw.get("due_date")) or due_date
        item_date_scope = _normalize_date_scope(raw.get("date_scope"), due_date=item_due_date)
        items.append(
            {
                "title": title,
                "item_type": _normalize_text(raw.get("item_type")).lower() or item_type,
                "due_date": item_due_date,
                "date_scope": item_date_scope,
                "optional": bool(raw.get("optional")),
                "status": _normalize_text(raw.get("status")) or "open",
            }
        )
    if not items:
        return None
    return {
        "item_type": item_type,
        "due_date": due_date,
        "date_scope": date_scope,
        "items": items[:8],
    }


def _normalize_operating_capture_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    items = []
    for raw in payload.get("items") or ():
        if not isinstance(raw, Mapping):
            continue
        record_type = str(raw.get("record_type") or "").strip()
        content = _normalize_text(raw.get("content"))
        if record_type not in OPERATING_RECORD_TYPES or not content:
            continue
        items.append({"record_type": record_type, "content": content})
    if not items:
        return None
    return {"items": items[:8]}


def _probe_task_lookup(
    store: Any,
    *,
    query: str,
    principal_scope_key: str,
) -> Dict[str, Any] | None:
    rows = list(
        store.search_task_items(
            query=query,
            principal_scope_key=principal_scope_key,
            statuses=("open",),
            limit=8,
        )
    )
    if not rows:
        return None
    item_types = {str(row.get("item_type") or "").strip() for row in rows if str(row.get("item_type") or "").strip()}
    due_dates = {str(row.get("due_date") or "").strip() for row in rows if str(row.get("due_date") or "").strip()}
    date_scopes = {str(row.get("date_scope") or "").strip() for row in rows if str(row.get("date_scope") or "").strip()}
    return {
        "item_type": next(iter(item_types)) if len(item_types) == 1 else "",
        "due_date": next(iter(due_dates)) if len(due_dates) == 1 else "",
        "date_scope": next(iter(date_scopes)) if len(date_scopes) == 1 else "",
        "followup_only": False,
        "matched_rows": [dict(row) for row in rows],
        "source": "brainstack.local_typed_understanding.task_probe",
    }


def _operating_projection(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    parts = [
        str(row.get("record_type") or "").replace("_", " ").strip(),
        _normalize_text(row.get("content")),
        _normalize_text((metadata or {}).get("input_excerpt")),
    ]
    return " ".join(part for part in parts if part)


def _rank_operating_rows_locally(rows: list[Mapping[str, Any]], *, query: str, limit: int) -> list[Dict[str, Any]]:
    query_tokens = [token for token in _normalize_text(query).casefold().split() if len(token) >= 2]
    if not query_tokens:
        return []
    ranked: list[tuple[float, Dict[str, Any]]] = []
    for raw in rows:
        row = dict(raw)
        projection = _operating_projection(row).casefold()
        if not projection:
            continue
        overlap = 0
        score = 0.0
        for token in query_tokens:
            if token in projection:
                overlap += 1
                score += 1.0
        if overlap <= 0:
            continue
        row["keyword_score"] = max(float(row.get("keyword_score") or 0.0), score)
        row["_brainstack_query_token_overlap"] = overlap
        row["retrieval_source"] = str(row.get("retrieval_source") or "operating.keyword")
        row["match_mode"] = str(row.get("match_mode") or "keyword")
        ranked.append((score, row))
    ranked.sort(
        key=lambda item: (
            item[0],
            str(item[1].get("updated_at") or ""),
            str(item[1].get("created_at") or ""),
        ),
        reverse=True,
    )
    return [row for _, row in ranked[: max(int(limit or 0), 1)]]


def _probe_operating_lookup(
    store: Any,
    *,
    query: str,
    principal_scope_key: str,
) -> Dict[str, Any] | None:
    rows = list(
        store.search_operating_records(
            query=query,
            principal_scope_key=principal_scope_key,
            limit=8,
        )
    )
    if not rows:
        rows = _rank_operating_rows_locally(
            list(
                store.list_operating_records(
                    principal_scope_key=principal_scope_key,
                    limit=24,
                )
            ),
            query=query,
            limit=8,
        )
    if not rows:
        return None
    record_types = [
        str(row.get("record_type") or "").strip()
        for row in rows
        if str(row.get("record_type") or "").strip() in OPERATING_RECORD_TYPES
    ]
    if not record_types:
        return None
    return {
        "record_types": list(dict.fromkeys(record_types)),
        "matched_rows": [dict(row) for row in rows],
        "source": "brainstack.local_typed_understanding.operating_probe",
    }


def analyze_local_query(
    store: Any,
    *,
    query: str,
    principal_scope_key: str,
    timezone_name: str = "UTC",
) -> Dict[str, Any]:
    normalized_query = _normalize_text(query)
    payload = _extract_mapping_payload(normalized_query if normalized_query.startswith("{") else str(query or ""))
    route_payload = _normalize_route_payload((payload or {}).get("route") if isinstance(payload, Mapping) else None)
    if route_payload is None and isinstance(payload, Mapping):
        route_payload = _normalize_route_payload(payload)

    task_lookup = _normalize_task_lookup_payload((payload or {}).get("task_lookup") if isinstance(payload, Mapping) else None)
    if task_lookup is None and normalized_query:
        task_lookup = _probe_task_lookup(
            store,
            query=normalized_query,
            principal_scope_key=principal_scope_key,
        )

    operating_lookup = _normalize_operating_lookup_payload((payload or {}).get("operating_lookup") if isinstance(payload, Mapping) else None)
    if operating_lookup is None and normalized_query:
        operating_lookup = _probe_operating_lookup(
            store,
            query=normalized_query,
            principal_scope_key=principal_scope_key,
        )

    return {
        "task_lookup": task_lookup,
        "operating_lookup": operating_lookup,
        "route_payload": route_payload,
        "reference_date_iso": current_local_date(timezone_name=resolve_user_timezone(timezone_name)).isoformat(),
    }


def parse_local_task_lookup_query(query: str, *, timezone_name: str = "UTC", now: datetime | None = None) -> Dict[str, Any] | None:
    del timezone_name, now
    payload = _extract_mapping_payload(str(query or ""))
    if not isinstance(payload, Mapping):
        return None
    return _normalize_task_lookup_payload(payload.get("task_lookup")) or _normalize_task_lookup_payload(payload)


def parse_local_operating_lookup_query(query: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    del timezone_name
    payload = _extract_mapping_payload(str(query or ""))
    if not isinstance(payload, Mapping):
        return None
    return _normalize_operating_lookup_payload(payload.get("operating_lookup")) or _normalize_operating_lookup_payload(payload)


def parse_local_task_capture(content: str, *, timezone_name: str = "UTC", now: datetime | None = None) -> Dict[str, Any] | None:
    del timezone_name, now
    payload = _extract_mapping_payload(str(content or ""))
    if not isinstance(payload, Mapping):
        return None
    return _normalize_task_capture_payload(payload.get("task_capture")) or _normalize_task_capture_payload(payload)


def parse_local_operating_capture(content: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    del timezone_name
    payload = _extract_mapping_payload(str(content or ""))
    if not isinstance(payload, Mapping):
        return None
    return _normalize_operating_capture_payload(payload.get("operating_capture")) or _normalize_operating_capture_payload(payload)
