#!/usr/bin/env python3
"""Run Brainstack memory-kernel release checks as one public-safe gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def _check_active_packet_budget(tmp: Path) -> CheckResult:
    out = tmp / "packet_budget_active_rollout.json"
    command = [
        sys.executable,
        "scripts/measure_packet_budget_active_rollout.py",
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
        and data.get("active_budget_enabled_for_supported_paths") is True
        and data.get("protected_truth_drop_attempts") == 0
        and data.get("budget_decision_trace_present") is True
        and data.get("budget_reason_code_registry_pass") is True
        and data.get("raw_text_in_budget_trace") is False
        and data.get("unsupported_path_fail_closed_count") == 1
    )
    return CheckResult(
        name="packet_budget_active_rollout",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "active_budget_enabled_for_supported_paths": data.get(
                "active_budget_enabled_for_supported_paths"
            ),
            "scenario_count": data.get("scenario_count"),
            "distinct_scenario_family_count": data.get("distinct_scenario_family_count"),
            "candidate_token_delta_percent": data.get("candidate_token_delta_percent"),
            "packet_build_latency_overhead_ms_p95": data.get(
                "packet_build_latency_overhead_ms_p95"
            ),
            "protected_truth_drop_attempts": data.get("protected_truth_drop_attempts"),
            "budget_reason_code_registry_pass": data.get("budget_reason_code_registry_pass"),
            "raw_text_in_budget_trace": data.get("raw_text_in_budget_trace"),
            "unsupported_path_fail_closed_count": data.get("unsupported_path_fail_closed_count"),
        },
    )


def _check_packet_budget_soak(tmp: Path) -> CheckResult:
    out = tmp / "packet_budget_soak.json"
    command = [
        sys.executable,
        "scripts/run_packet_budget_soak.py",
        "--sample-count",
        "100",
        "--budget-max-candidate-tokens",
        "120",
        "--out",
        str(out),
    ]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = (
        proc.returncode == 0
        and data.get("status") == "pass"
        and data.get("scenario_count", 0) >= 100
        and data.get("scenario_family_count", 0) >= 10
        and data.get("protected_truth_drop_attempts") == 0
        and data.get("selected_evidence_fingerprint_mismatch_count") == 0
        and data.get("trace_complete_count") == data.get("scenario_count")
        and data.get("soak_artifact_leak_findings") == 0
        and data.get("failure_bundle_count") == 0
        and data.get("retrieval_fusion_next_phase_required") is False
    )
    return CheckResult(
        name="packet_budget_soak",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "scenario_count": data.get("scenario_count"),
            "scenario_family_count": data.get("scenario_family_count"),
            "candidate_token_delta_percent": data.get("candidate_token_delta_percent"),
            "protected_truth_drop_attempts": data.get("protected_truth_drop_attempts"),
            "selected_evidence_fingerprint_mismatch_count": data.get(
                "selected_evidence_fingerprint_mismatch_count"
            ),
            "trace_complete_count": data.get("trace_complete_count"),
            "soak_artifact_leak_findings": data.get("soak_artifact_leak_findings"),
            "failure_bundle_count": data.get("failure_bundle_count"),
            "retrieval_fusion_next_phase_required": data.get(
                "retrieval_fusion_next_phase_required"
            ),
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


def _check_graph_conflict_lifecycle(tmp: Path) -> CheckResult:
    out = tmp / "graph_conflict_lifecycle_audit.json"
    command = [sys.executable, "scripts/audit_graph_conflict_lifecycle.py", "--out", str(out)]
    proc = _run(command)
    data = _load_json(out) if out.exists() else {}
    passed = (
        proc.returncode == 0
        and data.get("status") == "pass"
        and data.get("issue_count") == 0
        and data.get("release_blocked_before_resolution") is True
        and data.get("open_conflict_count_after_resolution") == 0
        and data.get("resolution_ledger_count") == 1
    )
    return CheckResult(
        name="graph_conflict_lifecycle",
        status=_status(passed),
        command=command,
        returncode=proc.returncode,
        summary={
            "status": data.get("status"),
            "issue_count": data.get("issue_count"),
            "release_blocked_before_resolution": data.get("release_blocked_before_resolution"),
            "open_conflict_count_after_resolution": data.get("open_conflict_count_after_resolution"),
            "resolution_ledger_count": data.get("resolution_ledger_count"),
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


def _tracked_files() -> list[str]:
    proc = _run(["git", "ls-files"])
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _private_payload_terms() -> list[str]:
    denylist_path = ROOT / ".planning" / "private_payload_denylist.txt"
    if not denylist_path.exists():
        return []
    terms: list[str] = []
    for raw in denylist_path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if not term or term.startswith("#"):
            continue
        terms.append(term)
    return terms


def _check_public_payload_leaks() -> CheckResult:
    local_terms = _private_payload_terms()
    platform_id_pattern = re.compile(
        r"(?:user_id|channel_id|thread_id|server_id|guild_id|principal|telegram|discord)[^\\n]{0,80}\\b\\d{12,}\\b",
        re.IGNORECASE,
    )
    token_shape_pattern = re.compile(r"\\b[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{6,}\\.[A-Za-z0-9_-]{20,}\\b")
    findings: list[dict[str, Any]] = []
    for relative in _tracked_files():
        path = ROOT / relative
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if platform_id_pattern.search(line):
                findings.append({"path": relative, "line": line_number, "kind": "platform_id_shape"})
            if token_shape_pattern.search(line):
                findings.append({"path": relative, "line": line_number, "kind": "token_shape"})
            for term in local_terms:
                if term in line:
                    findings.append(
                        {
                            "path": relative,
                            "line": line_number,
                            "kind": "local_private_denylist",
                            "term_hash": hashlib.sha256(term.encode("utf-8")).hexdigest()[:16],
                        }
                    )
    passed = not findings
    return CheckResult(
        name="public_payload_leak_scan",
        status=_status(passed),
        command=["git ls-files", "local private denylist scan if .planning/private_payload_denylist.txt exists"],
        returncode=0,
        summary={
            "tracked_file_count": len(_tracked_files()),
            "local_private_denylist_loaded": bool(local_terms),
            "finding_count": len(findings),
            "findings": findings[:20],
        },
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
            _check_active_packet_budget(tmp),
            _check_packet_budget_soak(tmp),
            _check_write_path(tmp),
            _check_graph_conflict_lifecycle(tmp),
            _check_public_fixtures(),
            _check_public_payload_leaks(),
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
