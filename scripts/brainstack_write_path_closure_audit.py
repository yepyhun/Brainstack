#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


DURABLE_WRITE_METHODS = {
    "upsert_profile_item",
    "upsert_graph_state",
    "upsert_graph_relation",
    "upsert_graph_inferred_relation",
    "upsert_typed_entity",
    "upsert_operating_record",
    "upsert_task_item",
}


@dataclass(frozen=True)
class Callsite:
    file: str
    line: int
    method: str
    caller: str
    write_path_class: str
    hard_failure: bool
    reason: str


def _iter_python_files(root: Path, *, include_tests: bool) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        parts = set(path.parts)
        if {".git", ".venv", "__pycache__"} & parts:
            continue
        rel = path.relative_to(root)
        if not include_tests and rel.parts and rel.parts[0] == "tests":
            continue
        yield path


def _classify(file: str, method: str, caller: str) -> tuple[str, str]:
    if file.startswith("brainstack/storage/durable_truth_port.py"):
        return "DURABLE_TRUTH_PORT", "typed durable truth port"
    if file.startswith("brainstack/storage/projection_writer.py"):
        return "DERIVED_ADMISSION_GATE", "ProjectionWriter writes with AdmissionDecision permit"
    if file.startswith("brainstack/storage/schema_migrations.py"):
        return "MIGRATION_OR_BACKFILL", "schema migration/backfill"
    if file.startswith("brainstack/storage/profile_read_store.py"):
        return "REPAIR_OR_OPERATOR_APPROVED", "operator/repair cleanup path"
    if file.startswith("brainstack/provider/explicit_capture.py"):
        return "TRUSTED_EXPLICIT_CAPTURE", "explicit provider capture path"
    if file.startswith("brainstack/provider/tools.py"):
        if "workstream_recap" in caller:
            return "TRUSTED_HOST_RUNTIME_WRITE", "host tool recap support path"
        return "TRUSTED_EXPLICIT_CAPTURE", "explicit tool capture path"
    if file.startswith("brainstack/provider/ingest_lifecycle.py"):
        return "TRUSTED_EXPLICIT_CAPTURE", "Hermes memory write lifecycle path"
    if file.startswith("brainstack/provider/inspection.py"):
        return "TRUSTED_HOST_RUNTIME_WRITE", "runtime handoff inspection helper"
    if file.startswith("brainstack/graph.py"):
        return "TRUSTED_HOST_RUNTIME_WRITE", "graph evidence import with receipt"
    if file.startswith("brainstack/storage/"):
        return "STORAGE_INTERNAL_ONLY", "storage implementation detail"
    if file.startswith("scripts/brainstack_golden_recall_eval.py"):
        return "TEST_OR_CANARY_SEED", "golden recall fixture seed"
    if file.startswith("scripts/measure_packet_budget_shadow_rollout.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget shadow measurement fixture seed"
    if file.startswith("scripts/measure_packet_budget_live_shadow_telemetry.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget live-like shadow measurement fixture seed"
    if file.startswith("scripts/measure_packet_budget_active_rollout.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget active rollout measurement fixture seed"
    if file.startswith("scripts/verify_packet_budget_runtime_parity.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget runtime parity measurement fixture seed"
    if file.startswith("scripts/verify_packet_budget_active_default.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget active default verifier fixture seed"
    if file.startswith("scripts/verify_adaptive_evidence_hotpath.py"):
        return "TEST_OR_CANARY_SEED", "adaptive evidence hotpath verifier fixture seed"
    if file.startswith("scripts/verify_adaptive_evidence_kernel.py"):
        return "TEST_OR_CANARY_SEED", "adaptive evidence kernel verifier fixture seed"
    if file.startswith("scripts/verify_fts5_fast_path.py"):
        return "TEST_OR_CANARY_SEED", "FTS5 fast-path verifier fixture seed"
    if file.startswith("scripts/verify_trace_tiering.py"):
        return "TEST_OR_CANARY_SEED", "trace-tiering verifier fixture seed"
    if file.startswith("scripts/verify_persistent_bloat_policy.py"):
        return "TEST_OR_CANARY_SEED", "persistent-bloat policy verifier fixture seed"
    if file.startswith("scripts/verify_profile_scope_index.py"):
        return "TEST_OR_CANARY_SEED", "profile-scope index verifier fixture seed"
    if file.startswith("scripts/verify_behavior_card_delivery.py"):
        return "TEST_OR_CANARY_SEED", "behavior-card delivery verifier fixture seed"
    if file.startswith("scripts/run_packet_budget_soak.py"):
        return "TEST_OR_CANARY_SEED", "packet-budget soak measurement fixture seed"
    if file.startswith("scripts/run_persistent_bloat_soak.py"):
        return "TEST_OR_CANARY_SEED", "persistent-bloat soak measurement fixture seed"
    if file.startswith("scripts/run_active_preference_contract_gauntlet.py"):
        return "TEST_OR_CANARY_SEED", "active preference contract gauntlet fixture seed"
    if file.startswith("scripts/run_agent_facing_memory_behavior_gauntlet.py"):
        return "TEST_OR_CANARY_SEED", "agent-facing memory behavior gauntlet fixture seed"
    if file.startswith("scripts/run_local_workload_performance_replay.py"):
        return "TEST_OR_CANARY_SEED", "local workload performance replay fixture seed"
    if file.startswith("scripts/run_canonical_truth_admission_coverage.py"):
        return "TEST_OR_CANARY_SEED", "canonical truth admission coverage fixture seed"
    if file.startswith("scripts/run_graph_supersession_runtime_population.py"):
        return "TEST_OR_CANARY_SEED", "graph supersession runtime population fixture seed"
    if file.startswith("scripts/run_source_backed_actionable_queue_substrate.py"):
        return "TEST_OR_CANARY_SEED", "source-backed actionable queue substrate fixture seed"
    if file.startswith("scripts/run_style_source_hygiene_repair_proof.py"):
        return "TEST_OR_CANARY_SEED", "style source hygiene repair proof fixture seed"
    if file.startswith("scripts/run_backend_lifecycle_gauntlet.py"):
        return "TEST_OR_CANARY_SEED", "backend lifecycle gauntlet fixture seed"
    if file.startswith("scripts/audit_graph_conflict_lifecycle.py"):
        return "TEST_OR_CANARY_SEED", "graph conflict lifecycle audit fixture seed"
    if file.startswith("scripts/brainstack_replay_canary.py"):
        return "TEST_OR_CANARY_SEED", "replay canary fixture seed"
    if file.startswith("tests/"):
        return "TEST_OR_CANARY_SEED", "test fixture seed"
    return "UNCLASSIFIED_DURABLE_TRUTH_WRITE", "no write-path classification"


def _scan_file(root: Path, path: Path) -> list[Callsite]:
    rel = str(path.relative_to(root))
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        return [
            Callsite(
                file=rel,
                line=int(exc.lineno or 0),
                method="<syntax>",
                caller="",
                write_path_class="UNCLASSIFIED_DURABLE_TRUTH_WRITE",
                hard_failure=True,
                reason=f"syntax error: {exc.msg}",
            )
        ]

    calls: list[Callsite] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            method = ""
            if isinstance(node.func, ast.Attribute):
                method = node.func.attr
            elif isinstance(node.func, ast.Name):
                method = node.func.id
            if method in DURABLE_WRITE_METHODS:
                caller = ".".join(self.stack[-3:])
                write_path_class, reason = _classify(rel, method, caller)
                hard_failure = write_path_class == "UNCLASSIFIED_DURABLE_TRUTH_WRITE"
                calls.append(
                    Callsite(
                        file=rel,
                        line=int(node.lineno),
                        method=method,
                        caller=caller,
                        write_path_class=write_path_class,
                        hard_failure=hard_failure,
                        reason=reason,
                    )
                )
            self.generic_visit(node)

    Visitor().visit(tree)
    return calls


def run_audit(root: Path, *, include_tests: bool) -> dict[str, object]:
    callsites: list[Callsite] = []
    for path in _iter_python_files(root, include_tests=include_tests):
        callsites.extend(_scan_file(root, path))
    hard = [item for item in callsites if item.hard_failure]
    by_class: dict[str, int] = {}
    for item in callsites:
        by_class[item.write_path_class] = by_class.get(item.write_path_class, 0) + 1
    return {
        "schema": "brainstack.write_path_closure_audit.v1",
        "root": str(root),
        "include_tests": include_tests,
        "callsite_count": len(callsites),
        "hard_failure_count": len(hard),
        "by_class": dict(sorted(by_class.items())),
        "callsites": [asdict(item) for item in callsites],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit durable truth write callsites.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--include-tests", action="store_true", help="Include tests in callsite scan")
    parser.add_argument("--json-out", default="", help="Write JSON artifact")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    result = run_audit(root, include_tests=bool(args.include_tests))
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "callsite_count": result["callsite_count"],
                "hard_failure_count": result["hard_failure_count"],
                "by_class": result["by_class"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if int(result["hard_failure_count"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
