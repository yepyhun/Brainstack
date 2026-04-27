from __future__ import annotations

from brainstack.product_contracts import apply_presentation_hygiene


def test_no_emoji_filter_non_semantic() -> None:
    cleaned, trace = apply_presentation_hygiene("A válasz igaz. 😊", no_emoji=True)

    assert cleaned == "A válasz igaz."
    assert trace["removed_emoji_count"] == 1


def test_filter_does_not_modify_tool_capability_claim() -> None:
    text = "A web.browse képesség configured_unavailable."
    cleaned, trace = apply_presentation_hygiene(text, no_emoji=True, no_em_dash=True)

    assert cleaned == text
    assert trace["semantic_changes_allowed"] is False


def test_no_final_followup_closer_filter_non_semantic() -> None:
    cleaned, trace = apply_presentation_hygiene(
        "Rögzítve.\nVan még kérdésed?",
        no_final_followup=True,
    )

    assert cleaned == "Rögzítve."
    assert trace["removed_followup_closer"] is True


def test_em_dash_filter_non_semantic() -> None:
    cleaned, trace = apply_presentation_hygiene("Rögzítve — kész.", no_em_dash=True)

    assert cleaned == "Rögzítve - kész."
    assert trace["replaced_em_dash_count"] == 1


def test_decorative_persona_prefix_removed_when_forbidden() -> None:
    cleaned, trace = apply_presentation_hygiene(
        "Hermes 😊\nRögzítve.",
        no_emoji=True,
        decorative_prefixes=("Hermes",),
    )

    assert cleaned == "Rögzítve."
    assert trace["removed_decorative_prefix"] is True


def test_persona_content_claim_not_silently_rewritten() -> None:
    text = "A nevem Hermes, és ezt állítom."
    cleaned, trace = apply_presentation_hygiene(text, decorative_prefixes=("Hermes",))

    assert cleaned == text
    assert trace["removed_decorative_prefix"] is False


def test_filter_does_not_modify_tool_result() -> None:
    text = "A parancs kimenete: /workspace"
    cleaned, _ = apply_presentation_hygiene(text, no_emoji=True, no_em_dash=True)

    assert cleaned == text


def test_filter_does_not_modify_capability_unavailable_diagnostic() -> None:
    text = "A web.browse capability configured_unavailable: missing_backend_or_env_key."
    cleaned, _ = apply_presentation_hygiene(text, no_emoji=True, no_em_dash=True)

    assert cleaned == text


def test_filter_does_not_modify_approval_or_refusal() -> None:
    text = "Approval required before command execution."
    cleaned, _ = apply_presentation_hygiene(text, no_emoji=True)

    assert cleaned == text
