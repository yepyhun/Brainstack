from __future__ import annotations

from brainstack.product_contracts import (
    apply_corrected_false,
    audit_contamination_candidates,
    build_correction_proposal,
    model_facing_packet_firewall,
)


def test_user_rejection_marks_prior_assistant_self_claim_corrected_false() -> None:
    claims = [{"claim_id": "a1", "source_role": "assistant", "claim_type": "assistant_self_claim"}]
    proposal = build_correction_proposal(
        source_event_id="u2",
        source_span_id="u2:s1",
        correction_type="reject_prior_assistant_self_claim",
        prior_claims=claims,
    )
    updated, receipts = apply_corrected_false(claims, proposal, corrected_at="2026-04-27T00:00:00Z")

    assert updated[0]["corrected_status"] == "corrected_false"
    assert updated[0]["support_visibility"] == "contradiction_only"
    assert receipts[0]["raw_transcript_deleted"] is False


def test_user_correction_marks_prior_assistant_user_claim_corrected_false() -> None:
    claims = [{"claim_id": "a2", "source_role": "assistant", "claim_type": "assistant_user_claim"}]
    proposal = build_correction_proposal(
        source_event_id="u3",
        source_span_id="u3:s1",
        correction_type="reject_prior_assistant_user_claim",
        prior_claims=claims,
    )
    updated, _ = apply_corrected_false(claims, proposal, corrected_at="2026-04-27T00:00:00Z")

    assert proposal.target_claim_ids == ("a2",)
    assert updated[0]["truth_eligible"] is False
    assert updated[0]["model_facing_default"] is False


def test_corrected_false_not_model_facing_normal_query() -> None:
    packet = model_facing_packet_firewall(
        [{"evidence_id": "a1", "corrected_status": "corrected_false", "truth_eligible": False}]
    )

    assert packet["kept_count"] == 0
    assert packet["dropped"][0]["drop_reason"] == "CORRECTED_FALSE_CONTRADICTION_ONLY"


def test_corrected_false_available_only_for_history_query() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "a1",
                "source_role": "assistant",
                "claim_type": "assistant_self_claim",
                "corrected_status": "corrected_false",
            }
        ],
        query_mode="history",
    )

    assert packet["kept_count"] == 1
    assert packet["kept"][0]["quote_only"] is True
    assert packet["kept"][0]["truth_eligible"] is False


def test_existing_contamination_audit_demotes_without_raw_delete() -> None:
    audit = audit_contamination_candidates(
        [
            {
                "claim_id": "a1",
                "source_role": "assistant",
                "claim_type": "assistant_self_claim",
                "model_facing_default": True,
                "truth_eligible": True,
            }
        ]
    )

    assert audit["suspect_count"] == 1
    assert audit["raw_transcript_deleted"] is False
    assert audit["repaired_claims"][0]["model_facing_default"] is False


def test_repair_receipt_created_for_contamination_demote() -> None:
    audit = audit_contamination_candidates(
        [
            {
                "claim_id": "a1",
                "source_role": "assistant",
                "claim_type": "assistant_user_claim",
                "model_facing_default": True,
            }
        ]
    )

    assert audit["repair_receipts"][0]["action"] == "demote_assistant_claim"
    assert audit["repair_receipts"][0]["raw_transcript_deleted"] is False


def test_prior_user_question_continuity_still_recallable() -> None:
    packet = model_facing_packet_firewall(
        [{"evidence_id": "u1", "source_role": "user", "lane": "user_event_continuity"}]
    )

    assert packet["kept_count"] == 1


def test_exact_literal_user_continuity_still_recallable() -> None:
    packet = model_facing_packet_firewall(
        [{"evidence_id": "literal1", "source_role": "user", "truth_eligible": True, "answer_evidence": True}]
    )

    assert packet["answer_evidence"][0]["evidence_id"] == "literal1"


def test_tool_result_continuity_still_model_facing() -> None:
    packet = model_facing_packet_firewall(
        [{"evidence_id": "tool1", "source_role": "tool", "lane": "tool_result_continuity"}]
    )

    assert packet["kept_count"] == 1
