from __future__ import annotations

from brainstack.product_contracts import decide_final_answer_allowed, decide_url_content_claim_allowed


def test_remember_url_does_not_auto_fetch() -> None:
    decision = decide_final_answer_allowed(
        external_capability_possible=True,
        renderer_resolved_memory_target=True,
        model_declared_tool_intent=False,
    )

    assert decision.final_answer_allowed is True
    assert decision.reason_code == "RESOLVED_MEMORY_OR_RUNTIME_STATUS_TARGET"


def test_inspect_url_requires_tool_result_or_unavailable_diagnostic() -> None:
    decision = decide_final_answer_allowed(external_capability_possible=True)

    assert decision.final_answer_allowed is False
    assert "tool_result" in decision.required_exit


def test_url_inspect_web_unavailable_returns_diagnostic() -> None:
    decision = decide_url_content_claim_allowed(
        url_present=True,
        content_claim_made=True,
        unavailable_diagnostic_emitted=True,
    )

    assert decision["allowed"] is True
    assert decision["reason_code"] == "CAPABILITY_UNAVAILABLE_DIAGNOSTIC"
    assert decision["content_claims_allowed"] is False


def test_url_inspect_no_content_guess_without_web_result() -> None:
    decision = decide_url_content_claim_allowed(
        url_present=True,
        content_claim_made=True,
    )

    assert decision["allowed"] is False
    assert decision["reason_code"] == "URL_CONTENT_CLAIM_WITHOUT_EVIDENCE"


def test_url_content_claim_requires_web_tool_result_id() -> None:
    decision = decide_url_content_claim_allowed(
        url_present=True,
        content_claim_made=True,
        web_tool_result_id="web:1",
    )

    assert decision["allowed"] is True
    assert decision["content_claims_allowed"] is True
    assert decision["web_tool_result_id"] == "web:1"
