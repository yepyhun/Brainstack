#!/usr/bin/env python3
"""Capture or compare deterministic retrieval shadow parity snapshots."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, cast

from brainstack_replay_canary import run_replay


VOLATILE_KEYS = {
    "latency_ms",
    "latency_bucket",
}


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(raw)
            for key, raw in sorted(value.items())
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def build_snapshot() -> dict[str, Any]:
    report = run_replay(repeat=1)
    rows: dict[str, Any] = {}
    for raw in report.get("results") or []:
        if not isinstance(raw, Mapping):
            continue
        key = "|".join(
            [
                str(raw.get("scenario_id") or ""),
                str(raw.get("fixture_variant") or ""),
                str(raw.get("mode") or ""),
            ]
        )
        rows[key] = _normalize(raw)
    return {
        "schema": "brainstack.retrieval_shadow_parity.v1",
        "scenario_count": len(rows),
        "results": rows,
    }


def compare_snapshot(current: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    current_rows = cast(dict[str, Any], current.get("results") if isinstance(current.get("results"), Mapping) else {})
    baseline_rows = cast(dict[str, Any], baseline.get("results") if isinstance(baseline.get("results"), Mapping) else {})
    current_keys = set(current_rows)
    baseline_keys = set(baseline_rows)
    changed = sorted(key for key in current_keys & baseline_keys if current_rows[key] != baseline_rows[key])
    return {
        "schema": "brainstack.retrieval_shadow_parity.compare.v1",
        "status": "pass" if not changed and current_keys == baseline_keys else "fail",
        "baseline_count": len(baseline_keys),
        "current_count": len(current_keys),
        "missing": sorted(baseline_keys - current_keys),
        "extra": sorted(current_keys - baseline_keys),
        "changed": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or compare retrieval shadow parity snapshots.")
    parser.add_argument("--baseline", type=Path, help="Existing baseline snapshot to compare against.")
    parser.add_argument("--output", type=Path, required=True, help="Write current snapshot JSON.")
    parser.add_argument("--compare-output", type=Path, help="Write comparison JSON.")
    args = parser.parse_args()

    current = build_snapshot()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.baseline:
        print(json.dumps({"status": "captured", "scenario_count": current["scenario_count"]}, sort_keys=True))
        return 0

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    comparison = compare_snapshot(current, baseline)
    if args.compare_output:
        args.compare_output.parent.mkdir(parents=True, exist_ok=True)
        args.compare_output.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(comparison, sort_keys=True))
    return 0 if comparison["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
