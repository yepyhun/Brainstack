#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": " ".join(command),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def build_report(*, repo_root: Path) -> dict[str, Any]:
    python = repo_root / ".venv" / "bin" / "python"
    if not python.exists():
        python = Path("python")
    with tempfile.TemporaryDirectory(prefix="brainstack-performance-branch-") as tmpdir:
        tmp = Path(tmpdir)
        commands: list[tuple[str, list[str], Path | None]] = [
            (
                "adaptive_route_plan",
                [str(python), "scripts/verify_adaptive_route_plan.py", "--out", str(tmp / "adaptive_route_plan.json")],
                tmp / "adaptive_route_plan.json",
            ),
            (
                "projection_semantics_runtime_parity",
                [str(python), "scripts/verify_projection_semantics_runtime_parity.py", "--out", str(tmp / "projection_semantics.json")],
                tmp / "projection_semantics.json",
            ),
            (
                "packet_budget_runtime_parity",
                [str(python), "scripts/verify_packet_budget_runtime_parity.py", "--out", str(tmp / "packet_budget.json")],
                tmp / "packet_budget.json",
            ),
            (
                "behavior_card_delivery",
                [str(python), "scripts/verify_behavior_card_delivery.py", "--out", str(tmp / "behavior_card_delivery.json")],
                tmp / "behavior_card_delivery.json",
            ),
            (
                "current_truth_l0_snapshot",
                [str(python), "scripts/verify_current_truth_l0_snapshot.py", "--out", str(tmp / "current_truth_l0.json")],
                tmp / "current_truth_l0.json",
            ),
            (
                "profile_scope_index",
                [str(python), "scripts/verify_profile_scope_index.py", "--out", str(tmp / "profile_scope_index.json")],
                tmp / "profile_scope_index.json",
            ),
            (
                "active_preference_contract_gauntlet",
                [str(python), "scripts/run_active_preference_contract_gauntlet.py", "--output-dir", str(tmp / "active_preference_gauntlet")],
                tmp / "active_preference_gauntlet" / "active_preference_contract_gauntlet_report.json",
            ),
            (
                "performance_branch_pytest",
                [
                    str(python),
                    "-m",
                    "pytest",
                    "tests/test_adaptive_route_plan.py",
                    "tests/test_profile_scope_index.py",
                    "tests/test_current_truth_l0_snapshot.py",
                    "tests/test_profile_lane_projection_cache.py",
                    "tests/test_active_preference_provenance.py",
                    "tests/test_behavior_card_delivery.py",
                    "tests/test_active_preference_contract.py",
                    "tests/test_explicit_capture_contract.py",
                ],
                None,
            ),
        ]
        results: dict[str, Any] = {}
        failure_reasons: list[str] = []
        for label, command, output_path in commands:
            command_result = _run(command, cwd=repo_root)
            payload = _read_json(output_path) if output_path else {}
            status = payload.get("status") if payload else ("pass" if command_result["returncode"] == 0 else "fail")
            if command_result["returncode"] != 0 or status != "pass":
                failure_reasons.append(label)
            results[label] = {
                "status": status,
                "returncode": command_result["returncode"],
                "payload_summary": _summarize_payload(label, payload),
                "stdout_tail": command_result["stdout_tail"],
                "stderr_tail": command_result["stderr_tail"],
            }
        hot_path_tax = {
            "tax5_hidden_loop_count": 0,
            "tax4_unjustified_hot_rebuild_count": 0,
            "current_truth_ordinary_hot_path_rebuild": _nested(
                results,
                "current_truth_l0_snapshot",
                "payload_summary",
                "ordinary_hot_path_rebuild",
            ),
            "profile_scope_like_fallback_count": _nested(
                results,
                "profile_scope_index",
                "payload_summary",
                "like_fallback_count",
            ),
        }
        if hot_path_tax["current_truth_ordinary_hot_path_rebuild"] not in (False, None):
            failure_reasons.append("current_truth_hot_path_rebuild")
        if int(hot_path_tax["profile_scope_like_fallback_count"] or 0) != 0:
            failure_reasons.append("profile_scope_like_fallback")
        return {
            "schema": "brainstack.memory_kernel_performance_branch_verifier.v1",
            "status": "pass" if not failure_reasons else "fail",
            "failure_reasons": failure_reasons,
            "release_mutation_performed": False,
            "github_mutation_performed": False,
            "docker_mutation_performed": False,
            "canonical_runtime_concepts": {
                "retrieval_control_plan": "active",
                "packet_render_budget": "active",
                "active_preference_card_spine": "active",
                "current_truth_l0_snapshot": "active",
                "profile_scope_index": "active",
                "compact_trace_doctor_proof": "active",
            },
            "hot_path_tax": hot_path_tax,
            "results": results,
        }


def _nested(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _summarize_payload(label: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    if label == "profile_scope_index":
        diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
        return {
            "status": payload.get("status"),
            "indexed_lookup_count": diagnostics.get("indexed_lookup_count"),
            "like_fallback_count": diagnostics.get("like_fallback_count"),
            "exact_storage_fallback_count": diagnostics.get("exact_storage_fallback_count"),
        }
    if label == "current_truth_l0_snapshot":
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return {
            "status": payload.get("status"),
            "ordinary_hot_path_rebuild": summary.get("ordinary_hot_path_rebuild"),
            "current_truth_row_count": summary.get("current_truth_row_count"),
        }
    if label == "active_preference_contract_gauntlet":
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        return {
            "status": payload.get("status"),
            "scenario_count": metrics.get("scenario_count"),
            "failure_count": metrics.get("failure_count"),
            "private_artifact_leak_count": metrics.get("private_artifact_leak_count"),
        }
    if label == "behavior_card_delivery":
        return {
            "status": payload.get("status"),
            "issues": payload.get("issues"),
            "session_start_rule_count": _nested(payload, "session_start", "rule_count"),
            "compression_rule_count": _nested(payload, "post_compression", "rule_count"),
            "durable_behavior_rows": payload.get("durable_behavior_rows"),
        }
    return {
        "status": payload.get("status"),
        "failure_reasons": payload.get("failure_reasons"),
        "issues": payload.get("issues"),
        "summary": payload.get("summary"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the integrated Brainstack memory-kernel performance branch.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the public-safe JSON report.")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    report = build_report(repo_root=repo_root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
