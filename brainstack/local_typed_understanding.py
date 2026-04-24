from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Mapping

from .operating_truth import OPERATING_RECORD_TYPES, recent_work_authority_rank
from .semantic_evidence import normalize_semantic_terms, semantic_similarity
from .structured_understanding import (
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

SESSION_RECOVERY_CONTRACT_VERSION = 1
VOLATILE_OPERATING_RECORD_TYPES = {"session_state"}

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


def _normalize_json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        normalized: Dict[str, Any] = {}
        for key, raw in value.items():
            normalized_key = _normalize_text(key)
            if not normalized_key:
                continue
            normalized_value = _normalize_json_value(raw)
            if normalized_value is None:
                continue
            normalized[normalized_key] = normalized_value
        return normalized or None
    if isinstance(value, (list, tuple)):
        items = []
        for raw in value:
            normalized_value = _normalize_json_value(raw)
            if normalized_value is None:
                continue
            items.append(normalized_value)
        return items or None
    return _normalize_text(value) or None


def _normalize_json_mapping(value: Any) -> Dict[str, Any]:
    normalized = _normalize_json_value(value)
    return dict(normalized) if isinstance(normalized, Mapping) else {}


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
                "metadata": _normalize_json_mapping(raw.get("metadata")),
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
        items.append(
            {
                "record_type": record_type,
                "content": content,
                "metadata": _normalize_json_mapping(raw.get("metadata")),
            }
        )
    if not items:
        return None
    return {"items": items[:8]}


def build_session_recovery_contract(
    *,
    live_system_state_count: int = 0,
    runtime_handoff_task_count: int = 0,
    current_commitment_count: int = 0,
    next_step_count: int = 0,
    open_decision_count: int = 0,
    approval_policy_present: bool = False,
) -> Dict[str, Any]:
    ordered_checks = [
        {
            "surface": "live_system_state",
            "required": True,
            "present": bool(live_system_state_count),
            "count": max(int(live_system_state_count or 0), 0),
            "purpose": "authoritative current runtime state",
        },
        {
            "surface": "runtime_handoff_tasks",
            "required": False,
            "present": bool(runtime_handoff_task_count),
            "count": max(int(runtime_handoff_task_count or 0), 0),
            "purpose": "explicit runtime-consumable pending work",
        },
        {
            "surface": "current_commitments",
            "required": False,
            "present": bool(current_commitment_count),
            "count": max(int(current_commitment_count or 0), 0),
            "purpose": "active committed work",
        },
        {
            "surface": "next_steps",
            "required": False,
            "present": bool(next_step_count),
            "count": max(int(next_step_count or 0), 0),
            "purpose": "near-term continuation hints",
        },
        {
            "surface": "open_decisions",
            "required": False,
            "present": bool(open_decision_count),
            "count": max(int(open_decision_count or 0), 0),
            "purpose": "blocked or unresolved choices",
        },
    ]
    return {
        "contract_version": SESSION_RECOVERY_CONTRACT_VERSION,
        "bounded": True,
        "startup_mode": "session_start_recovery",
        "approval_policy_present": bool(approval_policy_present),
        "ordered_checks": ordered_checks,
        "summary": (
            "Recover current live state first, then explicit runtime handoff tasks, then committed work, "
            "next steps, and open decisions. Do not reconstruct this order from loose transcripts."
        ),
    }


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
    semantic_terms = metadata.get("semantic_terms") if isinstance(metadata, Mapping) else ()
    if isinstance(semantic_terms, str):
        semantic_text = semantic_terms
    elif isinstance(semantic_terms, (list, tuple, set)):
        semantic_text = " ".join(str(term or "") for term in semantic_terms if isinstance(term, (str, int, float)))
    else:
        semantic_text = ""
    parts = [
        str(row.get("record_type") or "").replace("_", " ").strip(),
        _normalize_text(row.get("content")),
        _normalize_text((metadata or {}).get("input_excerpt")),
        _normalize_text(semantic_text),
    ]
    return " ".join(part for part in parts if part)


def _operating_record_type_priority(row: Mapping[str, Any]) -> float:
    record_type = str(row.get("record_type") or "").strip()
    if record_type == "recent_work_summary":
        return 1.0 if recent_work_authority_rank(dict(row)) >= 200 else 0.1
    if record_type in {
        "completed_outcome",
        "discarded_work",
        "active_work",
        "open_decision",
        "current_commitment",
        "next_step",
    }:
        return 0.8
    if record_type == "live_system_state":
        return 0.2
    return 0.5


def _rank_operating_rows_locally(rows: list[Mapping[str, Any]], *, query: str, limit: int) -> list[Dict[str, Any]]:
    query_terms = normalize_semantic_terms(query)
    if not query_terms:
        return []
    ranked: list[tuple[float, Dict[str, Any]]] = []
    for raw in rows:
        row = dict(raw)
        document_terms = normalize_semantic_terms(_operating_projection(row))
        if not document_terms:
            continue
        score = semantic_similarity(query_terms, document_terms)
        overlap = len(
            {
                query_term
                for query_term in query_terms
                if semantic_similarity((query_term,), document_terms) > 0.0
            }
        )
        if overlap <= 0:
            continue
        if str(row.get("record_type") or "").strip() in VOLATILE_OPERATING_RECORD_TYPES and len(query_terms) > 1:
            required_overlap = min(2, len(query_terms))
            if overlap < required_overlap:
                continue
        row["keyword_score"] = max(float(row.get("keyword_score") or 0.0), score)
        row["_brainstack_query_token_overlap"] = overlap
        row["retrieval_source"] = str(row.get("retrieval_source") or "operating.local_terms")
        row["match_mode"] = str(row.get("match_mode") or "local_terms")
        ranked.append((score, row))
    ranked.sort(
        key=lambda item: (
            item[0],
            _operating_record_type_priority(item[1]),
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
