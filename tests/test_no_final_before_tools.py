from __future__ import annotations

from brainstack.product_contracts import decide_final_answer_allowed


def test_url_inspect_cannot_guess_without_web_tool_or_unavailable_diagnostic() -> None:
    decision = decide_final_answer_allowed(external_capability_possible=True)

    assert decision.final_answer_allowed is False
    assert decision.reason_code == "EXTERNAL_CAPABILITY_UNRESOLVED"


def test_model_declared_tool_intent_blocks_final_until_result() -> None:
    decision = decide_final_answer_allowed(
        external_capability_possible=True,
        model_declared_tool_intent=True,
        required_bundle_loaded=True,
        tool_result_received=False,
    )

    assert decision.final_answer_allowed is False


def test_clarification_allows_final_guard_exit() -> None:
    decision = decide_final_answer_allowed(
        external_capability_possible=True,
        clarification_asked=True,
    )

    assert decision.final_answer_allowed is True

