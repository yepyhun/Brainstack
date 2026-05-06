from __future__ import annotations

from brainstack.product_contracts import DEFAULT_REPAIR_PLAYBOOKS, validate_patch_against_playbook


def test_repair_playbook_registry_for_core_owners() -> None:
    assert "TOOL_STATE_FINAL_ANSWER_BLOCK" in DEFAULT_REPAIR_PLAYBOOKS
    assert "IDENTITY_SLOT_CONFUSION" in DEFAULT_REPAIR_PLAYBOOKS
    assert "STYLE_PRESENTATION_FAILURE" in DEFAULT_REPAIR_PLAYBOOKS


def test_patch_guard_rejects_forbidden_module() -> None:
    result = validate_patch_against_playbook(
        ["brainstack/admission_policy.py"],
        "safe patch",
        "TOOL_STATE_FINAL_ANSWER_BLOCK",
    )

    assert result["accepted"] is False
    assert "brainstack/admission_policy.py" in result["forbidden_touches"]


def test_patch_guard_rejects_language_keyword_router() -> None:
    result = validate_patch_against_playbook(
        ["gateway/tool_state_guard.py"],
        "if 'literal command' in text: load_files()",
        "TOOL_STATE_FINAL_ANSWER_BLOCK",
    )

    assert result["accepted"] is False
    assert "language_keyword_router" in result["forbidden_fixes"]
