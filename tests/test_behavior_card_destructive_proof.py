from __future__ import annotations

from scripts.run_behavior_card_destructive_proof import build_report


def test_behavior_card_destructive_proof_passes() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.behavior_card_destructive_proof.v1"
    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["public_safe"] is True
    proof = report["proof"]
    assert proof["dirty_live_shaped_fixture"] is True
    assert proof["small_write_cannot_shrink_active_card"] is True
    assert proof["collapsed_summary_cannot_patch_card"] is True
    assert proof["non_behavior_profile_cannot_materialize_card"] is True
    assert proof["full_structured_replacement_final_state"] is True
    assert proof["session_start_delivery_uses_canonical_card"] is True
    assert proof["compression_delivery_uses_same_card"] is True
    assert proof["source_profile_not_prompt_authority"] is True
    assert proof["large_card_warning_not_prompt_spam"] is True
