from __future__ import annotations

from brainstack.product_contracts import (
    ProbeOwner,
    ProbeStatus,
    Repairability,
    Severity,
    build_capability_manifest,
    build_failure_bundles,
    continuity_visibility,
    decide_final_answer_allowed,
    default_hot_containment_toggles,
    direct_renderer_negative_allowed,
)


def test_default_config_personality_neutral_not_kawaii() -> None:
    toggles = default_hot_containment_toggles()

    assert toggles.production_personality == "neutral"


def test_conversation_heavy_not_capability_gate() -> None:
    toggles = default_hot_containment_toggles()
    manifest = build_capability_manifest(
        configured_capabilities=("filesystem.search_read", "terminal.execute", "web.browse"),
        executable_capabilities=("filesystem.search_read", "terminal.execute", "web.browse"),
    )

    assert toggles.conversation_heavy_capability_gate is False
    assert manifest["capability_shrunk"] is False


def test_negative_direct_renderer_requires_resolved_memory_target() -> None:
    blocked = direct_renderer_negative_allowed(
        resolved_memory_target=False,
        localized_template=True,
    )

    assert blocked["allowed"] is False
    assert blocked["reason_code"] == "NEGATIVE_RENDERER_CONTAINED"


def test_tool_only_in_heavy_prompt_residue_absent() -> None:
    toggles = default_hot_containment_toggles()

    assert toggles.tool_only_in_heavy_prompt_residue_forbidden is True


def test_assistant_output_continuity_not_model_facing_when_firewall_missing() -> None:
    visibility = continuity_visibility(
        source_role="assistant",
        claim_type="assistant_self_claim",
        truth_eligible=True,
    )

    assert visibility["raw_transcript_preserved"] is True
    assert visibility["truth_eligible"] is False
    assert visibility["model_facing_default"] is False
    assert visibility["support_visibility"] == "inspect_only"


def test_full_configured_tool_fallback_available_when_toolloader_not_proven() -> None:
    toggles = default_hot_containment_toggles()

    assert toggles.full_configured_tool_fallback_when_toolloader_unproven is True


def test_renderer_memory_status_still_allowed_when_resolved_and_not_external() -> None:
    decision = decide_final_answer_allowed(
        external_capability_possible=True,
        renderer_resolved_memory_target=True,
    )

    assert decision.final_answer_allowed is True
    assert decision.reason_code == "RESOLVED_MEMORY_OR_RUNTIME_STATUS_TARGET"


def test_rollback_matrix_emits_owner_classified_results() -> None:
    from brainstack.product_contracts import ProductProbeEnvelope

    probe = ProductProbeEnvelope(
        probe_id="phase1795.assistant_continuity",
        phase="179.5",
        scenario_id="assistant_output_containment",
        status=ProbeStatus.FAIL,
        owner=ProbeOwner.BRAINSTACK_RETRIEVAL_ANSWERABILITY,
        repairability=Repairability.REPAIRABLE_AUTOMATIC,
        severity=Severity.P1,
        reason_code="ASSISTANT_OUTPUT_MODEL_FACING",
        recommended_playbook="ASSISTANT_OUTPUT_CONTAINMENT",
    )

    bundle = build_failure_bundles([probe])[0]

    assert bundle["owner_classification"]["primary_owner"] == "brainstack_retrieval_answerability"
    assert "tests/test_hot_containment.py" in bundle["minimal_retest"]


def test_containment_toggles_are_source_of_truth_contracts() -> None:
    toggles = default_hot_containment_toggles().to_dict()

    assert toggles["schema"] == "brainstack.hot_containment_toggles.v1"
    assert toggles["configured_capabilities_preserved"] is True
