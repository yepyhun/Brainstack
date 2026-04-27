from __future__ import annotations

from scripts.ga_product_matrix import (
    discord_interaction_matrix,
    memory_correctness_matrix,
    product_e2e_matrix,
    provider_latency_resilience_matrix,
    tool_capability_safety_matrix,
)


def test_ga_memory_identity_style_project_reference_reset() -> None:
    matrix = memory_correctness_matrix()

    assert matrix["identity_preferred_name"] is True
    assert matrix["platform_handle_separate"] is True
    assert matrix["style_no_emoji"] is True
    assert matrix["reference_url_recall"] is True


def test_ga_assistant_contamination_not_refed() -> None:
    assert memory_correctness_matrix()["assistant_contamination_not_refed"] is True


def test_ga_support_only_not_answer_evidence() -> None:
    assert memory_correctness_matrix()["support_only_not_answer_evidence"] is True


def test_ga_terminal_approval_required_for_destructive_command() -> None:
    matrix = tool_capability_safety_matrix()

    assert matrix["terminal_destructive_requires_approval"] is True
    assert matrix["schema_loading_grants_approval"] is False


def test_ga_file_capability_truthful() -> None:
    assert tool_capability_safety_matrix()["file_capability_truthful_when_manifest_available"] is True


def test_ga_web_unavailable_no_guess() -> None:
    assert tool_capability_safety_matrix()["web_unavailable_no_guess"] is True


def test_ga_toolloader_fallback_preserves_capability() -> None:
    assert tool_capability_safety_matrix()["toolloader_fallback_preserves_capability"] is True


def test_ga_provider_delay_first_visible_commitment() -> None:
    assert provider_latency_resilience_matrix()["provider_delay_first_visible_commitment"] == "progress_or_final_required"


def test_ga_provider_unavailable_degrades_truthfully() -> None:
    assert provider_latency_resilience_matrix()["provider_unavailable_degrades_truthfully"] is True


def test_ga_provider_matrix_targeted_gpt55_diagnostic() -> None:
    gpt55 = provider_latency_resilience_matrix()["gpt55"]

    assert gpt55["default_soak_model"] is False
    assert gpt55["targeted_high_value_diagnostic"] is True


def test_ga_provider_matrix_scripted_adversarial_required() -> None:
    assert provider_latency_resilience_matrix()["scripted_adversarial_provider_required"] is True


def test_ga_discord_synthetic_path_proof() -> None:
    matrix = discord_interaction_matrix()

    assert matrix["synthetic_gateway_path_proof"] is True
    assert matrix["manual_only_proof"] is False
    assert matrix["passed"] is False


def test_product_matrix_blocks_on_missing_live_smoke() -> None:
    matrix = product_e2e_matrix()

    assert matrix["ready"] is False
    assert "LIVE_SMOKE_MISSING" in matrix["blocking"]
