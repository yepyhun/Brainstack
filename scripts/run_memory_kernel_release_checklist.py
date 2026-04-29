#!/usr/bin/env python3
"""Run Brainstack memory-kernel release checks as one public-safe gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    command: list[str]
    returncode: int
    summary: dict[str, Any]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_from_stdout(stdout: str) -> dict[str, Any]:
    return json.loads(stdout.strip() or "{}")


def _status(passed: bool) -> str:
    return "pass" if passed else "fail"


def _check_public_corpus(tmp: Path) -> CheckResult:
    out = tmp / "public_corpus_audit.json"
    command = [sys.executable, "scripts/audit_public_memory_kernel_corpus.py", "--out", str(out)]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = proc.returncode == 0 and data.get("status") == "pass" and not data.get("issues")
    return CheckResult(
        name="public_memory_kernel_corpus",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "status": data.get("status"),
            "scenario_count": data.get("scenario_count"),
            "negative_count": data.get("negative_count"),
            "leak_findings_count": len(data.get("leak_findings") or []),
            "issue_count": len(data.get("issues") or []),
        },
    )


def _check_evidence_trace(tmp: Path) -> CheckResult:
    out = tmp / "evidence_trace_audit.json"
    command = [sys.executable, "scripts/audit_evidence_trace_standard.py", "--out", str(out)]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = proc.returncode == 0 and data.get("status") == "pass" and data.get("issue_count") == 0
    return CheckResult(
        name="evidence_trace_standard",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "status": data.get("status"),
            "scenario_count": data.get("scenario_count"),
            "complete_trace_count": data.get("complete_trace_count"),
            "proof_chain_count": data.get("proof_chain_count"),
            "unknown_reason_code_count": data.get("unknown_reason_code_count"),
            "raw_text_issue_count": data.get("raw_text_issue_count"),
            "issue_count": data.get("issue_count"),
        },
    )


def _check_packet_budget(tmp: Path) -> CheckResult:
    out = tmp / "packet_budget_live_shadow.json"
    command = [
        sys.executable,
        "scripts/measure_packet_budget_live_shadow_telemetry.py",
        "--sample-count",
        "24",
        "--budget-max-candidate-tokens",
        "120",
        "--out",
        str(out),
    ]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = (
        proc.returncode == 0
        and data.get("scenario_count", 0) >= 20
        and data.get("distinct_scenario_family_count", 0) >= 6
        and data.get("output_changed_in_shadow") is False
        and data.get("protected_truth_drop_attempts") == 0
        and bool(data.get("activation_verdict"))
    )
    return CheckResult(
        name="packet_budget_live_shadow",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "scenario_count": data.get("scenario_count"),
            "distinct_scenario_family_count": data.get("distinct_scenario_family_count"),
            "estimated_delta_percent": data.get("estimated_delta_percent"),
            "protected_truth_drop_attempts": data.get("protected_truth_drop_attempts"),
            "output_changed_in_shadow": data.get("output_changed_in_shadow"),
            "fusion_signal_count": data.get("fusion_signal_count"),
            "retrieval_fusion_next_phase_required": data.get("retrieval_fusion_next_phase_required"),
            "activation_verdict": data.get("activation_verdict"),
        },
    )


def _check_write_path(tmp: Path) -> CheckResult:
    out = tmp / "write_path_closure_audit.json"
    command = [sys.executable, "scripts/brainstack_write_path_closure_audit.py", "--json-out", str(out)]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = proc.returncode == 0 and data.get("hard_failure_count") == 0
    return CheckResult(
        name="write_path_closure",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "callsite_count": data.get("callsite_count"),
            "hard_failure_count": data.get("hard_failure_count"),
            "by_class": data.get("by_class", {}),
        },
    )


def _check_public_fixtures() -> CheckResult:
    command = [sys.executable, "scripts/run_public_memory_kernel_fixtures.py", "--contract-only"]
    proc = _run(command)
    data = _json_from_stdout(proc.stdout) if proc.stdout.strip().startswith("{") else {}
    passed = proc.returncode == 0 and data.get("negative") == "pass" and data.get("run") == "pass"
    return CheckResult(
        name="public_fixture_runner",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={"negative": data.get("negative"), "run": data.get("run")},
    )


def _git_porcelain() -> list[str]:
    proc = _run(["git", "status", "--porcelain", "--untracked-files=all"])
    if proc.returncode != 0:
        return ["!! git status failed"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _visible_untracked() -> list[str]:
    proc = _run(["git", "ls-files", "--others", "--exclude-standard"])
    if proc.returncode != 0:
        return ["git ls-files failed"]
    return [line for line in proc.stdout.splitlines() if line.strip()]


def _git_hygiene_from_lists(porcelain: list[str], visible_untracked: list[str]) -> dict[str, Any]:
    private_live = [path for path in visible_untracked if "live" in path.lower() or "discord" in path.lower()]
    return {
        "git_dirty": bool(porcelain),
        "dirty_entry_count": len(porcelain),
        "visible_untracked_count": len(visible_untracked),
        "untracked_private_files_count": len(private_live),
        "untracked_private_files_policy": "blocked_if_visible",
        "private_live_untracked_visible": bool(private_live),
    }


def _check_git_hygiene() -> CheckResult:
    porcelain = _git_porcelain()
    visible_untracked = _visible_untracked()
    summary = _git_hygiene_from_lists(porcelain, visible_untracked)
    passed = not summary["git_dirty"] and summary["untracked_private_files_count"] == 0
    return CheckResult(
        name="git_hygiene",
        status=_status(passed),
        command=["git status --porcelain", "git ls-files --others --exclude-standard"],
        returncode=0,
        summary=summary,
    )


def _report(checks: list[CheckResult], *, ignore_git_dirty_for_dev: bool) -> dict[str, Any]:
    check_dicts = [
        {
            "name": check.name,
            "status": check.status,
            "returncode": check.returncode,
            "summary": check.summary,
        }
        for check in checks
    ]
    git_check = next((check for check in checks if check.name == "git_hygiene"), None)
    non_git_failures = [check.name for check in checks if check.name != "git_hygiene" and check.status != "pass"]
    git_pass = git_check is not None and git_check.status == "pass"
    release_allowed = not non_git_failures and git_pass
    checklist_passed = release_allowed or (ignore_git_dirty_for_dev and not non_git_failures)
    return {
        "schema": "brainstack.memory_kernel_release_checklist.v1",
        "status": "pass" if checklist_passed else "fail",
        "release_allowed": release_allowed,
        "ignore_git_dirty_for_dev": ignore_git_dirty_for_dev,
        "failed_checks": [check.name for check in checks if check.status != "pass"],
        "non_git_failures": non_git_failures,
        "checks": check_dicts,
    }


def run_checklist(*, ignore_git_dirty_for_dev: bool = False) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-release-checklist-") as temp:
        tmp = Path(temp)
        checks = [
            _check_public_corpus(tmp),
            _check_evidence_trace(tmp),
            _check_packet_budget(tmp),
            _check_write_path(tmp),
            _check_public_fixtures(),
            _check_git_hygiene(),
        ]
    return _report(checks, ignore_git_dirty_for_dev=ignore_git_dirty_for_dev)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--ignore-git-dirty-for-dev",
        action="store_true",
        help="Do not fail process solely because current worktree is dirty. Report still marks release_allowed=false.",
    )
    args = parser.parse_args()

    report = run_checklist(ignore_git_dirty_for_dev=args.ignore_git_dirty_for_dev)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
