#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.persistent_bloat import build_persistent_bloat_report  # noqa: E402
from scripts.verify_adaptive_evidence_hotpath import (  # noqa: E402
    CASES,
    HotpathCaseSpec,
    _packet_defaults,
    _route_resolver,
    _snapshot_table_counts,
    _storage_mutation_count,
)

SCHEMA = "brainstack.adaptive_evidence_performance_dashboard.v1"

SHELF_FIELDS = {
    "profile": "profile_items",
    "continuity": "continuity_items",
    "transcript": "transcript_rows",
    "graph": "graph_rows",
    "corpus": "corpus_rows",
    "operating": "operating_records",
    "tasks": "task_items",
}


def percentile(values: Iterable[float], percentile_value: float) -> float:
    samples = sorted(float(value) for value in values)
    if not samples:
        return 0.0
    if len(samples) == 1:
        return round(samples[0], 3)
    rank = (len(samples) - 1) * percentile_value
    lower = int(rank)
    upper = min(lower + 1, len(samples) - 1)
    weight = rank - lower
    return round(samples[lower] * (1.0 - weight) + samples[upper] * weight, 3)


def _elapsed_ms(start: float) -> float:
    return max(0.0, (time.perf_counter() - start) * 1000.0)


def _build_packet(store: BrainstackStore, *, spec: HotpathCaseSpec, scope: str, session: str) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query=spec.query,
        session_id=session,
        principal_scope_key=scope,
        route_resolver=_route_resolver(spec.route_mode),
        packet_budget_mode="active",
        packet_budget_max_candidate_tokens=120,
        **_packet_defaults(),
    )


def _count_items(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _shelf_counts(packet: Mapping[str, Any]) -> dict[str, int]:
    return {shelf: _count_items(packet.get(field)) for shelf, field in SHELF_FIELDS.items()}


def _route_class(packet: Mapping[str, Any]) -> str:
    plan = packet.get("adaptive_route_plan") if isinstance(packet.get("adaptive_route_plan"), Mapping) else {}
    return str(plan.get("route_class") or packet.get("route_mode") or "unknown")


def _tank_escalated(packet: Mapping[str, Any]) -> bool:
    plan = packet.get("adaptive_route_plan") if isinstance(packet.get("adaptive_route_plan"), Mapping) else {}
    decision = plan.get("route_decision") if isinstance(plan.get("route_decision"), Mapping) else {}
    return decision.get("escalated_to_tank") is True


def _budget_summary(packet: Mapping[str, Any]) -> dict[str, Any]:
    budget = packet.get("packet_budget") if isinstance(packet.get("packet_budget"), Mapping) else {}
    decisions = budget.get("budget_decisions") if isinstance(budget.get("budget_decisions"), list) else []
    protected_drops = [
        item
        for item in decisions
        if isinstance(item, Mapping)
        and str(item.get("decision") or "") in {"dropped", "demoted"}
        and str(item.get("reason_code") or "").startswith("selected_budget_protected")
    ]
    return {
        "mode": budget.get("mode"),
        "status": budget.get("status"),
        "max_tokens": budget.get("max_tokens"),
        "estimated_tokens_before": budget.get("estimated_tokens_before"),
        "selected_candidate_tokens": budget.get("selected_candidate_tokens"),
        "dropped_candidate_tokens": budget.get("dropped_candidate_tokens"),
        "protected_drop_count": len(protected_drops),
        "decision_count": len(decisions),
    }


def _case_report(*, root: Path, spec: HotpathCaseSpec, index: int, iterations: int) -> dict[str, Any]:
    store = BrainstackStore(str(root / f"{spec.case_id}.sqlite3"))
    store.open()
    scope = f"principal:m008:perf:{index}:{spec.query_class}"
    session = f"session:m008:perf:{index}:{spec.query_class}"
    try:
        spec.seeder(store, scope, session)
        _build_packet(store, spec=spec, scope=scope, session=session)  # warmup
        before_counts = _snapshot_table_counts(store)
        latencies: list[float] = []
        last_packet: dict[str, Any] = {}
        for _ in range(iterations):
            start = time.perf_counter()
            last_packet = _build_packet(store, spec=spec, scope=scope, session=session)
            latencies.append(_elapsed_ms(start))
        after_counts = _snapshot_table_counts(store)
        bloat = build_persistent_bloat_report(store, principal_scope_key=scope)
    finally:
        store.close()

    return {
        "case_id": spec.case_id,
        "query_class": spec.query_class,
        "route_class": _route_class(last_packet),
        "tank_escalated": _tank_escalated(last_packet),
        "latency_ms": {
            "samples": [round(value, 3) for value in latencies],
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": round(max(latencies or [0.0]), 3),
        },
        "shelf_counts": _shelf_counts(last_packet),
        "budget": _budget_summary(last_packet),
        "storage_mutation_count": _storage_mutation_count(before_counts, after_counts),
        "bloat": {
            "write_amplification": bloat.get("write_amplification"),
            "support_only_ratio": bloat.get("support_only_ratio"),
            "active_packet_tokens": bloat.get("active_packet_tokens"),
            "stale_prior_ratio": bloat.get("stale_prior_ratio"),
        },
    }


def _public_safe(report: Mapping[str, Any]) -> bool:
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    forbidden = ("private source text", "provider_secret", "api_key", "raw_text", "packet_text", "model_output")
    return not any(marker in rendered for marker in forbidden)


def build_report(*, iterations: int = 7) -> dict[str, Any]:
    iterations = max(1, int(iterations))
    with tempfile.TemporaryDirectory(prefix="brainstack-m008-perf-dashboard-") as tmp:
        root = Path(tmp)
        cases = [_case_report(root=root, spec=spec, index=index, iterations=iterations) for index, spec in enumerate(CASES)]
    all_latencies = [sample for case in cases for sample in case["latency_ms"]["samples"]]
    failures: list[str] = []
    for case in cases:
        if case["budget"].get("mode") != "active":
            failures.append(f"{case['case_id']}:packet_budget_not_active")
        if case["budget"].get("protected_drop_count") != 0:
            failures.append(f"{case['case_id']}:protected_drop_detected")
        if case["storage_mutation_count"] != 0:
            failures.append(f"{case['case_id']}:read_path_mutated_storage")
    report = {
        "schema": SCHEMA,
        "status": "pass" if not failures else "fail",
        "failure_reasons": failures,
        "iteration_count": iterations,
        "summary": {
            "case_count": len(cases),
            "latency_ms_p50": percentile(all_latencies, 0.50),
            "latency_ms_p95": percentile(all_latencies, 0.95),
            "tank_escalation_count": sum(1 for case in cases if case["tank_escalated"]),
            "active_budget_case_count": sum(1 for case in cases if case["budget"].get("mode") == "active"),
            "protected_drop_count": sum(int(case["budget"].get("protected_drop_count") or 0) for case in cases),
            "read_path_mutation_count": sum(int(case["storage_mutation_count"] or 0) for case in cases),
        },
        "cases": cases,
    }
    report["public_safe"] = _public_safe(report)
    if report["public_safe"] is not True:
        report["status"] = "fail"
        report["failure_reasons"].append("public_safety_failed")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build public-safe adaptive evidence performance dashboard.")
    parser.add_argument("--iterations", type=int, default=7)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(iterations=args.iterations)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
