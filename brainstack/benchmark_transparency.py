from __future__ import annotations

import importlib.util
from collections.abc import Mapping, Sequence
from typing import Any

from .core.packet_budget import PacketBudgetPolicy, apply_packet_budget, is_authority_critical
from .core.trace import (
    AUTHORITY_CITED_CORPUS,
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_SUPPORT_ONLY,
    DECISION_SELECTED,
    make_evidence_candidate,
)

BENCHMARK_REPORT_SCHEMA = "brainstack.benchmark_transparency_report.v1"
REQUIRED_BENCHMARK_VARIANTS = (
    "baseline",
    "full",
    "packet_budget_off",
    "packet_budget_shadow",
    "packet_budget_active",
)
REQUIRED_METRICS = (
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
)
FORBIDDEN_RAW_TEXT_FIELDS = {"raw_text", "raw_private_text", "packet_text", "model_output"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _issue(code: str, path: str, **extra: Any) -> dict[str, Any]:
    issue: dict[str, Any] = {"code": code, "path": path}
    issue.update(extra)
    return issue


def _scan_forbidden_raw_fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if str(key) in FORBIDDEN_RAW_TEXT_FIELDS:
                issues.append(_issue("forbidden_raw_text_field", child_path))
            issues.extend(_scan_forbidden_raw_fields(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}.{index}" if path else str(index)
            issues.extend(_scan_forbidden_raw_fields(child, child_path))
    return issues


def _validate_number(value: Any, path: str) -> list[dict[str, Any]]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [_issue("metric_not_number", path)]
    return []


def validate_benchmark_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if report.get("schema") != BENCHMARK_REPORT_SCHEMA:
        issues.append(_issue("unsupported_schema", "schema", value=report.get("schema")))
    if report.get("public_safe") is not True:
        issues.append(_issue("public_safe_not_true", "public_safe"))

    benchmark = _mapping(report.get("benchmark"))
    for field in ("name", "dataset", "dataset_version", "seed", "commit"):
        if field not in benchmark or benchmark.get(field) in (None, ""):
            issues.append(_issue("missing_benchmark_field", f"benchmark.{field}"))

    config = _mapping(report.get("config"))
    for field in ("model", "embedding_backend", "chunking", "top_k"):
        if field not in config or config.get(field) in (None, ""):
            issues.append(_issue("missing_config_field", f"config.{field}"))

    variants = _mapping(report.get("variants"))
    if not variants:
        issues.append(_issue("missing_variants", "variants"))
    for variant_name in REQUIRED_BENCHMARK_VARIANTS:
        variant = _mapping(variants.get(variant_name))
        if not variant:
            issues.append(_issue("missing_variant", f"variants.{variant_name}"))
            continue
        metrics = _mapping(variant.get("metrics"))
        for metric in REQUIRED_METRICS:
            metric_path = f"variants.{variant_name}.metrics.{metric}"
            if metric not in metrics:
                issues.append(_issue("missing_metric", metric_path))
            else:
                issues.extend(_validate_number(metrics.get(metric), metric_path))
        latency = _mapping(variant.get("latency_ms"))
        for field in ("p50", "p95"):
            field_path = f"variants.{variant_name}.latency_ms.{field}"
            if field not in latency:
                issues.append(_issue("missing_latency_field", field_path))
            else:
                issues.extend(_validate_number(latency.get(field), field_path))
        tokens = _mapping(variant.get("tokens"))
        for field in ("input", "output", "context"):
            field_path = f"variants.{variant_name}.tokens.{field}"
            if field not in tokens:
                issues.append(_issue("missing_token_field", field_path))
            else:
                issues.extend(_validate_number(tokens.get(field), field_path))
        if "case_count" not in variant:
            issues.append(_issue("missing_case_count", f"variants.{variant_name}.case_count"))
        else:
            issues.extend(_validate_number(variant.get("case_count"), f"variants.{variant_name}.case_count"))
        failure_bundles = variant.get("failure_bundles")
        if not isinstance(failure_bundles, list):
            issues.append(_issue("failure_bundles_not_list", f"variants.{variant_name}.failure_bundles"))

    issues.extend(_scan_forbidden_raw_fields(report))
    return issues


def _candidate(
    candidate_id: str,
    *,
    authority: str,
    relevant: bool,
    token_estimate: int,
    answer_evidence_allowed: bool = True,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    candidate = make_evidence_candidate(
        candidate_id=candidate_id,
        shelf="public_benchmark_fixture",
        source_role="trusted_fixture",
        authority=authority,
        decision=DECISION_SELECTED,
        reason_code="selected_fixture_candidate",
        target_slot="amnesty_fixture_answer",
        receipt_id=receipt_id,
        truth_eligible=authority in {AUTHORITY_RECEIPT_BACKED, AUTHORITY_CITED_CORPUS},
        model_facing_allowed=True,
        answer_evidence_allowed=answer_evidence_allowed,
        raw_value=candidate_id,
        redacted_excerpt=f"fixture:{candidate_id}",
        token_estimate=token_estimate,
    )
    candidate["benchmark_relevant"] = relevant
    return candidate


def deterministic_public_fixture_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "amnesty_fixture_context_noise",
            "expected_relevant_candidate_ids": ["truth_receipt", "cited_report"],
            "answer_support_candidate_ids": ["truth_receipt", "cited_report"],
            "candidate_ids_in_retrieval_order": [
                "truth_receipt",
                "cited_report",
                "near_topic_noise",
                "support_note",
            ],
            "candidates": [
                _candidate(
                    "truth_receipt",
                    authority=AUTHORITY_RECEIPT_BACKED,
                    relevant=True,
                    token_estimate=30,
                    receipt_id="receipt_public_fixture",
                ),
                _candidate(
                    "cited_report",
                    authority=AUTHORITY_CITED_CORPUS,
                    relevant=True,
                    token_estimate=30,
                ),
                _candidate(
                    "near_topic_noise",
                    authority="retrieval_candidate",
                    relevant=False,
                    token_estimate=35,
                ),
                _candidate(
                    "support_note",
                    authority=AUTHORITY_SUPPORT_ONLY,
                    relevant=False,
                    token_estimate=18,
                    answer_evidence_allowed=False,
                ),
            ],
        }
    ]


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _selected_ids(candidates: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("candidate_id") or "") for item in candidates if str(item.get("candidate_id") or "")]


def _token_total(candidates: Sequence[Mapping[str, Any]]) -> int:
    return sum(int(item.get("token_estimate") or 0) for item in candidates)


def _failure_bundles_for_case(
    *,
    case: Mapping[str, Any],
    selected_candidates: Sequence[Mapping[str, Any]],
    variant_name: str,
) -> list[dict[str, Any]]:
    selected_by_id = {str(item.get("candidate_id") or ""): item for item in selected_candidates}
    expected_relevant = {str(item) for item in case.get("expected_relevant_candidate_ids") or []}
    bundles: list[dict[str, Any]] = []
    for candidate_id, candidate in selected_by_id.items():
        if candidate_id in expected_relevant:
            continue
        authority = str(candidate.get("authority") or "")
        classification = "support_only_noise" if authority == AUTHORITY_SUPPORT_ONLY else "context_noise"
        bundles.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "variant": variant_name,
                "classification": classification,
                "candidate_id": candidate_id,
                "authority": authority,
                "reason_code": str(candidate.get("reason_code") or ""),
            }
        )
    missing_relevant = sorted(expected_relevant - set(selected_by_id))
    for candidate_id in missing_relevant:
        bundles.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "variant": variant_name,
                "classification": "retrieval_miss",
                "candidate_id": candidate_id,
                "authority": str(_mapping(selected_by_id.get(candidate_id)).get("authority") or ""),
                "reason_code": "expected_relevant_candidate_not_selected",
            }
        )
    return bundles


def _metrics_for_cases(
    *,
    cases: Sequence[Mapping[str, Any]],
    selected_by_case: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, float]:
    precision_scores: list[float] = []
    recall_scores: list[float] = []
    faithfulness_scores: list[float] = []
    relevancy_scores: list[float] = []
    for case in cases:
        case_id = str(case.get("case_id") or "")
        selected = list(selected_by_case.get(case_id) or [])
        selected_ids = set(_selected_ids(selected))
        relevant_ids = {str(item) for item in case.get("expected_relevant_candidate_ids") or []}
        support_ids = {str(item) for item in case.get("answer_support_candidate_ids") or []}
        relevant_selected = selected_ids & relevant_ids
        support_selected = selected_ids & support_ids
        precision_scores.append(_safe_divide(len(relevant_selected), len(selected_ids)))
        recall_scores.append(_safe_divide(len(relevant_selected), len(relevant_ids)))
        faithfulness_scores.append(_safe_divide(len(support_selected), len(support_ids)))
        relevancy_scores.append(1.0 if relevant_ids and relevant_ids <= selected_ids else 0.0)
    count = len(cases) or 1
    return {
        "faithfulness": round(sum(faithfulness_scores) / count, 6),
        "context_precision": round(sum(precision_scores) / count, 6),
        "context_recall": round(sum(recall_scores) / count, 6),
        "answer_relevancy": round(sum(relevancy_scores) / count, 6),
    }


def evaluate_deterministic_fixture(
    *,
    variant_name: str,
    packet_budget_mode: str,
    budget_max_candidate_tokens: int = 70,
) -> dict[str, Any]:
    cases = deterministic_public_fixture_cases()
    selected_by_case: dict[str, list[dict[str, Any]]] = {}
    failure_bundles: list[dict[str, Any]] = []
    budget_summaries: list[dict[str, Any]] = []
    protected_truth_drop_attempts = 0
    for case in cases:
        case_id = str(case.get("case_id") or "")
        candidates = [dict(item) for item in case.get("candidates") or [] if isinstance(item, Mapping)]
        selected = candidates
        budget_summary = {
            "mode": packet_budget_mode,
            "enabled": packet_budget_mode in {"shadow", "active"},
            "applied_to_output": False,
        }
        if packet_budget_mode in {"shadow", "active"}:
            budget_result = apply_packet_budget(
                candidates,
                PacketBudgetPolicy(max_candidate_tokens=budget_max_candidate_tokens),
            )
            budget_summary.update(budget_result.to_trace_packet_budget())
            budget_summary["mode"] = packet_budget_mode
            budget_summary["enabled"] = True
            budget_summary["applied_to_output"] = packet_budget_mode == "active"
            if packet_budget_mode == "active":
                selected = [item for item in budget_result.candidates if item.get("decision") == "selected"]
            for item in budget_result.candidates:
                if item.get("decision") == "dropped" and is_authority_critical(item):
                    protected_truth_drop_attempts += 1
        selected_by_case[case_id] = selected
        failure_bundles.extend(
            _failure_bundles_for_case(case=case, selected_candidates=selected, variant_name=variant_name)
        )
        budget_summaries.append(budget_summary)
    selected_all = [item for items in selected_by_case.values() for item in items]
    context_tokens = _token_total(selected_all)
    metrics = _metrics_for_cases(cases=cases, selected_by_case=selected_by_case)
    latency_base = 1.0 + (0.25 * len(cases)) + (0.01 * context_tokens)
    return {
        "metrics": metrics,
        "latency_ms": {"p50": round(latency_base, 3), "p95": round(latency_base + 0.5, 3)},
        "tokens": {"input": context_tokens + 24, "output": 16, "context": context_tokens},
        "case_count": len(cases),
        "selected_candidate_ids": _selected_ids(selected_all),
        "budget_summary": budget_summaries[0] if budget_summaries else {},
        "protected_truth_drop_attempts": protected_truth_drop_attempts,
        "failure_bundles": failure_bundles,
    }


def build_deterministic_benchmark_report(
    *,
    commit: str,
    budget_max_candidate_tokens: int = 70,
) -> dict[str, Any]:
    variants = {
        "baseline": evaluate_deterministic_fixture(
            variant_name="baseline",
            packet_budget_mode="off",
            budget_max_candidate_tokens=budget_max_candidate_tokens,
        ),
        "packet_budget_off": evaluate_deterministic_fixture(
            variant_name="packet_budget_off",
            packet_budget_mode="off",
            budget_max_candidate_tokens=budget_max_candidate_tokens,
        ),
        "packet_budget_shadow": evaluate_deterministic_fixture(
            variant_name="packet_budget_shadow",
            packet_budget_mode="shadow",
            budget_max_candidate_tokens=budget_max_candidate_tokens,
        ),
        "packet_budget_active": evaluate_deterministic_fixture(
            variant_name="packet_budget_active",
            packet_budget_mode="active",
            budget_max_candidate_tokens=budget_max_candidate_tokens,
        ),
    }
    variants["full"] = dict(variants["packet_budget_active"])
    return {
        "schema": BENCHMARK_REPORT_SCHEMA,
        "status": "pass",
        "benchmark": {
            "name": "deterministic_public_fixture",
            "dataset": "brainstack_public_fixture",
            "dataset_version": "v1",
            "seed": 7,
            "commit": commit,
        },
        "config": {
            "model": "deterministic-fixture",
            "embedding_backend": "none",
            "chunking": "fixture-candidates",
            "top_k": 4,
            "budget_max_candidate_tokens": budget_max_candidate_tokens,
        },
        "variants": variants,
        "public_safe": True,
        "schema_issues": [],
    }


def _installed_optional_packages() -> set[str]:
    return {name for name in ("datasets", "ragas") if importlib.util.find_spec(name) is not None}


def build_ragas_amnesty_readiness_report(
    *,
    installed_packages: set[str] | None = None,
    model_config: Mapping[str, Any] | None = None,
    dataset_id: str = "vibrantlabsai/amnesty_qa",
    split: str = "eval",
    sample_count: int = 25,
) -> dict[str, Any]:
    packages = set(installed_packages if installed_packages is not None else _installed_optional_packages())
    config = _mapping(model_config)
    required_dependencies = {"datasets", "ragas"}
    missing_dependencies = sorted(required_dependencies - packages)
    required_config = {"llm", "embeddings"}
    missing_config = sorted(field for field in required_config if not config.get(field))
    issues: list[dict[str, Any]] = []
    for dependency in missing_dependencies:
        issues.append({"code": "missing_dependency", "dependency": dependency})
    if missing_config:
        issues.append({"code": "missing_model_config", "fields": missing_config})
    ready = not issues
    return {
        "schema": "brainstack.ragas_amnesty_readiness.v1",
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "dataset": {
            "id": dataset_id,
            "split": split,
            "sample_count": int(sample_count),
        },
        "required_dependencies": sorted(required_dependencies),
        "missing_dependencies": missing_dependencies,
        "model_config": {
            "llm_configured": bool(config.get("llm")),
            "embeddings_configured": bool(config.get("embeddings")),
            "secret_values_redacted": True,
        },
        "issues": issues,
        "public_safe": True,
        "claim_boundary": "Readiness report only; it is not a RAGAS score unless ready dependencies and model config are present and the external runner is executed.",
    }
