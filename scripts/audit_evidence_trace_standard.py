#!/usr/bin/env python3
"""Audit public evidence traces for completeness, redaction, and reason-code stability."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.core.reason_codes import is_reason_code  # noqa: E402
from brainstack.core.trace import validate_evidence_trace  # noqa: E402
from scripts.run_public_memory_kernel_fixtures import run_fixture_directory  # noqa: E402


def _candidate_reason_code_errors(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for bucket in ("candidates", "selected_answer_evidence"):
        for item in trace.get(bucket) or []:
            if not isinstance(item, Mapping):
                continue
            reason_code = item.get("reason_code")
            if not is_reason_code(reason_code):
                errors.append(f"{bucket}:unknown_reason_code:{reason_code}")
    for item in trace.get("dropped_summary") or []:
        if not isinstance(item, Mapping):
            continue
        reason_code = item.get("reason_code")
        if not is_reason_code(reason_code):
            errors.append(f"dropped_summary:unknown_reason_code:{reason_code}")
    return errors


def _redaction_errors(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for bucket in ("candidates", "selected_answer_evidence"):
        for item in trace.get(bucket) or []:
            if not isinstance(item, Mapping):
                continue
            candidate_id = item.get("candidate_id") or "<unknown>"
            if item.get("raw_text_included") is True:
                errors.append(f"{bucket}:{candidate_id}:raw_text_included")
            if "raw_text" in item:
                errors.append(f"{bucket}:{candidate_id}:raw_text_field_present")
            if not item.get("value_fingerprint"):
                errors.append(f"{bucket}:{candidate_id}:missing_value_fingerprint")
    return errors


def _proof_chain_errors(trace: Mapping[str, Any]) -> list[str]:
    if not trace.get("selected_answer_evidence"):
        if trace.get("dropped_summary"):
            return []
        return ["missing_selected_evidence_or_dropped_summary"]
    proof_chain = trace.get("proof_chain")
    if not isinstance(proof_chain, list) or not proof_chain:
        return ["missing_proof_chain"]
    stages = {str(item.get("stage") or "") for item in proof_chain if isinstance(item, Mapping)}
    if "retrieval_candidate" not in stages:
        return ["proof_chain_missing_retrieval_candidate"]
    return []


def _visibility_errors(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if "packet_budget" not in trace:
        errors.append("missing_packet_budget")
    if "receipt_coverage" not in trace:
        errors.append("missing_receipt_coverage")
    if "scope" not in trace:
        errors.append("missing_scope")
    return errors


def audit_evidence_trace_standard(fixture_dir: Path) -> dict[str, Any]:
    run = run_fixture_directory(fixture_dir)
    scenario_reports: list[dict[str, Any]] = []
    issue_count = 0
    complete_count = 0
    proof_chain_count = 0
    selected_trace_count = 0
    dropped_only_explained_count = 0
    raw_text_issue_count = 0
    unknown_reason_code_count = 0

    for scenario in run.get("scenarios") or []:
        scenario_id = str(scenario.get("scenario_id") or "")
        trace = scenario.get("trace") or {}
        errors: list[str] = []
        errors.extend(validate_evidence_trace(trace))
        reason_errors = _candidate_reason_code_errors(trace)
        redaction_errors = _redaction_errors(trace)
        proof_errors = _proof_chain_errors(trace)
        visibility_errors = _visibility_errors(trace)
        errors.extend(reason_errors)
        errors.extend(redaction_errors)
        errors.extend(proof_errors)
        errors.extend(visibility_errors)
        completeness = trace.get("trace_completeness") or {}
        complete = bool(completeness.get("complete_for_audit")) and not errors
        if complete:
            complete_count += 1
        if trace.get("selected_answer_evidence"):
            selected_trace_count += 1
        elif trace.get("dropped_summary") and not proof_errors:
            dropped_only_explained_count += 1
        if not proof_errors and trace.get("proof_chain"):
            proof_chain_count += 1
        raw_text_issue_count += len(redaction_errors)
        unknown_reason_code_count += len(reason_errors)
        issue_count += len(errors)
        scenario_reports.append(
            {
                "scenario_id": scenario_id,
                "status": "pass" if not errors else "fail",
                "complete_for_audit": bool(completeness.get("complete_for_audit")),
                "proof_chain_present": not proof_errors,
                "selected_answer_evidence_count": len(trace.get("selected_answer_evidence") or []),
                "reason_code_errors": reason_errors,
                "redaction_errors": redaction_errors,
                "visibility_errors": visibility_errors,
                "errors": errors,
            }
        )

    return {
        "schema": "brainstack.evidence_trace_standard_audit.v1",
        "fixture_dir": str(fixture_dir),
        "fixture_status": run.get("status"),
        "status": "pass" if issue_count == 0 and run.get("status") == "pass" else "fail",
        "scenario_count": len(run.get("scenarios") or []),
        "complete_trace_count": complete_count,
        "proof_chain_count": proof_chain_count,
        "selected_trace_count": selected_trace_count,
        "dropped_only_explained_count": dropped_only_explained_count,
        "unknown_reason_code_count": unknown_reason_code_count,
        "raw_text_issue_count": raw_text_issue_count,
        "issue_count": issue_count,
        "scenarios": scenario_reports,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/public_memory_kernel"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = audit_evidence_trace_standard(args.fixtures)
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
