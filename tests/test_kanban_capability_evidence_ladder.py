from __future__ import annotations

from scripts.verify_kanban_capability_evidence_ladder import build_report


def test_kanban_capability_evidence_ladder_blocks_overclaims() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["issues"] == []
    assert report["scenario_verdicts"]["not_installed"] == "not_installed"
    assert report["scenario_verdicts"]["installed_only"] == "installed_only"
    assert report["scenario_verdicts"]["board_storage_accessible"] == "board_storage_accessible"
    assert report["scenario_verdicts"]["tool_surface_exposed"] == "tool_surface_exposed"
    assert report["scenario_verdicts"]["worker_lifecycle_certified"] == "worker_lifecycle_certified"
    assert all(report["proof"].values())
    assert report["outbox_split"]["pending_outbox_count"] == 1
    assert report["outbox_split"]["runtime_scope_pending_outbox_count"] == 1
    assert report["outbox_split"]["user_visible_pending_outbox_count"] == 0
