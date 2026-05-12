#!/usr/bin/env python3
"""Verify read-only Kanban recovery candidate classification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.operating_loop import build_kanban_recovery_candidates, recovery_summary  # noqa: E402


REPORT_SCHEMA = "brainstack.kanban_recovery_candidate_contract_proof.v1"


def build_report() -> dict[str, object]:
    snapshot = {
        "dispatcher_state": "blocked_ready_tasks",
        "wait_reasons": [
            {"task_id": "t-worker", "status": "ready", "assignee": "worker", "reason_code": "blocked_unknown_assignee"},
            {"task_id": "t-fanin", "status": "todo", "assignee": "reviewer", "reason_code": "waiting_for_parent_promotion_or_recompute"},
        ],
        "recent_failure_event_kinds": ["crashed", "timed_out"],
        "running_tasks": [
            {"task_id": "t-stale", "status": "running", "assignee": "builder", "running_age_seconds": 1800}
        ],
    }
    candidates = build_kanban_recovery_candidates(snapshot, stale_running_after_seconds=900)
    summary = recovery_summary(candidates)
    classes = {item["failure_class"] for item in candidates}
    forbidden = {action for item in candidates for action in item.get("forbidden_actions", [])}
    proof = {
        "unknown_assignee_candidate_present": "unknown_assignee" in classes,
        "fan_in_candidate_present": "parent_or_fan_in_wait" in classes,
        "failure_wave_candidate_present": "recent_failure_wave" in classes,
        "stale_running_candidate_present": "stale_running_worker" in classes,
        "does_not_auto_reassign_default": "auto_reassign_default" in forbidden
        and all("auto_reassign_default" not in item.get("allowed_actions", []) for item in candidates),
        "does_not_auto_unblock_or_retry": "retry_storm" in forbidden
        and all("retry_storm" not in item.get("allowed_actions", []) for item in candidates),
        "summary_is_agent_facing": summary["candidate_count"] == len(candidates)
        and summary["status"] == "recovery_candidates_present",
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True for item in candidates
        ),
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "side_effect_free": True,
        "issues": issues,
        "proof": proof,
        "candidate_count": len(candidates),
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Kanban recovery candidate contract.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

