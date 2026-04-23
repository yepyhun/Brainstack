from __future__ import annotations

import copy
import logging
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .tier2_extractor import _extract_json_object, _extract_text_content


logger = logging.getLogger(__name__)

ROUTE_FACT = "fact"
ROUTE_TEMPORAL = "temporal"
ROUTE_AGGREGATE = "aggregate"
ROUTE_STYLE_CONTRACT = "style_contract"
ROUTE_MODES = {
    ROUTE_FACT,
    ROUTE_TEMPORAL,
    ROUTE_AGGREGATE,
    ROUTE_STYLE_CONTRACT,
}

ITEM_TYPE_TASK = "task"
ITEM_TYPE_COMMITMENT = "commitment"
ITEM_TYPES = {
    ITEM_TYPE_TASK,
    ITEM_TYPE_COMMITMENT,
}

DATE_MODE_NONE = "none"
DATE_MODE_TODAY = "today"
DATE_MODE_YESTERDAY = "yesterday"
DATE_MODE_DAY_BEFORE_YESTERDAY = "day_before_yesterday"
DATE_MODE_TOMORROW = "tomorrow"
DATE_MODE_EXPLICIT = "explicit_date"
DATE_MODES = {
    DATE_MODE_NONE,
    DATE_MODE_TODAY,
    DATE_MODE_YESTERDAY,
    DATE_MODE_DAY_BEFORE_YESTERDAY,
    DATE_MODE_TOMORROW,
    DATE_MODE_EXPLICIT,
}

OPERATING_RECORD_TYPES = (
    "active_work",
    "recent_work_summary",
    "completed_outcome",
    "discarded_work",
    "open_decision",
    "current_commitment",
    "next_step",
    "external_owner_pointer",
)
OPERATING_RECORD_TYPE_SET = set(OPERATING_RECORD_TYPES)


def _structured_llm_caller(*, task: str, messages: list, timeout: float, max_tokens: int) -> Any:
    from agent.auxiliary_client import call_llm  # type: ignore[import-not-found,import-untyped]

    return call_llm(
        task=task,
        messages=messages,
        temperature=0.0,
        max_tokens=max_tokens,
        timeout=timeout,
    )


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def resolve_user_timezone(value: str | None) -> str:
    candidate = str(value or "").strip() or "UTC"
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return "UTC"
    return candidate


def current_local_date(*, timezone_name: str, now: datetime | None = None) -> date:
    zone = ZoneInfo(resolve_user_timezone(timezone_name))
    reference = now.astimezone(zone) if isinstance(now, datetime) else datetime.now(zone)
    return reference.date()


def _reference_date_iso(*, timezone_name: str, now: datetime | None = None) -> str:
    return current_local_date(timezone_name=timezone_name, now=now).isoformat()


def _resolve_due_date(*, date_mode: str, explicit_date: str, reference_date_iso: str) -> tuple[str, str]:
    normalized_mode = str(date_mode or "").strip() or DATE_MODE_NONE
    try:
        base = date.fromisoformat(str(reference_date_iso or "").strip())
    except ValueError:
        base = date.today()

    if normalized_mode == DATE_MODE_EXPLICIT:
        try:
            explicit = date.fromisoformat(str(explicit_date or "").strip())
        except ValueError:
            return "", DATE_MODE_NONE
        return explicit.isoformat(), DATE_MODE_EXPLICIT
    if normalized_mode == DATE_MODE_TODAY:
        return base.isoformat(), DATE_MODE_TODAY
    if normalized_mode == DATE_MODE_YESTERDAY:
        return (base - timedelta(days=1)).isoformat(), DATE_MODE_YESTERDAY
    if normalized_mode == DATE_MODE_DAY_BEFORE_YESTERDAY:
        return (base - timedelta(days=2)).isoformat(), DATE_MODE_DAY_BEFORE_YESTERDAY
    if normalized_mode == DATE_MODE_TOMORROW:
        return (base + timedelta(days=1)).isoformat(), DATE_MODE_TOMORROW
    return "", DATE_MODE_NONE


def _normalize_route_payload(payload: Mapping[str, Any] | None) -> Dict[str, Any]:
    route_mode = _normalize_text((payload or {}).get("route_mode")).lower()
    if route_mode not in ROUTE_MODES:
        route_mode = ROUTE_FACT
    return {
        "mode": route_mode,
        "reason": _normalize_text((payload or {}).get("route_reason")) or "structured query understanding",
        "source": "brainstack.structured_query_understanding",
    }


def _normalize_task_lookup(payload: Mapping[str, Any] | None, *, reference_date_iso: str) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    item_type = _normalize_text(payload.get("item_type")).lower()
    if item_type not in ITEM_TYPES:
        return None
    date_mode = _normalize_text(payload.get("date_mode")).lower() or DATE_MODE_NONE
    if date_mode not in DATE_MODES:
        date_mode = DATE_MODE_NONE
    due_date, date_scope = _resolve_due_date(
        date_mode=date_mode,
        explicit_date=_normalize_text(payload.get("explicit_date")),
        reference_date_iso=reference_date_iso,
    )
    return {
        "item_type": item_type,
        "due_date": due_date,
        "date_scope": date_scope,
        "followup_only": bool(payload.get("followup_only")),
    }


def _normalize_operating_lookup(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    record_types = [
        str(value or "").strip()
        for value in (payload.get("record_types") or ())
        if str(value or "").strip() in OPERATING_RECORD_TYPE_SET
    ]
    if not record_types:
        return None
    deduped = list(dict.fromkeys(record_types))
    return {"record_types": deduped}


def _normalize_task_capture(payload: Mapping[str, Any] | None, *, reference_date_iso: str) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    item_type = _normalize_text(payload.get("item_type")).lower()
    if item_type not in ITEM_TYPES:
        return None
    date_mode = _normalize_text(payload.get("date_mode")).lower() or DATE_MODE_NONE
    if date_mode not in DATE_MODES:
        date_mode = DATE_MODE_NONE
    due_date, date_scope = _resolve_due_date(
        date_mode=date_mode,
        explicit_date=_normalize_text(payload.get("explicit_date")),
        reference_date_iso=reference_date_iso,
    )
    items: List[Dict[str, Any]] = []
    for raw in payload.get("items") or ():
        if not isinstance(raw, Mapping):
            continue
        title = _normalize_text(raw.get("title"))
        if not title:
            continue
        items.append(
            {
                "title": title,
                "item_type": item_type,
                "due_date": due_date,
                "date_scope": date_scope,
                "optional": bool(raw.get("optional")),
                "status": "open",
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


def _normalize_operating_capture(payload: Mapping[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    items: List[Dict[str, Any]] = []
    for raw in payload.get("items") or ():
        if not isinstance(raw, Mapping):
            continue
        record_type = str(raw.get("record_type") or "").strip()
        content = _normalize_text(raw.get("content"))
        if record_type not in OPERATING_RECORD_TYPE_SET or not content:
            continue
        items.append({"record_type": record_type, "content": content})
    if not items:
        return None
    return {"items": items[:8]}


def _normalize_lookup_payload(payload: Mapping[str, Any] | None, *, reference_date_iso: str) -> Dict[str, Any]:
    raw = payload if isinstance(payload, Mapping) else {}
    return {
        "route": _normalize_route_payload(raw),
        "task_lookup": _normalize_task_lookup(raw.get("task_lookup"), reference_date_iso=reference_date_iso),
        "operating_lookup": _normalize_operating_lookup(raw.get("operating_lookup")),
    }


def _normalize_capture_payload(payload: Mapping[str, Any] | None, *, reference_date_iso: str) -> Dict[str, Any]:
    raw = payload if isinstance(payload, Mapping) else {}
    return {
        "task_capture": _normalize_task_capture(raw.get("task_capture"), reference_date_iso=reference_date_iso),
        "operating_capture": _normalize_operating_capture(raw.get("operating_capture")),
    }


@lru_cache(maxsize=256)
def _infer_lookup_payload_cached(query: str, timezone_name: str, reference_date_iso: str) -> Dict[str, Any]:
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return _normalize_lookup_payload({}, reference_date_iso=reference_date_iso)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Brainstack multilingual memory-kernel query analyzer.\n"
                "Return one compact JSON object only.\n"
                "Schema:\n"
                "{\n"
                '  "route_mode": "fact|temporal|aggregate|style_contract",\n'
                '  "route_reason": "short reason",\n'
                '  "task_lookup": null | {"item_type":"task|commitment","date_mode":"none|today|yesterday|day_before_yesterday|tomorrow|explicit_date","explicit_date":"YYYY-MM-DD or empty","followup_only":true|false},\n'
                '  "operating_lookup": null | {"record_types":["active_work","recent_work_summary","completed_outcome","discarded_work","open_decision","current_commitment","next_step","external_owner_pointer"]}\n'
                "}\n"
                "Rules:\n"
                "- use route_mode=fact if uncertain\n"
                "- task_lookup is only for explicit task or commitment lookup intent\n"
                "- followup_only=true only when the query is clearly a task follow-up by time reference without naming tasks again\n"
                "- operating_lookup is only for explicit operating-state lookup intent such as active work, recent checkpoint, open decisions, commitments, next steps, or owner pointers\n"
                "- do not rely on exact wording; classify the intent semantically from the user query itself\n"
                "- do not invent lookups for vague recap questions; those stay as fact route with null structured lookups\n"
                "- style_contract route is only for explicit detailed rule-pack or style-contract recall\n"
                f"- user local date: {reference_date_iso}\n"
                f"- user timezone: {timezone_name}\n"
            ),
        },
        {"role": "user", "content": normalized_query},
    ]
    try:
        response = _structured_llm_caller(
            task="brainstack_query_understanding",
            messages=messages,
            timeout=4.5,
            max_tokens=260,
        )
        payload = _extract_json_object(_extract_text_content(response))
        return _normalize_lookup_payload(payload, reference_date_iso=reference_date_iso)
    except Exception as exc:
        logger.warning("Brainstack structured query understanding failed: %s", exc)
        return _normalize_lookup_payload({}, reference_date_iso=reference_date_iso)


@lru_cache(maxsize=256)
def _infer_capture_payload_cached(content: str, timezone_name: str, reference_date_iso: str) -> Dict[str, Any]:
    normalized_content = _normalize_text(content)
    if not normalized_content:
        return _normalize_capture_payload({}, reference_date_iso=reference_date_iso)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Brainstack multilingual memory-kernel structured capture analyzer.\n"
                "Return one compact JSON object only.\n"
                "Schema:\n"
                "{\n"
                '  "task_capture": null | {"item_type":"task|commitment","date_mode":"none|today|yesterday|day_before_yesterday|tomorrow|explicit_date","explicit_date":"YYYY-MM-DD or empty","items":[{"title":"short item","optional":true|false}]},\n'
                '  "operating_capture": null | {"items":[{"record_type":"active_work|recent_work_summary|completed_outcome|discarded_work|open_decision|current_commitment|next_step|external_owner_pointer","content":"short factual content"}]}\n'
                "}\n"
                "Rules:\n"
                "- emit task_capture only when the user text itself explicitly provides durable tasks or commitments to remember\n"
                "- emit operating_capture only when the user text itself explicitly provides structured operating truth to remember\n"
                "- use null when the text is ordinary conversation or not explicit enough\n"
                "- keep item titles and contents short, factual, and directly grounded in the provided user text only\n"
                "- do not translate, soften, or invent structured memory that is not explicit in the user text\n"
                f"- user local date: {reference_date_iso}\n"
                f"- user timezone: {timezone_name}\n"
            ),
        },
        {"role": "user", "content": str(content or "")},
    ]
    try:
        response = _structured_llm_caller(
            task="brainstack_capture_understanding",
            messages=messages,
            timeout=5.5,
            max_tokens=360,
        )
        payload = _extract_json_object(_extract_text_content(response))
        return _normalize_capture_payload(payload, reference_date_iso=reference_date_iso)
    except Exception as exc:
        logger.warning("Brainstack structured capture understanding failed: %s", exc)
        return _normalize_capture_payload({}, reference_date_iso=reference_date_iso)


def infer_query_understanding(
    query: str,
    *,
    timezone_name: str = "UTC",
    now: datetime | None = None,
) -> Dict[str, Any]:
    reference_date_iso = _reference_date_iso(timezone_name=timezone_name, now=now)
    return copy.deepcopy(
        _infer_lookup_payload_cached(
            _normalize_text(query),
            resolve_user_timezone(timezone_name),
            reference_date_iso,
        )
    )


def infer_capture_understanding(
    content: str,
    *,
    timezone_name: str = "UTC",
    now: datetime | None = None,
) -> Dict[str, Any]:
    reference_date_iso = _reference_date_iso(timezone_name=timezone_name, now=now)
    return copy.deepcopy(
        _infer_capture_payload_cached(
            str(content or ""),
            resolve_user_timezone(timezone_name),
            reference_date_iso,
        )
    )
