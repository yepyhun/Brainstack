from __future__ import annotations

from scripts.run_sota_proof_harness import run_harness


def test_sota_proof_harness_passes_public_safe_negative_matrix() -> None:
    report = run_harness()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["metrics"]["negative_recall_error_rate"] == 0.0
    assert report["metrics"]["scope_bleed_count"] == 0
    assert report["metrics"]["support_only_answer_truth_count"] == 0
    assert report["metrics"]["superseded_truth_selected_as_current_count"] == 0
    assert report["metrics"]["assistant_authored_truth_selected_count"] == 0
    assert report["metrics"]["wrong_shelf_semantic_selected_count"] == 0
    assert report["metrics"]["behavior_card_shrink_without_replace_count"] == 0
    assert all(row["plan_id_stable"] for row in report["route_matrix"])


def test_sota_proof_harness_self_test_fails_closed() -> None:
    report = run_harness(force_failure=True)

    assert report["status"] == "fail"
    assert report["self_test"]["detects_failure"] is True
    assert report["negative_recall_matrix"]["negative_recall_error_rate"] > 0.0
