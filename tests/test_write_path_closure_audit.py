from __future__ import annotations

from pathlib import Path

from scripts.brainstack_write_path_closure_audit import run_audit


def test_write_path_closure_audit_has_no_unclassified_source_calls() -> None:
    result = run_audit(Path(__file__).resolve().parents[1], include_tests=False)
    assert result["hard_failure_count"] == 0
    assert result["callsite_count"] > 0
    assert "UNCLASSIFIED_DURABLE_TRUTH_WRITE" not in result["by_class"]


def test_write_path_closure_audit_can_include_tests() -> None:
    result = run_audit(Path(__file__).resolve().parents[1], include_tests=True)
    assert result["hard_failure_count"] == 0
    assert result["by_class"].get("TEST_OR_CANARY_SEED", 0) > 0
