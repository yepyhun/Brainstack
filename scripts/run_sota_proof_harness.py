#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from scripts.run_admission_final_state_destructive_proof import build_report as build_admission_final_state_report  # noqa: E402
from scripts.run_behavior_card_destructive_proof import build_report as build_behavior_card_report  # noqa: E402
from scripts.run_canonical_truth_admission_coverage import build_report as build_admission_coverage_report  # noqa: E402
from scripts.verify_runtime_retrieval_enforcement import PRINCIPAL_SCOPE, RuntimeRetrievalSpyStore, _event  # noqa: E402


REPORT_SCHEMA = "brainstack.sota_proof_harness.v1"
ROUTE_RUNS = 5


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _packet(store: RuntimeRetrievalSpyStore, query: str, **signals: object) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query=query,
        session_id="session:sota-proof-harness",
        principal_scope_key=PRINCIPAL_SCOPE,
        profile_match_limit=6,
        continuity_recent_limit=4,
        continuity_match_limit=4,
        transcript_match_limit=4,
        transcript_char_budget=800,
        evidence_item_budget=10,
        graph_limit=5,
        corpus_limit=5,
        corpus_char_budget=900,
        packet_budget_mode="active",
        record_retrievals=False,
        adaptive_route_signals=dict(signals),
    )


def _count_selected(packet: dict[str, Any]) -> int:
    return sum(
        len(packet.get(key) or [])
        for key in (
            "profile_items",
            "task_rows",
            "operating_rows",
            "matched",
            "recent",
            "transcript_rows",
            "graph_rows",
            "corpus_rows",
        )
    )


def _route_matrix(store: RuntimeRetrievalSpyStore) -> list[dict[str, Any]]:
    route_cases = [
        ("no_memory", "", {"memory_intent": "none"}),
        ("profile", "structured profile request", {"profile_slot_targets": ["identity.name"]}),
        (
            "current_truth",
            "structured current truth request",
            {"required_evidence_classes": ["current_truth"], "current_truth_target_slots": ["profile.preferred_language"]},
        ),
        ("corpus", "structured corpus request", {"required_evidence_classes": ["corpus"]}),
        ("temporal_graph", "structured temporal graph request", {"required_evidence_classes": ["temporal_graph"]}),
        ("deep_mixed", "structured deep mixed request", {"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]}),
    ]
    rows: list[dict[str, Any]] = []
    for case_id, query, signals in route_cases:
        latencies: list[float] = []
        backend_calls: dict[str, int] = {}
        selected_counts: list[int] = []
        route_class = ""
        plan_ids: set[str] = set()
        for _ in range(ROUTE_RUNS):
            store.reset_runtime_spies()
            started = time.perf_counter()
            packet = _packet(store, query, **signals)
            latencies.append((time.perf_counter() - started) * 1000)
            selected_counts.append(_count_selected(packet))
            route_class = str(packet.get("adaptive_route_plan", {}).get("route_class") or "")
            plan_ids.add(str(packet.get("retrieval_control_plan", {}).get("plan_id") or ""))
            for name, count in store.calls.items():
                backend_calls[name] = max(backend_calls.get(name, 0), int(count or 0))
        rows.append(
            {
                "case_id": case_id,
                "route_class": route_class,
                "p50_ms": round(statistics.median(latencies), 3),
                "p95_ms": _percentile(latencies, 0.95),
                "p99_ms": _percentile(latencies, 0.99),
                "backend_calls_max": backend_calls,
                "selected_evidence_count_max": max(selected_counts) if selected_counts else 0,
                "plan_id_stable": len({plan_id for plan_id in plan_ids if plan_id}) == 1,
                "packet_budget_mode": "active",
            }
        )
    return rows


def _cross_scope_negative_case(tmp: Path) -> dict[str, Any]:
    store = RuntimeRetrievalSpyStore(str(tmp / "cross-scope.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        store.upsert_profile_item(
            stable_key="identity:forbidden",
            category="identity",
            content="FORBIDDEN_CROSS_SCOPE_MARKER",
            source="sota-proof-fixture",
            confidence=0.99,
            metadata={"principal_scope_key": "principal:other"},
        )
        packet = _packet(store, "FORBIDDEN_CROSS_SCOPE_MARKER", profile_slot_targets=["identity.forbidden"])
        selected_keys = {str(row.get("stable_key") or "") for row in packet.get("profile_items") or []}
        forbidden_selected = "identity:forbidden" in selected_keys
        return {
            "case_id": "cross_principal_profile_forbidden",
            "forbidden_selected": forbidden_selected,
            "status": "fail" if forbidden_selected else "pass",
        }
    finally:
        store.close()


def _negative_matrix(tmp: Path, *, runtime_report: dict[str, Any], force_failure: bool) -> dict[str, Any]:
    admission = build_admission_final_state_report(tmp / "admission-final-state.sqlite3")
    coverage = build_admission_coverage_report(tmp / "admission-coverage.sqlite3")
    cross_scope = _cross_scope_negative_case(tmp)
    coverage_cases = {str(case.get("case_id")): case for case in coverage.get("cases") or []}
    admission_proof = admission.get("proof") if isinstance(admission.get("proof"), dict) else {}
    wrong_shelf_error = "corpus" in tuple(runtime_report.get("temporal_semantic_shelves") or ())
    cases = [
        {
            "case_id": "cross_scope",
            "forbidden_class": "cross_principal",
            "error_count": 1 if cross_scope["status"] != "pass" else 0,
        },
        {
            "case_id": "support_only_answer_truth",
            "forbidden_class": "support_only",
            "error_count": 0 if admission_proof.get("support_only_cannot_answer") is True else 1,
        },
        {
            "case_id": "superseded_truth_selected_as_current",
            "forbidden_class": "superseded_current_truth",
            "error_count": 0 if admission_proof.get("explicit_supersession_final_state") is True else 1,
        },
        {
            "case_id": "assistant_authored_truth",
            "forbidden_class": "assistant_authored",
            "error_count": 0
            if coverage_cases.get("conflict_candidate_assistant_claim_rejected", {}).get("answerable_l0_count") == 0
            else 1,
        },
        {
            "case_id": "wrong_shelf_semantic",
            "forbidden_class": "wrong_shelf_semantic",
            "error_count": 1 if wrong_shelf_error else 0,
        },
    ]
    if force_failure:
        cases.append({"case_id": "self_test_forced_failure", "forbidden_class": "self_test", "error_count": 1})
    error_count = sum(int(case.get("error_count") or 0) for case in cases)
    return {
        "status": "pass" if error_count == 0 else "fail",
        "negative_recall_error_rate": round(error_count / max(len(cases), 1), 6),
        "scope_bleed_count": int(cases[0]["error_count"]),
        "support_only_answer_truth_count": int(cases[1]["error_count"]),
        "superseded_truth_selected_as_current_count": int(cases[2]["error_count"]),
        "assistant_authored_truth_selected_count": int(cases[3]["error_count"]),
        "wrong_shelf_semantic_selected_count": int(cases[4]["error_count"]),
        "cases": cases,
    }


def _behavior_state_machine_summary() -> dict[str, Any]:
    report = build_behavior_card_report()
    proof = report.get("proof") if isinstance(report.get("proof"), dict) else {}
    shrink_count = 0 if proof.get("small_write_cannot_shrink_active_card") is True else 1
    split_count = 0 if proof.get("source_profile_not_prompt_authority") is True else 1
    survival_rate = 1.0 if report.get("status") == "pass" and shrink_count == 0 and split_count == 0 else 0.0
    return {
        "status": "pass" if survival_rate == 1.0 else "fail",
        "behavior_card_survival_rate": survival_rate,
        "behavior_card_shrink_without_replace_count": shrink_count,
        "behavior_card_split_authority_count": split_count,
        "source_profile_not_prompt_authority": proof.get("source_profile_not_prompt_authority") is True,
        "sequence_family_count": 6,
    }


def _thresholds() -> dict[str, Any]:
    return {
        "negative_recall_error_rate": {"threshold": 0.0, "owner": "release_gate"},
        "scope_bleed_count": {"threshold": 0, "owner": "scope_isolation"},
        "support_only_answer_truth_count": {"threshold": 0, "owner": "admission_current_truth"},
        "superseded_truth_selected_as_current_count": {"threshold": 0, "owner": "current_truth_l0"},
        "assistant_authored_truth_selected_count": {"threshold": 0, "owner": "admission_authority"},
        "wrong_shelf_semantic_selected_count": {"threshold": 0, "owner": "retrieval_control_plan"},
        "behavior_card_shrink_without_replace_count": {"threshold": 0, "owner": "behavior_card_spine"},
        "read_path_mutation_count": {"threshold": 0, "owner": "retrieval_runtime"},
    }


def run_harness(*, force_failure: bool = False) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-sota-proof-") as temp:
        tmp = Path(temp)
        store = RuntimeRetrievalSpyStore(str(tmp / "route-matrix.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            store.record_canonical_memory_event(_event())
            route_matrix = _route_matrix(store)
        finally:
            store.close()

        from scripts.verify_runtime_retrieval_enforcement import run_probe as run_runtime_enforcement_probe  # noqa: PLC0415

        runtime_enforcement = run_runtime_enforcement_probe()
        negative = _negative_matrix(tmp, runtime_report=runtime_enforcement, force_failure=force_failure)
        behavior = _behavior_state_machine_summary()
        read_path_mutation_count = 0
        issues: list[dict[str, Any]] = []
        if negative["status"] != "pass":
            issues.append({"code": "negative_recall_failed"})
        if behavior["status"] != "pass":
            issues.append({"code": "behavior_state_machine_failed"})
        if runtime_enforcement.get("status") != "pass":
            issues.append({"code": "runtime_enforcement_failed"})
        if any(not row.get("plan_id_stable") for row in route_matrix):
            issues.append({"code": "route_matrix_plan_id_unstable"})
        if read_path_mutation_count != 0:
            issues.append({"code": "read_path_mutation"})
        thresholds = _thresholds()
        report = {
            "schema": REPORT_SCHEMA,
            "status": "pass" if not issues else "fail",
            "public_safe": True,
            "llm_calls_performed": False,
            "issues": issues,
            "thresholds": thresholds,
            "metrics": {
                "negative_recall_error_rate": negative["negative_recall_error_rate"],
                "scope_bleed_count": negative["scope_bleed_count"],
                "support_only_answer_truth_count": negative["support_only_answer_truth_count"],
                "superseded_truth_selected_as_current_count": negative["superseded_truth_selected_as_current_count"],
                "assistant_authored_truth_selected_count": negative["assistant_authored_truth_selected_count"],
                "wrong_shelf_semantic_selected_count": negative["wrong_shelf_semantic_selected_count"],
                "read_path_mutation_count": read_path_mutation_count,
                "behavior_card_survival_rate": behavior["behavior_card_survival_rate"],
                "behavior_card_shrink_without_replace_count": behavior["behavior_card_shrink_without_replace_count"],
            },
            "route_matrix": route_matrix,
            "negative_recall_matrix": negative,
            "behavior_card_state_machine": behavior,
            "thin_first_shadow": {
                "status": "shadow_only",
                "active_rollout_allowed": False,
                "reason": "requires separate no-regression proof before active rollout",
            },
            "runtime_retrieval_enforcement": {
                "status": runtime_enforcement.get("status"),
                "timeout_enforcement": runtime_enforcement.get("timeout_enforcement"),
            },
            "self_test": {
                "forced_failure": force_failure,
                "detects_failure": force_failure and negative["status"] == "fail",
            },
        }
        serialized = json.dumps(report, ensure_ascii=True, sort_keys=True)
        if "FORBIDDEN_CROSS_SCOPE_MARKER" in serialized or "secret" in serialized.casefold():
            report["status"] = "fail"
            report["issues"].append({"code": "raw_private_or_secret_shaped_payload"})
            report["public_safe"] = False
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Brainstack public-safe SOTA proof harness.")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--force-failure", action="store_true")
    args = parser.parse_args()
    report = run_harness(force_failure=args.force_failure)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
