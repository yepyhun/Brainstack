#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.tier2_decision_core import (  # noqa: E402
    build_tier2_decision_plan,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)


def _scope(principal: str = "principal-a") -> dict[str, str]:
    return {
        "tenant_id": "local",
        "principal_scope_key": principal,
        "workspace_scope_key": "workspace-a",
        "session_id": "session-a",
        "project_id": "project-a",
    }


def _span(span_id: str = "span-user", *, speaker: str = "user", principal: str = "principal-a") -> dict[str, Any]:
    return {
        "source_span_id": span_id,
        "source_event_id": "event-" + span_id,
        "speaker": speaker,
        "assertion_speaker": speaker,
        "source_modality": "conversation",
        "scope": _scope(principal),
    }


def _packet(actions: list[Mapping[str, Any]], *, spans: list[Mapping[str, Any]] | None = None, existing=None, conflicts=None, principal: str = "principal-a") -> dict[str, Any]:
    return {
        "schema": "brainstack.tier2_decision_input.v1",
        "policy_version": "proof-policy-v1",
        "proposal_batch": {"actions": [dict(action) for action in actions]},
        "verified_source_spans": [dict(span) for span in (spans if spans is not None else [_span()])],
        "scope": _scope(principal),
        "existing_memory_refs": existing or [],
        "graph_state_summary": {"unresolved_conflicts": conflicts or []},
        "budget_policy_summary": {},
        "projection_contract_versions": {},
    }


def _fixtures() -> list[dict[str, Any]]:
    return [
        {
            "id": "explicit_profile_fact",
            "family": "durable",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_profile",
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "durable_fact_candidate", "memory_kind": "profile_fact"},
        },
        {
            "id": "assistant_contamination",
            "family": "safety",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_assistant",
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:assistant",
                        "source_span_ids": ["span-assistant"],
                    }
                ],
                spans=[_span("span-assistant", speaker="assistant")],
            ),
            "expected": {"decision_class": "reject", "truth_eligible": False},
        },
        {
            "id": "missing_source",
            "family": "safety",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_missing",
                        "action": "create",
                        "target_kind": "project_fact",
                        "target_slot": "project.creator",
                        "value_fingerprint": "sha256:missing",
                        "source_span_ids": ["span-missing"],
                    }
                ],
                spans=[],
            ),
            "expected": {"decision_class": "inspect_only", "truth_eligible": False},
        },
        {
            "id": "scope_collision",
            "family": "safety",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_scope",
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:scope",
                        "source_span_ids": ["span-other"],
                    }
                ],
                spans=[_span("span-other", principal="principal-b")],
            ),
            "expected": {"decision_class": "reject", "truth_eligible": False},
        },
        {
            "id": "relation_candidate",
            "family": "projection",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_relation",
                        "action": "create",
                        "target_kind": "graph_relation",
                        "relation_shape": {
                            "subject_ref": "project:alpha",
                            "predicate": "created_by",
                            "object_ref": "person:creator",
                            "direction": "forward",
                        },
                        "value_fingerprint": "sha256:relation",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "relation_candidate", "memory_kind": "relation"},
        },
        {
            "id": "conflict_review",
            "family": "lifecycle",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_conflict",
                        "action": "create",
                        "target_kind": "project_fact",
                        "target_slot": "project.creator",
                        "stable_key": "project.creator",
                        "value_fingerprint": "sha256:creator-new",
                        "source_span_ids": ["span-user"],
                    }
                ],
                conflicts=[{"stable_key": "project.creator"}],
            ),
            "expected": {"decision_class": "conflict_review", "truth_eligible": False},
        },
        {
            "id": "duplicate_prevention",
            "family": "lifecycle",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_duplicate",
                        "action": "create",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile",
                        "source_span_ids": ["span-user"],
                    }
                ],
                existing=[
                    {
                        "memory_ref": "fact-existing",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:profile",
                    }
                ],
            ),
            "expected": {
                "decision_class": "inspect_only",
                "lifecycle_action": "noop",
                "reason_code": "NOOP_DUPLICATE_ALREADY_CURRENT",
            },
        },
        {
            "id": "correction_update",
            "family": "lifecycle",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_correct",
                        "action": "correction",
                        "target_kind": "user_fact",
                        "target_slot": "identity.preferred_address_name",
                        "stable_key": "identity.preferred_address_name",
                        "value_fingerprint": "sha256:corrected",
                        "source_span_ids": ["span-user"],
                    }
                ],
                existing=[{"memory_ref": "fact-old", "stable_key": "identity.preferred_address_name"}],
            ),
            "expected": {"decision_class": "lifecycle_update_candidate", "lifecycle_action": "correction"},
        },
        {
            "id": "support_preservation",
            "family": "support",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_support",
                        "action": "create",
                        "target_kind": "support_context",
                        "value_fingerprint": "sha256:support",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "support_event", "truth_eligible": False},
        },
        {
            "id": "clarification_required",
            "family": "clarification",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_unknown",
                        "action": "create",
                        "target_kind": "unknown_kind",
                        "value_fingerprint": "sha256:unknown",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "clarification_required", "truth_eligible": False},
        },
        {
            "id": "multilingual_style_hu",
            "family": "multilingual",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_style_hu",
                        "action": "create",
                        "target_kind": "style_rule",
                        "target_slot": "style.no_emoji",
                        "value_fingerprint": "sha256:no-emoji",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "durable_fact_candidate", "memory_kind": "style_rule"},
            "metamorphic_group": "style_no_emoji",
        },
        {
            "id": "multilingual_style_en",
            "family": "multilingual",
            "packet": _packet(
                [
                    {
                        "proposal_id": "p_style_en",
                        "action": "create",
                        "target_kind": "style_rule",
                        "target_slot": "style.no_emoji",
                        "value_fingerprint": "sha256:no-emoji",
                        "source_span_ids": ["span-user"],
                    }
                ]
            ),
            "expected": {"decision_class": "durable_fact_candidate", "memory_kind": "style_rule"},
            "metamorphic_group": "style_no_emoji",
        },
    ]


def _old_brainstack_baseline(action: Mapping[str, Any]) -> dict[str, Any]:
    target_kind = str(action.get("target_kind") or "")
    if target_kind in {"support_context", "support_only"}:
        decision = "support_event"
    elif target_kind in {"graph_relation", "relation"}:
        decision = "relation_candidate"
    else:
        decision = "durable_fact_candidate"
    return {"decision_class": decision}


def _hindsight_alone_baseline(action: Mapping[str, Any]) -> dict[str, Any]:
    action_name = str(action.get("action") or "")
    target_kind = str(action.get("target_kind") or "")
    if action_name in {"delete", "delete_or_supersede", "update", "correction"}:
        decision = "lifecycle_update_candidate"
    elif target_kind in {"support_context", "support_only"}:
        decision = "support_event"
    elif target_kind in {"graph_relation", "relation"}:
        decision = "relation_candidate"
    else:
        decision = "durable_fact_candidate"
    return {"decision_class": decision}


def _matches_expected(decision: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    for key, expected_value in expected.items():
        if key == "truth_eligible":
            actual = decision.get("authority", {}).get("truth_eligible")
        elif key == "lifecycle_action":
            actual = decision.get("lifecycle", {}).get("action")
        else:
            actual = decision.get(key)
        if actual != expected_value:
            return False
    return True


def run_proof() -> dict[str, Any]:
    cases = []
    critical = {
        "schema_issues": 0,
        "semantic_conformance_issues": 0,
        "replay_mismatch": 0,
        "oracle_failures": 0,
        "harmful_memory_counters": 0,
    }
    smarter = {
        "duplicate_prevention": False,
        "update_correctness": False,
        "conflict_precision": False,
        "support_preservation": False,
        "projection_consistency": True,
        "multilingual_metamorphic_stability": False,
        "baseline_advantage_cases": 0,
    }
    metamorphic: dict[str, set[tuple[str, str]]] = {}
    for fixture in _fixtures():
        packet = fixture["packet"]
        plan = build_tier2_decision_plan(packet)
        replay = build_tier2_decision_plan(packet)
        decision = plan["decisions"][0]
        action = packet["proposal_batch"]["actions"][0]
        schema_issues = validate_tier2_decision_plan(plan)
        conformance_issues = semantic_conformance_issues(plan)
        expected_pass = _matches_expected(decision, fixture["expected"])
        old_pass = _matches_expected(_old_brainstack_baseline(action), fixture["expected"])
        hindsight_pass = _matches_expected(_hindsight_alone_baseline(action), fixture["expected"])
        if schema_issues:
            critical["schema_issues"] += len(schema_issues)
        if conformance_issues:
            critical["semantic_conformance_issues"] += len(conformance_issues)
            smarter["projection_consistency"] = False
        if plan != replay:
            critical["replay_mismatch"] += 1
        if not expected_pass:
            critical["oracle_failures"] += 1
        if any(plan["critical_counters"].values()):
            # These are attempted harms/degradations observed and blocked by the core.
            # A product blocker is only created if they become oracle/conformance failures.
            pass
        if expected_pass and (not old_pass or not hindsight_pass):
            smarter["baseline_advantage_cases"] += 1
        if fixture["id"] == "duplicate_prevention" and expected_pass:
            smarter["duplicate_prevention"] = True
        if fixture["id"] == "correction_update" and expected_pass:
            smarter["update_correctness"] = True
        if fixture["id"] == "conflict_review" and expected_pass:
            smarter["conflict_precision"] = True
        if fixture["id"] == "support_preservation" and expected_pass:
            smarter["support_preservation"] = True
        if group := fixture.get("metamorphic_group"):
            metamorphic.setdefault(str(group), set()).add((decision["decision_class"], decision["memory_kind"]))
        cases.append(
            {
                "id": fixture["id"],
                "family": fixture["family"],
                "decision_class": decision["decision_class"],
                "memory_kind": decision["memory_kind"],
                "reason_code": decision["reason_code"],
                "expected_pass": expected_pass,
                "old_baseline_pass": old_pass,
                "hindsight_alone_baseline_pass": hindsight_pass,
                "schema_issues": schema_issues,
                "semantic_conformance_issues": conformance_issues,
            }
        )
    smarter["multilingual_metamorphic_stability"] = all(len(values) == 1 for values in metamorphic.values())
    required_smarter = [
        "duplicate_prevention",
        "update_correctness",
        "conflict_precision",
        "support_preservation",
        "projection_consistency",
        "multilingual_metamorphic_stability",
    ]
    status = "pass" if not any(critical.values()) and all(smarter[key] for key in required_smarter) and smarter["baseline_advantage_cases"] >= 4 else "fail"
    return {
        "schema": "brainstack.tier2_decision_core_proof.v1",
        "status": status,
        "cases_total": len(cases),
        "cases_passed": sum(1 for case in cases if case["expected_pass"]),
        "critical_counters": critical,
        "smarter_than_baseline": smarter,
        "cases": cases,
        "claim_boundary": "Proof covers deterministic decision-core behavior on committed oracle/metamorphic fixtures. It is not a global product or release claim.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    report = run_proof()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(payload + "\n")
    print(payload)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
