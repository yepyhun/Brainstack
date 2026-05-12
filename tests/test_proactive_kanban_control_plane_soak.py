from __future__ import annotations

from scripts.verify_proactive_kanban_control_plane_soak import build_report


def test_proactive_kanban_control_plane_soak_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["issues"] == []
    assert all(report["proof"].values())
