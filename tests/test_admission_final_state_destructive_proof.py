from __future__ import annotations

from pathlib import Path

from scripts.run_admission_final_state_destructive_proof import build_report


def test_admission_final_state_destructive_proof_passes(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["issues"] == []
    assert report["failure_case_ids"] == []
    assert all(report["proof"].values())


def test_receipts_do_not_override_final_answerability(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")
    proof = report["proof"]

    assert proof["receipt_success_not_sufficient"] is True
    assert proof["rejected_receipt_not_answer_truth"] is True
    assert proof["support_only_cannot_answer"] is True
    assert proof["missing_receipt_event_not_answer_truth"] is True
    assert report["current_truth_final_state"]["unsafe_answer_truth_projection_count"] == 0


def test_supersession_rebuild_and_packet_final_state_are_consistent(tmp_path: Path) -> None:
    report = build_report(tmp_path / "brainstack.sqlite3")

    assert report["proof"]["explicit_supersession_final_state"] is True
    assert report["proof"]["newer_rejected_cannot_override_current"] is True
    assert report["proof"]["l0_matches_rebuild"] is True
    assert report["proof"]["packet_selected_only_answer_safe"] is True
    assert report["packet_final_state"]["conformance_status"] == "pass"
    assert report["packet_final_state"]["inspect_verdict"] == "pass"
