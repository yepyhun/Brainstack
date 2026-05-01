#!/usr/bin/env python3
"""Build the Phase 249 exact proof contract.

This script is intentionally stricter than the structural Tier2 write-path audit.
It may include structural evidence, but it must not launder partial evidence into
the exact Phase 249 universal operation claim.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_tier2_structural_unbreakability import run_structural_audit  # noqa: E402

EXACT_DONE_GATE_CLAIM = (
    "MINDE HELYZHETBEN BÁRMILYEN ESETBEN AKÁRHOGY KOMIBNÁLVA BÁRMILYEN "
    "HASZNÁLAT KÖZBEN NEM TÖRHET EL SEMMILYEN ESETBEN SEM SOHA SEHHOGY!"
)
EXACT_PROOF_CONTRACT_SCHEMA = "brainstack.phase249_exact_gate_proof.v1"

REQUIRED_OPERATION_CLASSES = {
    "arbitrary_combinations",
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
}
REQUIRED_TRUE_FLAGS = {
    "arbitrary_combinations_proven",
    "exact_done_gate_claim_proven",
    "forbidden_states_structurally_impossible",
    "independent_proof_contract",
    "no_capability_shutdown",
    "no_dumbing_down",
    "no_fail_closed_as_solution",
    "no_feature_removal",
    "no_permanent_degraded_mode",
    "no_regression",
    "no_release_note_softening",
    "no_scope_shrink",
    "no_sota_claim_split",
    "universal_operation_space_proven",
}
REQUIRED_FALSE_FLAGS = {
    "known_failure_family_uncovered",
    "partial_or_scope_limited",
    "structural_reachability_only",
}


def _proof_obligation(name: str, passed: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "evidence": dict(evidence),
    }


def build_exact_proof_contract(
    *,
    root: Path = ROOT,
    structural: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structural = dict(structural or run_structural_audit(root=root, claim=EXACT_DONE_GATE_CLAIM))
    structural_equivalence = dict(structural.get("proof_equivalence") or {})

    structural_exact = (
        structural.get("status") == "pass"
        and structural_equivalence.get("status") == "pass"
        and structural_equivalence.get("machine_proof_same_as_claim") is True
        and structural_equivalence.get("structural_reachability_only") is not True
        and structural_equivalence.get("partial_or_scope_limited") is not True
    )
    exact_contract_available = False
    operation_classes_proven = False
    sota_gate_proven = False

    obligations = [
        _proof_obligation(
            "structural_evidence_present",
            structural.get("status") == "pass",
            {
                "structural_status": structural.get("status"),
                "issue_count": structural.get("issue_count"),
            },
        ),
        _proof_obligation(
            "structural_evidence_is_exact_not_partial",
            structural_exact,
            {
                "proof_equivalence_status": structural_equivalence.get("status"),
                "machine_proof_same_as_claim": structural_equivalence.get("machine_proof_same_as_claim"),
                "structural_reachability_only": structural_equivalence.get("structural_reachability_only"),
                "partial_or_scope_limited": structural_equivalence.get("partial_or_scope_limited"),
            },
        ),
        _proof_obligation(
            "operation_class_coverage_exact",
            operation_classes_proven,
            {
                "required_operation_classes": sorted(REQUIRED_OPERATION_CLASSES),
                "reason": "No exact operation-class proof artifact is available yet.",
            },
        ),
        _proof_obligation(
            "sota_gate_exact",
            sota_gate_proven,
            {
                "reason": "No separate required SOTA proof gate has been connected to Phase 249 closure yet.",
            },
        ),
        _proof_obligation(
            "exact_contract_available",
            exact_contract_available,
            {
                "required_schema": EXACT_PROOF_CONTRACT_SCHEMA,
                "reason": "Current evidence is partial and cannot generate a passing exact contract.",
            },
        ),
    ]
    failed = [item for item in obligations if item["status"] != "pass"]

    flags = {field: False for field in REQUIRED_TRUE_FLAGS}
    flags["independent_proof_contract"] = True
    forbidden_flags = {field: True for field in REQUIRED_FALSE_FLAGS}
    if not failed:
        flags = {field: True for field in REQUIRED_TRUE_FLAGS}
        forbidden_flags = {field: False for field in REQUIRED_FALSE_FLAGS}

    result = "pass" if not failed else "fail"
    proof_equivalence = {
        "status": result,
        "claim": EXACT_DONE_GATE_CLAIM,
        "machine_proof_same_as_claim": result == "pass",
        "finite_gauntlet_used_as_universal_proof": False,
        "release_allowed_used_as_phase_success": False,
        "proof_source": "phase249_exact_proof_contract",
        "proof_contract_schema": EXACT_PROOF_CONTRACT_SCHEMA,
        "proof_contract_scope": EXACT_DONE_GATE_CLAIM,
        "proof_contract_result": result,
        "independent_verifier": "build_phase249_exact_proof_contract",
        **flags,
        **forbidden_flags,
    }
    return {
        "schema": EXACT_PROOF_CONTRACT_SCHEMA,
        "status": result,
        "claim": EXACT_DONE_GATE_CLAIM,
        "operation_classes": sorted(REQUIRED_OPERATION_CLASSES),
        "proof_obligations": obligations,
        "failed_obligation_count": len(failed),
        "failed_obligations": [item["name"] for item in failed],
        "proof_equivalence": proof_equivalence,
        "structural_evidence": structural,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = build_exact_proof_contract(root=args.root)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
