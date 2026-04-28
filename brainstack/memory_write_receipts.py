"""Receipt-backed durable memory acknowledgement contracts.

This module does not decide what should be remembered. It only models whether
an already-planned durable memory capture has committed enough receipts to make
a truthful acknowledgement.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

CAPTURE_PLAN_SCHEMA = "brainstack.capture_plan.v1"
MEMORY_WRITE_RECEIPT_SCHEMA = "brainstack.memory_write_receipt.v1"
RECEIPT_COVERAGE_SCHEMA = "brainstack.receipt_coverage.v1"
ACK_PLAN_SCHEMA = "hermes.memory_ack_plan.v1"

STATUS_COMMITTED = "committed"
STATUS_REJECTED = "rejected"
STATUS_ROLLED_BACK = "rolled_back"

COVERAGE_COMPLETE = "complete"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"
COVERAGE_NOT_APPLICABLE = "not_applicable"

ACK_FULL = "full"
ACK_PARTIAL = "partial"
ACK_NONE = "none"
ACK_CLARIFICATION = "clarification"

REASON_MISSING_RECEIPT = "ADMISSION_FAILED_OR_WRITE_NOT_COMMITTED"
REASON_SCOPE_MISMATCH = "RECEIPT_SCOPE_MISMATCH"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(part) for part in parts)
    return f"{prefix}_{_hash_text(body)[:24]}"


@dataclass(frozen=True)
class CaptureProposalRef:
    proposal_id: str
    target_slot: str
    stable_key: str
    source_span_id: str = ""
    normalized_value: str = ""
    required_for_full_ack: bool = True

    @classmethod
    def from_mapping(cls, proposal: Mapping[str, Any]) -> "CaptureProposalRef":
        stable_key = _text(proposal.get("stable_key")) or _text(proposal.get("target_slot"))
        proposal_id = _text(proposal.get("proposal_id")) or stable_id(
            "cap",
            proposal.get("turn_id"),
            stable_key,
            proposal.get("source_span_id"),
            proposal.get("normalized_value"),
        )
        return cls(
            proposal_id=proposal_id,
            target_slot=_text(proposal.get("target_slot")),
            stable_key=stable_key,
            source_span_id=_text(proposal.get("source_span_id")),
            normalized_value=_text(proposal.get("normalized_value")),
            required_for_full_ack=bool(proposal.get("required_for_full_ack", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target_slot": self.target_slot,
            "stable_key": self.stable_key,
            "source_span_id": self.source_span_id,
            "normalized_value": self.normalized_value,
            "required_for_full_ack": self.required_for_full_ack,
        }


@dataclass(frozen=True)
class CapturePlan:
    capture_plan_id: str
    turn_id: str
    source_event_id: str
    proposals: tuple[CaptureProposalRef, ...] = field(default_factory=tuple)
    plan_status: str = "has_proposals"

    @classmethod
    def from_proposals(
        cls,
        *,
        turn_id: str,
        source_event_id: str,
        proposals: Sequence[Mapping[str, Any] | CaptureProposalRef],
        capture_plan_id: str = "",
        plan_status: str = "has_proposals",
    ) -> "CapturePlan":
        refs = tuple(
            proposal if isinstance(proposal, CaptureProposalRef) else CaptureProposalRef.from_mapping(proposal)
            for proposal in proposals
        )
        plan_id = _text(capture_plan_id) or stable_id(
            "cp",
            turn_id,
            source_event_id,
            ",".join(ref.proposal_id for ref in refs),
        )
        return cls(
            capture_plan_id=plan_id,
            turn_id=_text(turn_id),
            source_event_id=_text(source_event_id),
            proposals=refs,
            plan_status=plan_status if (refs or plan_status != "has_proposals") else "no_capture",
        )

    @property
    def required_proposals(self) -> tuple[CaptureProposalRef, ...]:
        return tuple(ref for ref in self.proposals if ref.required_for_full_ack)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CAPTURE_PLAN_SCHEMA,
            "capture_plan_id": self.capture_plan_id,
            "turn_id": self.turn_id,
            "source_event_id": self.source_event_id,
            "plan_status": self.plan_status,
            "proposals": [ref.to_dict() for ref in self.proposals],
            "expected_required_proposal_count": len(self.required_proposals),
        }


def build_single_proposal_capture_plan(
    *,
    turn_id: str,
    source_event_id: str,
    target_slot: str,
    stable_key: str,
    source_span_id: str = "",
    normalized_value: str = "",
    proposal_id: str = "",
) -> CapturePlan:
    proposal = CaptureProposalRef(
        proposal_id=_text(proposal_id)
        or stable_id("cap", turn_id, source_event_id, stable_key, normalized_value),
        target_slot=_text(target_slot),
        stable_key=_text(stable_key),
        source_span_id=_text(source_span_id),
        normalized_value=_text(normalized_value),
        required_for_full_ack=True,
    )
    return CapturePlan.from_proposals(
        turn_id=turn_id,
        source_event_id=source_event_id,
        proposals=(proposal,),
    )


def build_memory_write_receipt(
    *,
    capture_plan: CapturePlan,
    proposal: CaptureProposalRef,
    receipt_id: str = "",
    receipt_status: str = STATUS_COMMITTED,
    source_event_id: str = "",
    source_span_ids: Sequence[str] = (),
    write_path_class: str = "TRUSTED_EXPLICIT_CAPTURE",
    source_authority: str = "USER_EXPLICIT",
    permit_id: str = "",
    admission_decision_id: str = "",
    transaction_id: str = "",
    principal_scope_key: str = "",
    workspace_scope_key: str = "",
    session_id: str = "",
    shelf: str = "profile",
    entity_id: str = "",
    value_fingerprint: str = "",
    policy_versions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    stable_key = _text(proposal.stable_key)
    tx_id = _text(transaction_id) or stable_id("tx", capture_plan.capture_plan_id, proposal.proposal_id, stable_key)
    durable_ref_id = stable_id("ref", shelf, stable_key, principal_scope_key)
    return {
        "schema": MEMORY_WRITE_RECEIPT_SCHEMA,
        "receipt_id": _text(receipt_id) or stable_id("mwr", tx_id, proposal.proposal_id),
        "receipt_status": _text(receipt_status) or STATUS_COMMITTED,
        "turn_id": capture_plan.turn_id,
        "capture_plan_id": capture_plan.capture_plan_id,
        "source_event_id": _text(source_event_id) or capture_plan.source_event_id,
        "source_span_ids": list(source_span_ids) or ([proposal.source_span_id] if proposal.source_span_id else []),
        "proposal_ids": [proposal.proposal_id],
        "write_path_class": _text(write_path_class),
        "source_authority": _text(source_authority),
        "permit_id": _text(permit_id),
        "admission_decision_id": _text(admission_decision_id),
        "transaction_id": tx_id,
        "idempotency_key": f"{capture_plan.turn_id}:{proposal.proposal_id}:{stable_key}",
        "scope": {
            "principal_scope_key": _text(principal_scope_key),
            "workspace_scope_key": _text(workspace_scope_key),
            "session_id": _text(session_id),
        },
        "durable_refs": [
            {
                "durable_ref_id": durable_ref_id,
                "shelf": _text(shelf),
                "slot_id": proposal.target_slot,
                "entity_id": _text(entity_id),
                "stable_key": stable_key,
                "value_fingerprint": _text(value_fingerprint)
                or (_hash_text(proposal.normalized_value) if proposal.normalized_value else ""),
                "temporal_status": "current",
                "truth_eligible": True,
                "model_facing_ack_allowed": True,
            }
        ],
        "supersession": {"supersedes_refs": [], "superseded_by": None},
        "failure": None,
        "policy_versions": dict(
            policy_versions
            or {
                "admission_policy": "admission.v1",
                "slot_registry": "slots.v1",
                "receipt_contract": "mwr.v1",
            }
        ),
    }


def is_committed_memory_write_receipt(receipt: Mapping[str, Any]) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    if receipt.get("schema") != MEMORY_WRITE_RECEIPT_SCHEMA:
        return False
    if receipt.get("receipt_status") != STATUS_COMMITTED:
        return False
    refs = receipt.get("durable_refs")
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        return False
    return any(
        isinstance(ref, Mapping)
        and bool(_text(ref.get("durable_ref_id")))
        and bool(_text(ref.get("slot_id")))
        and bool(_text(ref.get("stable_key")))
        and ref.get("truth_eligible") is True
        and ref.get("model_facing_ack_allowed") is True
        for ref in refs
    )


def compute_receipt_coverage(
    capture_plan: CapturePlan,
    receipts: Sequence[Mapping[str, Any]],
    *,
    principal_scope_key: str = "",
    workspace_scope_key: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    expected = [proposal.proposal_id for proposal in capture_plan.required_proposals]
    covered: list[str] = []
    failed: list[dict[str, str]] = []
    receipt_count = 0
    required_set = set(expected)
    for receipt in receipts:
        if not is_committed_memory_write_receipt(receipt):
            continue
        receipt_count += 1
        scope = receipt.get("scope") if isinstance(receipt.get("scope"), Mapping) else {}
        scope_mismatch = False
        if principal_scope_key and scope.get("principal_scope_key") != principal_scope_key:
            scope_mismatch = True
        if workspace_scope_key and scope.get("workspace_scope_key") != workspace_scope_key:
            scope_mismatch = True
        if session_id and scope.get("session_id") != session_id:
            scope_mismatch = True
        for proposal_id in receipt.get("proposal_ids") or []:
            proposal_id = _text(proposal_id)
            if proposal_id not in required_set:
                continue
            if scope_mismatch:
                failed.append({"proposal_id": proposal_id, "reason_code": REASON_SCOPE_MISMATCH})
            elif proposal_id not in covered:
                covered.append(proposal_id)
    missing = [proposal_id for proposal_id in expected if proposal_id not in covered]
    for proposal_id in missing:
        if not any(item["proposal_id"] == proposal_id for item in failed):
            failed.append({"proposal_id": proposal_id, "reason_code": REASON_MISSING_RECEIPT})
    if not expected:
        status = COVERAGE_NOT_APPLICABLE
    elif not covered:
        status = COVERAGE_NONE
    elif missing:
        status = COVERAGE_PARTIAL
    else:
        status = COVERAGE_COMPLETE
    return {
        "schema": RECEIPT_COVERAGE_SCHEMA,
        "turn_id": capture_plan.turn_id,
        "capture_plan_id": capture_plan.capture_plan_id,
        "coverage_status": status,
        "expected_proposals": expected,
        "covered_proposals": covered,
        "missing_proposals": missing,
        "failed_proposals": failed,
        "full_ack_allowed": status == COVERAGE_COMPLETE,
        "partial_ack_allowed": status == COVERAGE_PARTIAL,
        "receipt_count": receipt_count,
    }


def build_ack_plan(
    capture_plan: CapturePlan,
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    status = coverage.get("coverage_status")
    if status == COVERAGE_COMPLETE:
        ack_mode = ACK_FULL
    elif status == COVERAGE_PARTIAL:
        ack_mode = ACK_PARTIAL
    elif status == COVERAGE_NOT_APPLICABLE:
        ack_mode = ACK_NONE
    else:
        ack_mode = ACK_NONE
    proposal_by_id = {proposal.proposal_id: proposal for proposal in capture_plan.proposals}
    covered_slots = [
        proposal_by_id[proposal_id].target_slot
        for proposal_id in coverage.get("covered_proposals", [])
        if proposal_id in proposal_by_id
    ]
    missing_slots = [
        proposal_by_id[proposal_id].target_slot
        for proposal_id in coverage.get("missing_proposals", [])
        if proposal_id in proposal_by_id
    ]
    return {
        "schema": ACK_PLAN_SCHEMA,
        "turn_id": capture_plan.turn_id,
        "capture_plan_id": capture_plan.capture_plan_id,
        "ack_mode": ack_mode,
        "covered_slots": covered_slots,
        "missing_slots": missing_slots,
        "must_not_claim_full_commit": ack_mode != ACK_FULL,
        "allowed_response_modes": [
            "receipt_backed_full_ack",
            "receipt_backed_partial_ack",
            "honest_no_ack",
            "clarification",
        ],
    }


def commitment_guard_trace(
    *,
    capture_plan: CapturePlan,
    coverage: Mapping[str, Any],
    commitment_claim_present: bool,
) -> dict[str, Any]:
    expected = len(capture_plan.required_proposals)
    covered = len(coverage.get("covered_proposals") or [])
    allowed = not commitment_claim_present or coverage.get("coverage_status") == COVERAGE_COMPLETE
    return {
        "memory_commitment_guard": {
            "commitment_claim_present": bool(commitment_claim_present),
            "capture_plan_id": capture_plan.capture_plan_id,
            "receipt_coverage_status": coverage.get("coverage_status"),
            "expected_proposal_count": expected,
            "covered_proposal_count": covered,
            "final_answer_allowed": allowed,
            "reason_code": "" if allowed else "MEMORY_COMMITMENT_WITHOUT_WRITE_RECEIPT",
            "recovery_action": "" if allowed else "retry_capture_pipeline_once_or_honest_failure",
        }
    }
