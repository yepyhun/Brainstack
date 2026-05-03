#!/usr/bin/env python3
"""Write a deterministic public-safe Brainstack benchmark transparency report."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from brainstack.benchmark_transparency import (
    build_deterministic_benchmark_report,
    validate_benchmark_report,
)

ROOT = Path(__file__).resolve().parents[1]


def _head_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--budget-max-candidate-tokens", type=int, default=70)
    args = parser.parse_args()

    report = build_deterministic_benchmark_report(
        commit=str(args.commit or _head_commit()),
        budget_max_candidate_tokens=args.budget_max_candidate_tokens,
    )
    schema_issues = validate_benchmark_report(report)
    report["schema_issues"] = schema_issues
    if schema_issues:
        report["status"] = "fail"
    text = json.dumps(report, indent=2, sort_keys=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not schema_issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
