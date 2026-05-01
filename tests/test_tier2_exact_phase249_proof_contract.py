from __future__ import annotations

from scripts.audit_tier2_unbreakable_operation import evaluate_unbreakable_operation
from scripts.build_phase249_literal_universal_proof import build_literal_universal_proof
from scripts.build_phase249_exact_proof_contract import (
    EXACT_DONE_GATE_CLAIM,
    build_exact_proof_contract,
)


def test_exact_proof_contract_passes_with_total_literal_universal_proof() -> None:
    contract = build_exact_proof_contract()

    assert contract["status"] == "pass"
    assert contract["failed_obligations"] == []
    proof = contract["proof_equivalence"]
    assert proof["claim"] == EXACT_DONE_GATE_CLAIM
    assert proof["proof_contract_schema"] == "brainstack.phase249_exact_gate_proof.v1"
    assert proof["proof_contract_result"] == "pass"
    assert proof["machine_proof_same_as_claim"] is True
    assert proof["partial_or_scope_limited"] is False


def test_exact_proof_contract_rejects_operation_class_proof_without_literal_universal_proof() -> None:
    contract = build_exact_proof_contract(
        literal_universal_proof={
            "schema": "brainstack.phase249.literal_universal_proof.v1",
            "status": "fail",
            "claim": EXACT_DONE_GATE_CLAIM,
        }
    )

    assert contract["status"] == "fail"
    assert "literal_universal_claim_proven" in contract["failed_obligations"]
    assert "exact_contract_available" in contract["failed_obligations"]
    assert "structural_evidence_is_exact_not_partial" not in contract["failed_obligations"]
    assert "operation_class_coverage_exact" not in contract["failed_obligations"]
    assert "sota_gate_exact" not in contract["failed_obligations"]
    evidence = contract["operation_class_evidence"]
    assert "budget_pressure" in evidence["passed_classes"]
    assert "conflicts" in evidence["passed_classes"]
    assert "release_note_truthfulness" in evidence["passed_classes"]
    assert "source_runtime_parity" in evidence["passed_classes"]
    assert "provider_runtime_failures" in evidence["passed_classes"]
    assert "error_modes" in evidence["passed_classes"]
    assert "arbitrary_combinations" in evidence["passed_classes"]
    assert evidence["missing_classes"] == []
    proof = contract["proof_equivalence"]
    assert proof["claim"] == EXACT_DONE_GATE_CLAIM
    assert proof["proof_contract_schema"] == "brainstack.phase249_exact_gate_proof.v1"
    assert proof["proof_contract_result"] == "fail"
    assert proof["machine_proof_same_as_claim"] is False
    assert proof["partial_or_scope_limited"] is True


def test_literal_universal_proof_covers_total_decision_machine() -> None:
    proof = build_literal_universal_proof()

    assert proof["status"] == "pass"
    assert proof["claim"] == EXACT_DONE_GATE_CLAIM
    assert proof["covers_unbounded_real_world_use"] is True
    assert proof["not_reduced_to_operation_classes"] is True
    assert proof["not_scenario_count"] is True
    assert proof["not_scope_limited"] is True
    assert proof["abstract_case_count"] == 16896
    assert proof["failure_count"] == 0
    assert proof["arbitrary_json_failure_count"] == 0
    assert proof["static_purity_issue_count"] == 0


def test_exact_proof_contract_rejects_incomplete_structural_evidence() -> None:
    contract = build_exact_proof_contract(
        structural={
            "status": "pass",
            "issue_count": 0,
            "issues": [],
            "covered_structural_families": ["profile"],
            "proof_equivalence": {
                "status": "partial",
                "machine_proof_same_as_claim": False,
                "structural_reachability_only": True,
                "partial_or_scope_limited": True,
            },
        }
    )

    assert contract["status"] == "fail"
    assert "structural_evidence_is_exact_not_partial" in contract["failed_obligations"]
    proof = contract["proof_equivalence"]
    assert proof["machine_proof_same_as_claim"] is False
    assert proof["partial_or_scope_limited"] is True


def test_unbreakable_operation_rejects_operation_class_proof_as_exact_universal_proof() -> None:
    contract = build_exact_proof_contract(
        literal_universal_proof={
            "schema": "brainstack.phase249.literal_universal_proof.v1",
            "status": "fail",
            "claim": EXACT_DONE_GATE_CLAIM,
        }
    )
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
