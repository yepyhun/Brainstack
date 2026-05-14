#!/usr/bin/env python3
"""Verify durable work-state contract scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXT = ROOT / "extensions" / "hermes_continuation"
if EXT.exists() and str(EXT) not in sys.path:
    sys.path.insert(0, str(EXT))

from brainstack.operating_loop import build_operating_loop_verdict  # noqa: E402
from hermes_continuation.work_state import build_durable_work_state_contract  # noqa: E402


REPORT_SCHEMA = "hermes_continuation.durable_work_state_contract_proof.v1"


def build_report() -> dict[str, object]:
    healthy = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w-healthy",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["artifact:healthy"],
                    "side_effect_durable": True,
                    "acknowledged": True,
                    "handoff": {"next_action": "inspect next frontier"},
                }
            ]
        }
    )
    ack_before_durability = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w-ack",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["artifact:ack"],
                    "side_effect_durable": False,
                    "acknowledged": True,
                }
            ]
        }
    )
    unknown_authority = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w-auth",
                    "status": "ready",
                    "authority": "unknown",
                    "evidence_refs": ["artifact:auth"],
                }
            ]
        }
    )
    blocked_without_repair = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w-blocked",
                    "status": "blocked",
                    "authority": "verified",
                    "evidence_refs": ["artifact:block"],
                }
            ]
        }
    )
    stopped = build_durable_work_state_contract({"state": "stopped_intentionally"})
    operating_loop = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {
                "dispatcher_state": "workers_running",
                "running_worker_count": 1,
            },
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
            "durable_work_state": ack_before_durability,
        }
    )
    scenarios = {
        "healthy": healthy,
        "ack_before_durability": ack_before_durability,
        "unknown_authority": unknown_authority,
        "blocked_without_repair": blocked_without_repair,
        "stopped": stopped,
    }
    proof = {
        "healthy_requires_authority_evidence_durability_handoff": healthy["verdict"] == "healthy",
        "ack_before_durability_is_critical": ack_before_durability["verdict"] == "critical"
        and "ACK_BEFORE_DURABLE_SIDE_EFFECT" in ack_before_durability["reason_codes"],
        "unknown_authority_is_critical": unknown_authority["verdict"] == "critical"
        and "UNKNOWN_AUTHORITY" in unknown_authority["reason_codes"],
        "blocked_without_repair_is_not_healthy": blocked_without_repair["verdict"] == "degraded"
        and bool(blocked_without_repair["repair_candidates"]),
        "intentional_stop_is_distinct": stopped["verdict"] == "stopped_intentionally",
        "operating_loop_consumes_critical_work_state": operating_loop["verdict"] == "critical"
        and "durable_work_state_critical" in operating_loop["blockers"],
        "read_only_side_effect_free": all(
            item.get("read_only") is True and item.get("side_effect_free") is True
            for item in scenarios.values()
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
        "scenario_verdicts": {name: scenario["verdict"] for name, scenario in scenarios.items()},
        "operating_loop_verdict": operating_loop["verdict"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify durable work-state contract.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
