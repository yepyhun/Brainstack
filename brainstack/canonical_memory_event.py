from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from .core.admission import AdmissionDecision, AdmissionDecisionType, SupportVisibility

CANONICAL_MEMORY_EVENT_SCHEMA_VERSION = "brainstack.canonical_memory_event.v1"
CANONICAL_MEMORY_EVENT_CORE_GROUPS = (
    "event",
    "source",
    "scope",
    "claim",
    "authority",
    "temporal",
    "projection",
    "trace",
)

FORBIDDEN_CORE_EVENT_KEYS = {
    "raw_text",
    "raw_private_text",
    "embedding",
    "embedding_vector",
    "embedding_vectors",
    "full_prompt",
    "prompt",
    "large_summary",
    "model_output",
    "model_prose",
    "raw_donor_json",
    "provider_api_key",
    "provider_secret",
    "retrieval_rank_score",
    "packet_text",
    "metadata",
}

AUTHORITY_REDEFINITION_KEYS = {
    "authority",
    "authority_class",
    "scope",
    "truth_eligible",
    "support_visibility",
    "source",
    "source_event_id",
    "source_span_id",
    "principal_scope_key",
    "workspace_scope_key",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash_json(value: Any, *, length: int = 32) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _hash_text(value: Any, *, length: int = 32) -> str:
    return "sha256:" + hashlib.sha256(_text(value).encode("utf-8")).hexdigest()[:length]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _memory_kind(target_shelf: str, target_slot: str, proposal_type: str) -> str:
    shelf = target_shelf.strip().lower()
    slot = target_slot.strip().lower()
    proposal = proposal_type.strip().lower()
    if shelf == "profile" and slot.startswith("preference."):
        return "preference"
    if shelf == "profile":
        return "profile"
    if shelf == "graph":
        return "graph_relation" if proposal in {"relation", "inferred_relation"} else "graph_state"
    if proposal == "temporal_event":
        return "temporal_event"
    if shelf == "continuity":
        return "support_only"
    return shelf or proposal or "support_only"


def _event_type(decision: AdmissionDecision, *, durable_row_id: int) -> str:
    if decision.decision == AdmissionDecisionType.ACCEPT_SUPPORTING_EVENT:
        return "support_event"
    if decision.decision == AdmissionDecisionType.MARK_CORRECTED_FALSE_EVENT:
        return "corrected_false_event"
    if decision.decision in {AdmissionDecisionType.QUARANTINE_PROPOSAL, AdmissionDecisionType.REJECT_CANDIDATE}:
        return "proposal_rejected"
    if durable_row_id > 0:
        return "durable_fact_committed"
    return "proposal_accepted"


def _budget_class(decision: AdmissionDecision) -> str:
    if decision.truth_eligible and decision.support_visibility == SupportVisibility.ANSWER_EVIDENCE:
        return "task_relevant"
    if decision.support_visibility == SupportVisibility.NORMAL:
        return "support_only"
    if decision.support_visibility == SupportVisibility.CONTRADICTION_ONLY:
        return "archived"
    return "retrieval_only" if decision.truth_eligible else "archived"


def _scope_payload(metadata: Mapping[str, Any], session_id: str) -> dict[str, str]:
    principal_scope = _mapping(metadata.get("principal_scope"))
    return {
        "tenant_id": _text(metadata.get("tenant_id") or principal_scope.get("tenant_id") or "local"),
        "principal_scope_key": _text(metadata.get("principal_scope_key") or principal_scope.get("principal_scope_key")),
        "workspace_scope_key": _text(metadata.get("workspace_scope_key") or principal_scope.get("workspace_scope_key")),
        "session_id": _text(session_id or metadata.get("session_id")),
        "project_id": _text(metadata.get("project_id") or principal_scope.get("project_id")),
    }


def canonical_event_from_admission_decision(
    *,
    decision: AdmissionDecision,
    receipt_id: int,
    durable_row_id: int = 0,
    metadata: Mapping[str, Any] | None = None,
    observed_at: str,
) -> dict[str, Any]:
    """Build the durable seam event from an admission decision and receipt."""

    payload = dict(metadata or {})
    proposal = decision.proposal
    session_id = _text(payload.get("session_id"))
    event_type = _event_type(decision, durable_row_id=int(durable_row_id or 0))
    idempotency_seed = {
        "schema_version": CANONICAL_MEMORY_EVENT_SCHEMA_VERSION,
        "decision": decision.decision.value,
        "reason_code": decision.reason_code,
        "claim_id": proposal.claim_id,
        "source_event_id": proposal.source_event_id,
        "source_span_id": proposal.source_span_id,
        "target_shelf": proposal.target_shelf,
        "target_slot": decision.target_slot or proposal.target_slot,
        "stable_key": decision.stable_key,
        "value_hash": _hash_text(proposal.admitted_value),
    }
    idempotency_key = _hash_json(idempotency_seed, length=48)
    event_id = "cme_" + idempotency_key.removeprefix("sha256:")[:24]
    target_slot = decision.target_slot or proposal.target_slot
    subject_ref = _hash_text(proposal.subject, length=24) if proposal.subject else ""
    object_ref = _hash_text(proposal.admitted_value, length=24) if proposal.admitted_value else ""
    relation_refs = []
    if proposal.subject or proposal.predicate:
        relation_refs.append(_hash_json([proposal.subject, proposal.predicate, proposal.admitted_value], length=24))
    entity_refs = [ref for ref in (subject_ref, object_ref) if ref]
    donor_trace = _mapping(payload.get("donor_trace"))
    if not donor_trace:
        donor_trace = {
            "donor": "hindsight-compatible",
            "donor_version": _text(payload.get("donor_version")),
            "adapter_version": _text(payload.get("adapter_version")),
        }
    event = {
        "event": {
            "event_id": event_id,
            "schema_version": CANONICAL_MEMORY_EVENT_SCHEMA_VERSION,
            "event_type": event_type,
            "idempotency_key": idempotency_key,
        },
        "source": {
            "source_event_id": _text(proposal.source_event_id),
            "source_span_id": _text(proposal.source_span_id),
            "source_quote_hash": _text(proposal.source_text_hash),
            "speaker": _text(proposal.turn_role),
            "assertion_speaker": proposal.assertion_speaker.value,
            "source_modality": _text(payload.get("source_modality") or "conversation"),
            "observed_at": _text(payload.get("observed_at") or observed_at),
        },
        "scope": _scope_payload(payload, session_id),
        "claim": {
            "memory_kind": _memory_kind(proposal.target_shelf, target_slot, proposal.proposal_type),
            "target_slot": _text(target_slot),
            "subject_ref": subject_ref,
            "predicate": _text(proposal.predicate),
            "object_ref": object_ref,
            "normalized_value_hash": _hash_text(proposal.admitted_value),
            "stable_fact_id": _text(decision.stable_key or proposal.storage_key or proposal.claim_id),
        },
        "authority": {
            "authority_class": proposal.authority_class.value,
            "truth_eligible": bool(decision.truth_eligible),
            "support_visibility": decision.support_visibility.value,
            "confidence": float(proposal.confidence or 0.0),
            "admission_decision_id": proposal.claim_id,
            "receipt_id": str(int(receipt_id or 0)) if receipt_id else "",
        },
        "temporal": {
            "valid_from": _text(_mapping(payload.get("temporal")).get("valid_from") or observed_at),
            "valid_to": _text(_mapping(payload.get("temporal")).get("valid_to")),
            "transaction_time": observed_at,
            "supersedes": _list(payload.get("supersedes")),
            "superseded_by": _text(payload.get("superseded_by")),
        },
        "projection": {
            "entity_refs": entity_refs,
            "relation_refs": relation_refs,
            "budget_class": _budget_class(decision),
            "authority_critical": bool(decision.truth_eligible),
            "projection_hints": {
                "graph_ready": proposal.target_shelf == "graph" or bool(relation_refs),
                "budget_ready": True,
                "multihop_ready": bool(relation_refs) and bool(proposal.source_span_id),
            },
        },
        "trace": {
            "proposal_id": proposal.trace_id or proposal.claim_id,
            "donor_trace": dict(donor_trace),
            "policy_versions": {
                "admission": decision.policy_version,
                "slot_registry": decision.slot_registry_version,
            },
        },
        "extensions": {},
    }
    return event


def _walk_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_walk_keys(child))
    return keys


def validate_canonical_memory_event(event: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS:
        if not isinstance(event.get(group), Mapping):
            issues.append(f"missing_group:{group}")
    if issues:
        return issues
    event_group = _mapping(event.get("event"))
    authority = _mapping(event.get("authority"))
    source = _mapping(event.get("source"))
    claim = _mapping(event.get("claim"))
    projection = _mapping(event.get("projection"))
    if event_group.get("schema_version") != CANONICAL_MEMORY_EVENT_SCHEMA_VERSION:
        issues.append("schema_version_mismatch")
    for field in ("event_id", "event_type", "idempotency_key"):
        if not _text(event_group.get(field)):
            issues.append(f"missing_event_field:{field}")
    for field in ("source_event_id", "source_span_id", "source_quote_hash", "assertion_speaker", "source_modality"):
        if not _text(source.get(field)):
            issues.append(f"missing_source_field:{field}")
    if not _text(claim.get("memory_kind")):
        issues.append("missing_claim_field:memory_kind")
    if not _text(authority.get("authority_class")):
        issues.append("missing_authority_field:authority_class")
    support_visibility = _text(authority.get("support_visibility"))
    truth_eligible = bool(authority.get("truth_eligible"))
    event_type = _text(event_group.get("event_type"))
    if event_type == "durable_fact_committed" and not _text(authority.get("receipt_id")):
        issues.append("durable_event_missing_receipt_id")
    if not truth_eligible and support_visibility == SupportVisibility.ANSWER_EVIDENCE.value:
        issues.append("non_truth_event_marked_answer_evidence")
    if event_type == "proposal_rejected" and truth_eligible:
        issues.append("rejected_event_truth_eligible")
    if not isinstance(projection.get("projection_hints"), Mapping):
        issues.append("missing_projection_hints")
    forbidden = FORBIDDEN_CORE_EVENT_KEYS.intersection(_walk_keys({k: event.get(k) for k in CANONICAL_MEMORY_EVENT_CORE_GROUPS}))
    for key in sorted(forbidden):
        issues.append(f"forbidden_core_key:{key}")
    extensions = event.get("extensions", {})
    if extensions and not isinstance(extensions, Mapping):
        issues.append("extensions_not_mapping")
    if isinstance(extensions, Mapping):
        for name, extension in extensions.items():
            if not isinstance(extension, Mapping):
                issues.append(f"extension_not_mapping:{name}")
                continue
            for key in sorted(AUTHORITY_REDEFINITION_KEYS.intersection(_walk_keys(extension))):
                issues.append(f"extension_redefines_core_semantics:{name}:{key}")
    return issues


@dataclass(frozen=True)
class CanonicalMemoryEventValidation:
    passed: bool
    issues: tuple[str, ...]


def validate_canonical_memory_events(events: list[Mapping[str, Any]]) -> CanonicalMemoryEventValidation:
    issues: list[str] = []
    seen_idempotency: set[str] = set()
    for index, event in enumerate(events):
        prefix = f"event[{index}]"
        event_issues = validate_canonical_memory_event(event)
        issues.extend(f"{prefix}:{issue}" for issue in event_issues)
        idempotency_key = _text(_mapping(event.get("event")).get("idempotency_key"))
        if idempotency_key:
            if idempotency_key in seen_idempotency:
                issues.append(f"{prefix}:duplicate_idempotency_key")
            seen_idempotency.add(idempotency_key)
    return CanonicalMemoryEventValidation(passed=not issues, issues=tuple(issues))
