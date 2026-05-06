from __future__ import annotations

from scripts.run_retrieval_packet_source_destructive_proof import build_report


def test_retrieval_packet_source_destructive_proof_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["issues"] == []
    assert report["failure_case_ids"] == []
    assert all(report["proof"].values())


def test_agent_facing_context_and_source_handles_are_safe() -> None:
    report = build_report()
    proof = report["proof"]

    assert proof["agent_facing_context_matches_current_stale_support_counts"] is True
    assert proof["stale_support_not_rendered_as_fresh_answer"] is True
    assert proof["source_expand_handles_public_safe"] is True
    assert proof["source_sync_remains_source_only"] is True
    assert proof["no_private_source_or_scope_leak"] is True


def test_backend_gates_stay_capability_preserving() -> None:
    report = build_report()
    proof = report["proof"]

    assert proof["hard_gated_routes_keep_backend_calls_skipped"] is True
    assert proof["deep_route_capability_preserved"] is True
