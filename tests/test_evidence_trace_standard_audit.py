from __future__ import annotations

from pathlib import Path

from scripts.audit_evidence_trace_standard import audit_evidence_trace_standard


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_fixture_evidence_traces_are_audit_complete() -> None:
    report = audit_evidence_trace_standard(FIXTURE_DIR)

    assert report["status"] == "pass"
    assert report["fixture_status"] == "pass"
    assert report["scenario_count"] == 8
    assert report["complete_trace_count"] == report["scenario_count"]
    assert report["selected_trace_count"] >= 1
    assert report["proof_chain_count"] == report["selected_trace_count"]
    assert report["dropped_only_explained_count"] >= 1
    assert report["unknown_reason_code_count"] == 0
    assert report["raw_text_issue_count"] == 0
    assert report["issue_count"] == 0
