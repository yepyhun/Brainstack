#!/usr/bin/env python3
"""Fail Phase 249 closeout while Ralph-style implementation plan has open work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / ".planning" / "phases" / "249-release-claim-contract-hard-gate" / "IMPLEMENTATION_PLAN.md"
BLOCKED_SENTINEL = (
    "No open implementation items in Phase 249. Phase remains blocked by proof-equivalence until "
    "linked Phase 250 resolves it."
)


def _section_items(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    items: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() == f"## {heading}"
            continue
        if in_section and line.startswith("- "):
            items.append(line[2:].strip())
    return items


def run_check(path: Path = PLAN) -> dict[str, object]:
    if not path.exists():
        return {
            "schema": "brainstack.phase249_ralph_gate.v1",
            "status": "fail",
            "issue_count": 1,
            "issues": [{"code": "implementation_plan_missing", "path": str(path)}],
            "open_items": [],
        }
    text = path.read_text(encoding="utf-8")
    open_items = _section_items(text, "Open")
    issues = []
    actionable_open_items = [
        item
        for item in open_items
        if item != BLOCKED_SENTINEL
    ]
    if actionable_open_items:
        issues.append({"code": "implementation_plan_open_items", "count": len(actionable_open_items)})
    return {
        "schema": "brainstack.phase249_ralph_gate.v1",
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "issues": issues,
        "open_items": actionable_open_items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PLAN)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run_check(args.plan)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
