#!/usr/bin/env python3
"""Prove Phase 249 operation-class guard composition.

This is not a scenario-count substitute for the exact Phase 249 claim. It is a
small deterministic model that checks every combination of the operation classes
named by the Phase 249 gate and verifies that their guards compose without
creating a forbidden success path.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "brainstack.phase249.operation_combination_proof.v1"

BASE_OPERATION_CLASSES = (
    "budget_pressure",
    "conflicts",
    "contamination",
    "error_modes",
    "inputs",
    "isolation",
    "provider_runtime_failures",
    "release_note_truthfulness",
    "replay_idempotency",
    "source_runtime_parity",
    "state_transitions",
)

CLASS_GUARDS: dict[str, set[str]] = {
    "budget_pressure": {
        "authority_critical_preserved",
        "support_noise_never_answer_truth",
    },
    "conflicts": {
        "unresolved_conflict_not_answer_truth",
        "no_newer_wins_conflict_resolution",
    },
    "contamination": {
        "assistant_claim_never_user_truth",
        "support_only_never_durable_truth",
    },
    "error_modes": {
        "no_hidden_success_on_error",
        "no_fail_closed_as_product_solution",
    },
    "inputs": {
        "verified_source_span_required_for_durable_truth",
        "source_speaker_required",
    },
    "isolation": {
        "principal_scope_match_required",
        "workspace_scope_match_required",
    },
    "provider_runtime_failures": {
        "no_random_provider_fallback",
        "provider_unavailable_not_success",
    },
    "release_note_truthfulness": {
        "release_claim_not_stronger_than_proof",
        "no_release_note_softening",
    },
    "replay_idempotency": {
        "same_input_same_decision",
        "no_duplicate_strength_inflation",
    },
    "source_runtime_parity": {
        "source_of_truth_reproduces_runtime",
        "no_mirror_only_fix",
    },
    "state_transitions": {
        "state_transition_requires_lifecycle_plan",
        "no_direct_state_write_without_gate",
    },
}

FORBIDDEN_STATE_RULES: tuple[dict[str, Any], ...] = (
    {
        "code": "unverified_durable_truth",
        "requires_all": {"inputs", "contamination"},
        "guards": {"verified_source_span_required_for_durable_truth", "assistant_claim_never_user_truth"},
    },
    {
        "code": "support_only_answer_truth",
        "requires_all": {"budget_pressure", "contamination"},
        "guards": {"support_only_never_durable_truth", "support_noise_never_answer_truth"},
    },
    {
        "code": "conflict_answer_authority",
        "requires_all": {"conflicts"},
        "guards": {"unresolved_conflict_not_answer_truth"},
    },
    {
        "code": "newer_wins_conflict_resolution",
        "requires_all": {"conflicts", "state_transitions"},
        "guards": {"no_newer_wins_conflict_resolution", "state_transition_requires_lifecycle_plan"},
    },
    {
        "code": "provider_failure_hidden_success",
        "requires_all": {"provider_runtime_failures", "error_modes"},
        "guards": {"provider_unavailable_not_success", "no_hidden_success_on_error"},
    },
    {
        "code": "provider_failure_random_fallback",
        "requires_all": {"provider_runtime_failures"},
        "guards": {"no_random_provider_fallback"},
    },
    {
        "code": "scope_leak_under_contamination",
        "requires_all": {"isolation", "contamination"},
        "guards": {"principal_scope_match_required", "assistant_claim_never_user_truth"},
    },
    {
        "code": "budget_pressure_drops_authority",
        "requires_all": {"budget_pressure", "inputs"},
        "guards": {"authority_critical_preserved", "verified_source_span_required_for_durable_truth"},
    },
    {
        "code": "replay_state_duplicate_inflation",
        "requires_all": {"replay_idempotency", "state_transitions"},
        "guards": {"same_input_same_decision", "no_duplicate_strength_inflation"},
    },
    {
        "code": "release_claim_masks_parity_gap",
        "requires_all": {"release_note_truthfulness", "source_runtime_parity"},
        "guards": {"release_claim_not_stronger_than_proof", "source_of_truth_reproduces_runtime"},
    },
    {
        "code": "release_claim_masks_runtime_failure",
        "requires_all": {"release_note_truthfulness", "provider_runtime_failures"},
        "guards": {"release_claim_not_stronger_than_proof", "provider_unavailable_not_success"},
    },
    {
        "code": "fail_closed_abused_as_product_solution",
        "requires_all": {"error_modes", "release_note_truthfulness"},
        "guards": {"no_fail_closed_as_product_solution", "no_release_note_softening"},
    },
    {
        "code": "mirror_only_release_success",
        "requires_all": {"source_runtime_parity", "state_transitions"},
        "guards": {"no_mirror_only_fix", "no_direct_state_write_without_gate"},
    },
)


def _power_set(items: tuple[str, ...]) -> list[tuple[str, ...]]:
    result: list[tuple[str, ...]] = []
    for size in range(len(items) + 1):
        result.extend(itertools.combinations(items, size))
    return result


def _rule_applies(rule: Mapping[str, Any], active: set[str]) -> bool:
    requires_all = set(rule.get("requires_all") or ())
    requires_any = set(rule.get("requires_any") or ())
    if requires_all and not requires_all.issubset(active):
        return False
    if requires_any and not (requires_any & active):
        return False
    return True


def run_proof(
    *,
    class_guards: Mapping[str, set[str]] | None = None,
    rules: tuple[dict[str, Any], ...] = FORBIDDEN_STATE_RULES,
) -> dict[str, Any]:
    guard_map = {key: set(value) for key, value in (class_guards or CLASS_GUARDS).items()}
    combinations = _power_set(BASE_OPERATION_CLASSES)
    failures: list[dict[str, Any]] = []
    for combo in combinations:
        active = set(combo)
        guards: set[str] = set()
        for class_name in active:
            guards.update(guard_map.get(class_name, set()))
        for rule in rules:
            if not _rule_applies(rule, active):
                continue
            missing = sorted(set(rule.get("guards") or ()) - guards)
            if missing:
                failures.append(
                    {
                        "code": str(rule.get("code") or "unknown_forbidden_state"),
                        "active_classes": sorted(active),
                        "missing_guards": missing,
                    }
                )

    status = "pass" if not failures else "fail"
    return {
        "schema": SCHEMA,
        "status": status,
        "base_operation_classes": list(BASE_OPERATION_CLASSES),
        "operation_classes_covered": sorted([*BASE_OPERATION_CLASSES, "arbitrary_combinations"]),
        "combination_count": len(combinations),
        "forbidden_state_rule_count": len(rules),
        "forbidden_state_failures": failures,
        "claim_boundary": (
            "This proves deterministic composition of Phase 249 operation-class guards. "
            "It is necessary evidence for arbitrary-combinations coverage, not a standalone exact universal proof."
        ),
        "proof_nature": "operation_class_cross_product",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = run_proof()
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
