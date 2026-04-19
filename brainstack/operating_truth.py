from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Iterable, List


OPERATING_RECORD_ACTIVE_WORK = "active_work"
OPERATING_RECORD_OPEN_DECISION = "open_decision"
OPERATING_RECORD_CURRENT_COMMITMENT = "current_commitment"
OPERATING_RECORD_NEXT_STEP = "next_step"
OPERATING_RECORD_EXTERNAL_OWNER_POINTER = "external_owner_pointer"

OPERATING_RECORD_TYPES = (
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
)

OPERATING_SINGLETON_RECORD_TYPES = {
    OPERATING_RECORD_ACTIVE_WORK,
}

OPERATING_OWNER = "brainstack.operating_truth"

LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|(?:\d+[\.\)])|(?:\d+\s*-\s*))\s*")
SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)

_CAPTURE_LABELS = {
    "active work": OPERATING_RECORD_ACTIVE_WORK,
    "current work": OPERATING_RECORD_ACTIVE_WORK,
    "aktív munka": OPERATING_RECORD_ACTIVE_WORK,
    "aktiv munka": OPERATING_RECORD_ACTIVE_WORK,
    "aktuális munka": OPERATING_RECORD_ACTIVE_WORK,
    "aktualis munka": OPERATING_RECORD_ACTIVE_WORK,
    "open decision": OPERATING_RECORD_OPEN_DECISION,
    "open decisions": OPERATING_RECORD_OPEN_DECISION,
    "nyitott döntés": OPERATING_RECORD_OPEN_DECISION,
    "nyitott döntések": OPERATING_RECORD_OPEN_DECISION,
    "nyitott dontes": OPERATING_RECORD_OPEN_DECISION,
    "nyitott dontesek": OPERATING_RECORD_OPEN_DECISION,
    "current commitment": OPERATING_RECORD_CURRENT_COMMITMENT,
    "current commitments": OPERATING_RECORD_CURRENT_COMMITMENT,
    "vállalás": OPERATING_RECORD_CURRENT_COMMITMENT,
    "vállalások": OPERATING_RECORD_CURRENT_COMMITMENT,
    "vallalas": OPERATING_RECORD_CURRENT_COMMITMENT,
    "vallalasok": OPERATING_RECORD_CURRENT_COMMITMENT,
    "next step": OPERATING_RECORD_NEXT_STEP,
    "next steps": OPERATING_RECORD_NEXT_STEP,
    "következő lépés": OPERATING_RECORD_NEXT_STEP,
    "következő lépések": OPERATING_RECORD_NEXT_STEP,
    "kovetkezo lepes": OPERATING_RECORD_NEXT_STEP,
    "kovetkezo lepesek": OPERATING_RECORD_NEXT_STEP,
    "external owner": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    "external owners": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    "külső owner": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    "külső ownerek": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    "kulso owner": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    "kulso ownerek": OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
}

_LOOKUP_PHRASES = {
    OPERATING_RECORD_ACTIVE_WORK: (
        "active work",
        "current work",
        "working on",
        "what are we doing",
        "mi az aktív munka",
        "mi az aktualis munka",
        "min dolgozunk",
    ),
    OPERATING_RECORD_OPEN_DECISION: (
        "open decision",
        "open decisions",
        "what is open",
        "nyitott döntés",
        "nyitott döntések",
        "nyitott dontes",
        "nyitott dontesek",
    ),
    OPERATING_RECORD_CURRENT_COMMITMENT: (
        "current commitment",
        "current commitments",
        "vállalás",
        "vállalások",
        "vallalas",
        "vallalasok",
    ),
    OPERATING_RECORD_NEXT_STEP: (
        "next step",
        "next steps",
        "what happens next",
        "következő lépés",
        "következő lépések",
        "kovetkezo lepes",
        "kovetkezo lepesek",
        "mi a következő lépés",
        "mi a kovetkezo lepes",
    ),
    OPERATING_RECORD_EXTERNAL_OWNER_POINTER: (
        "external owner",
        "external owners",
        "owner pointer",
        "külső owner",
        "kulso owner",
        "ki a külső owner",
        "ki a kulso owner",
    ),
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _strip_list_marker(value: Any) -> str:
    return _normalize_text(LIST_MARKER_RE.sub("", str(value or "").strip()))


def _heading_key(value: Any) -> str:
    text = _normalize_text(value).rstrip(":").strip()
    return text.casefold()


def _record_type_label(record_type: str) -> str:
    labels = {
        OPERATING_RECORD_ACTIVE_WORK: "active work",
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


def parse_operating_capture(text: str) -> Dict[str, Any] | None:
    lines = [str(line or "").rstrip() for line in str(text or "").splitlines()]
    if not lines:
        return None

    items: List[OperatingTruthItem] = []
    current_type = ""
    saw_heading = False

    for raw_line in lines:
        line = str(raw_line or "").strip()
        if not line:
            continue

        head, has_inline = (line.split(":", 1) + [""])[:2] if ":" in line else (line, "")
        record_type = _CAPTURE_LABELS.get(_heading_key(head))
        if record_type:
            saw_heading = True
            current_type = record_type
            inline_content = _strip_list_marker(has_inline)
            if inline_content:
                items.append(OperatingTruthItem(record_type=record_type, content=inline_content))
            continue

        if not current_type:
            continue
        content = _strip_list_marker(line)
        if content:
            items.append(OperatingTruthItem(record_type=current_type, content=content))

    if not saw_heading or not items:
        return None
    return OperatingTruthCapture(items=items).to_dict()


def parse_operating_lookup_query(query: str) -> Dict[str, Any] | None:
    normalized = _normalize_text(query)
    if not normalized:
        return None
    lowered = normalized.casefold()
    matched: List[str] = []
    for record_type, phrases in _LOOKUP_PHRASES.items():
        if any(phrase in lowered for phrase in phrases):
            matched.append(record_type)
    if not matched:
        return None
    deduped = list(dict.fromkeys(matched))
    return OperatingTruthLookup(record_types=deduped).to_dict()


def ordered_record_types(record_types: Iterable[str]) -> List[str]:
    requested = {str(value or "").strip() for value in record_types if str(value or "").strip()}
    return [record_type for record_type in OPERATING_RECORD_TYPES if record_type in requested]
