#!/usr/bin/env python3
"""Report refactor quality gates for Brainstack.

This is a phase gate, not a formatter. It detects architecture regressions that
file-size-only refactors miss: replacement godlets, import cycles, broad
exceptions, and public surface drift.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "brainstack"

MAX_FILE_BYTES = 80_000
WARN_FUNCTION_LINES = 120
HARD_FUNCTION_LINES = 300
WARN_CLASS_LINES = 600
HARD_CLASS_LINES = 900
WARN_COMPLEXITY = 20
HARD_COMPLEXITY = 45

GENERIC_GODLET_NAMES = {
    "common",
    "helper",
    "helpers",
    "manager",
    "misc",
    "service",
    "services",
    "util",
    "utils",
}

ALLOWED_GENERIC_MODULES: set[str] = set()

PROTECTED_IMPORTS = {
    "brainstack.BrainstackMemoryProvider",
    "brainstack.db.BrainstackStore",
    "brainstack.executive_retrieval.retrieve_executive_context",
    "brainstack.diagnostics.build_query_inspect",
    "brainstack.diagnostics.build_memory_kernel_doctor",
    "brainstack.answerability.build_memory_answerability",
    "brainstack.authority_policy.classify_evidence_authority",
    "brainstack.authority_policy.is_current_assignment_authority",
}


def _iter_python_files() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT))


def _node_lines(node: ast.AST) -> int:
    end = getattr(node, "end_lineno", getattr(node, "lineno", 0))
    start = getattr(node, "lineno", end)
    return max(int(end) - int(start) + 1, 0)


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(len(child.values) - 1, 0)
        elif isinstance(child, ast.Match):
            score += max(len(child.cases), 1)
        elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            score += sum(1 for _ in child.generators)
    return score


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _import_edges(files: list[Path]) -> dict[str, set[str]]:
    modules = {_module_name(path): path for path in files}
    package_modules = set(modules)
    edges: dict[str, set[str]] = {module: set() for module in package_modules}
    for module, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            target: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("brainstack"):
                        target = alias.name
                        if target in package_modules:
                            edges[module].add(target)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if node.level:
                        base_parts = module.split(".")[:-node.level]
                        target = ".".join([*base_parts, node.module])
                    else:
                        target = node.module
                    if target.startswith("brainstack"):
                        while target and target not in package_modules:
                            target = ".".join(target.split(".")[:-1])
                        if target in package_modules and target != module:
                            edges[module].add(target)
        edges[module].discard(module)
    return edges


def _cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for succ in edges.get(node, ()):
            if succ not in indices:
                visit(succ)
                lowlinks[node] = min(lowlinks[node], lowlinks[succ])
            elif succ in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[succ])
        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1:
                cycles.append(sorted(component))

    for node in sorted(edges):
        if node not in indices:
            visit(node)
    return cycles


def _protected_surface_status() -> dict[str, bool]:
    status: dict[str, bool] = {}
    for import_path in sorted(PROTECTED_IMPORTS):
        module_name, _, attr = import_path.rpartition(".")
        module_rel = module_name.replace(".", "/") + ".py"
        module_init = module_name.replace(".", "/") + "/__init__.py"
        candidates = [REPO_ROOT / module_rel, REPO_ROOT / module_init]
        status[import_path] = any(path.exists() and attr in path.read_text(encoding="utf-8") for path in candidates)
    return status


def build_report() -> dict[str, Any]:
    files = _iter_python_files()
    file_sizes: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    broad_excepts: list[dict[str, Any]] = []
    generic_modules: list[str] = []
    reason_strings: Counter[str] = Counter()

    for path in files:
        text = path.read_text(encoding="utf-8")
        rel = _rel(path)
        size = path.stat().st_size
        file_sizes.append({"path": rel, "bytes": size, "hard_fail": size > MAX_FILE_BYTES})
        stem = path.stem.lower()
        if (stem in GENERIC_GODLET_NAMES or stem.endswith("_utils") or stem.endswith("_helpers")) and rel not in ALLOWED_GENERIC_MODULES:
            generic_modules.append(rel)
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                line_count = _node_lines(node)
                complexity = _complexity(node)
                functions.append(
                    {
                        "path": rel,
                        "name": node.name,
                        "line": node.lineno,
                        "lines": line_count,
                        "complexity": complexity,
                        "warn": line_count > WARN_FUNCTION_LINES or complexity > WARN_COMPLEXITY,
                        "hard_fail": line_count > HARD_FUNCTION_LINES or complexity > HARD_COMPLEXITY,
                    }
                )
            elif isinstance(node, ast.ClassDef):
                line_count = _node_lines(node)
                classes.append(
                    {
                        "path": rel,
                        "name": node.name,
                        "line": node.lineno,
                        "lines": line_count,
                        "warn": line_count > WARN_CLASS_LINES,
                        "hard_fail": line_count > HARD_CLASS_LINES,
                    }
                )
            elif isinstance(node, ast.ExceptHandler):
                if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                    broad_excepts.append(
                        {
                            "path": rel,
                            "line": node.lineno,
                            "type": "bare" if node.type is None else "Exception",
                        }
                    )
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.strip()
                if value.isupper() and "_" in value and 4 <= len(value) <= 80:
                    reason_strings[value] += 1

    edges = _import_edges(files)
    cycles = _cycles(edges)
    protected_surface = _protected_surface_status()
    hard_failures: dict[str, list[Any]] = {
        "file_size": [row for row in file_sizes if row["hard_fail"]],
        "function_budget": [row for row in functions if row["hard_fail"]],
        "class_budget": [row for row in classes if row["hard_fail"]],
        "generic_modules": generic_modules,
        "import_cycles": cycles,
        "protected_surface_missing": [key for key, present in protected_surface.items() if not present],
    }
    warnings: dict[str, list[Any]] = {
        "large_functions": [row for row in functions if row["warn"] and not row["hard_fail"]],
        "large_classes": [row for row in classes if row["warn"] and not row["hard_fail"]],
        "broad_excepts": broad_excepts,
        "duplicate_reason_like_strings": [
            {"value": key, "count": count}
            for key, count in sorted(reason_strings.items())
            if count >= 3
        ],
    }
    return {
        "schema": "brainstack.refactor_metrics.v1",
        "thresholds": {
            "max_file_bytes": MAX_FILE_BYTES,
            "warn_function_lines": WARN_FUNCTION_LINES,
            "hard_function_lines": HARD_FUNCTION_LINES,
            "warn_class_lines": WARN_CLASS_LINES,
            "hard_class_lines": HARD_CLASS_LINES,
            "warn_complexity": WARN_COMPLEXITY,
            "hard_complexity": HARD_COMPLEXITY,
        },
        "summary": {
            "files": len(files),
            "hard_failure_count": sum(len(value) for value in hard_failures.values()),
            "warning_count": sum(len(value) for value in warnings.values()),
            "status": "pass" if not any(hard_failures.values()) else "fail",
        },
        "hard_failures": hard_failures,
        "warnings": warnings,
        "top_functions_by_lines": sorted(functions, key=lambda row: row["lines"], reverse=True)[:30],
        "top_functions_by_complexity": sorted(functions, key=lambda row: row["complexity"], reverse=True)[:30],
        "top_classes_by_lines": sorted(classes, key=lambda row: row["lines"], reverse=True)[:20],
        "protected_surface": protected_surface,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Brainstack refactor quality metrics.")
    parser.add_argument("--output", type=Path, help="Write JSON report to path.")
    parser.add_argument("--summary", action="store_true", help="Print compact summary.")
    args = parser.parse_args()

    report = build_report()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.summary or not args.output:
        print(json.dumps(report["summary"], indent=2, sort_keys=True))
        if report["summary"]["status"] != "pass":
            print(json.dumps(report["hard_failures"], indent=2, sort_keys=True))
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
