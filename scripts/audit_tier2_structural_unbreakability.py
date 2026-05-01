#!/usr/bin/env python3
"""Structural proof for Tier2 runtime-enforcement write boundaries."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

RECONCILER_WRITES = {
    "write_profile",
    "write_graph_state",
    "write_graph_relation",
    "add_continuity_event",
}
OPERATING_WRITE = "_upsert_brainstack_operating_record"
DECISION_GATE = "evaluate_tier2_decision_core_gate"
CONTINUITY_GATE_HELPER = "_continuity_core_block"
OPEN_DECISION_GUARD = "should_promote_open_decision"
FORBIDDEN_DECISION_CORE_IMPORTS = {
    "BrainstackStore",
    "ProjectionWriter",
    "DurableTruthPort",
    "MemoryProvider",
    "requests",
    "subprocess",
}
FORBIDDEN_DECISION_CORE_CALLS = {
    "write_profile",
    "write_graph_state",
    "write_graph_relation",
    "write_operating",
    "write_task",
    "add_continuity_event",
    "upsert_operating_record",
    "record_admission_receipt",
    "record_canonical_memory_event",
    "extract_tier2_candidates",
    "recall_memories",
    "search",
    "assemble",
}
REQUIRED_RECONCILER_FUNCTIONS = {
    "_reconcile_profile_items",
    "_reconcile_style_contract",
    "_reconcile_states",
    "_reconcile_relations",
    "_reconcile_inferred_relations",
    "_reconcile_typed_entities",
    "_reconcile_continuity",
}


@dataclass(frozen=True)
class CallEvent:
    function: str
    name: str
    lineno: int


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _function_calls(source: str) -> dict[str, list[CallEvent]]:
    tree = ast.parse(source)
    result: dict[str, list[CallEvent]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        events: list[CallEvent] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                name = _call_name(child)
                if name:
                    events.append(CallEvent(function=node.name, name=name, lineno=child.lineno))
        result[node.name] = sorted(events, key=lambda item: item.lineno)
    return result


def _ungated_write_issues(
    *,
    source: str,
    file_path: str,
    write_names: set[str],
    guard_names: set[str],
    function_names: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    calls_by_function = _function_calls(source)
    selected_names = set(function_names or calls_by_function)
    for function_name in sorted(selected_names):
        events = calls_by_function.get(function_name, [])
        write_events = [event for event in events if event.name in write_names]
        if not write_events:
            if function_names is not None:
                issues.append(
                    {
                        "code": "expected_function_write_not_found",
                        "file": file_path,
                        "function": function_name,
                    }
                )
            continue
        for write_event in write_events:
            has_prior_guard = any(
                event.name in guard_names and event.lineno < write_event.lineno for event in events
            )
            if not has_prior_guard:
                issues.append(
                    {
                        "code": "durable_write_without_prior_gate",
                        "file": file_path,
                        "function": function_name,
                        "write_call": write_event.name,
                        "line": write_event.lineno,
                        "required_guard": sorted(guard_names),
                    }
                )
    return issues


def _decision_core_purity_issues(source: str, *, file_path: str) -> list[dict[str, Any]]:
    tree = ast.parse(source)
    issues: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".", 1)[0] for alias in node.names]
            else:
                names = [node.module or "", *[alias.name for alias in node.names]]
            for name in names:
                if name in FORBIDDEN_DECISION_CORE_IMPORTS:
                    issues.append(
                        {
                            "code": "decision_core_forbidden_import",
                            "file": file_path,
                            "name": name,
                            "line": node.lineno,
                        }
                    )
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name in FORBIDDEN_DECISION_CORE_CALLS:
                issues.append(
                    {
                        "code": "decision_core_forbidden_call",
                        "file": file_path,
                        "name": name,
                        "line": node.lineno,
                    }
                )
    return issues


def _gate_allowlist_issues(source: str, *, file_path: str) -> list[dict[str, Any]]:
    required = {
        "profile": {"durable_fact_candidate", "lifecycle_update_candidate"},
        "style_contract": {"durable_fact_candidate", "lifecycle_update_candidate"},
        "state": {"relation_candidate", "lifecycle_update_candidate"},
        "relation": {"relation_candidate", "lifecycle_update_candidate"},
        "continuity": {"support_event"},
    }
    missing = []
    for kind, classes in required.items():
        if f'"{kind}"' not in source:
            missing.append(kind)
            continue
        for decision_class in classes:
            if f'"{decision_class}"' not in source:
                missing.append(f"{kind}:{decision_class}")
    if missing:
        return [{"code": "runtime_gate_allowlist_missing", "file": file_path, "missing": sorted(missing)}]
    return []


def run_structural_audit(*, root: Path = ROOT, claim: str = "") -> dict[str, Any]:
    reconciler_path = root / "brainstack/reconciler.py"
    explicit_capture_path = root / "brainstack/provider/explicit_capture.py"
    decision_core_path = root / "brainstack/tier2_decision_core.py"
    runtime_gate_path = root / "brainstack/tier2_decision_runtime_gate.py"

    issues: list[dict[str, Any]] = []
    issues.extend(
        _ungated_write_issues(
            source=reconciler_path.read_text(encoding="utf-8"),
            file_path=str(reconciler_path.relative_to(root)),
            write_names=RECONCILER_WRITES,
            guard_names={DECISION_GATE, CONTINUITY_GATE_HELPER},
            function_names=REQUIRED_RECONCILER_FUNCTIONS,
        )
    )
    explicit_capture_source = explicit_capture_path.read_text(encoding="utf-8")
    issues.extend(
        _ungated_write_issues(
            source=explicit_capture_source,
            file_path=str(explicit_capture_path.relative_to(root)),
            write_names={OPERATING_WRITE},
            guard_names={DECISION_GATE},
            function_names={"_promote_recent_work_summary"},
        )
    )
    issues.extend(
        _ungated_write_issues(
            source=explicit_capture_source,
            file_path=str(explicit_capture_path.relative_to(root)),
            write_names={OPERATING_WRITE},
            guard_names={OPEN_DECISION_GUARD},
            function_names={"_promote_open_decisions"},
        )
    )
    issues.extend(
        _decision_core_purity_issues(
            decision_core_path.read_text(encoding="utf-8"),
            file_path=str(decision_core_path.relative_to(root)),
        )
    )
    issues.extend(
        _gate_allowlist_issues(
            runtime_gate_path.read_text(encoding="utf-8"),
            file_path=str(runtime_gate_path.relative_to(root)),
        )
    )

    status = "pass" if not issues else "fail"
    proof_equivalence_status = "partial" if status == "pass" else "fail"
    return {
        "schema": "brainstack.tier2_structural_unbreakability_proof.v1",
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
        "covered_structural_families": [
            "profile",
            "style_contract",
            "state",
            "relation",
            "inferred_relation",
            "typed_entity",
            "continuity_support",
            "recent_work_support",
            "open_decision_operating_guard",
            "decision_core_purity",
        ],
        "proof_equivalence": {
            "status": proof_equivalence_status,
            "claim": claim,
            "machine_proof_same_as_claim": False,
            "finite_gauntlet_used_as_universal_proof": False,
            "release_allowed_used_as_phase_success": False,
            "proof_source": "structural_source_reachability_proof",
            "proof_scope": "tier2_durable_write_structural_reachability",
            "structural_reachability_only": True,
            "partial_or_scope_limited": True,
            "reason": (
                "Structural source-reachability proof is necessary Tier2 write-path evidence, "
                "but it is not equivalent to the exact Phase 249 universal operation gate."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--claim", default="")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = run_structural_audit(root=args.root, claim=args.claim)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
