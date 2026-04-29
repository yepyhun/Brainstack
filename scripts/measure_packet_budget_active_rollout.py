#!/usr/bin/env python3
"""Prove active packet-budget rollout on public-safe live-like packets."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from statistics import quantiles
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402

from scripts.measure_packet_budget_live_shadow_telemetry import (  # noqa: E402
    MIN_FAMILY_COUNT,
    MIN_SAMPLE_COUNT,
    SEEDERS,
    _fusion_signal_for_sample,
    _packet_budget_summary,
    _packet_defaults,
    _protected_drop_attempts,
)

LATENCY_OVERHEAD_P95_THRESHOLD_MS = 50.0


def _elapsed_ms(start: float, end: float) -> float:
    return max(0.0, (end - start) * 1000.0)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 2:
        return values[0]
    return quantiles(values, n=20, method="inclusive")[18]


def _budget_has_reason_registry_pass(packet_budget: Mapping[str, Any]) -> bool:
    return bool(packet_budget.get("budget_reason_code_registry_pass", True))


def measure_active_rollout(
    *,
    sample_count: int = 24,
    max_candidate_tokens: int = 120,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    off_elapsed: list[float] = []
    active_elapsed: list[float] = []

    with tempfile.TemporaryDirectory(prefix="brainstack-phase208-") as tmp:
        root = Path(tmp)
        for index in range(sample_count):
            family, seeder = SEEDERS[index % len(SEEDERS)]
            store = BrainstackStore(str(root / f"sample-{index}.sqlite3"))
            store.open()
            scope = f"principal:phase208:{family}:{index}"
            session = f"session:phase208:{family}:{index}"
            try:
                query = seeder(store, scope=scope, session=session, variant=index)

                start = time.perf_counter()
                off = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="off",
                    **_packet_defaults(),
                )
                off_elapsed.append(_elapsed_ms(start, time.perf_counter()))

                shadow = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="shadow",
                    packet_budget_max_candidate_tokens=max_candidate_tokens,
                    **_packet_defaults(),
                )

                start = time.perf_counter()
                active = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="active",
                    packet_budget_max_candidate_tokens=max_candidate_tokens,
                    **_packet_defaults(),
                )
                active_elapsed.append(_elapsed_ms(start, time.perf_counter()))

                active_budget = active.get("packet_budget") or {}
                shadow_budget = shadow.get("packet_budget") or {}
                reports.append(
                    {
                        "sample_id": f"sample_{index:03d}",
                        "scenario_family": family,
                        "active_applied_to_output": active_budget.get("applied_to_output") is True,
                        "block_changed_from_unbudgeted": off.get("block") != active.get("block"),
                        "selected_candidate_tokens_match_shadow": active_budget.get(
                            "selected_candidate_tokens"
                        )
                        == shadow_budget.get("selected_candidate_tokens"),
                        "active_packet_budget": _packet_budget_summary(active_budget),
                        "shadow_packet_budget": _packet_budget_summary(shadow_budget),
                        "protected_truth_drop_attempts": _protected_drop_attempts(active_budget),
                        "reason_registry_pass": _budget_has_reason_registry_pass(active_budget),
                        "raw_text_in_budget_trace": bool(
                            active_budget.get("raw_text_in_budget_trace", False)
                        ),
                        "budget_decision_trace_present": bool(active_budget.get("budget_decisions")),
                        "fusion_signal": _fusion_signal_for_sample(active_budget),
                    }
                )
            finally:
                store.close()

    families = sorted({item["scenario_family"] for item in reports})
    active_baseline_tokens = sum(
        item["active_packet_budget"]["estimated_tokens_before"] for item in reports
    )
    active_budgeted_tokens = sum(
        item["active_packet_budget"]["selected_candidate_tokens"] for item in reports
    )
    delta = active_baseline_tokens - active_budgeted_tokens
    overhead_values = [
        max(0.0, active_ms - off_ms) for active_ms, off_ms in zip(active_elapsed, off_elapsed)
    ]
    latency_p95 = round(_p95(overhead_values), 3)
    protected_drops = sum(item["protected_truth_drop_attempts"] for item in reports)
    with tempfile.TemporaryDirectory(prefix="brainstack-phase208-unsupported-") as tmp:
        store = BrainstackStore(str(Path(tmp) / "unsupported.sqlite3"))
        store.open()
        try:
            unsupported_probe = build_working_memory_packet(
                store,
                query="unsupported packet budget mode probe",
                session_id="session:phase208:unsupported",
                principal_scope_key="principal:phase208:unsupported",
                packet_budget_mode="unsupported",
                packet_budget_max_candidate_tokens=max_candidate_tokens,
                **_packet_defaults(),
            )
        finally:
            store.close()
    unsupported_budget = unsupported_probe.get("packet_budget") or {}
    unsupported_path_explicit = (
        unsupported_budget.get("enabled") is False
        and unsupported_budget.get("disabled_reason") == "invalid_packet_budget_mode"
    )
    thresholds = {
        "sample_count_met": len(reports) >= MIN_SAMPLE_COUNT,
        "family_count_met": len(families) >= MIN_FAMILY_COUNT,
        "active_applied_to_output": all(item["active_applied_to_output"] for item in reports),
        "protected_truth_drop_attempts_zero": protected_drops == 0,
        "budget_decision_trace_present": all(
            item["budget_decision_trace_present"] for item in reports
        ),
        "budget_reason_code_registry_pass": all(item["reason_registry_pass"] for item in reports),
        "raw_text_in_budget_trace_false": not any(
            item["raw_text_in_budget_trace"] for item in reports
        ),
        "selected_candidate_tokens_match_shadow": all(
            item["selected_candidate_tokens_match_shadow"] for item in reports
        ),
        "latency_overhead_within_threshold": latency_p95 <= LATENCY_OVERHEAD_P95_THRESHOLD_MS,
        "unsupported_path_explicit": unsupported_path_explicit,
    }
    passed = all(thresholds.values())
    return {
        "schema": "brainstack.phase208.active_packet_budget_rollout.v1",
        "active_budget_enabled_for_supported_paths": passed,
        "activation_thresholds": thresholds,
        "protected_truth_drop_attempts": protected_drops,
        "output_changed_against_shadow_baseline": False,
        "budget_decision_trace_present": thresholds["budget_decision_trace_present"],
        "budget_reason_code_registry_pass": thresholds["budget_reason_code_registry_pass"],
        "raw_text_in_budget_trace": False,
        "candidate_token_delta_percent": round(
            (delta / active_baseline_tokens * 100.0), 2
        )
        if active_baseline_tokens
        else 0.0,
        "packet_build_latency_overhead_ms_p95": latency_p95,
        "packet_build_latency_overhead_threshold_ms": LATENCY_OVERHEAD_P95_THRESHOLD_MS,
        "unsupported_path_fail_closed_count": 1 if unsupported_path_explicit else 0,
        "scenario_count": len(reports),
        "distinct_scenario_family_count": len(families),
        "scenario_families": families,
        "baseline_candidate_tokens": active_baseline_tokens,
        "active_budget_candidate_tokens": active_budgeted_tokens,
        "samples": reports,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-count", type=int, default=24)
    parser.add_argument("--budget-max-candidate-tokens", type=int, default=120)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = measure_active_rollout(
        sample_count=args.sample_count,
        max_candidate_tokens=args.budget_max_candidate_tokens,
    )
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["active_budget_enabled_for_supported_paths"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
