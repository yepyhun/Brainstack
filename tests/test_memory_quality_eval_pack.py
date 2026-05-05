from __future__ import annotations

from scripts.run_memory_quality_eval_pack import build_eval_pack
from scripts.verify_behavior_card_delivery import DEFAULT_HERMES_SOURCE


def test_memory_quality_eval_pack_passes_with_required_coverage() -> None:
    report = build_eval_pack(hermes_source=DEFAULT_HERMES_SOURCE)

    assert report["status"] == "pass"
    assert report["case_count"] >= 30
    assert report["failure_count"] == 0
    assert report["failure_to_owner"] == {}
    assert report["llm_calls_performed"] is False
    assert report["optional_live_smoke_required"] is False
    assert report["public_safe"] is True
    assert {
        "behavior_card",
        "stale_truth",
        "answerability",
        "current_truth",
        "performance",
        "scope_isolation",
        "uncertainty",
        "proactive_negative",
    }.issubset(set(report["categories"]))


def test_memory_quality_eval_pack_maps_each_case_to_owner() -> None:
    report = build_eval_pack(hermes_source=DEFAULT_HERMES_SOURCE)

    for case in report["cases"]:
        assert case["owner_module"]
        assert case["owner_phase"]
        assert case["description"]
        assert case["category"]
        assert case["status"] == "pass"


def test_memory_quality_eval_pack_contains_key_regression_cases() -> None:
    report = build_eval_pack(hermes_source=DEFAULT_HERMES_SOURCE)
    cases = {case["case_id"]: case for case in report["cases"]}

    assert cases["behavior_card_session_25_rules"]["observed"] == 25
    assert cases["generic_profile_not_active_card"]["observed"] is False
    assert cases["stale_old_not_answer_safe"]["observed"] == "not_answer_safe"
    assert cases["stale_new_selected"]["observed"] == "selected"
    assert cases["hard_gated_semantic_zero"]["observed"] == 0
    assert cases["current_truth_no_rebuild"]["observed"] == 0
    assert cases["scope_like_fallback_zero"]["observed"] == 0
    assert cases["unknown_memory_is_unanswerable"]["observed"] is False
