from __future__ import annotations

import hashlib
from typing import Any, Dict, Mapping

from .operating_truth import OPERATING_RECORD_TYPES
from .task_memory import ITEM_TYPE_TASK, STATUS_OPEN
from .transcript import trim_text_boundary
from .write_contract import build_write_decision_trace


EXPLICIT_CAPTURE_SCHEMA_VERSION = "brainstack.explicit_capture.v1"
SUPPORTED_EXPLICIT_CAPTURE_SHELVES = {"profile", "operating", "task"}
SUPPORTED_EXPLICIT_CAPTURE_SOURCE_ROLES = {"user", "operator"}
MODEL_CALLABLE_EXPLICIT_CAPTURE_SOURCE_ROLES = {"user"}
SUPPORTED_EXPLICIT_CAPTURE_OPERATIONS = {"remember", "supersede"}


def _compact(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _error(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def build_rejection_receipt(
    *,
    tool_name: str,
    operation: str,
    errors: list[Dict[str, str]],
    principal_scope_key: str,
    session_id: str,
    turn_number: int,
    lane: str = "",
    source_role: str = "",
    authority_class: str = "",
) -> Dict[str, Any]:
    reason_code = str((errors[0] or {}).get("code") or "rejected") if errors else "rejected"
    return {
        "schema": EXPLICIT_CAPTURE_SCHEMA_VERSION,
        "tool_name": tool_name,
        "operation": operation,
        "status": "rejected",
        "errors": errors,
        "principal_scope_key": principal_scope_key,
        "session_id": session_id,
        "turn_number": int(turn_number),
        "write_contract_trace": build_write_decision_trace(
            lane=lane,
            accepted=False,
            reason_code=reason_code,
            source_role=source_role,
            authority_class=authority_class,
            canonical=False,
            source_present=bool(source_role),
        ),
    }


def validate_explicit_capture_payload(
    payload: Mapping[str, Any] | None,
    *,
    operation: str,
    principal_scope_key: str,
    session_id: str,
    turn_number: int,
    allow_operator_source_role: bool = True,
) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
    if not isinstance(payload, Mapping):
        return None, build_rejection_receipt(
            tool_name=f"brainstack_{operation}",
            operation=operation,
            errors=[_error("invalid_payload", "Explicit capture requires an object payload.")],
            principal_scope_key=principal_scope_key,
            session_id=session_id,
            turn_number=turn_number,
            lane="",
        )

    errors: list[Dict[str, str]] = []
    if operation not in SUPPORTED_EXPLICIT_CAPTURE_OPERATIONS:
        errors.append(_error("unsupported_operation", "Unsupported explicit capture operation."))

    shelf = _compact(payload.get("shelf"))
    stable_key = _compact(payload.get("stable_key"))
    source_role = _compact(payload.get("source_role")).lower()
    authority_class = _compact(payload.get("authority_class")) or shelf
    raw_metadata = payload.get("metadata")
    metadata: Dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}

    if shelf not in SUPPORTED_EXPLICIT_CAPTURE_SHELVES:
        errors.append(_error("unsupported_shelf", "Shelf must be one of profile, operating, or task."))
    if not stable_key:
        errors.append(_error("missing_stable_key", "stable_key is required."))
    if source_role not in SUPPORTED_EXPLICIT_CAPTURE_SOURCE_ROLES:
        errors.append(_error("invalid_source_role", "source_role must be explicit user or operator."))
    elif source_role == "operator" and not allow_operator_source_role:
        errors.append(
            _error(
                "untrusted_operator_source_role",
                "operator source_role requires a trusted non-model write path.",
            )
        )
    if raw_metadata is not None and not isinstance(raw_metadata, Mapping):
        errors.append(_error("invalid_metadata", "metadata must be an object when provided."))

    normalized: Dict[str, Any] = {
        "schema": EXPLICIT_CAPTURE_SCHEMA_VERSION,
        "operation": operation,
        "shelf": shelf,
        "stable_key": stable_key,
        "source_role": source_role,
        "authority_class": authority_class,
        "principal_scope_key": principal_scope_key,
        "session_id": session_id,
        "turn_number": int(turn_number),
        "metadata": metadata,
    }

    if shelf == "profile":
        content = _compact(payload.get("content"))
        category = _compact(payload.get("category"))
        confidence_raw = payload.get("confidence", 0.95)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
            errors.append(_error("invalid_confidence", "confidence must be numeric when provided."))
        if not category:
            errors.append(_error("missing_category", "profile capture requires category."))
        if not content:
            errors.append(_error("missing_content", "profile capture requires content."))
        if confidence <= 0 or confidence > 1:
            errors.append(_error("invalid_confidence", "confidence must be in the range (0, 1]."))
        normalized.update(
            {
                "category": category,
                "content": content,
                "confidence": confidence,
                "content_hash": _content_hash(content),
            }
        )
    elif shelf == "operating":
        content = _compact(payload.get("content"))
        record_type = _compact(payload.get("record_type"))
        if record_type not in OPERATING_RECORD_TYPES:
            errors.append(_error("invalid_record_type", "operating capture requires a supported record_type."))
        if not content:
            errors.append(_error("missing_content", "operating capture requires content."))
        normalized.update(
            {
                "record_type": record_type,
                "content": content,
                "content_hash": _content_hash(content),
            }
        )
    elif shelf == "task":
        title = _compact(payload.get("title")) or _compact(payload.get("content"))
        status = _compact(payload.get("status")) or STATUS_OPEN
        item_type = _compact(payload.get("item_type")) or ITEM_TYPE_TASK
        due_date = _compact(payload.get("due_date"))
        date_scope = _compact(payload.get("date_scope"))
        if not title:
            errors.append(_error("missing_title", "task capture requires title or content."))
        normalized.update(
            {
                "item_type": item_type,
                "title": title,
                "due_date": due_date,
                "date_scope": date_scope,
                "optional": bool(payload.get("optional", False)),
                "status": status,
                "content_hash": _content_hash(title),
            }
        )

    supersedes_stable_key = _compact(payload.get("supersedes_stable_key")) or stable_key
    if operation == "supersede":
        normalized["supersedes_stable_key"] = supersedes_stable_key
    elif payload.get("supersedes_stable_key"):
        errors.append(_error("unexpected_supersession", "supersedes_stable_key is only accepted for supersede."))

    if errors:
        return None, build_rejection_receipt(
            tool_name=f"brainstack_{operation}",
            operation=operation,
            errors=errors,
            principal_scope_key=principal_scope_key,
            session_id=session_id,
            turn_number=turn_number,
            lane=shelf,
            source_role=source_role,
            authority_class=authority_class,
        )
    normalized["write_contract_trace"] = build_write_decision_trace(
        lane=shelf,
        accepted=True,
        reason_code="explicit_schema_validated",
        source_role=source_role,
        authority_class=authority_class,
        canonical=True,
        source_present=True,
        stable_key=stable_key,
    )
    return normalized, None


def build_commit_metadata(capture: Mapping[str, Any]) -> Dict[str, Any]:
    metadata = dict(capture.get("metadata") or {})
    metadata.update(
        {
            "explicit_capture_schema": EXPLICIT_CAPTURE_SCHEMA_VERSION,
            "explicit_capture_operation": capture.get("operation"),
            "source_role": capture.get("source_role"),
            "authority_class": capture.get("authority_class"),
            "principal_scope_key": capture.get("principal_scope_key"),
            "source_session_id": capture.get("session_id"),
            "source_turn_number": capture.get("turn_number"),
            "content_hash": capture.get("content_hash"),
        }
    )
    if capture.get("supersedes_stable_key"):
        metadata["supersedes_stable_key"] = capture.get("supersedes_stable_key")
    if isinstance(capture.get("write_contract_trace"), Mapping):
        metadata["write_contract_trace"] = dict(capture["write_contract_trace"])
    return metadata


def receipt_excerpt(value: Any, *, max_len: int = 180) -> str:
    return trim_text_boundary(_compact(value), max_len=max_len)
