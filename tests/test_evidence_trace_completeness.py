from __future__ import annotations

from pathlib import Path

import pytest

from brainstack.core.trace import assert_evidence_trace_complete, validate_evidence_trace
from scripts.run_public_memory_kernel_fixtures import run_fixture_directory


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_fixture_traces_are_complete_for_audit() -> None:
    result = run_fixture_directory(FIXTURE_DIR)

    for scenario in result["scenarios"]:
        assert_evidence_trace_complete(scenario["trace"])


def test_trace_completeness_rejects_missing_selected_source_span() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    trace = next(
        item
        for item in result["scenarios"]
        if item["scenario_id"] == "explicit_capture_complete_public_001"
    )["trace"]
    bad = dict(trace)
    bad["candidates"] = [dict(item) for item in trace["candidates"]]
    bad["candidates"][0]["source_span_id"] = ""
    bad["trace_completeness"] = dict(trace["trace_completeness"])
    bad["trace_completeness"]["complete_for_audit"] = True

    errors = validate_evidence_trace(bad)

    assert "selected_candidate_missing_source_span_id" in errors
    assert any(error.startswith("trace_completeness_mismatch") for error in errors)


def test_trace_assertion_raises_when_incomplete() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    trace = next(
        item
        for item in result["scenarios"]
        if item["scenario_id"] == "assistant_contamination_public_001"
    )["trace"]
    bad = dict(trace)
    bad["trace_completeness"] = dict(trace["trace_completeness"])
    bad["trace_completeness"]["complete_for_audit"] = False

    with pytest.raises(ValueError):
        assert_evidence_trace_complete(bad)
