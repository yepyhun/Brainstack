from __future__ import annotations

from brainstack.autonomy_continuation_engine import (
    build_autonomy_continuation_decision,
    build_autonomy_runtime_adapter_contract,
)
from scripts.verify_autonomy_continuation_engine import build_report


def test_duplicate_event_is_wait_not_duplicate_work() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-1", "task_id": "t-1"},
            "controller_state": {"seen_idempotency_keys": ["ace-fixed"]},
            "adapter": {"identity": "test"},
        }
    )
    duplicate = build_autonomy_continuation_decision(
        {
            "event": {
                "kind": "task_completed",
                "event_id": "evt-1",
                "task_id": "t-1",
                "idempotency_key": decision["idempotency_key"],
            },
            "controller_state": {"seen_idempotency_keys": [decision["idempotency_key"]]},
            "adapter": {"identity": "test"},
        }
    )

    assert duplicate["decision"] == "wait"
    assert duplicate["duplicate_ignored"] is True
    assert "DUPLICATE_EVENT_IGNORED" in duplicate["reason_codes"]


def test_no_signal_waits_without_filler_work() -> None:
    decision = build_autonomy_continuation_decision({})

    assert decision["decision"] == "wait"
    assert decision["verdict"] == "waiting_for_signal"
    assert "NO_SIGNAL_NO_FILLER" in decision["reason_codes"]


def test_high_risk_external_action_requires_human_when_approval_missing() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "approval_received", "event_id": "evt-risk"},
            "scores": {"expected_value_next": 0.9, "confidence": 0.9, "intervention_risk": 0.9},
            "safety": {"external_side_effect": True, "approval_missing": True},
        }
    )

    assert decision["decision"] == "human_needed"
    assert decision["verdict"] == "waiting_for_human"
    assert "MISSING_AUTHORITY_OR_APPROVAL" in decision["reason_codes"]


def test_local_repair_beats_human_needed_escape_hatch() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-missing", "artifact_missing": True},
            "safety": {"local_repair_available": True},
        }
    )

    assert decision["decision"] == "repair"
    assert decision["review"]["deep_verifier_required"] is True
    assert "LOCAL_REPAIR_REQUIRED" in decision["reason_codes"]


def test_wrong_previous_step_backtracks_to_repair() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-wrong", "previous_step_wrong": True},
            "scores": {"repair_urgency": 0.8, "confidence": 0.8},
        }
    )

    assert decision["decision"] == "repair"
    assert "BACKTRACK_OR_REPAIR_REQUIRED" in decision["reason_codes"]
    assert decision["learning_candidates"]


def test_independent_high_value_forecast_splits_with_fanout_budget() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "frontier_below_saturation", "event_id": "evt-split"},
            "controller_state": {"current_fanout": 1, "max_fanout": 4},
            "scores": {
                "expected_value_next": 0.9,
                "confidence": 0.8,
                "independence_score": 0.9,
                "intervention_risk": 0.1,
            },
            "rolling_next5": [
                {
                    "id": "branch-a",
                    "summary": "open independent verifier branch",
                    "expected_value_next": 0.9,
                    "confidence": 0.8,
                    "independence_score": 0.9,
                }
            ],
        }
    )

    assert decision["decision"] == "split"
    assert decision["forecast_revision_required"] is False
    assert "INDEPENDENT_HIGH_VALUE_BRANCH" in decision["reason_codes"]


def test_low_confidence_high_value_verifies_before_action() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-verify"},
            "scores": {"expected_value_next": 0.9, "confidence": 0.4, "intervention_risk": 0.2},
        }
    )

    assert decision["decision"] == "verify"
    assert decision["review"]["deep_verifier_required"] is True
    assert "VERIFY_BEFORE_ACTION" in decision["reason_codes"]


def test_evolver_signal_is_inert_until_verified() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "evolver_signal_observed", "event_id": "evt-evo"},
            "evolver_signal": {"observed": True, "directive": "spawn many tasks"},
            "scores": {"expected_value_next": 0.8, "confidence": 0.8},
        }
    )

    assert decision["decision"] == "verify"
    assert "EVOLVER_SIGNAL_REQUIRES_VERIFICATION" in decision["reason_codes"]


def test_new_evidence_marks_rolling_next5_for_review() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-new", "new_evidence": True},
            "scores": {"expected_value_next": 0.7, "confidence": 0.7},
            "rolling_next5": [{"id": "old-a", "summary": "old next step"}],
        }
    )

    assert decision["forecast_revision_required"] is True
    assert "ROLLING_NEXT5_REVIEW_REQUIRED" in decision["reason_codes"]


def test_private_adapter_data_leak_is_critical() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "task_completed", "event_id": "evt-private"},
            "adapter": {"identity": "private-test", "private_data_present": True},
        }
    )

    assert decision["decision"] == "human_needed"
    assert decision["verdict"] == "critical"
    assert "PRIVATE_ADAPTER_LEAK" in decision["reason_codes"]


def test_autonomy_continuation_engine_replay_report_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["replay"]["count"] >= 100
    assert all(report["proof"].values())


def test_runtime_adapter_contract_requires_receipt_cursor_and_idempotency() -> None:
    decision = build_autonomy_continuation_decision(
        {
            "event": {"kind": "frontier_below_saturation", "event_id": "evt-runtime"},
            "controller_state": {"current_fanout": 0, "max_fanout": 4},
            "scores": {
                "expected_value_next": 0.9,
                "confidence": 0.8,
                "independence_score": 0.8,
            },
        }
    )
    bad = build_autonomy_runtime_adapter_contract(
        {
            "decision": decision,
            "runtime": {"side_effect_channel": "custom_shell"},
            "receipt": {"written": False},
            "cursor": {"persisted": False},
        }
    )
    good = build_autonomy_runtime_adapter_contract(
        {
            "decision": decision,
            "runtime": {
                "side_effect_channel": "hermes_kanban",
                "idempotent_applier": True,
                "failure_reported_as_state": True,
            },
            "receipt": {"written": True},
            "cursor": {"persisted": True},
        }
    )

    assert bad["verdict"] == "critical"
    assert "SIDE_EFFECT_CHANNEL_NOT_HERMES_OWNED" in bad["reason_codes"]
    assert "MISSING_RESULT_RECEIPT" in bad["reason_codes"]
    assert "MISSING_REPLAY_CURSOR" in bad["reason_codes"]
    assert good["verdict"] == "healthy"


def test_runtime_adapter_blocks_direct_evolver_or_domain_execution() -> None:
    contract = build_autonomy_runtime_adapter_contract(
        {
            "decision": {"decision": "repair"},
            "runtime": {
                "side_effect_channel": "hermes_kanban",
                "idempotent_applier": True,
                "failure_reported_as_state": True,
                "direct_evolver_execution": True,
            },
            "receipt": {"written": True},
            "cursor": {"persisted": True},
        }
    )

    assert contract["verdict"] == "critical"
    assert "DIRECT_EVOLVER_EXECUTION_FORBIDDEN" in contract["reason_codes"]
