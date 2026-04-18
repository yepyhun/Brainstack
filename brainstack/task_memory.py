from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any, Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TASK_CAPTURE_CUES = (
    "task",
    "tasks",
    "todo",
    "to do",
    "agenda",
    "feladatom",
    "feladataim",
    "feladat",
    "teendő",
    "teendo",
)
COMMITMENT_CAPTURE_CUES = (
    "commitment",
    "commitments",
    "vállalás",
    "vallalas",
    "elköteleződés",
    "elkotelezodes",
    "ígéretem",
    "igeretem",
)
TASK_LOOKUP_CUES = TASK_CAPTURE_CUES + COMMITMENT_CAPTURE_CUES
TASK_FOLLOWUP_DATE_CUES = (
    "ma",
    "mai",
    "mára",
    "mara",
    "tegnap",
    "tegnapra",
    "tegnapelőtt",
    "tegnapelott",
    "tegnapelőttre",
    "tegnapelottre",
    "today",
    "yesterday",
    "day before yesterday",
    "tomorrow",
)
TODAY_CUES = ("today", "ma", "mai", "mára", "mara")
YESTERDAY_CUES = ("yesterday", "tegnap", "tegnapra", "tegnapi")
DAY_BEFORE_CUES = ("day before yesterday", "tegnapelőtt", "tegnapelott", "tegnapelőtti", "tegnapelőttre", "tegnapelottre")
TOMORROW_CUES = ("tomorrow", "holnap", "holnapra")
OPTIONAL_PREFIXES = ("esetleg ", "talán ", "talan ", "maybe ", "optional ")
STATUS_OPEN = "open"
ITEM_TYPE_TASK = "task"
ITEM_TYPE_COMMITMENT = "commitment"
DATE_RE = re.compile(r"\b(20\d{2})[-./](\d{1,2})[-./](\d{1,2})\b")
LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|(?:\d+[\.\)])|(?:\d+\s*-\s*))\s*")


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
    items: List[TaskMemoryItem]

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


def _detect_item_type(text: str) -> str:
    lowered = f" {text.casefold()} "
    if any(cue in lowered for cue in COMMITMENT_CAPTURE_CUES) and not any(cue in lowered for cue in TASK_CAPTURE_CUES):
        return ITEM_TYPE_COMMITMENT
    return ITEM_TYPE_TASK


def _extract_due_date(*, text: str, timezone_name: str, now: datetime | None = None) -> tuple[str, str]:
    lowered = f" {_normalize_text(text).casefold()} "
    base = current_local_date(timezone_name=timezone_name, now=now)
    match = DATE_RE.search(text)
    if match:
        year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        try:
            explicit = date(year, month, day)
        except ValueError:
            return "", "none"
        return explicit.isoformat(), "explicit_date"
    if any(cue in lowered for cue in DAY_BEFORE_CUES):
        return (base - timedelta(days=2)).isoformat(), "day_before_yesterday"
    if any(cue in lowered for cue in YESTERDAY_CUES):
        return (base - timedelta(days=1)).isoformat(), "yesterday"
    if any(cue in lowered for cue in TOMORROW_CUES):
        return (base + timedelta(days=1)).isoformat(), "tomorrow"
    if any(cue in lowered for cue in TODAY_CUES):
        return base.isoformat(), "today"
    return "", "none"


def _strip_task_line(raw: str) -> tuple[str, bool]:
    text = LIST_MARKER_RE.sub("", str(raw or "").strip())
    lowered = text.casefold()
    optional = False
    for prefix in OPTIONAL_PREFIXES:
        if lowered.startswith(prefix):
            optional = True
            text = text[len(prefix):].strip()
            lowered = text.casefold()
            break
    for prefix in ("és ", "es ", "and "):
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            lowered = text.casefold()
            break
    text = text.strip(" \t\r\n-:;,.!?")
    return _normalize_text(text), optional


def _looks_like_explicit_task_capture(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    lowered = f" {normalized.casefold()} "
    if not any(cue in lowered for cue in TASK_CAPTURE_CUES + COMMITMENT_CAPTURE_CUES):
        return False
    if "\n" in str(text or ""):
        return True
    return ":" in normalized


def parse_task_capture(text: str, *, timezone_name: str, now: datetime | None = None) -> Dict[str, Any] | None:
    raw_text = str(text or "")
    if not _looks_like_explicit_task_capture(raw_text):
        return None

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return None

    item_type = _detect_item_type(raw_text)
    due_date, date_scope = _extract_due_date(text=raw_text, timezone_name=timezone_name, now=now)
    items: List[TaskMemoryItem] = []

    head = lines[0]
    if ":" in head:
        _, remainder = head.split(":", 1)
        title, optional = _strip_task_line(remainder)
        if title:
            items.append(
                TaskMemoryItem(
                    title=title,
                    item_type=item_type,
                    due_date=due_date,
                    date_scope=date_scope,
                    optional=optional,
                )
            )
        lines = lines[1:]
    else:
        lines = lines[1:]

    for line in lines:
        title, optional = _strip_task_line(line)
        if not title:
            continue
        items.append(
            TaskMemoryItem(
                title=title,
                item_type=item_type,
                due_date=due_date,
                date_scope=date_scope,
                optional=optional,
            )
        )

    if not items:
        return None
    capture = TaskCapture(item_type=item_type, due_date=due_date, date_scope=date_scope, items=items)
    return capture.to_dict()


def parse_task_lookup_query(query: str, *, timezone_name: str, now: datetime | None = None) -> Dict[str, Any] | None:
    normalized = _normalize_text(query)
    if not normalized:
        return None
    lowered = f" {normalized.casefold()} "
    explicit_due_date, date_scope = _extract_due_date(text=normalized, timezone_name=timezone_name, now=now)
    cue_hit = any(cue in lowered for cue in TASK_LOOKUP_CUES)
    followup_only = False
    if not cue_hit:
        if any(cue in lowered for cue in TASK_FOLLOWUP_DATE_CUES):
            cue_hit = True
            followup_only = True
    if not cue_hit:
        return None
    item_type = _detect_item_type(normalized)
    return TaskLookup(
        item_type=item_type,
        due_date=explicit_due_date,
        date_scope=date_scope,
        followup_only=followup_only,
    ).to_dict()

