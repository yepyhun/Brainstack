from __future__ import annotations

import ast
from pathlib import Path

from brainstack.tier2_decision_core import (
    build_tier2_decision_plan,
    render_ten_line_decision_trace,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)


def _input(actions, *, spans=None, existing=None, conflicts=None):
    scope = {
        "tenant_id": "local",
        "principal_scope_key": "principal-a",
        "workspace_scope_key": "workspace-a",
        "session_id": "session-a",
        "project_id": "project-a",
    }
    return {
        "schema": "brainstack.tier2_decision_input.v1",
        "policy_version": "test-policy-v1",
        "proposal_batch": {"actions": actions},
        "verified_source_spans": spans
        if spans is not None
        else [
            {
                "source_span_id": "span-user-1",
                "source_event_id": "event-user-1",
                "speaker": "user",
                "assertion_speaker": "user",
                "source_modality": "conversation",
                "scope": scope,
            }
        ],
        "scope": scope,
        "existing_memory_refs": existing or [],
        "graph_state_summary": {"unresolved_conflicts": conflicts or []},
        "budget_policy_summary": {},
        "projection_contract_versions": {},
    }


def test_decision_core_is_deterministic_for_same_input() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-1",
                "action": "create",
                "target_kind": "user_fact",
                "target_slot": "identity.preferred_address_name",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-user-1"],
            }
        ]
    )

    plan_a = build_tier2_decision_plan(packet)
    plan_b = build_tier2_decision_plan(packet)

    assert plan_a == plan_b
    assert validate_tier2_decision_plan(plan_a) == []
    assert semantic_conformance_issues(plan_a) == []
    decision = plan_a["decisions"][0]
    assert decision["decision_class"] == "durable_fact_candidate"
    assert decision["authority"]["truth_eligible"] is True
    assert decision["receipt_requirement"]["coverage"] == "durable_write"
    assert len(render_ten_line_decision_trace(decision)) == 10


def test_decision_core_rejects_assistant_authored_truth_attempt() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-assistant",
                "action": "create",
                "target_kind": "user_fact",
                "target_slot": "identity.preferred_address_name",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-assistant-1"],
            }
        ],
        spans=[
            {
                "source_span_id": "span-assistant-1",
                "source_event_id": "event-assistant-1",
                "speaker": "assistant",
                "assertion_speaker": "assistant",
                "source_modality": "conversation",
                "scope": {
                    "tenant_id": "local",
                    "principal_scope_key": "principal-a",
                    "workspace_scope_key": "workspace-a",
                    "session_id": "session-a",
                },
            }
        ],
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "reject"
    assert decision["authority"]["truth_eligible"] is False
    assert plan["critical_counters"]["assistant_truth_attempt"] == 1
    assert decision["reason_code"] == "REJECTED_ASSISTANT_AUTHORED_TRUTH_ATTEMPT"
    assert semantic_conformance_issues(plan) == []


def test_decision_core_missing_verified_source_is_inspect_only() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-missing-source",
                "action": "create",
                "target_kind": "project_fact",
                "target_slot": "project.creator",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-missing"],
            }
        ],
        spans=[],
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "inspect_only"
    assert decision["authority"]["truth_eligible"] is False
    assert plan["critical_counters"]["missing_verified_source"] == 1
    assert semantic_conformance_issues(plan) == []


def test_decision_core_relation_candidate_preserves_shape() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-relation",
                "action": "create",
                "target_kind": "graph_relation",
                "relation_shape": {
                    "subject_ref": "project:alpha",
                    "predicate": "created_by",
                    "object_ref": "person:creator",
                    "direction": "forward",
                },
                "value_fingerprint": "sha256:relation",
                "source_span_ids": ["span-user-1"],
            }
        ]
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "relation_candidate"
    assert decision["memory_kind"] == "relation"
    assert decision["normalized_candidate"]["relation_shape"]["predicate"] == "created_by"
    assert decision["receipt_requirement"]["coverage"] == "relation_write"


def test_decision_core_conflict_review_is_not_answer_evidence() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-conflict",
                "action": "create",
                "target_kind": "project_fact",
                "target_slot": "project.creator",
                "value_fingerprint": "sha256:new",
                "source_span_ids": ["span-user-1"],
            }
        ],
        conflicts=[{"target_slot": "project.creator"}],
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "conflict_review"
    assert decision["authority"]["truth_eligible"] is False
    assert decision["authority"]["support_visibility"] == "contradiction_only"
    assert decision["receipt_requirement"]["coverage"] == "operator_resolution"
    assert semantic_conformance_issues(plan) == []


def test_decision_core_unknown_kind_requires_clarification() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-unknown",
                "action": "create",
                "target_kind": "mystery",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-user-1"],
            }
        ]
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "clarification_required"
    assert decision["authority"]["truth_eligible"] is False
    assert decision["reason_code"] == "CLARIFICATION_REQUIRED_MEMORY_KIND_AMBIGUOUS"


def test_decision_core_duplicate_create_becomes_noop_inspect_only() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-duplicate",
                "action": "create",
                "target_kind": "user_fact",
                "target_slot": "identity.preferred_address_name",
                "stable_key": "identity.preferred_address_name",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-user-1"],
            }
        ],
        existing=[
            {
                "memory_ref": "fact-existing",
                "stable_key": "identity.preferred_address_name",
                "value_fingerprint": "sha256:value",
            }
        ],
    )

    plan = build_tier2_decision_plan(packet)
    decision = plan["decisions"][0]

    assert decision["decision_class"] == "inspect_only"
    assert decision["lifecycle"]["action"] == "noop"
    assert decision["authority"]["truth_eligible"] is False
    assert decision["reason_code"] == "NOOP_DUPLICATE_ALREADY_CURRENT"


def test_decision_core_has_no_forbidden_imports() -> None:
    module_path = Path("brainstack/tier2_decision_core.py")
    tree = ast.parse(module_path.read_text())
    forbidden_roots = {
        "provider",
        "storage",
        "graph_backend",
        "retrieval",
        "packet",
        "hindsight_public_api_bridge",
        "hindsight_hermes_llm_proxy",
    }
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(any(part == forbidden for part in name.split(".")) for name in imports for forbidden in forbidden_roots)


def test_decision_plan_contains_no_free_form_metadata_key() -> None:
    packet = _input(
        [
            {
                "proposal_id": "proposal-1",
                "action": "create",
                "target_kind": "support_context",
                "value_fingerprint": "sha256:value",
                "source_span_ids": ["span-user-1"],
            }
        ]
    )

    plan = build_tier2_decision_plan(packet)

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    assert "metadata" not in set(walk(plan))
