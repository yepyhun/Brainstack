from __future__ import annotations

from brainstack.product_contracts import model_facing_packet_firewall


def test_model_facing_packet_firewall_drops_assistant_self_claim() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "a1",
                "source_role": "assistant",
                "claim_type": "assistant_self_claim",
                "truth_eligible": False,
            }
        ]
    )

    assert packet["kept_count"] == 0
    assert packet["dropped"][0]["drop_reason"] == "ASSISTANT_CLAIM_NOT_MODEL_FACING"


def test_model_facing_packet_firewall_drops_corrected_false_by_default() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "c1",
                "source_role": "assistant",
                "claim_type": "assistant_user_claim",
                "corrected_status": "corrected_false",
            }
        ]
    )

    assert packet["kept_count"] == 0
    assert packet["dropped"][0]["drop_reason"] == "CORRECTED_FALSE_CONTRADICTION_ONLY"


def test_support_only_never_answer_evidence() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "s1",
                "source_role": "assistant",
                "evidence_class": "support_only",
                "truth_eligible": False,
                "answer_evidence": True,
            }
        ]
    )

    assert packet["answer_evidence"] == []
    assert packet["dropped"][0]["drop_reason"] == "SUPPORT_ONLY_NOT_ANSWER_EVIDENCE"


def test_raw_transcript_retained_but_not_model_facing() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "raw1",
                "raw_transcript_preserved": True,
                "source_role": "assistant",
                "claim_type": "assistant_self_claim",
            }
        ]
    )

    assert packet["kept"] == []
    assert packet["dropped"][0]["evidence_id"] == "raw1"


def test_history_query_can_include_assistant_output_as_quote_only() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "h1",
                "source_role": "assistant",
                "claim_type": "assistant_self_claim",
                "truth_eligible": False,
            }
        ],
        query_mode="history",
    )

    assert packet["kept_count"] == 1
    assert packet["kept"][0]["quote_only"] is True
    assert packet["kept"][0]["truth_eligible"] is False


def test_current_assignment_not_promoted_from_assistant_or_background() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "task1",
                "lane": "current_assignment",
                "source_role": "assistant",
                "authority": "BACKGROUND_OR_PULSE",
                "truth_eligible": True,
            }
        ]
    )

    assert packet["kept_count"] == 0
    assert packet["dropped"][0]["drop_reason"] == "CURRENT_ASSIGNMENT_UNTRUSTED_AUTHORITY"


def test_admitted_truth_can_be_answer_evidence() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "truth1",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
            }
        ]
    )

    assert packet["kept_count"] == 1
    assert packet["answer_evidence"][0]["evidence_id"] == "truth1"
