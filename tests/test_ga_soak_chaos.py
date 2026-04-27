from __future__ import annotations

from scripts.ga_soak_chaos import run_chaos_contract, run_soak_contract


def test_ga_soak_blocks_contamination_recurrence() -> None:
    assert run_soak_contract()["counts"]["contamination_recurrence_count"] == 0


def test_ga_soak_blocks_support_only_leak() -> None:
    assert run_soak_contract()["counts"]["support_only_leak_count"] == 0


def test_ga_soak_blocks_capability_false_claim() -> None:
    assert run_soak_contract()["counts"]["capability_false_claim_count"] == 0


def test_ga_soak_blocks_approval_bypass() -> None:
    assert run_soak_contract()["counts"]["approval_bypass_count"] == 0


def test_ga_soak_blocks_silent_latency_violation() -> None:
    assert run_soak_contract()["counts"]["silent_latency_violation_count"] == 0


def test_ga_chaos_provider_timeout_degrades_truthfully() -> None:
    assert run_chaos_contract()["faults"]["provider_timeout_degrades_truthfully"] is True


def test_ga_chaos_toolloader_failure_preserves_capability() -> None:
    assert run_chaos_contract()["faults"]["toolloader_failure_preserves_capability"] is True


def test_ga_chaos_corrupt_db_fail_closed() -> None:
    assert run_chaos_contract()["faults"]["corrupt_db_fail_closed"] is True
