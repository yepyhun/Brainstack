from __future__ import annotations

from scripts.audit_tier2_unbreakable_operation import (
    REQUIRED_PROOF_FAMILIES,
    evaluate_unbreakable_operation,
)


def _packet() -> dict[str, object]:
    return {
        "schema": "brainstack.tier2_sota_eligibility_packet.v1",
        "status": "pass",
        "blockers": [],
        "critical_counters": {
            "false_durable_write": 0,
            "assistant_authored_durable_truth": 0,
            "unverified_tier2_durable_write": 0,
            "bloat_durable_write": 0,
            "projection_rebuild_mismatch": 0,
            "raw_private_value_leak": 0,
            "canonical_event_count": 12,
        },
        "proof_families": {family: True for family in REQUIRED_PROOF_FAMILIES},
    }


def test_tier2_unbreakable_operation_passes_clean_packet() -> None:
    result = evaluate_unbreakable_operation(_packet())

    assert result["status"] == "pass"
    assert result["issue_count"] == 0


def test_tier2_unbreakable_operation_blocks_nonzero_critical_counter() -> None:
    packet = _packet()
    critical_counters = dict(packet["critical_counters"])  # type: ignore[arg-type]
    critical_counters["unverified_tier2_durable_write"] = 1
    packet["critical_counters"] = critical_counters

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    assert {
        "code": "tier2_critical_counters_nonzero",
        "counters": {"unverified_tier2_durable_write": 1},
    } in result["issues"]


def test_tier2_unbreakable_operation_blocks_failed_proof_family() -> None:
    packet = _packet()
    proof_families = dict(packet["proof_families"])  # type: ignore[arg-type]
    proof_families["bloat_and_token_discipline"] = False
    packet["proof_families"] = proof_families

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    assert {
        "code": "tier2_proof_families_failed",
        "failed": ["bloat_and_token_discipline"],
    } in result["issues"]


def test_tier2_unbreakable_operation_blocks_missing_canonical_events() -> None:
    packet = _packet()
    critical_counters = dict(packet["critical_counters"])  # type: ignore[arg-type]
    critical_counters["canonical_event_count"] = 0
    packet["critical_counters"] = critical_counters

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    assert {
        "code": "tier2_canonical_events_missing",
        "canonical_event_count": 0,
    } in result["issues"]
