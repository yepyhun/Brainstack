from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import re
from typing import Any, Dict

from .structured_understanding import resolve_user_timezone

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
    del timezone_name, now
    from .local_typed_understanding import parse_local_task_capture

    return parse_local_task_capture(text)


def parse_task_lookup_query(query: str, *, timezone_name: str, now: datetime | None = None) -> Dict[str, Any] | None:
    del timezone_name, now
    from .local_typed_understanding import parse_local_task_lookup_query

    return parse_local_task_lookup_query(query)
