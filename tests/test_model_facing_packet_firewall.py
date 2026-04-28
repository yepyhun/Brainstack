from __future__ import annotations

import random

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


def test_packet_budget_shadow_reports_without_changing_output() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "truth1",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
                "receipt_id": "mwr_truth1",
                "token_estimate": 8,
            },
            {
                "evidence_id": "support1",
                "source_role": "user",
                "evidence_class": "support_only",
                "truth_eligible": False,
                "answer_evidence": False,
                "token_estimate": 12,
            },
        ],
        packet_budget_mode="shadow",
        packet_budget_max_candidate_tokens=8,
    )

    assert packet["kept_count"] == 2
    assert packet["packet_budget"]["mode"] == "shadow"
    assert packet["packet_budget"]["applied_to_output"] is False
    assert packet["packet_budget"]["dropped_candidate_tokens"] == 12


def test_packet_budget_active_drops_support_without_dropping_truth() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "truth1",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
                "receipt_id": "mwr_truth1",
                "token_estimate": 8,
            },
            {
                "evidence_id": "support1",
                "source_role": "user",
                "evidence_class": "support_only",
                "truth_eligible": False,
                "answer_evidence": False,
                "token_estimate": 12,
            },
        ],
        packet_budget_mode="active",
        packet_budget_max_candidate_tokens=8,
    )

    assert packet["packet_budget"]["applied_to_output"] is True
    assert [item["evidence_id"] for item in packet["kept"]] == ["truth1"]
    assert packet["answer_evidence"][0]["evidence_id"] == "truth1"
    assert packet["dropped"][-1] == {
        "evidence_id": "support1",
        "drop_reason": "dropped_budget_support_only",
    }


def test_packet_budget_active_fails_closed_when_truth_exceeds_cap() -> None:
    packet = model_facing_packet_firewall(
        [
            {
                "evidence_id": "truth1",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
                "receipt_id": "mwr_truth1",
                "token_estimate": 8,
            },
            {
                "evidence_id": "truth2",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
                "receipt_id": "mwr_truth2",
                "token_estimate": 8,
            },
            {
                "evidence_id": "support1",
                "source_role": "user",
                "evidence_class": "support_only",
                "truth_eligible": False,
                "answer_evidence": False,
                "token_estimate": 4,
            },
        ],
        packet_budget_mode="active",
        packet_budget_max_candidate_tokens=10,
    )

    assert packet["packet_budget"]["status"] == "insufficient_for_authority_minimum"
    assert packet["packet_budget"]["fail_closed"] is True
    assert [item["evidence_id"] for item in packet["kept"]] == ["truth1", "truth2"]
    assert [item["evidence_id"] for item in packet["answer_evidence"]] == ["truth1", "truth2"]


def test_packet_budget_active_stress_preserves_truth_evidence() -> None:
    rng = random.Random(1961)
    for index in range(500):
        truth_rows = [
            {
                "evidence_id": f"truth_{index}_{inner}",
                "source_role": "user",
                "lane": "admitted_durable_truth",
                "truth_eligible": True,
                "answer_evidence": True,
                "receipt_id": f"mwr_{index}_{inner}",
                "token_estimate": rng.randint(3, 12),
            }
            for inner in range(rng.randint(1, 4))
        ]
        support_rows = [
            {
                "evidence_id": f"support_{index}_{inner}",
                "source_role": "user",
                "evidence_class": "support_only",
                "truth_eligible": False,
                "answer_evidence": False,
                "token_estimate": rng.randint(1, 18),
            }
            for inner in range(rng.randint(0, 8))
        ]
        rows = [*truth_rows, *support_rows]
        rng.shuffle(rows)
        budget = rng.randint(1, max(1, sum(item["token_estimate"] for item in truth_rows) + 18))

        packet = model_facing_packet_firewall(
            rows,
            packet_budget_mode="active",
            packet_budget_max_candidate_tokens=budget,
        )

        kept_ids = {item["evidence_id"] for item in packet["kept"]}
        answer_ids = {item["evidence_id"] for item in packet["answer_evidence"]}
        truth_ids = {item["evidence_id"] for item in truth_rows}
        assert truth_ids.issubset(kept_ids)
        assert truth_ids.issubset(answer_ids)
