from __future__ import annotations

from pathlib import Path

from scripts.run_canonical_truth_admission_coverage import build_report


def test_canonical_truth_admission_coverage_matrix_passes(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")

    assert report["status"] == "pass"
    assert report["llm_calls_performed"] is False
    assert report["second_truth_authority_created"] is False
    assert report["proactive_mutation_count"] == 0
    assert report["failure_case_ids"] == []
    assert report["case_count"] >= 8


def test_rejected_candidates_get_receipts_but_never_answerable_truth(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")
    rejected = [case for case in report["cases"] if not case["truth_eligible"]]

    assert rejected
    assert all(case["admission_receipt_id"] > 0 for case in rejected)
    assert all(case["canonical_event_count"] > 0 for case in rejected)
    assert all(case["answerable_l0_count"] == 0 for case in rejected)
    assert all(case["durable_row_id"] > 0 for case in rejected)


def test_accepted_candidates_project_to_receipt_backed_l0_truth(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")
    accepted = [case for case in report["cases"] if case["truth_eligible"]]

    assert accepted
    assert all(case["admission_receipt_id"] > 0 for case in accepted)
    assert all(case["canonical_event_count"] > 0 for case in accepted)
    assert all(case["durable_row_id"] > 0 for case in accepted)
    assert all(case["answerable_l0_count"] > 0 for case in accepted)
