from __future__ import annotations

from brainstack.memory_write_collision import (
    COLLISION_UNSAFE_AUTHORITY_SHRINK,
    attach_write_collision_if_any,
    build_memory_write_collision,
)


def test_unsafe_style_contract_shrink_returns_structured_collision() -> None:
    receipt = {
        "schema": "brainstack.explicit_capture.v1",
        "status": "committed",
        "style_contract_materialization": {
            "status": "skipped",
            "reason_code": "would_shrink_existing_style_contract",
            "active_card_mutated": False,
            "rule_count": 25,
            "agent_safe_repair_action": "use_dedicated_active_card_update_surface_or_write_full_rule_pack",
        },
    }

    enriched = attach_write_collision_if_any(receipt)

    assert enriched["write_collision"]["code"] == COLLISION_UNSAFE_AUTHORITY_SHRINK
    assert enriched["write_collision"]["mutation_status"] == "blocked_no_mutation"
    assert enriched["write_collision"]["next_safe_action"] == "ask_user_for_explicit_replace_or_full_rule_pack"
    assert enriched["final_state_success"] is False


def test_collision_envelope_is_agent_facing_and_not_receipt_success() -> None:
    collision = build_memory_write_collision(
        code="source_integrity_violation",
        reason="Source fingerprint changed before write.",
        affected_authority="current_truth",
        mutation_status="blocked_no_mutation",
        next_safe_action="re_admit_from_updated_source",
    )

    assert collision["schema"] == "brainstack.memory_write_collision.v1"
    assert collision["agent_facing"] is True
    assert collision["receipt_is_final_success"] is False
    assert collision["next_safe_action"] == "re_admit_from_updated_source"
