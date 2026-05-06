from __future__ import annotations

from brainstack.capture_pipeline import (
    admit_structured_capture_items,
    build_capture_plan_from_structured,
    simulate_receipt_coverage_for_accepted_capture,
)
from brainstack.memory_write_receipts import ACK_FULL, ACK_PARTIAL, COVERAGE_COMPLETE, COVERAGE_PARTIAL


def _item(target_slot: str, value: str, span: str, **extra):
    return {
        "target_slot": target_slot,
        "normalized_value": value,
        "source_span_id": span,
        "stable_key": target_slot,
        "confidence": 0.94,
        **extra,
    }


def test_explicit_identity_capture_produces_span_anchored_proposal() -> None:
    plan = build_capture_plan_from_structured(
        turn_id="turn-hu",
        source_event_id="user-msg-hu",
        source_role="user",
        items=[
            _item(
                "identity.preferred_address_name",
                "Alex",
                "span-name",
                surface_value="Alex a nevem",
                language="hu",
            )
        ],
    )

    assert plan["plan_status"] == "has_proposals"
    assert plan["proposals"][0]["target_slot"] == "identity.preferred_address_name"
    assert plan["proposals"][0]["normalized_value"] == "Alex"
    assert plan["proposals"][0]["source_span_id"] == "span-name"
    assert plan["proposals"][0]["required_for_full_ack"] is True


def test_capture_plan_lists_expected_required_proposals() -> None:
    plan = build_capture_plan_from_structured(
        turn_id="turn-1",
        source_event_id="user-msg-1",
        source_role="user",
        items=[
            _item("identity.preferred_address_name", "Alex", "span-name"),
            _item("identity.age", "19", "span-age"),
            _item("reference.repository_url", "https://example.com/example-lib", "span-url"),
        ],
    )

    assert plan["expected_required_proposal_count"] == 3
    assert [p["target_slot"] for p in plan["proposals"]] == [
        "identity.preferred_address_name",
        "identity.age",
        "reference.repository_url",
    ]


def test_capture_plan_required_for_full_ack_drives_receipt_coverage() -> None:
    result = simulate_receipt_coverage_for_accepted_capture(
        turn_id="turn-1",
        source_event_id="user-msg-1",
        source_role="user",
        items=[
            _item("identity.preferred_address_name", "Alex", "span-name"),
            _item("identity.age", "19", "span-age"),
        ],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )

    assert result["receipt_coverage"]["coverage_status"] == COVERAGE_COMPLETE
    assert result["receipt_coverage"]["full_ack_allowed"] is True
    assert result["ack_plan"]["ack_mode"] == ACK_FULL


def test_style_preference_capture_produces_preference_slots() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-style",
        source_event_id="user-msg-style",
        source_role="user",
        items=[_item("preference.formatting", "no emoji; no em dash", "span-style")],
    )

    assert result["admission_decisions"][0]["accepted"] is True
    assert result["admission_decisions"][0]["target_slot"] == "preference.formatting"


def test_assistant_address_capture_uses_profile_preference_slot() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-assistant-address",
        source_event_id="user-msg-assistant-address",
        source_role="user",
        items=[_item("preference.assistant_address_name", "Helper", "span-assistant-address")],
    )

    decision = result["admission_decisions"][0]
    assert decision["accepted"] is True
    assert decision["target_slot"] == "preference.assistant_address_name"
    assert decision["stable_key"] == "preference:assistant_address_name"
    assert decision["truth_eligible"] is True


def test_project_created_by_capture_uses_generic_project_slot() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-project",
        source_event_id="user-msg-project",
        source_role="user",
        items=[
            _item(
                "project.created_by",
                "Alex",
                "span-created-by",
                capture_intent="project_metadata",
            )
        ],
    )

    assert result["admission_decisions"][0]["accepted"] is True
    assert result["admission_decisions"][0]["target_slot"] == "project.created_by"


def test_component_inspired_by_capture_uses_generic_project_slot() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-project",
        source_event_id="user-msg-project",
        source_role="user",
        items=[
            _item(
                "project.component_inspired_by",
                "Graphiti",
                "span-graphiti",
                capture_intent="project_metadata",
            )
        ],
    )

    assert result["admission_decisions"][0]["accepted"] is True
    assert result["admission_decisions"][0]["target_slot"] == "project.component_inspired_by"


def test_reference_repository_url_capture_preserves_exact_url_literal() -> None:
    url = "https://example.com/example-lib"
    result = admit_structured_capture_items(
        turn_id="turn-url",
        source_event_id="user-msg-url",
        source_role="user",
        items=[_item("reference.repository_url", url, "span-url", capture_intent="reference_save")],
    )

    assert result["capture_plan"]["proposals"][0]["normalized_value"] == url
    assert result["admission_decisions"][0]["accepted"] is True


def test_assistant_message_never_generates_capture_proposal() -> None:
    result = build_capture_plan_from_structured(
        turn_id="turn-bad",
        source_event_id="assistant-msg",
        source_role="assistant",
        items=[_item("identity.preferred_address_name", "PlatformAlex", "span-assistant")],
    )

    assert result["plan_status"] == "rejected"
    assert result["rejection_reason"] == "non_user_source_role"
    assert result["expected_required_proposal_count"] == 0


def test_low_confidence_capture_does_not_write_durable_truth() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-low",
        source_event_id="user-msg-low",
        source_role="user",
        items=[_item("identity.preferred_address_name", "Alex", "span-name", confidence=0.49)],
    )

    assert result["capture_plan"]["plan_status"] == "needs_clarification"
    assert result["admission_decisions"] == []


def test_admission_only_decides_capture_plan_proposals() -> None:
    result = admit_structured_capture_items(
        turn_id="turn-mixed",
        source_event_id="user-msg-mixed",
        source_role="user",
        items=[
            _item("identity.age", "19", "span-age"),
            _item("identity.preferred_address_name", "Alex", "span-name", confidence=0.0),
            _item("reference.repository_url", "https://example.com/example-lib", "", capture_intent="reference_save"),
        ],
    )

    plan_ids = {proposal["proposal_id"] for proposal in result["capture_plan"]["proposals"]}
    decision_ids = {decision["proposal_id"] for decision in result["admission_decisions"]}

    assert result["capture_plan"]["expected_required_proposal_count"] == 1
    assert [proposal["target_slot"] for proposal in result["capture_plan"]["proposals"]] == ["identity.age"]
    assert decision_ids == plan_ids
    assert [decision["target_slot"] for decision in result["admission_decisions"]] == ["identity.age"]


def test_capture_receipt_coverage_partial_requires_partial_ack() -> None:
    result = simulate_receipt_coverage_for_accepted_capture(
        turn_id="turn-partial",
        source_event_id="user-msg-partial",
        source_role="user",
        items=[
            _item("identity.preferred_address_name", "Alex", "span-name"),
            _item("runtime.terminal_access", "yes", "span-runtime"),
        ],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )

    assert result["receipt_coverage"]["coverage_status"] == COVERAGE_PARTIAL
    assert result["receipt_coverage"]["full_ack_allowed"] is False
    assert result["ack_plan"]["ack_mode"] == ACK_PARTIAL


def test_capture_pipeline_has_no_language_keyword_router() -> None:
    import inspect
    import brainstack.capture_pipeline as capture_pipeline

    source = inspect.getsource(capture_pipeline)
    assert "My name is Alex" not in source
    assert "remember that" not in source


def test_multilingual_structured_items_map_to_same_target_slot_class() -> None:
    samples = [
        ("hu", "Alex"),
        ("en", "Alex"),
        ("de", "Alex"),
    ]
    slots = []
    for language, value in samples:
        plan = build_capture_plan_from_structured(
            turn_id=f"turn-{language}",
            source_event_id=f"user-msg-{language}",
            source_role="user",
            items=[
                _item(
                    "identity.preferred_address_name",
                    value,
                    f"span-{language}",
                    language=language,
                )
            ],
        )
        slots.append(plan["proposals"][0]["target_slot"])

    assert slots == ["identity.preferred_address_name"] * 3
