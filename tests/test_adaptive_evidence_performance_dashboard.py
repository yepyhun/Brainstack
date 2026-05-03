from __future__ import annotations

from scripts.measure_adaptive_evidence_performance import build_report, percentile


def test_percentile_interpolates_sorted_samples() -> None:
    assert percentile([10, 20, 30], 0.50) == 20.0
    assert percentile([10, 20, 30], 0.95) == 29.0
    assert percentile([], 0.95) == 0.0


def test_adaptive_evidence_performance_dashboard_passes_public_safe_baseline() -> None:
    report = build_report(iterations=2)

    assert report["schema"] == "brainstack.adaptive_evidence_performance_dashboard.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["summary"]["case_count"] >= 5
    assert report["summary"]["active_budget_case_count"] == report["summary"]["case_count"]
    assert report["summary"]["protected_drop_count"] == 0
    assert report["summary"]["read_path_mutation_count"] == 0
    assert report["summary"]["latency_ms_p95"] >= report["summary"]["latency_ms_p50"]
    assert all(case["latency_ms"]["samples"] for case in report["cases"])
