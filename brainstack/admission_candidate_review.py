"""Agent-facing admission candidate review.

This module is a thin read-only facade over the Tier2 decision core. It helps
the agent route structured memory candidates to the existing explicit admission
path without creating a second truth writer or a hidden governor.
"""

from __future__ import annotations

from typing import Any, Mapping

from .admission_policy import canonical_profile_slot
from .profile_contract import normalize_profile_slot
from .tier2_decision_core import (
    build_tier2_decision_plan,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)


ADMISSION_CANDIDATE_REVIEW_SCHEMA = "brainstack.admission_candidate_review.v1"

_OPERATING_RECORD_TYPE_BY_TARGET_SLOT = {
    "operating.current_commitment": "current_commitment",
    "operating.next_step": "next_step",
    "operating.live_system_state": "live_system_state",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _source_role(action: Mapping[str, Any]) -> str:
    return _text(action.get("assertion_speaker") or action.get("source_role") or "unknown").lower()


def _normalized_actions(actions: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(actions):
        if not isinstance(raw, Mapping):
            continue
        source_span_id = _text(raw.get("source_span_id"))
        source_event_id = _text(raw.get("source_event_id"))
        action = {
            "proposal_id": _text(raw.get("proposal_id")) or f"candidate:{index}",
            "action": _text(raw.get("action")) or "create",
            "target_kind": _text(raw.get("target_kind")),
            "target_slot": _text(raw.get("target_slot")),
            "stable_key": _text(raw.get("stable_key") or raw.get("target_slot")),
            "source_span_ids": [source_span_id] if source_span_id else [],
            "source_event_ids": [source_event_id] if source_event_id else [],
            "assertion_speaker": _source_role(raw),
            "source_role": _source_role(raw),
            "value_fingerprint": _text(raw.get("value_fingerprint") or raw.get("normalized_value_hash")),
            "normalized_value_hash": _text(raw.get("normalized_value_hash") or raw.get("value_fingerprint")),
        }
        relation = raw.get("relation_shape")
        if isinstance(relation, Mapping):
            action["relation_shape"] = dict(relation)
        normalized.append(action)
    return normalized


def _source_spans(
    actions: list[Mapping[str, Any]],
    *,
    tenant_id: str,
    principal_scope_key: str,
    workspace_scope_key: str,
    session_id: str,
    project_id: str,
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    seen: set[str] = set()
    for action in actions:
        source_span_id = _text(action.get("source_span_id"))
        source_event_id = _text(action.get("source_event_id"))
        if not source_span_id or source_span_id in seen:
            continue
        seen.add(source_span_id)
        role = _source_role(action)
        spans.append(
            {
                "source_span_id": source_span_id,
                "source_event_id": source_event_id,
                "speaker": role,
                "assertion_speaker": role,
                "source_modality": _text(action.get("source_modality") or "conversation"),
                "scope": {
                    "tenant_id": tenant_id,
                    "principal_scope_key": principal_scope_key,
                    "workspace_scope_key": workspace_scope_key,
                    "session_id": session_id,
                    "project_id": project_id,
                },
            }
        )
    return spans


def _storage_key_for_profile(target_slot: str, stable_key: str) -> str:
    normalized_key = normalize_profile_slot(stable_key)
    if normalized_key:
        return normalized_key
    slot = _text(target_slot)
    if slot.startswith(("identity.", "preference.", "reference.")):
        return slot.replace(".", ":", 1)
    return slot


def _category_for_profile(target_slot: str, stable_key: str) -> str:
    slot = canonical_profile_slot(stable_key or target_slot)
    return _text(slot.split(".", 1)[0] if "." in slot else slot.split(":", 1)[0]) or "profile"


def _decision_source_role(decision: Mapping[str, Any]) -> str:
    return _text(_mapping(decision.get("source")).get("assertion_speaker")).lower()


def _suggested_write(action: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    authority = _mapping(decision.get("authority"))
    if not bool(authority.get("truth_eligible")):
        return {"available": False, "reason_code": "CANDIDATE_NOT_TRUTH_ELIGIBLE"}
    if _decision_source_role(decision) != "user":
        return {"available": False, "reason_code": "MODEL_CALLABLE_WRITE_REQUIRES_USER_SOURCE"}
    memory_kind = _text(decision.get("memory_kind"))
    normalized = _mapping(decision.get("normalized_candidate"))
    target_slot = _text(normalized.get("target_slot") or action.get("target_slot"))
    stable_key = _text(action.get("stable_key") or target_slot)
    content = _text(action.get("content") or action.get("title") or action.get("normalized_value"))
    base = {
        "available": True,
        "tool": "brainstack_remember",
        "source_role": "user",
        "admitted_truth_after_write_only": True,
    }
    if memory_kind in {"profile_fact", "style_rule"}:
        return {
            **base,
            "shelf": "profile",
            "stable_key": _storage_key_for_profile(target_slot, stable_key),
            "category": _category_for_profile(target_slot, stable_key),
            "content_preview": content[:240],
        }
    if memory_kind == "task_memory":
        return {
            **base,
            "shelf": "task",
            "stable_key": stable_key,
            "title_preview": content[:240],
            "status": "open",
        }
    if memory_kind == "operating_memory":
        record_type = _OPERATING_RECORD_TYPE_BY_TARGET_SLOT.get(target_slot, "")
        return {
            **base,
            "shelf": "operating",
            "stable_key": stable_key,
            "record_type": record_type,
            "content_preview": content[:240],
            "missing_required_fields": [] if record_type else ["record_type"],
        }
    return {"available": False, "reason_code": "NO_MODEL_CALLABLE_WRITE_FOR_MEMORY_KIND"}


def _agent_next_action(decision: Mapping[str, Any]) -> str:
    decision_class = _text(decision.get("decision_class"))
    authority = _mapping(decision.get("authority"))
    if decision_class in {"durable_fact_candidate", "lifecycle_update_candidate", "relation_candidate"} and bool(
        authority.get("truth_eligible")
    ):
        if _decision_source_role(decision) != "user":
            return "requires_trusted_host_admission_path"
        return "explicit_user_can_commit_with_brainstack_remember"
    if decision_class == "conflict_review":
        return "requires_operator_conflict_review"
    if decision_class == "clarification_required":
        return "ask_user_to_clarify_memory_target"
    if decision_class == "support_event":
        return "support_only_do_not_write_truth"
    if decision_class == "reject":
        return "reject_do_not_write"
    return "inspect_only_do_not_write_truth"


def build_admission_candidate_review(
    *,
    actions: list[Any],
    principal_scope_key: str,
    tenant_id: str = "local",
    workspace_scope_key: str = "",
    session_id: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    normalized_actions = _normalized_actions(actions)
    scope = {
        "tenant_id": _text(tenant_id) or "local",
        "principal_scope_key": _text(principal_scope_key),
        "workspace_scope_key": _text(workspace_scope_key),
        "session_id": _text(session_id),
        "project_id": _text(project_id),
    }
    source_spans = _source_spans(
        [raw for raw in actions if isinstance(raw, Mapping)],
        tenant_id=scope["tenant_id"],
        principal_scope_key=scope["principal_scope_key"],
        workspace_scope_key=scope["workspace_scope_key"],
        session_id=scope["session_id"],
        project_id=scope["project_id"],
    )
    plan = build_tier2_decision_plan(
        {
            "schema": "brainstack.tier2_decision_input.v1",
            "policy_version": "brainstack.agent_admission_candidate_review.v1",
            "scope": scope,
            "verified_source_spans": source_spans,
            "existing_memory_refs": [],
            "graph_state_summary": {"unresolved_conflicts": []},
            "proposal_batch": {"actions": normalized_actions},
        }
    )
    issues = validate_tier2_decision_plan(plan) + semantic_conformance_issues(plan)
    review_items: list[dict[str, Any]] = []
    for action, decision in zip(normalized_actions, _list(plan.get("decisions")), strict=False):
        if not isinstance(decision, Mapping):
            continue
        review_items.append(
            {
                "candidate_id": _text(decision.get("candidate_id")),
                "proposal_id": _text(decision.get("proposal_id")),
                "decision_class": _text(decision.get("decision_class")),
                "reason_code": _text(decision.get("reason_code")),
                "memory_kind": _text(decision.get("memory_kind")),
                "truth_eligible": bool(_mapping(decision.get("authority")).get("truth_eligible")),
                "support_visibility": _text(_mapping(decision.get("authority")).get("support_visibility")),
                "candidate_is_durable_truth_now": False,
                "agent_next_action": _agent_next_action(decision),
                "suggested_write": _suggested_write(action, decision),
                "trace_safe": True,
            }
        )
    return {
        "schema": ADMISSION_CANDIDATE_REVIEW_SCHEMA,
        "status": "pass" if not issues else "fail",
        "read_only": True,
        "side_effect": False,
        "durable_write_performed": False,
        "second_truth_authority_created": False,
        "candidate_count": len(review_items),
        "issues": issues,
        "review_items": review_items,
        "summary": {
            "eligible_for_explicit_admission_count": sum(
                1
                for item in review_items
                if item["agent_next_action"] == "explicit_user_can_commit_with_brainstack_remember"
            ),
            "blocked_or_inspect_only_count": sum(
                1
                for item in review_items
                if item["agent_next_action"] != "explicit_user_can_commit_with_brainstack_remember"
            ),
        },
        "model_use_contract": {
            "candidate_is_not_truth_until_explicit_write_receipt": True,
            "use_brainstack_remember_only_for_explicit_user_approved_writes": True,
            "do_not_execute_schedule_or_notify": True,
            "do_not_infer_current_assignment_from_candidate": True,
        },
    }
