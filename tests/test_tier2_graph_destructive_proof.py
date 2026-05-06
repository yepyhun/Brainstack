from __future__ import annotations

from scripts.run_tier2_graph_destructive_proof import build_report


def test_tier2_graph_destructive_proof_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["issues"] == []
    assert report["failure_case_ids"] == []
    assert all(report["proof"].values())


def test_failed_unbound_and_empty_graph_states_are_truthful() -> None:
    report = build_report()
    proof = report["proof"]

    assert proof["dirty_live_shaped_failed_runs"] is True
    assert proof["configured_unbound_not_healthy"] is True
    assert proof["empty_graph_explains_no_input_or_failed_dependency"] is True
    assert proof["no_enabled_means_healthy"] is True
    assert proof["failed_run_raw_error_not_agent_facing"] is True


def test_graph_rows_require_safe_source_backed_candidates() -> None:
    report = build_report()
    proof = report["proof"]

    assert proof["source_backed_relation_requires_lineage_receipt_event"] is True
    assert proof["assistant_candidate_no_graph_truth"] is True
    assert proof["unverified_raw_chat_candidate_no_graph_truth"] is True
