from __future__ import annotations

from brainstack.product_contracts import classify_assistant_claim


def test_assistant_self_claim_default_inspect_only() -> None:
    claim = classify_assistant_claim("assistant_self_claim")

    assert claim["truth_eligible"] is False
    assert claim["model_facing_default"] is False
    assert claim["support_visibility"] == "inspect_only"


def test_assistant_user_claim_not_identity_truth() -> None:
    claim = classify_assistant_claim("assistant_user_claim")

    assert claim["truth_eligible"] is False
    assert claim["authority_source"] == "not_authority"


def test_assistant_tool_capability_claim_uses_runtime_manifest_only() -> None:
    claim = classify_assistant_claim("assistant_tool_capability_claim")

    assert claim["truth_eligible"] is False
    assert claim["authority_source"] == "hermes_capability_manifest"


def test_assistant_style_claim_not_style_authority() -> None:
    claim = classify_assistant_claim("assistant_style_claim")

    assert claim["truth_eligible"] is False
    assert claim["authority_source"] == "user_preference_and_hermes_presentation_contract"


def test_assistant_commitment_not_write_receipt() -> None:
    claim = classify_assistant_claim("assistant_commitment")

    assert claim["truth_eligible"] is False
    assert claim["authority_source"] == "write_receipt_required"


def test_tool_result_paraphrase_preserves_tool_result_authority() -> None:
    claim = classify_assistant_claim(
        "assistant_tool_result_paraphrase",
        linked_tool_result_id="tool_result:pwd:1",
    )

    assert claim["truth_eligible"] is False
    assert claim["authority_source"] == "linked_tool_result"
    assert claim["model_facing_default"] is True
