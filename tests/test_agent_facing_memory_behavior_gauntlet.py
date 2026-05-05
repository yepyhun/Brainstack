from __future__ import annotations

from pathlib import Path

from scripts.run_agent_facing_memory_behavior_gauntlet import (
    _case_generic_profile_not_active_card,
    _case_tool_and_packet_current_truth_agree,
    run_gauntlet,
)
from scripts.verify_behavior_card_delivery import DEFAULT_HERMES_SOURCE


def _case(report: dict, name: str) -> dict:
    matches = [case for case in report["cases"] if case["name"] == name]
    assert len(matches) == 1
    return matches[0]


def test_agent_facing_memory_behavior_gauntlet_passes_without_llm_calls() -> None:
    report = run_gauntlet(hermes_source=DEFAULT_HERMES_SOURCE)

    assert report["status"] == "pass"
    assert report["provider_llm_calls_performed"] is False
    assert report["optional_live_smoke_required"] is False
    assert report["failure_count"] == 0
    assert report["public_safe"] is True
    assert report["case_count"] == 4

    behavior = _case(report, "active_behavior_card_session_and_compression")
    assert behavior["summary"]["session_start_rule_count"] == 25
    assert behavior["summary"]["post_compression_rule_count"] == 25
    assert behavior["summary"]["source_stable_key"] == "preference:style_contract"

    stale = _case(report, "stale_diagnostic_support_loses_to_new_truth")
    assert stale["summary"]["old_answer_decision"] == "not_answer_safe"
    assert stale["summary"]["old_packet_action"] != "selected"
    assert stale["summary"]["new_answer_decision"] == "answer_safe"
    assert stale["summary"]["new_packet_action"] == "selected"


def test_generic_profile_only_cannot_satisfy_active_card(tmp_path: Path) -> None:
    case = _case_generic_profile_not_active_card(tmp_path)

    assert case["status"] == "pass"
    assert case["summary"]["generic_profile_row_present"] is True
    assert case["summary"]["generic_profile_only_counted_as_active_card"] is False
    assert case["summary"]["source_stable_key"] != "preference:style_contract"


def test_tool_inspect_and_packet_current_truth_payloads_agree(tmp_path: Path) -> None:
    case = _case_tool_and_packet_current_truth_agree(tmp_path)

    assert case["status"] == "pass"
    assert case["summary"]["inspect_current_truth_row_count"] == 1
    assert case["summary"]["packet_current_truth_row_count"] == 1
    assert case["summary"]["inspect_non_answerable_row_count"] == 1
    assert case["summary"]["packet_non_answerable_row_count"] == 1
    assert case["summary"]["packet_route_class"] == "current_truth"
    assert case["summary"]["packet_ordinary_hot_path_rebuild"] is False
