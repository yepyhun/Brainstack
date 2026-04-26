#!/usr/bin/env python3
"""Advisory architecture fitness checks for Brainstack refactors."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GENERIC_MODULE_NAMES = {
    "common.py",
    "helper.py",
    "helpers.py",
    "manager.py",
    "managers.py",
    "misc.py",
    "service.py",
    "services.py",
    "util.py",
    "utils.py",
}


@dataclass(frozen=True, slots=True)
class FitnessReport:
    root: str
    core_import_violations: list[str]
    generic_module_violations: list[str]
    advisory_contracts: list[str]

    @property
    def hard_failures(self) -> list[str]:
        return self.core_import_violations + self.generic_module_violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "hard_failures": self.hard_failures,
            "core_import_violations": self.core_import_violations,
            "generic_module_violations": self.generic_module_violations,
            "advisory_contracts": self.advisory_contracts,
            "status": "pass" if not self.hard_failures else "fail",
        }


def _python_files(root: Path) -> list[Path]:
    ignored_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".venv-quality",
        "__pycache__",
    }
    return sorted(
        path
        for path in root.rglob("*.py")
        if not any(part in ignored_parts for part in path.parts)
    )


def _imports_from_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                imports.append(node.module)
    return imports


def _core_import_violations(root: Path) -> list[str]:
    core_root = root / "brainstack" / "core"
    if not core_root.exists():
        return ["brainstack/core missing"]

    violations: list[str] = []
    for path in _python_files(core_root):
        for module in _imports_from_file(path):
            if module == "brainstack" or (
                module.startswith("brainstack.") and not module.startswith("brainstack.core")
            ):
                rel = path.relative_to(root)
                violations.append(f"{rel}: imports high-level module {module}")
    return violations


def _generic_module_violations(root: Path) -> list[str]:
    package_root = root / "brainstack"
    if not package_root.exists():
        return ["brainstack package missing"]
    return [
        str(path.relative_to(root))
        for path in _python_files(package_root)
        if path.name in GENERIC_MODULE_NAMES
    ]


def run_checks(root: Path) -> FitnessReport:
    root = root.resolve()
    return FitnessReport(
        root=str(root),
        core_import_violations=_core_import_violations(root),
        generic_module_violations=_generic_module_violations(root),
        advisory_contracts=[
            "storage imports core and DB infrastructure only",
            "retrieval imports core and storage read ports, not provider",
            "provider imports public facades and ports only",
            "diagnostics inspects behavior but does not own policy",
            "scripts and installer do not define runtime memory policy",
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args()

    report = run_checks(args.root)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"status: {report.to_dict()['status']}")
        print(f"hard_failures: {len(report.hard_failures)}")
        for failure in report.hard_failures:
            print(f"- {failure}")
    return 1 if report.hard_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
