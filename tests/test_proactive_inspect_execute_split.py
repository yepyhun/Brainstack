from __future__ import annotations

from scripts.verify_proactive_inspect_execute_split import build_report


def test_proactive_inspect_execute_split_and_foreground_wait_guard() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["issues"] == []
    assert all(report["proof"].values())
    assert "run_agent:terminal_final_guard_helpers" in report["patch_applied"]
