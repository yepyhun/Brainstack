from __future__ import annotations

from brainstack.core import (
    AnswerType,
    AnswerabilityState,
    AuthorityBoundaryViolation,
    AuthorityClass,
    EvidenceId,
    EvidenceRef,
    EvidenceRole,
    MaxClaimStrength,
    MemoryAnswerability,
    ProjectionReceipt,
    ReasonCode,
    ReceiptId,
    ReceiptStatus,
    ScopeKey,
    SourceRole,
    StableKey,
    TraceId,
    WriteReceipt,
)


def test_memory_answerability_dict_uses_public_values() -> None:
    answerability = MemoryAnswerability(
        state=AnswerabilityState.ANSWERABLE,
        max_claim_strength=MaxClaimStrength.MEMORY_TRUTH,
        answer_type=AnswerType.EXPLICIT_USER_FACT,
        authority=AuthorityClass.EXPLICIT_CURRENT_FACT,
        reason_code=ReasonCode.AUTHORITATIVE_MEMORY_EVIDENCE,
        answer_evidence_ids=(EvidenceId("profile:debug-marker"),),
        must_not_claim=("current_assignment",),
        can_claim_memory_truth=True,
    )

    assert answerability.to_dict() == {
        "state": "answerable",
        "max_claim_strength": "memory_truth",
        "answer_type": "explicit_user_fact",
        "authority": "explicit_current_fact",
        "reason_code": "authoritative_memory_evidence",
        "answer_evidence_ids": ["profile:debug-marker"],
        "supporting_context_ids": [],
        "excluded_evidence_ids": [],
        "can_claim_memory_truth": True,
        "can_claim_current_assignment": False,
        "must_not_claim": ["current_assignment"],
    }


def test_evidence_receipt_contracts_are_json_ready() -> None:
    evidence = EvidenceRef(
        evidence_id=EvidenceId("ev-1"),
        shelf="profile",
        stable_key=StableKey("debug-marker"),
        role=EvidenceRole.ANSWER,
        authority=AuthorityClass.EXPLICIT_CURRENT_FACT,
        source_role=SourceRole.USER,
        reason_code=ReasonCode.AUTHORITATIVE_MEMORY_EVIDENCE,
    )
    write_receipt = WriteReceipt(
        receipt_id=ReceiptId("wr-1"),
        turn_trace_id=TraceId("turn-1"),
        stable_key=StableKey("debug-marker"),
        status=ReceiptStatus.COMMITTED,
    )
    projection_receipt = ProjectionReceipt(
        host_receipt_id=ReceiptId("host-1"),
        brainstack_receipt_id=ReceiptId("bs-1"),
        stable_key=StableKey("debug-marker"),
        status=ReceiptStatus.COMMITTED,
        parity_observable=True,
    )

    assert evidence.to_dict()["authority"] == "explicit_current_fact"
    assert write_receipt.to_dict()["status"] == "committed"
    assert projection_receipt.to_dict()["parity_observable"] is True


def test_typed_errors_expose_reason_code() -> None:
    assert AuthorityBoundaryViolation.reason_code == ReasonCode.AUTHORITY_MISMATCH
    assert issubclass(AuthorityBoundaryViolation, Exception)
    assert ScopeKey("principal:tomi") == "principal:tomi"
