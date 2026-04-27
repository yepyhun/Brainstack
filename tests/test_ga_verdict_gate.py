from __future__ import annotations

from scripts.ga_soak_chaos import final_verdict_from_dashboard


def test_ga_verdict_ready_requires_all_gates() -> None:
    verdict = final_verdict_from_dashboard(
        {
            "ready": False,
            "blocking": ["LIVE_SMOKE_MISSING"],
            "counts": {"open_p0": 0, "open_p1": 1},
            "manual_only_proof": False,
        }
    )

    assert verdict["verdict"] == "BLOCKED"
    assert verdict["ready"] is False


def test_ga_verdict_blocks_manual_only_core_proof() -> None:
    verdict = final_verdict_from_dashboard(
        {
            "ready": False,
            "blocking": ["MANUAL_ONLY_PROOF"],
            "counts": {"open_p0": 0, "open_p1": 0},
            "manual_only_proof": True,
        }
    )

    assert verdict["verdict"] == "BLOCKED"
    assert verdict["manual_only_proof"] is True
