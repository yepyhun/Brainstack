#!/usr/bin/env python3
"""Run public-safe Brainstack memory-kernel fixture contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.capture_pipeline import admit_structured_capture_items  # noqa: E402
from brainstack.core.packet_budget import (  # noqa: E402
    PacketBudgetPolicy,
    apply_packet_budget,
    validate_packet_budget_trace,
)
from brainstack.core.reason_codes import ReasonCode  # noqa: E402
from brainstack.core.trace import (  # noqa: E402
    AUTHORITY_CORRECTED_FALSE,
    AUTHORITY_INSPECT_ONLY,
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_SUPPORT_ONLY,
    DECISION_DROPPED,
    DECISION_SELECTED,
    build_evidence_trace,
    make_evidence_candidate,
    validate_evidence_trace,
)
from brainstack.memory_write_receipts import (  # noqa: E402
    ACK_NONE,
    CapturePlan,
    build_ack_plan,
    build_memory_write_receipt,
    compute_receipt_coverage,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _shelf_for_slot(slot: str) -> str:
    if slot.startswith("reference."):
        return "reference"
    if slot.startswith("project."):
        return "project"
    if slot.startswith("preference."):
        return "profile"
    if slot.startswith("identity."):
        return "profile"
    return "literal"


def _plan_from_payload(payload: Mapping[str, Any]) -> CapturePlan:
    return CapturePlan.from_proposals(
        turn_id=str(payload.get("turn_id") or ""),
        source_event_id=str(payload.get("source_event_id") or ""),
        proposals=payload.get("proposals") or [],
        capture_plan_id=str(payload.get("capture_plan_id") or ""),
        plan_status=str(payload.get("plan_status") or "has_proposals"),
    )


def _receipt_set(
    *,
    scenario: Mapping[str, Any],
    plan: CapturePlan,
) -> list[dict[str, Any]]:
    mode = str(scenario.get("receipt_mode") or "complete")
    if mode in {"none", "not_applicable"}:
        return []
    proposal_ids = {item.proposal_id for item in plan.proposals}
    if mode == "partial":
        proposal_ids = set(scenario.get("receipt_proposal_ids") or [])
    receipts: list[dict[str, Any]] = []
    for proposal in plan.proposals:
        if proposal.proposal_id not in proposal_ids:
            continue
        receipts.append(
            build_memory_write_receipt(
                capture_plan=plan,
                proposal=proposal,
                principal_scope_key=str(scenario.get("principal_scope_key") or ""),
                workspace_scope_key=str(scenario.get("workspace_scope_key") or ""),
                session_id=str(scenario.get("session_id") or ""),
                shelf=_shelf_for_slot(proposal.target_slot),
                admission_decision_id=f"adm_{proposal.proposal_id}",
            )
        )
    return receipts


def _receipt_by_proposal(receipts: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    mapping: dict[str, Mapping[str, Any]] = {}
    for receipt in receipts:
        for proposal_id in receipt.get("proposal_ids") or []:
            mapping[str(proposal_id)] = receipt
    return mapping


def _candidate_for_proposal(
    *,
    scenario: Mapping[str, Any],
    proposal: Mapping[str, Any],
    coverage: Mapping[str, Any],
    receipt_by_proposal: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    proposal_id = str(proposal.get("proposal_id") or "")
    covered = proposal_id in set(coverage.get("covered_proposals") or [])
    receipt = receipt_by_proposal.get(proposal_id) or {}
    if covered:
        return make_evidence_candidate(
            candidate_id=f"ev_{proposal_id}",
            shelf=_shelf_for_slot(str(proposal.get("target_slot") or "")),
            target_slot=str(proposal.get("target_slot") or ""),
            source_role=str(scenario.get("source_role") or "user"),
            authority=AUTHORITY_RECEIPT_BACKED,
            decision=DECISION_SELECTED,
            reason_code=ReasonCode.SELECTED_RECEIPT_BACKED_FACT.value,
            source_event_id=str(scenario.get("source_event_id") or ""),
            source_span_id=str(proposal.get("source_span_id") or ""),
            capture_plan_id=str(coverage.get("capture_plan_id") or ""),
            proposal_id=proposal_id,
            admission_id=f"adm_{proposal_id}",
            receipt_id=str(receipt.get("receipt_id") or ""),
            truth_eligible=True,
            model_facing_allowed=True,
            answer_evidence_allowed=True,
            raw_value=proposal.get("normalized_value"),
            redacted_excerpt=f"Public fixture value for {proposal.get('target_slot')}",
            token_estimate=8,
        )
    return make_evidence_candidate(
        candidate_id=f"ev_missing_{proposal_id}",
        shelf=_shelf_for_slot(str(proposal.get("target_slot") or "")),
        target_slot=str(proposal.get("target_slot") or ""),
        source_role=str(scenario.get("source_role") or "user"),
        authority=AUTHORITY_INSPECT_ONLY,
        decision=DECISION_DROPPED,
        reason_code=ReasonCode.FULL_ACK_REQUIRES_COMPLETE_RECEIPT_COVERAGE.value,
        source_event_id=str(scenario.get("source_event_id") or ""),
        source_span_id=str(proposal.get("source_span_id") or ""),
        capture_plan_id=str(coverage.get("capture_plan_id") or ""),
        proposal_id=proposal_id,
        truth_eligible=False,
        model_facing_allowed=False,
        answer_evidence_allowed=False,
        raw_value=proposal.get("normalized_value"),
        redacted_excerpt=f"Missing receipt for {proposal.get('target_slot')}",
        token_estimate=5,
    )


def _extra_candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    authority = str(item.get("authority") or AUTHORITY_INSPECT_ONLY)
    decision = str(item.get("decision") or DECISION_DROPPED)
    answer_allowed = bool(item.get("answer_evidence_allowed", False))
    truth_eligible = bool(item.get("truth_eligible", False))
    if authority in {AUTHORITY_SUPPORT_ONLY, AUTHORITY_INSPECT_ONLY, AUTHORITY_CORRECTED_FALSE}:
        answer_allowed = False
        truth_eligible = False
    candidate = make_evidence_candidate(
        candidate_id=str(item.get("candidate_id") or ""),
        shelf=str(item.get("shelf") or "transcript"),
        target_slot=str(item.get("target_slot") or ""),
        source_role=str(item.get("source_role") or "assistant"),
        authority=authority,
        decision=decision,
        reason_code=str(item.get("reason_code") or ReasonCode.UNCLASSIFIED.value),
        source_event_id=str(item.get("source_event_id") or ""),
        source_span_id=str(item.get("source_span_id") or ""),
        truth_eligible=truth_eligible,
        model_facing_allowed=bool(item.get("model_facing_allowed", False)),
        answer_evidence_allowed=answer_allowed,
        raw_value=item.get("raw_value"),
        redacted_excerpt=item.get("redacted_excerpt"),
        corrected_by=item.get("corrected_by"),
        token_estimate=int(item.get("token_estimate") or 4),
    )
    for key in ("stable_key", "protected", "required_for_answer", "stale"):
        if key in item:
            candidate[key] = item[key]
    return candidate


def _reset_recall(plan: CapturePlan, coverage: Mapping[str, Any]) -> dict[str, str]:
    covered = set(coverage.get("covered_proposals") or [])
    recall: dict[str, str] = {}
    for proposal in plan.proposals:
        if proposal.proposal_id not in covered:
            continue
        recall[proposal.stable_key] = proposal.normalized_value
    return recall


def run_scenario(scenario: Mapping[str, Any]) -> dict[str, Any]:
    items = scenario.get("capture_items") or []
    if items:
        admitted = admit_structured_capture_items(
            turn_id=str(scenario.get("turn_id") or ""),
            source_event_id=str(scenario.get("source_event_id") or ""),
            source_role=str(scenario.get("source_role") or "user"),
            items=items,
        )
        plan = _plan_from_payload(admitted["capture_plan"])
        receipts = _receipt_set(scenario=scenario, plan=plan)
        coverage = compute_receipt_coverage(
            plan,
            receipts,
            principal_scope_key=str(scenario.get("principal_scope_key") or ""),
            workspace_scope_key=str(scenario.get("workspace_scope_key") or ""),
            session_id=str(scenario.get("session_id") or ""),
        )
        ack_plan = build_ack_plan(plan, coverage)
        receipt_by_proposal = _receipt_by_proposal(receipts)
        candidates = [
            _candidate_for_proposal(
                scenario=scenario,
                proposal=proposal.to_dict(),
                coverage=coverage,
                receipt_by_proposal=receipt_by_proposal,
            )
            for proposal in plan.proposals
        ]
    else:
        admitted = {"capture_plan": {"proposals": [], "plan_status": "not_applicable"}}
        plan = CapturePlan.from_proposals(
            turn_id=str(scenario.get("turn_id") or ""),
            source_event_id=str(scenario.get("source_event_id") or ""),
            proposals=(),
            plan_status="not_applicable",
        )
        coverage = {"coverage_status": "not_applicable", "capture_plan_id": plan.capture_plan_id}
        ack_plan = {
            "ack_mode": ACK_NONE,
            "must_not_claim_full_commit": True,
            "covered_slots": [],
            "missing_slots": [],
        }
        candidates = []
    candidates.extend(_extra_candidate(item) for item in scenario.get("extra_candidates") or [])
    budget_result = None
    budget_max = scenario.get("packet_budget_max_candidate_tokens")
    if budget_max is not None:
        budget_result = apply_packet_budget(
            candidates,
            PacketBudgetPolicy(max_candidate_tokens=int(budget_max)),
        )
        candidates = budget_result.candidates
    trace = build_evidence_trace(
        trace_id=f"trace_{scenario.get('scenario_id')}",
        turn_id=str(scenario.get("turn_id") or ""),
        query_summary=str(scenario.get("query_summary") or ""),
        principal_scope_key=str(scenario.get("principal_scope_key") or ""),
        workspace_scope_key=str(scenario.get("workspace_scope_key") or ""),
        candidates=candidates,
        receipt_coverage=coverage,
        max_tokens=int(budget_max) if budget_max is not None else None,
        truncated=bool(budget_result.truncated) if budget_result is not None else False,
    )
    if budget_result is not None:
        trace["packet_budget"].update(budget_result.to_trace_packet_budget())
    errors = validate_evidence_trace(trace) + validate_packet_budget_trace(trace)
    expected = scenario.get("expected") or {}
    observed_recall = _reset_recall(plan, coverage)
    contract_errors = []
    if expected.get("receipt_coverage") and coverage.get("coverage_status") != expected["receipt_coverage"]:
        contract_errors.append("receipt_coverage_mismatch")
    if expected.get("ack_mode") and ack_plan.get("ack_mode") != expected["ack_mode"]:
        contract_errors.append("ack_mode_mismatch")
    if "full_ack_allowed" in expected and bool(coverage.get("full_ack_allowed")) != bool(expected["full_ack_allowed"]):
        contract_errors.append("full_ack_allowed_mismatch")
    selected_slots = [
        item.get("target_slot")
        for item in candidates
        if item.get("decision") == DECISION_SELECTED
    ]
    if expected.get("selected_slots") and selected_slots != expected["selected_slots"]:
        contract_errors.append("selected_slots_mismatch")
    for code in expected.get("required_trace_reason_codes") or []:
        all_codes = [item.get("reason_code") for item in candidates]
        if code not in all_codes:
            contract_errors.append(f"missing_required_reason_code:{code}")
    for code in expected.get("dropped_reason_codes") or []:
        dropped_codes = [
            item.get("reason_code")
            for item in candidates
            if item.get("decision") == DECISION_DROPPED
        ]
        if code not in dropped_codes:
            contract_errors.append(f"missing_dropped_reason_code:{code}")
    if expected.get("packet_budget_status"):
        if trace["packet_budget"].get("status") != expected["packet_budget_status"]:
            contract_errors.append("packet_budget_status_mismatch")
    if "packet_budget_fail_closed" in expected:
        if bool(trace["packet_budget"].get("fail_closed")) != bool(expected["packet_budget_fail_closed"]):
            contract_errors.append("packet_budget_fail_closed_mismatch")
    if expected.get("selected_candidate_ids"):
        selected_ids = [
            item.get("candidate_id")
            for item in candidates
            if item.get("decision") == DECISION_SELECTED
        ]
        if selected_ids != expected["selected_candidate_ids"]:
            contract_errors.append("selected_candidate_ids_mismatch")
    if expected.get("dropped_candidate_ids"):
        dropped_ids = [
            item.get("candidate_id")
            for item in candidates
            if item.get("decision") == DECISION_DROPPED
        ]
        for candidate_id in expected["dropped_candidate_ids"]:
            if candidate_id not in dropped_ids:
                contract_errors.append(f"missing_dropped_candidate_id:{candidate_id}")
    if expected.get("reset_recall") is not None and observed_recall != expected["reset_recall"]:
        contract_errors.append("reset_recall_mismatch")
    status = "pass" if not errors and not contract_errors else "fail"
    return {
        "scenario_id": scenario.get("scenario_id"),
        "status": status,
        "capture_plan": admitted.get("capture_plan"),
        "receipt_coverage": coverage,
        "ack_plan": ack_plan,
        "reset_recall": observed_recall,
        "trace": trace,
        "errors": errors,
        "contract_errors": contract_errors,
    }


def run_fixture_directory(fixture_dir: Path) -> dict[str, Any]:
    scenarios = []
    for path in sorted((fixture_dir / "conversations").glob("*.json")):
        scenarios.append(run_scenario(_load_json(path)))
    failures = [item for item in scenarios if item["status"] != "pass"]
    return {
        "schema": "brainstack.public_memory_fixture_run.v1",
        "fixture_dir": str(fixture_dir),
        "scenario_count": len(scenarios),
        "failure_count": len(failures),
        "status": "pass" if not failures else "fail",
        "scenarios": scenarios,
    }


def run_negative_fixtures(fixture_dir: Path) -> dict[str, Any]:
    results = []
    for path in sorted((fixture_dir / "negative").glob("*.json")):
        payload = _load_json(path)
        errors = validate_evidence_trace(payload["trace"]) + validate_packet_budget_trace(
            payload["trace"]
        )
        expected = str(payload.get("expected_error") or "")
        results.append(
            {
                "negative_id": payload.get("negative_id"),
                "status": "pass" if any(expected in error for error in errors) else "fail",
                "expected_error": expected,
                "errors": errors,
            }
        )
    failures = [item for item in results if item["status"] != "pass"]
    return {
        "schema": "brainstack.public_memory_negative_fixture_run.v1",
        "fixture_dir": str(fixture_dir),
        "negative_count": len(results),
        "failure_count": len(failures),
        "status": "pass" if not failures else "fail",
        "negative_fixtures": results,
    }


def failure_bundles(run: Mapping[str, Any]) -> list[dict[str, Any]]:
    bundles = []
    for scenario in run.get("scenarios") or []:
        if scenario.get("status") == "pass":
            continue
        bundles.append(
            {
                "schema": "brainstack.failure_bundle.v1",
                "scenario_id": scenario.get("scenario_id"),
                "owner": "brainstack_memory_kernel_contract",
                "observed_errors": scenario.get("errors", []) + scenario.get("contract_errors", []),
                "recommended_retest": "pytest tests/test_public_memory_kernel_corpus.py",
            }
        )
    return bundles


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default="tests/fixtures/public_memory_kernel")
    parser.add_argument("--emit-traces", default="")
    parser.add_argument("--emit-failures", default="")
    parser.add_argument("--contract-only", action="store_true")
    args = parser.parse_args()
    fixture_dir = Path(args.fixtures)
    run = run_fixture_directory(fixture_dir)
    negative = run_negative_fixtures(fixture_dir)
    if args.emit_traces:
        out = Path(args.emit_traces)
        for scenario in run["scenarios"]:
            _write_json(out / f"{scenario['scenario_id']}.json", scenario["trace"])
    if args.emit_failures:
        out = Path(args.emit_failures)
        for bundle in failure_bundles(run):
            _write_json(out / f"{bundle['scenario_id']}.json", bundle)
    print(json.dumps({"run": run["status"], "negative": negative["status"]}, sort_keys=True))
    return 0 if run["status"] == "pass" and negative["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
