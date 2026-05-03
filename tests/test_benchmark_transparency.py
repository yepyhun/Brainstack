from __future__ import annotations

import json
import subprocess
import sys

from brainstack.benchmark_transparency import (
    REQUIRED_BENCHMARK_VARIANTS,
    build_deterministic_benchmark_report,
    build_ragas_amnesty_readiness_report,
    evaluate_deterministic_fixture,
    validate_benchmark_report,
)


def _valid_report() -> dict[str, object]:
    return {
        "schema": "brainstack.benchmark_transparency_report.v1",
        "status": "pass",
        "benchmark": {
            "name": "deterministic_public_fixture",
            "dataset": "brainstack_public_fixture",
            "dataset_version": "v1",
            "seed": 7,
            "commit": "2d1792d",
        },
        "config": {
            "model": "deterministic-fixture",
            "embedding_backend": "none",
            "chunking": "fixture",
            "top_k": 3,
        },
        "variants": {
            variant: {
                "metrics": {
                    "faithfulness": 1.0,
                    "context_precision": 0.75,
                    "context_recall": 1.0,
                    "answer_relevancy": 1.0,
                },
                "latency_ms": {"p50": 1.0, "p95": 2.0},
                "tokens": {"input": 100, "output": 20, "context": 80},
                "case_count": 2,
                "failure_bundles": [],
            }
            for variant in REQUIRED_BENCHMARK_VARIANTS
        },
        "public_safe": True,
    }


def test_valid_benchmark_report_passes_schema_contract() -> None:
    issues = validate_benchmark_report(_valid_report())

    assert issues == []


def test_benchmark_report_requires_all_ablation_variants() -> None:
    report = _valid_report()
    variants = dict(report["variants"])  # type: ignore[arg-type]
    variants.pop("packet_budget_active")
    report["variants"] = variants

    issues = validate_benchmark_report(report)

    assert {
        "code": "missing_variant",
        "path": "variants.packet_budget_active",
    } in issues


def test_benchmark_report_requires_core_metrics_per_variant() -> None:
    report = _valid_report()
    variants = dict(report["variants"])  # type: ignore[arg-type]
    baseline = dict(variants["baseline"])  # type: ignore[index]
    metrics = dict(baseline["metrics"])  # type: ignore[index]
    metrics.pop("context_precision")
    baseline["metrics"] = metrics
    variants["baseline"] = baseline
    report["variants"] = variants

    issues = validate_benchmark_report(report)

    assert {
        "code": "missing_metric",
        "path": "variants.baseline.metrics.context_precision",
    } in issues


def test_benchmark_report_blocks_raw_private_text_shapes() -> None:
    report = _valid_report()
    variants = dict(report["variants"])  # type: ignore[arg-type]
    full = dict(variants["full"])  # type: ignore[index]
    full["failure_bundles"] = [
        {
            "case_id": "case_1",
            "classification": "context_noise",
            "raw_text": "private transcript should never be in benchmark reports",
        }
    ]
    variants["full"] = full
    report["variants"] = variants

    issues = validate_benchmark_report(report)

    assert {
        "code": "forbidden_raw_text_field",
        "path": "variants.full.failure_bundles.0.raw_text",
    } in issues


def test_benchmark_report_requires_public_safe_true() -> None:
    report = _valid_report()
    report["public_safe"] = False

    issues = validate_benchmark_report(report)

    assert {"code": "public_safe_not_true", "path": "public_safe"} in issues


def test_deterministic_fixture_ablation_distinguishes_off_shadow_and_active() -> None:
    report = build_deterministic_benchmark_report(commit="testcommit", budget_max_candidate_tokens=70)

    issues = validate_benchmark_report(report)
    assert issues == []

    variants = report["variants"]
    off = variants["packet_budget_off"]
    shadow = variants["packet_budget_shadow"]
    active = variants["packet_budget_active"]

    assert off["selected_candidate_ids"] == shadow["selected_candidate_ids"]
    assert shadow["budget_summary"]["applied_to_output"] is False
    assert active["budget_summary"]["applied_to_output"] is True
    assert active["metrics"]["context_precision"] > off["metrics"]["context_precision"]
    assert active["metrics"]["context_recall"] == 1.0
    assert active["protected_truth_drop_attempts"] == 0


def test_deterministic_fixture_failure_bundles_classify_context_noise() -> None:
    variant = evaluate_deterministic_fixture(
        variant_name="packet_budget_off",
        packet_budget_mode="off",
        budget_max_candidate_tokens=70,
    )

    classifications = {bundle["classification"] for bundle in variant["failure_bundles"]}

    assert "context_noise" in classifications
    assert "support_only_noise" in classifications
    assert all("raw_text" not in bundle for bundle in variant["failure_bundles"])


def test_full_variant_matches_active_budget_for_current_supported_path() -> None:
    report = build_deterministic_benchmark_report(commit="testcommit", budget_max_candidate_tokens=70)

    assert report["variants"]["full"]["metrics"] == report["variants"]["packet_budget_active"]["metrics"]
    assert report["benchmark"]["commit"] == "testcommit"
    assert report["public_safe"] is True


def test_ragas_amnesty_readiness_reports_missing_dependencies_and_config_without_secrets() -> None:
    report = build_ragas_amnesty_readiness_report(
        installed_packages=set(),
        model_config={"api_key": "secret-value-should-not-appear"},
        dataset_id="vibrantlabsai/amnesty_qa",
        split="eval",
        sample_count=12,
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["schema"] == "brainstack.ragas_amnesty_readiness.v1"
    assert report["status"] == "not_ready"
    assert report["ready"] is False
    assert report["dataset"]["id"] == "vibrantlabsai/amnesty_qa"
    assert report["missing_dependencies"] == ["datasets", "ragas"]
    assert "missing_model_config" in {issue["code"] for issue in report["issues"]}
    assert "secret-value-should-not-appear" not in rendered
    assert report["public_safe"] is True


def test_ragas_amnesty_readiness_can_pass_when_dependencies_and_config_are_present() -> None:
    report = build_ragas_amnesty_readiness_report(
        installed_packages={"datasets", "ragas"},
        model_config={"llm": "configured", "embeddings": "configured"},
        dataset_id="vibrantlabsai/amnesty_qa",
        split="eval",
        sample_count=12,
    )

    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["missing_dependencies"] == []
    assert report["issues"] == []


def test_benchmark_transparency_cli_writes_valid_report(tmp_path) -> None:
    out = tmp_path / "benchmark.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_benchmark_transparency.py",
            "--commit",
            "testcommit",
            "--budget-max-candidate-tokens",
            "70",
            "--out",
            str(out),
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert validate_benchmark_report(report) == []
    assert report["benchmark"]["commit"] == "testcommit"
    assert report["variants"]["packet_budget_active"]["metrics"]["context_precision"] > report["variants"]["packet_budget_off"]["metrics"]["context_precision"]


def test_ragas_amnesty_cli_writes_not_ready_report_when_evaluator_is_unavailable(tmp_path) -> None:
    out = tmp_path / "ragas_readiness.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_ragas_amnesty_benchmark.py",
            "--readiness-only",
            "--ollama-model",
            "brainstack-test-missing-model:latest",
            "--tei-url",
            "http://127.0.0.1:9/embed",
            "--out",
            str(out),
        ],
        cwd=".",
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2, proc.stdout
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "brainstack.ragas_amnesty_readiness.v2"
    assert report["status"] == "not_ready"
    assert report["ready"] is False
    issue_codes = {issue["code"] for issue in report["issues"]}
    assert "ollama_model_missing_or_unavailable" in issue_codes
    assert "tei_embeddings_unavailable" in issue_codes
    assert report["public_safe"] is True

