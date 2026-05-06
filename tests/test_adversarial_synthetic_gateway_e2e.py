from __future__ import annotations

from brainstack.product_contracts import build_failure_bundles, run_adversarial_synthetic_gateway_contract


def test_synthetic_gateway_path_proof_uses_required_boundaries() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert result["path_proof"]["used_gateway_equivalent"] is True
    assert result["path_proof"]["used_prompt_packet_firewall"] is True
    assert result["path_proof"]["used_presentation_hygiene"] is True
    assert result["path_proof"]["used_url_final_answer_guard"] is True


def test_assistant_self_contamination_does_not_refeed_after_reset() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    kept_ids = {item["evidence_id"] for item in result["packet"]["kept"]}
    dropped_reasons = {item["drop_reason"] for item in result["packet"]["dropped"]}

    assert "a1" not in kept_ids
    assert "a2" not in kept_ids
    assert "CORRECTED_FALSE_CONTRADICTION_ONLY" in dropped_reasons
    assert "ASSISTANT_CLAIM_NOT_MODEL_FACING" in dropped_reasons


def test_identity_split_survives_adversarial_wrong_handle_claim() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert result["identity"]["preferred_name"] == "Alex"
    assert result["identity"]["platform_handle"] == "ExampleHandle"


def test_reference_url_recalls_exact_after_reset() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert result["reference_recall"] == "https://example.com/org/resource-x"


def test_current_assignment_renderer_is_style_clean() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert "No typed current-assignment evidence is recorded" in result["final_text"]
    assert "🐞" not in result["final_text"]
    assert "SyntheticPersona" not in result["final_text"]


def test_url_inspect_web_unavailable_returns_diagnostic_not_guess() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert result["url_guard"]["allowed"] is True
    assert result["url_guard"]["reason_code"] == "CAPABILITY_UNAVAILABLE_DIAGNOSTIC"
    assert result["url_guard"]["content_claims_allowed"] is False


def test_phrase_provenance_blocks_provider_generated_persona() -> None:
    result = run_adversarial_synthetic_gateway_contract()

    assert result["phrase_provenance"]["first_origin"]["type"] == "provider_generated"
    assert result["phrase_provenance"]["final_verdict"] == "blocked_by_firewall"


def test_failed_probe_would_emit_failure_bundle() -> None:
    result = run_adversarial_synthetic_gateway_contract()
    failed = []
    for probe in result["probes"]:
        probe = dict(probe)
        if probe["probe_id"] == "184.url.no_guess":
            probe["status"] = "fail"
        failed.append(probe)

    from brainstack.product_contracts import ProductProbeEnvelope

    bundles = build_failure_bundles(ProductProbeEnvelope.from_dict(item) for item in failed)

    assert bundles
    assert bundles[0]["owner_classification"]["primary_owner"] == "hermes_tool_state_guard"
