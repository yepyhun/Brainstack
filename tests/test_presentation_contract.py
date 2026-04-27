from __future__ import annotations

from brainstack.product_contracts import (
    apply_presentation_hygiene,
    build_interim_assistant_message,
    default_presentation_runtime_contract,
    render_current_assignment_status,
)


def test_hermes_prompt_includes_style_contract() -> None:
    cleaned, trace = apply_presentation_hygiene(
        "Szia 😊\nMiben segíthetek?",
        no_emoji=True,
        no_final_followup=True,
    )

    assert "😊" not in cleaned
    assert "Miben segíthetek?" not in cleaned
    assert trace["applied_by"] == "hermes.presentation"


def test_direct_renderer_uses_user_language_template() -> None:
    text = render_current_assignment_status(
        has_current_assignment_evidence=False,
        language="hu",
    )
    cleaned, trace = apply_presentation_hygiene(text, no_emoji=True)

    assert "Nincs rögzített aktuális feladat" in cleaned
    assert "No typed" not in cleaned
    assert trace["semantic_changes_allowed"] is False


def test_default_discord_personality_not_kawaii_after_wizard() -> None:
    contract = default_presentation_runtime_contract()

    assert contract["default_personality"] == "neutral"


def test_soul_examples_not_active_prompt() -> None:
    contract = default_presentation_runtime_contract()

    assert contract["soul_examples_active_prompt"] is False


def test_style_contract_reaches_final_delivery_path() -> None:
    contract = default_presentation_runtime_contract()

    assert contract["applied_by"] == "hermes.presentation"
    assert contract["style_preferences_source"] == "brainstack.preference_evidence"


def test_interim_assistant_message_respects_style_or_disabled() -> None:
    disabled, disabled_trace = build_interim_assistant_message(
        enabled=False,
        text="Hermes 😊\nDolgozom.",
        no_emoji=True,
        decorative_prefixes=("Hermes",),
    )
    enabled, enabled_trace = build_interim_assistant_message(
        enabled=True,
        text="Hermes 😊\nDolgozom.",
        no_emoji=True,
        decorative_prefixes=("Hermes",),
    )

    assert disabled is None
    assert disabled_trace["enabled"] is False
    assert enabled == "Dolgozom."
    assert enabled_trace["enabled"] is True
