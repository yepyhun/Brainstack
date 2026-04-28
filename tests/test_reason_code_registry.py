from __future__ import annotations

from brainstack.core.reason_codes import ReasonCode, is_reason_code, reason_code_values


def test_reason_code_registry_contains_public_trace_codes() -> None:
    values = reason_code_values()

    assert ReasonCode.SELECTED_RECEIPT_BACKED_FACT.value in values
    assert ReasonCode.DROPPED_ASSISTANT_CLAIM_NOT_TRUTH_AUTHORITY.value in values
    assert ReasonCode.DROPPED_SUPPORT_ONLY_FOR_ANSWER_TRUTH.value in values
    assert ReasonCode.FULL_ACK_REQUIRES_COMPLETE_RECEIPT_COVERAGE.value in values
    assert ReasonCode.SELECTED_BUDGET_PROTECTED_AUTHORITY.value in values
    assert ReasonCode.DROPPED_BUDGET_SUPPORT_ONLY.value in values
    assert ReasonCode.DROPPED_BUDGET_DUPLICATE_LOWER_AUTHORITY.value in values
    assert ReasonCode.BUDGET_INSUFFICIENT_FOR_AUTHORITY_MINIMUM.value in values


def test_free_text_reason_is_not_registered() -> None:
    assert is_reason_code("dropped_assistant_claim_not_truth_authority")
    assert not is_reason_code("assistant looked suspicious, so I dropped it")
