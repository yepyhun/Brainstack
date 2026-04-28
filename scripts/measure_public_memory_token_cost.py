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


def measure_fixture_directory(fixture_dir: Path) -> dict[str, Any]:
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
        scenarios.append(
            {
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
        )
    aggregate["selected_token_ratio"] = round(
        aggregate["selected_candidate_tokens"] / aggregate["total_candidate_tokens"], 4
    ) if aggregate["total_candidate_tokens"] else 0.0
    aggregate["dropped_token_ratio"] = round(
        aggregate["dropped_candidate_tokens"] / aggregate["total_candidate_tokens"], 4
    ) if aggregate["total_candidate_tokens"] else 0.0
    return {
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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="tests/fixtures/public_memory_kernel")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    report = measure_fixture_directory(Path(args.fixtures))
    if args.out:
        _write_json(Path(args.out), report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["fixture_status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
