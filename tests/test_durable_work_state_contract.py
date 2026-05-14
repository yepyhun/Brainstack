from __future__ import annotations

from brainstack.operating_loop import build_operating_loop_verdict
from hermes_continuation.work_state import build_durable_work_state_contract


def test_durable_work_state_healthy_requires_authority_evidence_durability_and_handoff() -> None:
    contract = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w1",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["artifact:1"],
                    "side_effect_durable": True,
                    "acknowledged": True,
                    "handoff": {"next_action": "verify artifact"},
                }
            ]
        }
    )

    assert contract["schema"] == "hermes_continuation.durable_work_state_contract.v1"
    assert contract["verdict"] == "healthy"
    assert contract["late_participant_continuable"] is True
    assert contract["read_only"] is True
    assert contract["side_effect_free"] is True


def test_ack_before_durable_side_effect_is_critical() -> None:
    contract = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w1",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["artifact:1"],
                    "side_effect_durable": False,
                    "acknowledged": True,
                    "handoff": {"next_action": "verify artifact"},
                }
            ]
        }
    )

    assert contract["verdict"] == "critical"
    assert "ACK_BEFORE_DURABLE_SIDE_EFFECT" in contract["reason_codes"]


def test_unknown_authority_is_critical() -> None:
    contract = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w1",
                    "status": "ready",
                    "authority": "unknown",
                    "evidence_refs": ["artifact:1"],
                }
            ]
        }
    )

    assert contract["verdict"] == "critical"
    assert "UNKNOWN_AUTHORITY" in contract["reason_codes"]


def test_blocked_without_repair_or_handoff_is_degraded() -> None:
    contract = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w1",
                    "status": "blocked",
                    "authority": "verified",
                    "evidence_refs": ["artifact:1"],
                }
            ]
        }
    )

    assert contract["verdict"] == "degraded"
    assert "BLOCKED_WITHOUT_REPAIR_PATH" in contract["reason_codes"]
    assert contract["repair_candidates"][0]["work_item_id"] == "w1"
    assert "auto_complete" in contract["repair_candidates"][0]["forbidden_actions"]


def test_intentional_stop_stays_distinct() -> None:
    contract = build_durable_work_state_contract({"state": "stopped_intentionally"})

    assert contract["verdict"] == "stopped_intentionally"
    assert "DURABLE_WORK_STOPPED_INTENTIONALLY" in contract["reason_codes"]


def test_operating_loop_consumes_durable_work_state_contract() -> None:
    critical_contract = build_durable_work_state_contract(
        {
            "work_items": [
                {
                    "id": "w1",
                    "status": "completed",
                    "authority": "verified",
                    "evidence_refs": ["artifact:1"],
                    "side_effect_durable": False,
                    "acknowledged": True,
                }
            ]
        }
    )
    verdict = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": {
                "dispatcher_state": "workers_running",
                "running_worker_count": 1,
            },
            "signal_bus": {"status": "ok"},
            "executor": {"status": "ok"},
            "durable_work_state": critical_contract,
        }
    )

    assert verdict["verdict"] == "critical"
    assert "durable_work_state_critical" in verdict["blockers"]
