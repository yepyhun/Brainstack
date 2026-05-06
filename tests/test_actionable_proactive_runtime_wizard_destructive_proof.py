from __future__ import annotations

from scripts.run_actionable_proactive_runtime_wizard_destructive_proof import build_report


def test_actionable_proactive_runtime_wizard_destructive_proof_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["issues"] == []
    assert report["failure_case_ids"] == []
    assert all(report["proof"].values())


def test_actionable_and_proactive_paths_have_no_governor_side_effects() -> None:
    proof = build_report()["proof"]

    assert proof["support_only_action_rejected_without_substrate"] is True
    assert proof["proactive_status_read_only_no_side_effect"] is True
    assert proof["no_outbox_or_scheduler_side_effect"] is True


def test_runtime_wizard_paths_are_truthful_and_reproducible() -> None:
    proof = build_report()["proof"]

    assert proof["runtime_degraded_states_truthful"] is True
    assert proof["auxiliary_invalid_routes_block_before_call"] is True
    assert proof["main_model_inheritance_ready"] is True
    assert proof["wizard_core_patches_auxiliary_and_session_search"] is True
    assert proof["proactive_payload_files_present"] is True
