from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Dict, Iterable, List


OPERATING_RECORD_ACTIVE_WORK = "active_work"
OPERATING_RECORD_LIVE_SYSTEM_STATE = "live_system_state"
OPERATING_RECORD_RECENT_WORK_SUMMARY = "recent_work_summary"
OPERATING_RECORD_COMPLETED_OUTCOME = "completed_outcome"
OPERATING_RECORD_DISCARDED_WORK = "discarded_work"
OPERATING_RECORD_OPEN_DECISION = "open_decision"
OPERATING_RECORD_CURRENT_COMMITMENT = "current_commitment"
OPERATING_RECORD_NEXT_STEP = "next_step"
OPERATING_RECORD_EXTERNAL_OWNER_POINTER = "external_owner_pointer"
OPERATING_RECORD_RUNTIME_APPROVAL_POLICY = "runtime_approval_policy"
OPERATING_RECORD_CANONICAL_POLICY = "canonical_policy"
OPERATING_RECORD_PROCEDURE_MEMORY = "procedure_memory"
OPERATING_RECORD_SESSION_STATE = "session_state"

OPERATING_RECORD_TYPES = (
    OPERATING_RECORD_ACTIVE_WORK,
    OPERATING_RECORD_LIVE_SYSTEM_STATE,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_COMPLETED_OUTCOME,
    OPERATING_RECORD_DISCARDED_WORK,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_NEXT_STEP,
    OPERATING_RECORD_EXTERNAL_OWNER_POINTER,
    OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
    OPERATING_RECORD_CANONICAL_POLICY,
    OPERATING_RECORD_PROCEDURE_MEMORY,
    OPERATING_RECORD_SESSION_STATE,
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

RECENT_WORK_AUTHORITY_CANONICAL = "canonical"
RECENT_WORK_AUTHORITY_SCOPED_SUMMARY = "scoped_summary"
RECENT_WORK_AUTHORITY_BACKGROUND = "background_evidence"
RECENT_WORK_AUTHORITY_LEVELS = {
    RECENT_WORK_AUTHORITY_CANONICAL,
    RECENT_WORK_AUTHORITY_SCOPED_SUMMARY,
    RECENT_WORK_AUTHORITY_BACKGROUND,
}

RECENT_WORK_SOURCE_EXPLICIT = "explicit_operating_truth"
RECENT_WORK_SOURCE_TIER2_IDLE = "tier2_idle_window"
RECENT_WORK_SOURCE_TIER2_BATCH = "tier2_batch"
RECENT_WORK_SOURCE_RUNTIME_HANDOFF = "runtime_handoff"
RECENT_WORK_SOURCE_MANUAL_MIGRATION = "manual_migration"
RECENT_WORK_SOURCE_KINDS = {
    RECENT_WORK_SOURCE_EXPLICIT,
    RECENT_WORK_SOURCE_TIER2_IDLE,
    RECENT_WORK_SOURCE_TIER2_BATCH,
    RECENT_WORK_SOURCE_RUNTIME_HANDOFF,
    RECENT_WORK_SOURCE_MANUAL_MIGRATION,
}

RECENT_WORK_OWNER_USER_PROJECT = "user_project"
RECENT_WORK_OWNER_AGENT_ASSIGNMENT = "agent_assignment"
RECENT_WORK_OWNER_RUNTIME_SYSTEM = "runtime_system"
RECENT_WORK_OWNER_UNKNOWN = "unknown"
RECENT_WORK_OWNER_ROLES = {
    RECENT_WORK_OWNER_USER_PROJECT,
    RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
    RECENT_WORK_OWNER_RUNTIME_SYSTEM,
    RECENT_WORK_OWNER_UNKNOWN,
}


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_identifier(value: Any) -> str:
    normalized = SLUG_RE.sub("-", _normalize_text(value).casefold()).strip("-")
    return normalized[:96]


def recent_work_stable_key(
    *,
    principal_scope_key: str,
    workstream_id: str,
) -> str:
    normalized_workstream = _normalize_identifier(workstream_id)
    if not normalized_workstream:
        return ""
    return "::".join(
        [
            "operating_truth",
            str(principal_scope_key or "").strip() or "global",
            OPERATING_RECORD_RECENT_WORK_SUMMARY,
            normalized_workstream,
        ]
    )


def recent_workstream_id_from_stable_key(stable_key: Any) -> str:
    marker = f"::{OPERATING_RECORD_RECENT_WORK_SUMMARY}::"
    text = str(stable_key or "").strip()
    if marker not in text:
        return ""
    return _normalize_identifier(text.rsplit(marker, 1)[-1])


def recent_work_source_kind(source: Any, metadata: Dict[str, Any] | None = None) -> str:
    payload = metadata if isinstance(metadata, dict) else {}
    explicit = _normalize_identifier(payload.get("source_kind")).replace("-", "_")
    if explicit in RECENT_WORK_SOURCE_KINDS:
        return explicit

    source_text = _normalize_text(source).casefold()
    batch_reason = _normalize_text(payload.get("batch_reason")).casefold()
    if source_text.startswith("tier2:"):
        if "idle_window" in source_text or batch_reason == "idle_window":
            return RECENT_WORK_SOURCE_TIER2_IDLE
        return RECENT_WORK_SOURCE_TIER2_BATCH
    if source_text.startswith("runtime_handoff"):
        return RECENT_WORK_SOURCE_RUNTIME_HANDOFF
    if source_text.startswith("migration:"):
        return RECENT_WORK_SOURCE_MANUAL_MIGRATION
    return RECENT_WORK_SOURCE_EXPLICIT


def normalize_recent_work_metadata(
    *,
    stable_key: str,
    source: str,
    metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    source_kind = recent_work_source_kind(source, payload)
    workstream_id = _normalize_identifier(payload.get("workstream_id")) or recent_workstream_id_from_stable_key(stable_key)
    owner_role = _normalize_identifier(payload.get("owner_role")).replace("-", "_")
    authority_level = _normalize_identifier(payload.get("authority_level")).replace("-", "_")

    if workstream_id:
        payload["workstream_id"] = workstream_id
    payload["source_kind"] = source_kind

    if owner_role not in RECENT_WORK_OWNER_ROLES:
        if source_kind == RECENT_WORK_SOURCE_RUNTIME_HANDOFF:
            owner_role = RECENT_WORK_OWNER_RUNTIME_SYSTEM
        elif source_kind in {RECENT_WORK_SOURCE_TIER2_IDLE, RECENT_WORK_SOURCE_TIER2_BATCH}:
            owner_role = RECENT_WORK_OWNER_UNKNOWN
        else:
            owner_role = RECENT_WORK_OWNER_USER_PROJECT
    payload["owner_role"] = owner_role

    if authority_level not in RECENT_WORK_AUTHORITY_LEVELS:
        if not workstream_id:
            authority_level = RECENT_WORK_AUTHORITY_BACKGROUND
        elif source_kind in {RECENT_WORK_SOURCE_TIER2_IDLE, RECENT_WORK_SOURCE_TIER2_BATCH}:
            authority_level = RECENT_WORK_AUTHORITY_SCOPED_SUMMARY
        else:
            authority_level = RECENT_WORK_AUTHORITY_CANONICAL
    if not workstream_id and authority_level == RECENT_WORK_AUTHORITY_CANONICAL:
        authority_level = RECENT_WORK_AUTHORITY_BACKGROUND
    payload["authority_level"] = authority_level
    payload["authority_schema"] = "brainstack.recent_work_authority.v1"
    return payload


def normalize_operating_record_metadata(
    *,
    record_type: str,
    stable_key: str,
    source: str,
    metadata: Dict[str, Any] | None,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    if str(record_type or "").strip() != OPERATING_RECORD_RECENT_WORK_SUMMARY:
        return payload
    return normalize_recent_work_metadata(
        stable_key=stable_key,
        source=source,
        metadata=payload,
    )


def recent_work_authority_level(row: Dict[str, Any]) -> str:
    if str(row.get("record_type") or "").strip() != OPERATING_RECORD_RECENT_WORK_SUMMARY:
        return RECENT_WORK_AUTHORITY_CANONICAL
    metadata = row.get("metadata")
    payload = metadata if isinstance(metadata, dict) else {}
    normalized = normalize_recent_work_metadata(
        stable_key=str(row.get("stable_key") or ""),
        source=str(row.get("source") or ""),
        metadata=dict(payload),
    )
    return str(normalized.get("authority_level") or RECENT_WORK_AUTHORITY_BACKGROUND)


def recent_work_authority_rank(row: Dict[str, Any]) -> int:
    level = recent_work_authority_level(row)
    if level == RECENT_WORK_AUTHORITY_CANONICAL:
        return 300
    if level == RECENT_WORK_AUTHORITY_SCOPED_SUMMARY:
        return 200
    if level == RECENT_WORK_AUTHORITY_BACKGROUND:
        return 20
    return 0


def is_background_recent_work(row: Dict[str, Any]) -> bool:
    return (
        str(row.get("record_type") or "").strip() == OPERATING_RECORD_RECENT_WORK_SUMMARY
        and recent_work_authority_level(row) == RECENT_WORK_AUTHORITY_BACKGROUND
    )


def _record_type_label(record_type: str) -> str:
    labels = {
        OPERATING_RECORD_ACTIVE_WORK: "active work",
        OPERATING_RECORD_LIVE_SYSTEM_STATE: "live system state",
        OPERATING_RECORD_RECENT_WORK_SUMMARY: "recent work summary",
        OPERATING_RECORD_COMPLETED_OUTCOME: "completed outcome",
        OPERATING_RECORD_DISCARDED_WORK: "discarded work",
        OPERATING_RECORD_OPEN_DECISION: "open decision",
        OPERATING_RECORD_CURRENT_COMMITMENT: "current commitment",
        OPERATING_RECORD_NEXT_STEP: "next step",
        OPERATING_RECORD_EXTERNAL_OWNER_POINTER: "external owner",
        OPERATING_RECORD_RUNTIME_APPROVAL_POLICY: "runtime approval policy",
        OPERATING_RECORD_CANONICAL_POLICY: "canonical policy",
        OPERATING_RECORD_PROCEDURE_MEMORY: "procedure memory",
        OPERATING_RECORD_SESSION_STATE: "session state",
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
        payload: Dict[str, Any] = {"items": [item.to_dict() for item in self.items]}
        payload["item_count"] = len(self.items)
        payload["record_types"] = [item.record_type for item in self.items]
        return payload


@dataclass
class OperatingTruthLookup:
    record_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"record_types": list(self.record_types)}


def parse_operating_capture(text: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    del timezone_name
    from .local_typed_understanding import parse_local_operating_capture

    return parse_local_operating_capture(text)


def parse_operating_lookup_query(query: str, *, timezone_name: str = "UTC") -> Dict[str, Any] | None:
    del timezone_name
    from .local_typed_understanding import parse_local_operating_lookup_query

    return parse_local_operating_lookup_query(query)


def ordered_record_types(record_types: Iterable[str]) -> List[str]:
    requested = {str(value or "").strip() for value in record_types if str(value or "").strip()}
    return [record_type for record_type in OPERATING_RECORD_TYPES if record_type in requested]
