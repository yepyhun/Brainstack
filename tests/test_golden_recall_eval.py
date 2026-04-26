from __future__ import annotations

from scripts.brainstack_golden_recall_eval import run_golden_recall_eval


def test_golden_recall_hard_gates_pass() -> None:
    report = run_golden_recall_eval()

    assert report["schema"] == "brainstack.golden_recall_eval.v1"
    assert report["verdict"] == "pass"
    assert report["hard_gate"]["failed"] == 0
    assert report["hard_gate"]["passed"] >= 6


def test_golden_recall_records_baseline_gaps_without_failing() -> None:
    report = run_golden_recall_eval()

    scenario_ids = {scenario["id"] for scenario in report["scenarios"]}
    assert "profile.paraphrase_semantic_gap" in scenario_ids
    assert "negative.unsupported_query_has_no_memory_truth" in scenario_ids
    assert report["baseline"]["count"] >= 1


def test_golden_recall_hard_gates_unsupported_no_evidence_answerability() -> None:
    report = run_golden_recall_eval()

    scenario = next(
        item for item in report["scenarios"] if item["id"] == "negative.unsupported_query_has_no_memory_truth"
    )
    assert scenario["status"] == "pass"
    assert scenario["hard_gate"] is True
    assert scenario["reason"] == "no answerable memory truth selected"
