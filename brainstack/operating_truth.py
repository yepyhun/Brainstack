from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Iterable, List, Mapping

from .structured_understanding import infer_capture_understanding, infer_query_understanding


OPERATING_RECORD_ACTIVE_WORK = "active_work"
OPERATING_RECORD_RECENT_WORK_SUMMARY = "recent_work_summary"
OPERATING_RECORD_COMPLETED_OUTCOME = "completed_outcome"
OPERATING_RECORD_DISCARDED_WORK = "discarded_work"
OPERATING_RECORD_OPEN_DECISION = "open_decision"
OPERATING_RECORD_CURRENT_COMMITMENT = "current_commitment"
OPERATING_RECORD_NEXT_STEP = "next_step"
OPERATING_RECORD_EXTERNAL_OWNER_POINTER = "external_owner_pointer"

OPERATING_RECORD_TYPES = (
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_COMPLETED_OUTCOME,
    OPERATING_RECORD_DISCARDED_WORK,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
)

OPERATING_SINGLETON_RECORD_TYPES = {
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
}

RECENT_WORK_RECAP_RECORD_TYPES = (
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_COMPLETED_OUTCOME,
    OPERATING_RECORD_DISCARDED_WORK,
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
)

OPERATING_OWNER = "brainstack.operating_truth"
SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _record_type_label(record_type: str) -> str:
    labels = {
        OPERATING_RECORD_ACTIVE_WORK: "active work",
        OPERATING_RECORD_RECENT_WORK_SUMMARY: "recent work summary",
        OPERATING_RECORD_COMPLETED_OUTCOME: "completed outcome",
        OPERATING_RECORD_DISCARDED_WORK: "discarded work",
        OPERATING_RECORD_OPEN_DECISION: "open decision",
        OPERATING_RECORD_CURRENT_COMMITMENT: "current commitment",
        OPERATING_RECORD_NEXT_STEP: "next step",
        OPERATING_RECORD_EXTERNAL_OWNER_POINTER: "external owner",
    }
    return labels.get(str(record_type or "").strip(), "operating truth")


def build_operating_stable_key(*, principal_scope_key: str, record_type: str, content: str) -> str:
    normalized_type = str(record_type or "").strip() or OPERATING_RECORD_ACTIVE_WORK
    parts = ["operating_truth", str(principal_scope_key or "").strip() or "global", normalized_type]
    if normalized_type not in OPERATING_SINGLETON_RECORD_TYPES:
        slug = SLUG_RE.sub("-", _normalize_text(content).casefold()).strip("-")
        parts.append(slug or "item")
    return "::".join(parts)


@dataclass
class OperatingTruthItem:
    record_type: str
    content: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["label"] = _record_type_label(self.record_type)
        return payload


@dataclass
class OperatingTruthCapture:
    items: List[OperatingTruthItem]

    def to_dict(self) -> Dict[str, Any]:
        payload = {"items": [item.to_dict() for item in self.items]}
        payload["item_count"] = len(self.items)
        payload["record_types"] = [item.record_type for item in self.items]
        return payload


@dataclass
class OperatingTruthLookup:
    record_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"record_types": list(self.record_types)}


def parse_operating_capture(text: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    payload = infer_capture_understanding(text, timezone_name=timezone_name).get("operating_capture")
    if not isinstance(payload, Mapping):
        return None
    items = [
        OperatingTruthItem(
            record_type=str(item.get("record_type") or "").strip(),
            content=str(item.get("content") or "").strip(),
        )
        for item in payload.get("items") or ()
        if str((item or {}).get("record_type") or "").strip() in OPERATING_RECORD_TYPES
        and str((item or {}).get("content") or "").strip()
    ]
    if not items:
        return None
    return OperatingTruthCapture(items=items).to_dict()


def parse_operating_lookup_query(query: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    payload = infer_query_understanding(query, timezone_name=timezone_name).get("operating_lookup")
    if not isinstance(payload, Mapping):
        return None
    record_types = [
        str(value or "").strip()
        for value in (payload.get("record_types") or ())
        if str(value or "").strip() in OPERATING_RECORD_TYPES
    ]
    if not record_types:
        return None
    deduped = list(dict.fromkeys(record_types))
    return OperatingTruthLookup(record_types=deduped).to_dict()


def ordered_record_types(record_types: Iterable[str]) -> List[str]:
    requested = {str(value or "").strip() for value in record_types if str(value or "").strip()}
    return [record_type for record_type in OPERATING_RECORD_TYPES if record_type in requested]
