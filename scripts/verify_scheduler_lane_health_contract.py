#!/usr/bin/env python3
"""Verify scheduler lane classification and starvation detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.operating_loop import build_scheduler_lane_health  # noqa: E402


REPORT_SCHEMA = "brainstack.scheduler_lane_health_contract_proof.v1"


def build_report() -> dict[str, object]:
    healthy = build_scheduler_lane_health(
        [
            {"id": "heartbeat", "kind": "heartbeat", "lane": "heartbeat", "last_run_age_seconds": 20, "stale_after_seconds": 180},
            {"id": "signal", "kind": "status_projection", "lane": "signal", "last_run_age_seconds": 30, "stale_after_seconds": 180},
        ]
    )
    starvation = build_scheduler_lane_health(
        [
            {"id": "builder", "name": "builder", "lane": "builder", "creates_work": True, "fixed_schedule": True, "reads_events": False, "running_duration_seconds": 800, "max_runtime_seconds": 120},
            {"id": "heartbeat", "kind": "heartbeat", "lane": "heartbeat", "last_run_age_seconds": 900, "stale_after_seconds": 180},
            {"id": "signal", "kind": "status_projection", "lane": "status_projection", "last_run_age_seconds": 900, "stale_after_seconds": 180},
        ]
    )
    missed = build_scheduler_lane_health(
        [
            {"id": "executor", "kind": "recovery", "lane": "recovery", "missed_run_count": 3, "last_run_age_seconds": 60, "stale_after_seconds": 180}
        ]
    )
    empty = build_scheduler_lane_health([])
    proof = {
        "healthy_lanes_pass": healthy["verdict"] == "healthy",
        "heavy_job_plus_stale_lane_is_critical": starvation["verdict"] == "critical"
        and starvation["starvation_risk"] is True
        and "SCHEDULER_STARVATION_RISK" in starvation["reason_codes"],
        "missed_runs_are_not_healthy": missed["verdict"] == "degraded",
        "empty_evidence_is_not_healthy": empty["verdict"] == "insufficient_evidence",
        "controller_substitute_classified": any(
            item["job_class"] == "controller_substitute" and item["migration_target"] == "controller_decision_required"
            for item in starvation["jobs"]
        ),
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True
            for item in (healthy, starvation, missed, empty)
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
        "scenario_verdicts": {
            "healthy": healthy["verdict"],
            "starvation": starvation["verdict"],
            "missed": missed["verdict"],
            "empty": empty["verdict"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify scheduler lane health contract.")
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

