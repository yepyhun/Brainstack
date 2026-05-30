#!/usr/bin/env python3
"""Verify Brainstack's Hermes host tool-result budget seam.

This is a public-safe structural/destructive fixture: it patches a temporary
copy of Hermes' budget_config.py, then proves the installed default budget
would externalize observed context-heavy tool outputs instead of letting them
enter the protected model-facing tail.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


REPORT_SCHEMA = "brainstack.host_tool_result_budget.v1"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HERMES_SOURCE = REPO_ROOT.parent / "hermes-latest-source-current"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import install_into_hermes  # noqa: E402
INLINE_LIMIT = 32_000
SMALL_LIMIT = 12_000
OBSERVED_CONTEXT_HEAVY_TOOLS = (
    "brainstack_inspect",
    "brainstack_recall",
    "browser_navigate",
    "delegate_task",
    "execute_code",
    "kanban_list",
    "kanban_show",
    "process",
    "read_file",
    "search_files",
    "skill_view",
    "skills_list",
    "terminal",
)


def _minimal_budget_config() -> str:
    return '''
from dataclasses import dataclass, field
from typing import Dict

PINNED_THRESHOLDS: Dict[str, float] = {
    "read_file": float("inf"),
}

DEFAULT_RESULT_SIZE_CHARS: int = 100_000
DEFAULT_TURN_BUDGET_CHARS: int = 200_000
DEFAULT_PREVIEW_SIZE_CHARS: int = 1_500

@dataclass(frozen=True)
class BudgetConfig:
    default_result_size: int = DEFAULT_RESULT_SIZE_CHARS
    turn_budget: int = DEFAULT_TURN_BUDGET_CHARS
    preview_size: int = DEFAULT_PREVIEW_SIZE_CHARS
    tool_overrides: Dict[str, int] = field(default_factory=dict)

    def resolve_threshold(self, tool_name: str) -> int | float:
        if tool_name in PINNED_THRESHOLDS:
            return PINNED_THRESHOLDS[tool_name]
        if tool_name in self.tool_overrides:
            return self.tool_overrides[tool_name]
        return self.default_result_size

DEFAULT_BUDGET = BudgetConfig()
'''


def _exec_budget_config(text: str, path: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(compile(text, str(path), "exec"), namespace)
    return namespace


def _verify_thresholds(namespace: dict[str, Any]) -> tuple[dict[str, int | float], list[str]]:
    budget = namespace["DEFAULT_BUDGET"]
    thresholds: dict[str, int | float] = {
        tool: budget.resolve_threshold(tool)
        for tool in OBSERVED_CONTEXT_HEAVY_TOOLS
    }
    issues: list[str] = []
    for tool, value in thresholds.items():
        if isinstance(value, float) and math.isinf(value):
            issues.append(f"{tool} threshold is infinite")
        elif value > INLINE_LIMIT:
            issues.append(f"{tool} threshold {value} exceeds {INLINE_LIMIT}")
    if thresholds.get("brainstack_recall") != SMALL_LIMIT:
        issues.append("brainstack_recall should use the compact 12k budget")
    if thresholds.get("skills_list") != SMALL_LIMIT:
        issues.append("skills_list should use the compact 12k budget")
    if thresholds.get("browser_navigate") != SMALL_LIMIT:
        issues.append("browser_navigate should use the compact 12k budget")
    if thresholds.get("kanban_list") != SMALL_LIMIT:
        issues.append("kanban_list should use the compact 12k budget")
    if thresholds.get("kanban_show") != 16_000:
        issues.append("kanban_show should use the compact 16k budget")
    return thresholds, issues


def build_report(hermes_source: Path) -> dict[str, Any]:
    issues: list[str] = []
    hermes_source = hermes_source.expanduser().resolve()
    source_budget = hermes_source / "tools" / "budget_config.py"
    source_storage = hermes_source / "tools" / "tool_result_storage.py"
    source_kanban = hermes_source / "tools" / "kanban_tools.py"

    with tempfile.TemporaryDirectory(prefix="brainstack-tool-budget-") as tmp_raw:
        tmp = Path(tmp_raw)
        budget_path = tmp / "budget_config.py"
        storage_path = tmp / "tool_result_storage.py"
        kanban_path = tmp / "kanban_tools.py"
        if source_budget.exists():
            shutil.copy2(source_budget, budget_path)
            source_mode = "hermes_source"
        else:
            budget_path.write_text(_minimal_budget_config(), encoding="utf-8")
            source_mode = "minimal_fixture"
            issues.append(f"Hermes budget_config.py not found at {source_budget}")
        if source_storage.exists():
            shutil.copy2(source_storage, storage_path)
        if source_kanban.exists():
            shutil.copy2(source_kanban, kanban_path)

        applied = install_into_hermes._patch_tool_result_budget_config(budget_path, dry_run=False)
        storage_applied = install_into_hermes._patch_tool_result_storage_no_env_artifact(
            storage_path, dry_run=False
        )
        kanban_applied = install_into_hermes._patch_kanban_list_compact_default(
            kanban_path, dry_run=False
        )
        patched = budget_path.read_text(encoding="utf-8")
        patched_storage = storage_path.read_text(encoding="utf-8") if storage_path.exists() else ""
        patched_kanban = kanban_path.read_text(encoding="utf-8") if kanban_path.exists() else ""
        namespace = _exec_budget_config(patched, budget_path)
        thresholds, threshold_issues = _verify_thresholds(namespace)
        issues.extend(threshold_issues)

    installer_source = (REPO_ROOT / "scripts" / "install_into_hermes.py").read_text(encoding="utf-8")
    legacy_kanban_compact_contract = (
        "KANBAN_LIST_DEFAULT_LIMIT = 20" in patched_kanban
        and '"include_links"' in patched_kanban
        and "include_links=include_links" in patched_kanban
        and "include_links: bool = False" in patched_kanban
        and "return summary" in patched_kanban
        and "Pass include_links=true" in patched_kanban
    )
    native_kanban_compact_contract = install_into_hermes._kanban_list_has_native_compact_rows(
        patched_kanban
    )
    proof = {
        "installer_registers_required_core_host_seam": (
            '"patcher": "_patch_tool_result_budget_config"' in installer_source
            and '"category": "required_seam"' in installer_source
            and '_run_host_patch("_patch_tool_result_budget_config"' in installer_source
        ),
        "wizard_patches_budget_config": '_run_host_patch("_patch_tool_result_budget_config"' in installer_source,
        "wizard_patches_no_env_artifact_storage": '_run_host_patch("_patch_tool_result_storage_no_env_artifact"' in installer_source,
        "wizard_patches_compact_kanban_list": '_run_host_patch("_patch_kanban_list_compact_default"' in installer_source,
        "observed_context_heavy_tools_covered": all(
            tool in namespace["BRAINSTACK_MODEL_FACING_TOOL_THRESHOLDS"]
            for tool in OBSERVED_CONTEXT_HEAVY_TOOLS
        ),
        "read_file_no_longer_infinite_pinned": namespace["PINNED_THRESHOLDS"] == {},
        "skill_view_86k_would_not_inline": thresholds["skill_view"] < 86_000,
        "brainstack_inspect_95k_would_not_inline": thresholds["brainstack_inspect"] < 95_000,
        "kanban_list_49k_would_not_inline": thresholds["kanban_list"] < 49_000,
        "kanban_show_17k_would_not_inline": thresholds["kanban_show"] < 17_600,
        "full_output_artifact_contract_present": (
            "Full output saved to:" in patched_storage
            and "read_file tool with offset and limit" in patched_storage
            and "preview + path" in patched_storage
        ),
        "no_env_large_tool_output_artifact_present": (
            "_write_to_local_temp" in patched_storage
            and "Persisted large tool result locally" in patched_storage
            and "env is None" in patched_storage
        ),
        "kanban_list_compact_default_present": (
            legacy_kanban_compact_contract or native_kanban_compact_contract
        ),
        "kanban_list_native_compact_rows_accepted": native_kanban_compact_contract,
        "kanban_list_compact_patch_consistent": not install_into_hermes._kanban_list_compact_patch_issues(
            patched_kanban
        ),
        "no_blind_drop_contract": "tool capability limits" in patched and "persisted-output" in patched_storage,
        "public_safe": True,
    }
    for key, ok in proof.items():
        if ok is not True:
            issues.append(f"proof failed: {key}")

    status = "pass" if not issues else "fail"
    return {
        "schema": REPORT_SCHEMA,
        "status": status,
        "public_safe": True,
        "source_mode": source_mode,
        "hermes_source": str(hermes_source),
        "applied": applied,
        "storage_applied": storage_applied,
        "kanban_applied": kanban_applied,
        "thresholds": thresholds,
        "issues": issues,
        "proof": proof,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hermes-source",
        default=os.environ.get("BRAINSTACK_RELEASE_HERMES_SOURCE", str(DEFAULT_HERMES_SOURCE)),
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = build_report(Path(args.hermes_source))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
