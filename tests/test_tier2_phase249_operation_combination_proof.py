from __future__ import annotations

from scripts.run_phase249_operation_combination_proof import (
    BASE_OPERATION_CLASSES,
    CLASS_GUARDS,
    run_proof,
)


def test_phase249_operation_combination_proof_passes_all_class_combinations() -> None:
    result = run_proof()

    assert result["status"] == "pass"
    assert result["combination_count"] == 2 ** len(BASE_OPERATION_CLASSES)
    assert result["forbidden_state_failures"] == []
    assert "arbitrary_combinations" in result["operation_classes_covered"]
    assert result["proof_nature"] == "operation_class_cross_product"
    assert "not a standalone exact universal proof" in result["claim_boundary"]


def test_phase249_operation_combination_proof_catches_missing_guard() -> None:
    guards = {key: set(value) for key, value in CLASS_GUARDS.items()}
    guards["contamination"].discard("assistant_claim_never_user_truth")

    result = run_proof(class_guards=guards)

    assert result["status"] == "fail"
    codes = {item["code"] for item in result["forbidden_state_failures"]}
    assert "unverified_durable_truth" in codes
    assert "scope_leak_under_contamination" in codes
