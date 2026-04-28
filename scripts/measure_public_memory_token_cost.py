#!/usr/bin/env python3
"""Measure public fixture trace token-cost baseline.

This is measurement-only. It does not rank, truncate, optimize, or change any
memory-kernel behavior.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.core.packet_budget import build_budgeted_evidence_trace  # noqa: E402
from scripts.run_public_memory_kernel_fixtures import run_fixture_directory  # noqa: E402


def _json_token_estimate(value: object) -> int:
    """Cheap deterministic estimate for trace overhead, not a tokenizer claim."""

    text = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return max(1, (len(text) + 3) // 4)


def _candidate_token_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    candidates = [item for item in trace.get("candidates") or [] if isinstance(item, Mapping)]
    selected = [
        item for item in candidates if str(item.get("decision") or "") == "selected"
    ]
    dropped = [
        item
        for item in candidates
        if str(item.get("decision") or "") in {"dropped", "demoted"}
    ]
    dropped_by_reason: dict[str, int] = {}
    for item in dropped:
        reason_code = str(item.get("reason_code") or "unclassified")
        dropped_by_reason[reason_code] = dropped_by_reason.get(reason_code, 0) + int(
            item.get("token_estimate") or 0
        )
    total_candidate_tokens = sum(int(item.get("token_estimate") or 0) for item in candidates)
    selected_tokens = sum(int(item.get("token_estimate") or 0) for item in selected)
    dropped_tokens = sum(int(item.get("token_estimate") or 0) for item in dropped)
    return {
        "candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "dropped_candidate_count": len(dropped),
        "total_candidate_tokens": total_candidate_tokens,
        "selected_candidate_tokens": selected_tokens,
        "dropped_candidate_tokens": dropped_tokens,
        "dropped_tokens_by_reason": dict(sorted(dropped_by_reason.items())),
        "selected_token_ratio": round(selected_tokens / total_candidate_tokens, 4)
        if total_candidate_tokens
        else 0.0,
    }


def _budget_simulation(
    *,
    trace: Mapping[str, Any],
    max_candidate_tokens: int,
) -> dict[str, Any]:
    budgeted_trace = build_budgeted_evidence_trace(
        trace=trace,
        max_candidate_tokens=max_candidate_tokens,
    )
    summary = _candidate_token_summary(budgeted_trace)
    packet_budget = budgeted_trace.get("packet_budget") or {}
    return {
        "max_candidate_tokens": max_candidate_tokens,
        "packet_budget_status": packet_budget.get("status"),
        "fail_closed": bool(packet_budget.get("fail_closed")),
        "selected_candidate_tokens_after_budget": summary["selected_candidate_tokens"],
        "dropped_candidate_tokens_after_budget": summary["dropped_candidate_tokens"],
        "estimated_candidate_token_delta": int(packet_budget.get("estimated_tokens_before") or 0)
        - summary["selected_candidate_tokens"],
        "trace_complete_for_audit": budgeted_trace["trace_completeness"].get(
            "complete_for_audit"
        ),
    }


def measure_fixture_directory(
    fixture_dir: Path,
    *,
    budget_max_candidate_tokens: int | None = None,
) -> dict[str, Any]:
    run = run_fixture_directory(fixture_dir)
    scenarios = []
    aggregate = {
        "scenario_count": int(run.get("scenario_count") or 0),
        "total_candidate_tokens": 0,
        "selected_candidate_tokens": 0,
        "dropped_candidate_tokens": 0,
        "trace_overhead_tokens": 0,
    }
    for scenario in run.get("scenarios") or []:
        trace = scenario["trace"]
        summary = _candidate_token_summary(trace)
        trace_overhead = _json_token_estimate(trace)
        aggregate["total_candidate_tokens"] += summary["total_candidate_tokens"]
        aggregate["selected_candidate_tokens"] += summary["selected_candidate_tokens"]
        aggregate["dropped_candidate_tokens"] += summary["dropped_candidate_tokens"]
        aggregate["trace_overhead_tokens"] += trace_overhead
        scenario_report = {
            "scenario_id": scenario["scenario_id"],
            "status": scenario["status"],
            "receipt_coverage": scenario["receipt_coverage"].get("coverage_status"),
            "ack_mode": scenario["ack_plan"].get("ack_mode"),
            "trace_complete_for_audit": scenario["trace"]["trace_completeness"].get(
                "complete_for_audit"
            ),
            "trace_overhead_tokens": trace_overhead,
            **summary,
        }
        if budget_max_candidate_tokens is not None:
            scenario_report["budget_simulation"] = _budget_simulation(
                trace=trace,
                max_candidate_tokens=budget_max_candidate_tokens,
            )
        scenarios.append(scenario_report)
    aggregate["selected_token_ratio"] = round(
        aggregate["selected_candidate_tokens"] / aggregate["total_candidate_tokens"], 4
    ) if aggregate["total_candidate_tokens"] else 0.0
    aggregate["dropped_token_ratio"] = round(
        aggregate["dropped_candidate_tokens"] / aggregate["total_candidate_tokens"], 4
    ) if aggregate["total_candidate_tokens"] else 0.0
    report = {
        "schema": "brainstack.public_memory_token_cost_baseline.v1",
        "measurement_only": True,
        "production_optimization_enabled": False,
        "fixture_dir": str(fixture_dir),
        "fixture_status": run["status"],
        "aggregate": aggregate,
        "scenarios": scenarios,
        "notes": [
            "Token counts are deterministic estimates from public fixture traces.",
            "Dropped-candidate tokens are exclusion baseline, not a production savings claim.",
            "Trace overhead is measured separately so auditability is not hidden.",
        ],
    }
    if budget_max_candidate_tokens is not None:
        budgeted = [
            item["budget_simulation"]
            for item in scenarios
            if isinstance(item.get("budget_simulation"), Mapping)
        ]
        report["budget_simulation"] = {
            "measurement_only": True,
            "production_optimization_enabled": False,
            "max_candidate_tokens": budget_max_candidate_tokens,
            "scenario_count": len(budgeted),
            "fail_closed_count": sum(1 for item in budgeted if item.get("fail_closed")),
            "estimated_candidate_token_delta": sum(
                int(item.get("estimated_candidate_token_delta") or 0)
                for item in budgeted
            ),
        }
    return report


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="tests/fixtures/public_memory_kernel")
    parser.add_argument("--budget-max-candidate-tokens", type=int, default=None)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = measure_fixture_directory(
        Path(args.fixtures),
        budget_max_candidate_tokens=args.budget_max_candidate_tokens,
    )
    if args.out:
        _write_json(Path(args.out), report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["fixture_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
