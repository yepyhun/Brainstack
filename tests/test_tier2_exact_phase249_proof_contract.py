from __future__ import annotations

from scripts.audit_tier2_unbreakable_operation import evaluate_unbreakable_operation
from scripts.build_phase249_exact_proof_contract import (
    EXACT_DONE_GATE_CLAIM,
    build_exact_proof_contract,
)


def test_exact_proof_contract_fails_current_partial_structural_evidence() -> None:
    contract = build_exact_proof_contract()

    assert contract["status"] == "fail"
    assert "structural_evidence_is_exact_not_partial" in contract["failed_obligations"]
    assert "operation_class_coverage_exact" in contract["failed_obligations"]
    assert "sota_gate_exact" in contract["failed_obligations"]
    proof = contract["proof_equivalence"]
    assert proof["claim"] == EXACT_DONE_GATE_CLAIM
    assert proof["proof_contract_schema"] == "brainstack.phase249_exact_gate_proof.v1"
    assert proof["proof_contract_result"] == "fail"
    assert proof["machine_proof_same_as_claim"] is False
    assert proof["partial_or_scope_limited"] is True


def test_unbreakable_operation_rejects_exact_contract_until_all_obligations_pass() -> None:
    contract = build_exact_proof_contract()
    packet = {
        "status": "pass",
        "blockers": [],
        "critical_counters": {"canonical_event_count": 1},
        "proof_families": {
            "safety_critical_counters": True,
            "canonical_event_and_projection_readiness": True,
            "bloat_and_token_discipline": True,
            "event_replay_and_projection_rebuild": True,
            "scope_and_leak_resistance": True,
            "multi_hop_preservation": True,
            "hindsight_update_rehearsal": True,
        },
        "proof_equivalence": contract["proof_equivalence"],
    }

    result = evaluate_unbreakable_operation(packet)

    assert result["status"] == "fail"
    codes = {issue["code"] for issue in result["issues"]}
    assert "proof_equivalence_status_not_pass" in codes
    assert "machine_proof_not_equivalent_to_done_gate" in codes
    assert "exact_proof_contract_result_not_pass" in codes
