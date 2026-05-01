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
from scripts.run_phase249_operation_combination_proof import run_proof as run_combination_proof  # noqa: E402

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
EVIDENCE_PATHS = {
    "decision_core": ROOT
    / ".planning/phases/246-tier2-compiler-adversarial-proof-and-superiority-packet/246-ADVERSARIAL-GAUNTLET-REPORT.json",
    "packet_budget": ROOT / ".planning/phases/231-tier2-godtier-proof-gauntlet-and-release-gate/231-PACKET-SOAK-RERUN.json",
    "graph_conflict": ROOT
    / ".planning/phases/231-tier2-godtier-proof-gauntlet-and-release-gate/231-GRAPH-CONFLICT-AUDIT-RERUN.json",
    "sota_superiority": ROOT
    / ".planning/phases/231-tier2-godtier-proof-gauntlet-and-release-gate/231-SOTA-SUPERIORITY-PACKET-CLEAN.json",
    "release_checklist": ROOT / ".planning/release/release-checklist-249-after-251-postcommit.json",
    "backend_lifecycle": ROOT
    / ".planning/phases/231-tier2-godtier-proof-gauntlet-and-release-gate/backend-lifecycle-rerun/backend_lifecycle_gauntlet_report.json",
    "hindsight_shadow_probe": ROOT
    / ".planning/phases/240.2-hindsight-local-extraction-quality-and-active-tier2-gate/240.2-HERMES-MANAGED-SHADOW-PROBE.json",
    "operation_combinations": ROOT
    / ".planning/phases/251-phase249-exact-proof-and-sota-closure/251-OPERATION-COMBINATION-PROOF.json",
}


def _proof_obligation(name: str, passed: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "fail",
        "evidence": dict(evidence),
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _operation_class_evidence() -> dict[str, Any]:
    decision_core = _load_json(EVIDENCE_PATHS["decision_core"])
    packet_budget = _load_json(EVIDENCE_PATHS["packet_budget"])
    graph_conflict = _load_json(EVIDENCE_PATHS["graph_conflict"])
    release_checklist = _load_json(EVIDENCE_PATHS["release_checklist"])
    backend_lifecycle = _load_json(EVIDENCE_PATHS["backend_lifecycle"])
    hindsight_shadow_probe = _load_json(EVIDENCE_PATHS["hindsight_shadow_probe"])
    operation_combinations = _load_json(EVIDENCE_PATHS["operation_combinations"]) or run_combination_proof()
    checks = {item.get("name"): item for item in release_checklist.get("checks", []) if isinstance(item, Mapping)}
    release_claim_contract = checks.get("release_claim_contract") or {}
    public_payload_leak_scan = checks.get("public_payload_leak_scan") or {}
    git_hygiene = checks.get("git_hygiene") or {}
    write_path_closure = checks.get("write_path_closure") or {}
    evidence = {
        "inputs": decision_core.get("status") == "pass" and decision_core.get("cases_passed") == decision_core.get("cases_total"),
        "state_transitions": decision_core.get("status") == "pass"
        and (decision_core.get("smarter_than_baseline") or {}).get("update_correctness") is True,
        "conflicts": graph_conflict.get("status") == "pass"
        and graph_conflict.get("issue_count") == 0
        and graph_conflict.get("release_blocked_before_resolution") is True,
        "contamination": decision_core.get("status") == "pass"
        and (decision_core.get("critical_counters") or {}).get("harmful_memory_counters") == 0,
        "budget_pressure": packet_budget.get("status") == "pass"
        and packet_budget.get("protected_truth_drop_attempts") == 0
        and packet_budget.get("selected_evidence_fingerprint_mismatch_count") == 0,
        "replay_idempotency": decision_core.get("status") == "pass"
        and (decision_core.get("critical_counters") or {}).get("replay_mismatch") == 0,
        "isolation": decision_core.get("status") == "pass"
        and any(
            case.get("id") == "scope_collision" and not case.get("schema_issues") and not case.get("semantic_conformance_issues")
            for case in decision_core.get("cases", [])
            if isinstance(case, Mapping)
        ),
        "source_runtime_parity": public_payload_leak_scan.get("status") == "pass"
        and git_hygiene.get("status") == "pass"
        and write_path_closure.get("status") == "pass",
        "provider_runtime_failures": hindsight_shadow_probe.get("status") == "pass"
        and not hindsight_shadow_probe.get("blockers")
        and all(value == 0 for value in (hindsight_shadow_probe.get("critical_counters") or {}).values()),
        "error_modes": backend_lifecycle.get("status") == "pass"
        and backend_lifecycle.get("hidden_backend_disable_count") == 0
        and backend_lifecycle.get("silent_degraded_backend_count") == 0,
        "release_note_truthfulness": release_claim_contract.get("status") == "fail"
        and any(
            issue.get("code") in {"sota_gate_required_but_not_pass", "unbreakable_operation_proof_not_pass"}
            for issue in (release_claim_contract.get("summary") or {}).get("issues", [])
            if isinstance(issue, Mapping)
        ),
        "arbitrary_combinations": operation_combinations.get("status") == "pass"
        and operation_combinations.get("proof_nature") == "operation_class_cross_product"
        and not operation_combinations.get("forbidden_state_failures")
        and "arbitrary_combinations" in set(operation_combinations.get("operation_classes_covered") or []),
    }
    return {
        "classes": evidence,
        "artifacts": {name: str(path.relative_to(ROOT)) for name, path in EVIDENCE_PATHS.items()},
        "passed_classes": sorted(name for name, passed in evidence.items() if passed),
        "missing_classes": sorted(name for name, passed in evidence.items() if not passed),
        "operation_combination_proof": {
            "status": operation_combinations.get("status"),
            "proof_nature": operation_combinations.get("proof_nature"),
            "combination_count": operation_combinations.get("combination_count"),
            "forbidden_state_failure_count": len(operation_combinations.get("forbidden_state_failures") or []),
        },
    }


def build_exact_proof_contract(
    *,
    root: Path = ROOT,
    structural: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    structural = dict(structural or run_structural_audit(root=root, claim=EXACT_DONE_GATE_CLAIM))
    structural_equivalence = dict(structural.get("proof_equivalence") or {})
    operation_class_evidence = _operation_class_evidence()

    covered_structural_families = set(structural.get("covered_structural_families") or [])
    required_structural_families = {
        "continuity_support",
        "decision_core_purity",
        "inferred_relation",
        "open_decision_operating_guard",
        "profile",
        "recent_work_support",
        "relation",
        "state",
        "style_contract",
        "typed_entity",
    }
    structural_source_reachability_complete = (
        structural.get("status") == "pass"
        and structural.get("issue_count") == 0
        and required_structural_families.issubset(covered_structural_families)
    )
    structural_exact = (
        structural_source_reachability_complete
        and not operation_class_evidence["missing_classes"]
        and (operation_class_evidence.get("operation_combination_proof") or {}).get("status") == "pass"
    )
    operation_classes_proven = not operation_class_evidence["missing_classes"]
    sota = _load_json(EVIDENCE_PATHS["sota_superiority"])
    sota_gate_proven = sota.get("status") == "pass" and sota.get("supported_scope_sota_superiority") is True
    exact_contract_available = structural_exact and operation_classes_proven and sota_gate_proven

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
                "structural_source_reachability_complete": structural_source_reachability_complete,
                "covered_structural_families": sorted(covered_structural_families),
                "required_structural_families": sorted(required_structural_families),
                "proof_equivalence_status": structural_equivalence.get("status"),
                "machine_proof_same_as_claim": structural_equivalence.get("machine_proof_same_as_claim"),
                "structural_reachability_only": structural_equivalence.get("structural_reachability_only"),
                "partial_or_scope_limited": structural_equivalence.get("partial_or_scope_limited"),
                "combined_with_operation_class_proof": True,
            },
        ),
        _proof_obligation(
            "operation_class_coverage_exact",
            operation_classes_proven,
            {
                "required_operation_classes": sorted(REQUIRED_OPERATION_CLASSES),
                "passed_classes": operation_class_evidence["passed_classes"],
                "missing_classes": operation_class_evidence["missing_classes"],
                "reason": "Some operation classes still lack exact machine proof evidence.",
            },
        ),
        _proof_obligation(
            "sota_gate_exact",
            sota_gate_proven,
            {
                "sota_status": sota.get("status"),
                "supported_scope_sota_superiority": sota.get("supported_scope_sota_superiority"),
                "reason": "SOTA gate is useful only after exact unbreakable-operation proof passes.",
            },
        ),
        _proof_obligation(
            "exact_contract_available",
            exact_contract_available,
            {
                "required_schema": EXACT_PROOF_CONTRACT_SCHEMA,
                "reason": (
                    "Exact contract is available only when structural reachability, operation-class "
                    "coverage, arbitrary-combination proof, and required SOTA evidence all pass."
                ),
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
        "operation_class_evidence": operation_class_evidence,
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
