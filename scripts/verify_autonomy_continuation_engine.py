#!/usr/bin/env python3
"""Verify the universal autonomy continuation engine contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.autonomy_continuation_engine import (  # noqa: E402
    build_autonomy_continuation_decision,
    build_autonomy_runtime_adapter_contract,
)


REPORT_SCHEMA = "brainstack.autonomy_continuation_engine_proof.v1"


def _decision(name: str, evidence: dict) -> dict:
    result = build_autonomy_continuation_decision(evidence)
    return {"name": name, **result}


def _build_replay_fixture() -> dict:
    seen: list[str] = []
    decisions: list[dict] = []
    for index in range(120):
        evidence = {
            "event": {
                "kind": "task_completed",
                "event_id": f"evt-replay-{index}",
                "task_id": f"t-replay-{index}",
            },
            "controller_state": {"seen_idempotency_keys": seen},
            "scores": {
                "expected_value_next": 0.72,
                "confidence": 0.74,
                "progress_delta": 0.4,
                "novelty": 0.3,
            },
        }
        result = build_autonomy_continuation_decision(evidence)
        decisions.append(result)
        seen.append(result["idempotency_key"])

    duplicate = build_autonomy_continuation_decision(
        {
            "event": {
                "kind": "task_completed",
                "event_id": "evt-replay-42",
                "task_id": "t-replay-42",
                "idempotency_key": decisions[42]["idempotency_key"],
            },
            "controller_state": {"seen_idempotency_keys": seen},
        }
    )
    return {
        "count": len(decisions),
        "unique_idempotency_keys": len({item["idempotency_key"] for item in decisions}),
        "all_read_only": all(item["read_only"] and item["side_effect_free"] for item in decisions),
        "duplicate_decision": duplicate["decision"],
        "duplicate_ignored": duplicate["duplicate_ignored"],
    }


def build_report() -> dict[str, object]:
    scenarios = {
        "no_signal": _decision("no_signal", {}),
        "high_risk_human": _decision(
            "high_risk_human",
            {
                "event": {"kind": "approval_received", "event_id": "evt-risk"},
                "scores": {"expected_value_next": 0.9, "confidence": 0.9, "intervention_risk": 0.9},
                "safety": {"external_side_effect": True, "approval_missing": True},
            },
        ),
        "local_repair": _decision(
            "local_repair",
            {
                "event": {"kind": "task_completed", "event_id": "evt-repair", "artifact_missing": True},
                "safety": {"local_repair_available": True},
            },
        ),
        "wrong_step": _decision(
            "wrong_step",
            {
                "event": {"kind": "task_completed", "event_id": "evt-wrong", "previous_step_wrong": True},
                "scores": {"repair_urgency": 0.9, "confidence": 0.8},
            },
        ),
        "split": _decision(
            "split",
            {
                "event": {"kind": "frontier_below_saturation", "event_id": "evt-split"},
                "controller_state": {"current_fanout": 1, "max_fanout": 4},
                "scores": {
                    "expected_value_next": 0.9,
                    "confidence": 0.8,
                    "independence_score": 0.9,
                    "intervention_risk": 0.1,
                },
                "rolling_next5": [{"id": "branch", "summary": "branch verifier"}],
            },
        ),
        "verify": _decision(
            "verify",
            {
                "event": {"kind": "task_completed", "event_id": "evt-verify"},
                "scores": {"expected_value_next": 0.9, "confidence": 0.4},
            },
        ),
        "evolver": _decision(
            "evolver",
            {
                "event": {"kind": "evolver_signal_observed", "event_id": "evt-evo"},
                "evolver_signal": {"observed": True, "directive": "execute"},
            },
        ),
        "private_leak": _decision(
            "private_leak",
            {
                "event": {"kind": "task_completed", "event_id": "evt-private"},
                "adapter": {"private_data_present": True},
            },
        ),
        "filler_loop": _decision(
            "filler_loop",
            {
                "event": {"kind": "frontier_empty", "event_id": "evt-filler"},
                "scores": {"repetition_penalty": 0.8, "expected_value_next": 0.2, "confidence": 0.8},
            },
        ),
    }
    replay = _build_replay_fixture()
    adapter_bad = build_autonomy_runtime_adapter_contract(
        {
            "decision": scenarios["split"],
            "runtime": {"side_effect_channel": "custom_shell"},
            "receipt": {"written": False},
            "cursor": {"persisted": False},
        }
    )
    adapter_good = build_autonomy_runtime_adapter_contract(
        {
            "decision": scenarios["split"],
            "runtime": {
                "side_effect_channel": "hermes_kanban",
                "idempotent_applier": True,
                "failure_reported_as_state": True,
            },
            "receipt": {"written": True},
            "cursor": {"persisted": True},
        }
    )
    proof = {
        "no_signal_waits_without_filler": scenarios["no_signal"]["decision"] == "wait"
        and "NO_SIGNAL_NO_FILLER" in scenarios["no_signal"]["reason_codes"],
        "high_risk_requires_human": scenarios["high_risk_human"]["decision"] == "human_needed",
        "local_repair_not_human_escape": scenarios["local_repair"]["decision"] == "repair",
        "wrong_step_backtracks": scenarios["wrong_step"]["decision"] == "repair",
        "independent_high_value_splits": scenarios["split"]["decision"] == "split",
        "low_confidence_high_value_verifies": scenarios["verify"]["decision"] == "verify",
        "evolver_signal_is_inert": scenarios["evolver"]["decision"] == "verify",
        "private_adapter_leak_blocks": scenarios["private_leak"]["verdict"] == "critical",
        "filler_loop_learns_not_spins": scenarios["filler_loop"]["decision"] == "learn",
        "replay_100_plus_events_unique": replay["count"] >= 100
        and replay["unique_idempotency_keys"] == replay["count"],
        "restart_duplicate_is_suppressed": replay["duplicate_decision"] == "wait" and replay["duplicate_ignored"] is True,
        "read_only_side_effect_free": replay["all_read_only"]
        and all(item["read_only"] and item["side_effect_free"] for item in scenarios.values()),
        "runtime_adapter_rejects_unowned_side_effects": adapter_bad["verdict"] == "critical"
        and "SIDE_EFFECT_CHANNEL_NOT_HERMES_OWNED" in adapter_bad["reason_codes"],
        "runtime_adapter_accepts_hermes_owned_receipted_idempotent_apply": adapter_good["verdict"] == "healthy",
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
        "scenario_decisions": {key: item["decision"] for key, item in scenarios.items()},
        "scenario_verdicts": {key: item["verdict"] for key, item in scenarios.items()},
        "replay": replay,
        "runtime_adapter_verdicts": {
            "bad": adapter_bad["verdict"],
            "good": adapter_good["verdict"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify autonomy continuation engine.")
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
