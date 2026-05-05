from __future__ import annotations

from scripts.run_local_workload_performance_replay import build_report


def _case(report: dict, case_id: str) -> dict:
    matches = [case for case in report["cases"] if case["case_id"] == case_id]
    assert len(matches) == 1
    return matches[0]


def test_local_workload_performance_replay_passes_without_llm_calls() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["summary"]["llm_calls_performed"] is False
    assert report["summary"]["hard_gated_semantic_backend_calls"] == 0
    assert report["summary"]["profile_like_fallback_count"] == 0
    assert report["summary"]["protected_truth_drop_attempts"] == 0
    assert report["summary"]["case_count"] == 8


def test_replay_proves_simple_routes_skip_semantic_and_unneeded_shelves() -> None:
    report = build_report()

    no_memory = _case(report, "no_memory_minimal")
    profile = _case(report, "profile_only")
    current_truth = _case(report, "current_truth_lookup")

    assert no_memory["semantic_backend_call_total"] == 0
    assert all(value == 0 for value in no_memory["shelf_backend_calls"].values())
    assert profile["semantic_backend_call_total"] == 0
    assert profile["shelf_backend_calls"]["search_graph"] == 0
    assert profile["shelf_backend_calls"]["search_corpus"] == 0
    assert current_truth["semantic_backend_call_total"] == 0
    assert current_truth["current_truth_rebuild_calls"] == 0
    assert current_truth["ordinary_hot_path_rebuild"] is False


def test_replay_keeps_deep_semantic_route_and_protected_budget() -> None:
    report = build_report()

    deep = _case(report, "corpus_semantic_supported")
    tight = _case(report, "tight_packet_budget")

    assert deep["semantic_backend_call_total"] >= 1
    assert deep["shelf_backend_calls"]["search_corpus"] >= 1
    assert tight["packet_budget_status"] in {"insufficient_for_authority_minimum", "applied", "within_limit"}
    assert tight["protected_truth_drop_attempts"] == 0
    assert tight["packet_token_estimate"] > 0


def test_replay_proves_scoped_profile_lookup_uses_index_not_like() -> None:
    report = build_report()

    scoped = _case(report, "scoped_profile_lookup")

    assert scoped["lookup_hit"] is True
    assert scoped["profile_indexed_lookup_count"] >= 1
    assert scoped["profile_like_fallback_count"] == 0
