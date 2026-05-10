from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Mapping


SOURCE_INTEGRITY_SCHEMA = "brainstack.source_integrity_envelope.v1"
SOURCE_INTEGRITY_TRANSITION_SCHEMA = "brainstack.source_integrity_transition.v1"

DRIFT_FRESH = "fresh"
DRIFT_DRIFTED = "drifted"
DRIFT_MISSING_FINGERPRINT = "missing_fingerprint"
DRIFT_UNVERIFIED = "unverified"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _short_hash(value: Any, *, length: int = 16) -> str:
    payload = _text(value).encode("utf-8", "surrogatepass")
    return hashlib.sha256(payload).hexdigest()[:length]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_private_source_handle(value: str) -> bool:
    lowered = value.casefold()
    return (
        value.startswith("/")
        or value.startswith("~/")
        or lowered.startswith("file:")
        or "\\" in value
        or "/home/" in value
    )


def _public_source_handle(value: str) -> str:
    handle = _text(value)
    if not handle:
        return ""
    if _is_private_source_handle(handle):
        return f"private:source:{_short_hash(handle, length=20)}"
    if len(handle) > 96:
        return f"source:{_short_hash(handle, length=20)}"
    return handle


def _fingerprint_present(envelope: Mapping[str, Any]) -> bool:
    return bool(_text(envelope.get("content_hash")) or _text(envelope.get("span_hash")))


def build_source_integrity_envelope(
    *,
    source_handle: str,
    source_adapter: str,
    source_scope: str = "",
    content_hash: str = "",
    span_hash: str = "",
    observed_at: str = "",
    drift_status: str = "",
    lock_policy: str = "source_locked",
    mutation_policy: str = "readmit_on_drift",
    receipt_id: str = "",
    admission_decision_id: str = "",
    truth_eligible: bool = False,
) -> dict[str, Any]:
    """Build a bounded source-integrity envelope for source-backed memory evidence."""

    content = _text(content_hash)
    span = _text(span_hash)
    normalized_status = _text(drift_status)
    if not normalized_status:
        normalized_status = DRIFT_FRESH if (content or span) else DRIFT_MISSING_FINGERPRINT
    return {
        "schema": SOURCE_INTEGRITY_SCHEMA,
        "source_handle": _public_source_handle(source_handle),
        "source_adapter": _text(source_adapter),
        "source_scope": _text(source_scope),
        "content_hash": content,
        "span_hash": span,
        "observed_at": _text(observed_at) or _utc_now_iso(),
        "drift_status": normalized_status,
        "lock_policy": _text(lock_policy) or "source_locked",
        "mutation_policy": _text(mutation_policy) or "readmit_on_drift",
        "receipt_id": _text(receipt_id),
        "admission_decision_id": _text(admission_decision_id),
        "truth_eligible": bool(truth_eligible),
        "raw_private_source_in_envelope": False,
    }


def is_source_backed_truth_answerable(envelope: Mapping[str, Any]) -> bool:
    if not isinstance(envelope, Mapping):
        return False
    if envelope.get("schema") != SOURCE_INTEGRITY_SCHEMA:
        return False
    if envelope.get("truth_eligible") is not True:
        return True
    if _text(envelope.get("drift_status")) != DRIFT_FRESH:
        return False
    if not _fingerprint_present(envelope):
        return False
    return bool(_text(envelope.get("receipt_id")) or _text(envelope.get("admission_decision_id")))


def verify_source_integrity_transition(
    *,
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    previous_hash = _text(previous.get("content_hash")) or _text(previous.get("span_hash"))
    current_hash = _text(current.get("content_hash")) or _text(current.get("span_hash"))
    current_envelope = dict(current)

    if current_envelope.get("truth_eligible") is True and not current_hash:
        current_envelope["drift_status"] = DRIFT_MISSING_FINGERPRINT
        return {
            "schema": SOURCE_INTEGRITY_TRANSITION_SCHEMA,
            "status": "blocked",
            "reason_code": "SOURCE_FINGERPRINT_REQUIRED",
            "durable_truth_mutation_allowed": False,
            "next_safe_action": "attach_source_fingerprint_before_admission",
            "previous_envelope": dict(previous),
            "current_envelope": current_envelope,
        }

    if previous_hash and current_hash and previous_hash != current_hash:
        current_envelope["drift_status"] = DRIFT_DRIFTED
        return {
            "schema": SOURCE_INTEGRITY_TRANSITION_SCHEMA,
            "status": "blocked",
            "reason_code": "SOURCE_DRIFT_REQUIRES_READMISSION",
            "durable_truth_mutation_allowed": False,
            "next_safe_action": "re_admit_from_updated_source",
            "previous_envelope": dict(previous),
            "current_envelope": current_envelope,
        }

    current_envelope["drift_status"] = current_envelope.get("drift_status") or DRIFT_FRESH
    return {
        "schema": SOURCE_INTEGRITY_TRANSITION_SCHEMA,
        "status": "allowed" if is_source_backed_truth_answerable(current_envelope) else "degraded",
        "reason_code": "SOURCE_INTEGRITY_UNCHANGED",
        "durable_truth_mutation_allowed": is_source_backed_truth_answerable(current_envelope),
        "next_safe_action": "none" if is_source_backed_truth_answerable(current_envelope) else "inspect_source_integrity",
        "previous_envelope": dict(previous),
        "current_envelope": current_envelope,
    }


def public_source_integrity_status(envelope: Mapping[str, Any]) -> dict[str, Any]:
    status = _text(envelope.get("drift_status")) or DRIFT_UNVERIFIED
    answerable = is_source_backed_truth_answerable(envelope)
    return {
        "schema": "brainstack.source_integrity_public_status.v1",
        "status": status,
        "source_handle": _public_source_handle(_text(envelope.get("source_handle"))),
        "source_adapter": _text(envelope.get("source_adapter")),
        "fingerprint_present": _fingerprint_present(envelope),
        "receipt_linked": bool(_text(envelope.get("receipt_id")) or _text(envelope.get("admission_decision_id"))),
        "answerable_truth_allowed": answerable,
        "next_safe_action": "none" if answerable else "inspect_or_readmit_source",
        "raw_private_source_in_status": False,
    }
