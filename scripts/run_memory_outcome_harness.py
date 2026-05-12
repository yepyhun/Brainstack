#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.outcome_harness import REPORT_SCHEMA, run_harness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Brainstack memory outcome harnesses.")
    parser.add_argument("--out", type=Path, help="Write the full JSON report to this path.")
    parser.add_argument("--case", action="append", default=[], help="Run only this harness id. Can be repeated.")
    args = parser.parse_args(argv)

    report = run_harness(case_ids=args.case or None)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "schema": REPORT_SCHEMA,
                "status": report["status"],
                "harness_count": report["harness_count"],
                "brainstack_correct": report["summary"]["brainstack_answer_correct_count"],
                "raw_history_correct": report["summary"]["raw_history_answer_correct_count"],
                "token_savings_cases": report["summary"]["brainstack_token_savings_cases"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
