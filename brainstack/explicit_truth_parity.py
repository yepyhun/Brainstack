from __future__ import annotations

import hashlib
from typing import Any, Mapping

EXPLICIT_TRUTH_PARITY_SCHEMA = "brainstack.explicit_truth_parity.v1"

PROJECTION_PENDING = "pending"
PROJECTION_COMMITTED = "committed"
PROJECTION_FAILED = "failed"
PROJECTION_SKIPPED = "skipped"
PROJECTION_MISSING_AFTER_TIMEOUT = "missing_after_timeout"
PROJECTION_CONFLICT = "conflict"
PROJECTION_UNKNOWN_HOST_RECEIPT = "unknown_host_receipt"

OBSERVABLE_CLEAN = "observable_clean"
PARTIALLY_OBSERVABLE = "partially_observable"
UNOBSERVABLE = "unobservable"
OBSERVABLE_DIVERGED = "observable_diverged"

DIVERGENCE_NONE = "none"
DIVERGENCE_DERIVED_PARTIAL = "derived_partial"
DIVERGENCE_PARITY_UNOBSERVABLE = "parity_unobservable"
DIVERGENCE_HOST_COMMITTED_BRAINSTACK_MISSING = "host_committed_brainstack_missing"
DIVERGENCE_BRAINSTACK_COMMITTED_HOST_MISSING = "brainstack_committed_host_missing"
DIVERGENCE_HOST_AND_BRAINSTACK_CONFLICT = "host_and_brainstack_conflict"
DIVERGENCE_SCOPE_MISMATCH = "scope_mismatch"
DIVERGENCE_STABLE_KEY_MISMATCH = "stable_key_mismatch"
DIVERGENCE_AUTHORITY_MISMATCH = "authority_mismatch"
DIVERGENCE_CURRENT_PRIOR_MISMATCH = "current_prior_mismatch"
DIVERGENCE_CONTENT_CONFLICT = "content_conflict"

DEGRADED_PROJECTION_STATUSES = {
    PROJECTION_PENDING,
    PROJECTION_FAILED,
    PROJECTION_MISSING_AFTER_TIMEOUT,
    PROJECTION_CONFLICT,
    PROJECTION_UNKNOWN_HOST_RECEIPT,
}
DEGRADED_DIVERGENCE_STATUSES = {
    DIVERGENCE_HOST_COMMITTED_BRAINSTACK_MISSING,
    DIVERGENCE_BRAINSTACK_COMMITTED_HOST_MISSING,
    DIVERGENCE_HOST_AND_BRAINSTACK_CONFLICT,
    DIVERGENCE_SCOPE_MISMATCH,
    DIVERGENCE_STABLE_KEY_MISMATCH,
    DIVERGENCE_AUTHORITY_MISMATCH,
    DIVERGENCE_CURRENT_PRIOR_MISMATCH,
    DIVERGENCE_CONTENT_CONFLICT,
}


def content_hash(value: Any) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest() if text else ""


def derive_host_trace_id(*, action: str, target: str, content: str, metadata: Mapping[str, Any] | None = None) -> str:
    metadata = metadata if isinstance(metadata, Mapping) else {}
    seed = "|".join(
        [
            str(action or ""),
            str(target or ""),
            content_hash(content),
            str(metadata.get("session_id") or ""),
            str(metadata.get("tool_call_id") or ""),
            str(metadata.get("task_id") or ""),
            str(metadata.get("write_origin") or ""),
        ]
    )
    return "derived-host-" + hashlib.sha256(seed.encode("utf-8", "replace")).hexdigest()[:24]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _status_from_mismatch(
    *,
    host_content_hash: str,
    brainstack_content_hash: str,
    host_stable_key: str,
    brainstack_stable_key: str,
    host_scope: str,
    brainstack_scope: str,
    host_temporal_status: str,
    brainstack_temporal_status: str,
) -> str:
    if host_scope and brainstack_scope and host_scope != brainstack_scope:
        return DIVERGENCE_SCOPE_MISMATCH
    if host_stable_key and brainstack_stable_key and host_stable_key != brainstack_stable_key:
        return DIVERGENCE_STABLE_KEY_MISMATCH
    if host_content_hash and brainstack_content_hash and host_content_hash != brainstack_content_hash:
        return DIVERGENCE_CONTENT_CONFLICT
    if host_temporal_status and brainstack_temporal_status and host_temporal_status != brainstack_temporal_status:
        return DIVERGENCE_CURRENT_PRIOR_MISMATCH
    return DIVERGENCE_NONE


def build_explicit_truth_parity(
    *,
    projection_status: str,
    source_role: str = "",
    stable_key: str = "",
    principal_scope_key: str = "",
    content: str = "",
    brainstack_projection_receipt_id: str = "",
    host_receipt_id: str = "",
    host_receipt_source: str = "",
    host_content_hash: str = "",
    host_stable_key: str = "",
    host_scope: str = "",
    host_temporal_status: str = "",
    brainstack_temporal_status: str = "",
    authority_class: str = "",
    error: str = "",
) -> dict[str, Any]:
    projection_status = _text(projection_status) or PROJECTION_UNKNOWN_HOST_RECEIPT
    brainstack_content_hash = content_hash(content)
    host_receipt_id = _text(host_receipt_id)
    host_receipt_source = _text(host_receipt_source)
    host_content_hash = _text(host_content_hash)
    host_stable_key = _text(host_stable_key)
    host_scope = _text(host_scope)
    host_temporal_status = _text(host_temporal_status)
    brainstack_temporal_status = _text(brainstack_temporal_status)
    brainstack_stable_key = _text(stable_key)
    brainstack_scope = _text(principal_scope_key)

    divergence = _status_from_mismatch(
        host_content_hash=host_content_hash,
        brainstack_content_hash=brainstack_content_hash,
        host_stable_key=host_stable_key,
        brainstack_stable_key=brainstack_stable_key,
        host_scope=host_scope,
        brainstack_scope=brainstack_scope,
        host_temporal_status=host_temporal_status,
        brainstack_temporal_status=brainstack_temporal_status,
    )
    if projection_status == PROJECTION_FAILED:
        divergence = DIVERGENCE_HOST_COMMITTED_BRAINSTACK_MISSING if host_receipt_id else DIVERGENCE_PARITY_UNOBSERVABLE
    elif projection_status == PROJECTION_MISSING_AFTER_TIMEOUT:
        divergence = DIVERGENCE_HOST_COMMITTED_BRAINSTACK_MISSING
    elif projection_status == PROJECTION_CONFLICT and divergence == DIVERGENCE_NONE:
        divergence = DIVERGENCE_HOST_AND_BRAINSTACK_CONFLICT
    elif not host_receipt_id:
        divergence = DIVERGENCE_PARITY_UNOBSERVABLE
    elif host_receipt_source == "derived_host_trace" and divergence == DIVERGENCE_NONE:
        divergence = DIVERGENCE_DERIVED_PARTIAL

    if projection_status == PROJECTION_PENDING:
        observable = PARTIALLY_OBSERVABLE
    elif projection_status in {PROJECTION_FAILED, PROJECTION_MISSING_AFTER_TIMEOUT, PROJECTION_CONFLICT}:
        observable = OBSERVABLE_DIVERGED
    elif divergence in DEGRADED_DIVERGENCE_STATUSES:
        observable = OBSERVABLE_DIVERGED
    elif not host_receipt_id:
        observable = UNOBSERVABLE
    elif host_receipt_source == "derived_host_trace":
        observable = PARTIALLY_OBSERVABLE
    else:
        observable = OBSERVABLE_CLEAN if divergence == DIVERGENCE_NONE else OBSERVABLE_DIVERGED

    transaction_id_seed = "|".join(
        [
            host_receipt_id,
            brainstack_projection_receipt_id,
            brainstack_stable_key,
            brainstack_scope,
            brainstack_content_hash,
        ]
    )
    return {
        "schema": EXPLICIT_TRUTH_PARITY_SCHEMA,
        "explicit_user_truth_transaction_id": "truth-tx-"
        + hashlib.sha256(transaction_id_seed.encode("utf-8", "replace")).hexdigest()[:24],
        "host_receipt_id": host_receipt_id,
        "host_receipt_source": host_receipt_source,
        "brainstack_projection_receipt_id": _text(brainstack_projection_receipt_id),
        "projection_status": projection_status,
        "divergence_status": divergence,
        "parity_observable": observable,
        "source_role": _text(source_role),
        "stable_key": brainstack_stable_key,
        "principal_scope_key": brainstack_scope,
        "authority_class": _text(authority_class),
        "host_content_hash": host_content_hash,
        "brainstack_content_hash": brainstack_content_hash,
        "host_stable_key": host_stable_key,
        "brainstack_stable_key": brainstack_stable_key,
        "host_scope": host_scope,
        "brainstack_scope": brainstack_scope,
        "host_temporal_status": host_temporal_status,
        "brainstack_temporal_status": brainstack_temporal_status,
        "error": _text(error),
    }


def parity_degrades_answerability(parity: Mapping[str, Any] | None) -> bool:
    if not isinstance(parity, Mapping):
        return False
    projection_status = _text(parity.get("projection_status"))
    divergence_status = _text(parity.get("divergence_status"))
    return projection_status in DEGRADED_PROJECTION_STATUSES or divergence_status in DEGRADED_DIVERGENCE_STATUSES
