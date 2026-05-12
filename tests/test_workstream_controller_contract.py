from __future__ import annotations

from scripts.verify_workstream_controller_contract import build_report


def test_workstream_controller_contract_blocks_filler_and_replays_events() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["side_effect_free"] is True
    assert report["issues"] == []
    assert all(report["proof"].values())
