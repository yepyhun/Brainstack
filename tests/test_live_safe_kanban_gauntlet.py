from __future__ import annotations

from scripts.verify_live_safe_kanban_gauntlet import build_report


def test_live_safe_kanban_gauntlet_proves_usefulness_without_real_work() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["issues"] == []
    assert all(report["proof"].values())
    assert report["completed_verdict"] == "worker_lifecycle_certified"
    assert report["blocked_verdict"] == "board_write_certified"
