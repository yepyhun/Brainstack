#!/usr/bin/env python3
"""Fail Phase 249 closeout and force the next loop while work remains."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / ".planning" / "phases" / "249-release-claim-contract-hard-gate" / "IMPLEMENTATION_PLAN.md"
BLOCKED_SENTINEL_PREFIX = "BLOCKED:"


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
        next_action = {
            "action": "continue_loop",
            "work_item": f"Create missing Phase 249 implementation plan at {path}",
            "rule": "Do not stop at a missing plan. Create the plan, add the blocker, and rerun this gate.",
        }
        return {
            "schema": "brainstack.phase249_ralph_gate.v1",
            "status": "fail",
            "issue_count": 1,
            "issues": [{"code": "implementation_plan_missing", "path": str(path)}],
            "open_items": [],
            "blocked_items": [],
            "done_allowed": False,
            "stop_allowed": False,
            "loop_enforcement": {
                "mode": "force_continue_until_phase_done",
                "must_continue": True,
                "next_action": next_action,
            },
            "next_action": next_action,
        }
    text = path.read_text(encoding="utf-8")
    open_items = _section_items(text, "Open")
    issues = []
    blocked_items = [item for item in open_items if item.startswith(BLOCKED_SENTINEL_PREFIX)]
    actionable_open_items = [item for item in open_items if item not in blocked_items]
    if actionable_open_items:
        issues.append({"code": "implementation_plan_open_items", "count": len(actionable_open_items)})
    if blocked_items:
        issues.append({"code": "implementation_plan_blocked_items", "count": len(blocked_items)})
    next_action = None
    if open_items:
        next_action = {
            "action": "continue_loop",
            "work_item": open_items[0],
            "rule": "Do not report Phase 249 done. Execute the first open item or open/execute its linked phase, then rerun this gate.",
        }
    done_allowed = not issues
    return {
        "schema": "brainstack.phase249_ralph_gate.v1",
        "status": "pass" if done_allowed else "fail",
        "issue_count": len(issues),
        "issues": issues,
        "open_items": actionable_open_items,
        "blocked_items": blocked_items,
        "done_allowed": done_allowed,
        "stop_allowed": done_allowed,
        "loop_enforcement": {
            "mode": "force_continue_until_phase_done",
            "must_continue": not done_allowed,
            "next_action": next_action,
        },
        "next_action": next_action,
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
