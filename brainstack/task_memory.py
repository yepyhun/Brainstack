from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import re
from typing import Any, Dict, Mapping

from .structured_understanding import (
    current_local_date,
    infer_capture_understanding,
    infer_query_understanding,
    resolve_user_timezone,
)


STATUS_OPEN = "open"
ITEM_TYPE_TASK = "task"
ITEM_TYPE_COMMITMENT = "commitment"


@dataclass
class TaskMemoryItem:
    title: str
    item_type: str
    due_date: str
    date_scope: str
    optional: bool
    status: str = STATUS_OPEN

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskCapture:
    item_type: str
    due_date: str
    date_scope: str
    items: list[TaskMemoryItem]

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["item_count"] = len(self.items)
        return payload


@dataclass
class TaskLookup:
    item_type: str
    due_date: str
    date_scope: str
    followup_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def build_task_stable_key(*, principal_scope_key: str, item_type: str, due_date: str, title: str) -> str:
    normalized_title = re.sub(r"[^\w]+", "-", _normalize_text(title).casefold(), flags=re.UNICODE).strip("-")
    parts = [
        "task_memory",
        str(principal_scope_key or "").strip() or "global",
        str(item_type or ITEM_TYPE_TASK).strip() or ITEM_TYPE_TASK,
        str(due_date or "undated").strip() or "undated",
        normalized_title or "item",
    ]
    return "::".join(parts)


def parse_task_capture(text: str, *, timezone_name: str, now: datetime | None = None) -> Dict[str, Any] | None:
    payload = infer_capture_understanding(text, timezone_name=timezone_name, now=now).get("task_capture")
    if not isinstance(payload, Mapping):
        return None
    items = [
        TaskMemoryItem(
            title=str(item.get("title") or "").strip(),
            item_type=str(item.get("item_type") or payload.get("item_type") or ITEM_TYPE_TASK).strip() or ITEM_TYPE_TASK,
            due_date=str(item.get("due_date") or payload.get("due_date") or "").strip(),
            date_scope=str(item.get("date_scope") or payload.get("date_scope") or "").strip(),
            optional=bool(item.get("optional")),
            status=str(item.get("status") or STATUS_OPEN).strip() or STATUS_OPEN,
        )
        for item in payload.get("items") or ()
        if str((item or {}).get("title") or "").strip()
    ]
    if not items:
        return None
    return TaskCapture(
        item_type=str(payload.get("item_type") or ITEM_TYPE_TASK).strip() or ITEM_TYPE_TASK,
        due_date=str(payload.get("due_date") or "").strip(),
        date_scope=str(payload.get("date_scope") or "").strip(),
        items=items,
    ).to_dict()


def parse_task_lookup_query(query: str, *, timezone_name: str, now: datetime | None = None) -> Dict[str, Any] | None:
    payload = infer_query_understanding(query, timezone_name=timezone_name, now=now).get("task_lookup")
    if not isinstance(payload, Mapping):
        return None
    return TaskLookup(
        item_type=str(payload.get("item_type") or ITEM_TYPE_TASK).strip() or ITEM_TYPE_TASK,
        due_date=str(payload.get("due_date") or "").strip(),
        date_scope=str(payload.get("date_scope") or "").strip(),
        followup_only=bool(payload.get("followup_only")),
    ).to_dict()
