from __future__ import annotations

from scripts.audit_tier2_unbreakable_operation import (
    EXACT_DONE_GATE_CLAIM,
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
        "proof_equivalence": {
            "status": "pass",
            "claim": EXACT_DONE_GATE_CLAIM,
            "machine_proof_same_as_claim": True,
            "finite_gauntlet_used_as_universal_proof": False,
            "release_allowed_used_as_phase_success": False,
            "proof_source": "exhaustive_structural_proof",
        },
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


def test_tier2_unbreakable_operation_blocks_missing_proof_equivalence() -> None:
    packet = _packet()
    del packet["proof_equivalence"]

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    codes = {issue["code"] for issue in result["issues"]}
    assert "proof_equivalence_missing" in codes


def test_tier2_unbreakable_operation_blocks_finite_gauntlet_as_universal_proof() -> None:
    packet = _packet()
    packet["proof_equivalence"] = {
        "status": "pass",
        "claim": EXACT_DONE_GATE_CLAIM,
        "machine_proof_same_as_claim": False,
        "finite_gauntlet_used_as_universal_proof": True,
        "release_allowed_used_as_phase_success": False,
        "proof_source": "gauntlet",
    }

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    codes = {issue["code"] for issue in result["issues"]}
    assert "machine_proof_not_equivalent_to_done_gate" in codes
    assert "finite_gauntlet_used_as_universal_proof" in codes
    assert "finite_proof_source_cannot_prove_universal_claim" in codes


def test_tier2_unbreakable_operation_blocks_release_allowed_as_success() -> None:
    packet = _packet()
    proof_equivalence = dict(packet["proof_equivalence"])  # type: ignore[arg-type]
    proof_equivalence["release_allowed_used_as_phase_success"] = True
    packet["proof_equivalence"] = proof_equivalence

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    assert {"code": "release_allowed_used_as_phase_success"} in result["issues"]
