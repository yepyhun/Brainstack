from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

TIER2_DECISION_CORE_VERSION = "brainstack.tier2_decision_core.v1"
TIER2_DECISION_INPUT_SCHEMA = "brainstack.tier2_decision_input.v1"
TIER2_DECISION_PLAN_SCHEMA = "brainstack.tier2_decision_plan.v1"

DECISION_CLASSES = {
    "reject",
    "inspect_only",
    "support_event",
    "durable_fact_candidate",
    "relation_candidate",
    "conflict_review",
    "lifecycle_update_candidate",
    "clarification_required",
}

MEMORY_KINDS = {
    "profile_fact",
    "style_rule",
    "project_fact",
    "reference",
    "task_memory",
    "operating_memory",
    "relation",
    "temporal_event",
    "support_context",
    "unknown",
}

TRUTH_AUTHORITY_SPEAKERS = {"user", "tool", "runtime", "operator", "trusted_host"}
ASSISTANT_SPEAKERS = {"assistant", "quoted_assistant"}

TARGET_KIND_TO_MEMORY_KIND = {
    "user_fact": "profile_fact",
    "profile_fact": "profile_fact",
    "style_rule": "style_rule",
    "preference": "style_rule",
    "project_fact": "project_fact",
    "reference": "reference",
    "task_memory": "task_memory",
    "operating_memory": "operating_memory",
    "graph_relation": "relation",
    "relation": "relation",
    "temporal_event": "temporal_event",
    "support_context": "support_context",
    "support_only": "support_context",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _has_source_refs(action: Mapping[str, Any]) -> bool:
    return bool(_list(action.get("source_span_ids"))) and bool(_list(action.get("source_event_ids")))


def _hash_json(value: Any, *, length: int = 32) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _scope(input_packet: Mapping[str, Any]) -> dict[str, str]:
    scope = _mapping(input_packet.get("scope"))
    return {
        "tenant_id": _text(scope.get("tenant_id") or "local"),
        "principal_scope_key": _text(scope.get("principal_scope_key")),
        "workspace_scope_key": _text(scope.get("workspace_scope_key")),
        "session_id": _text(scope.get("session_id")),
        "project_id": _text(scope.get("project_id")),
    }


def _source_index(input_packet: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    spans: dict[str, Mapping[str, Any]] = {}
    for span in _list(input_packet.get("verified_source_spans")):
        if isinstance(span, Mapping):
            span_id = _text(span.get("source_span_id"))
            if span_id:
                spans[span_id] = span
    return spans


def _action_source(action: Mapping[str, Any], spans: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    source_span_ids = [_text(item) for item in _list(action.get("source_span_ids")) if _text(item)]
    source_event_ids = [_text(item) for item in _list(action.get("source_event_ids")) if _text(item)]
    matched_spans = [spans[item] for item in source_span_ids if item in spans]
    blocked_by: list[str] = []
    if not source_span_ids or not matched_spans:
        blocked_by.append("REJECTED_MISSING_VERIFIED_SOURCE_SPAN")
    first_span = matched_spans[0] if matched_spans else {}
    assertion_speaker = _text(
        first_span.get("assertion_speaker")
        or first_span.get("speaker")
        or action.get("assertion_speaker")
        or action.get("source_role")
        or "unknown"
    ).lower()
    if not source_event_ids and first_span:
        event_id = _text(first_span.get("source_event_id"))
        if event_id:
            source_event_ids = [event_id]
    if not source_event_ids:
        blocked_by.append("REJECTED_MISSING_VERIFIED_SOURCE_EVENT")
    return (
        {
            "source_event_ids": source_event_ids,
            "source_span_ids": source_span_ids,
            "assertion_speaker": assertion_speaker or "unknown",
            "source_modality": _text(first_span.get("source_modality") or "conversation"),
        },
        blocked_by,
    )


def _scope_blockers(source: Mapping[str, Any], spans: Mapping[str, Mapping[str, Any]], scope: Mapping[str, str]) -> list[str]:
    blockers: list[str] = []
    for span_id in _list(source.get("source_span_ids")):
        span = _mapping(spans.get(_text(span_id)))
        span_scope = _mapping(span.get("scope"))
        if not span_scope:
            continue
        for key in ("tenant_id", "principal_scope_key", "workspace_scope_key", "session_id"):
            expected = _text(scope.get(key))
            actual = _text(span_scope.get(key))
            if expected and actual and expected != actual:
                blockers.append("REJECTED_SCOPE_MISMATCH")
                return blockers
    return blockers


def _memory_kind(action: Mapping[str, Any]) -> str:
    target_kind = _text(action.get("target_kind")).lower()
    return TARGET_KIND_TO_MEMORY_KIND.get(target_kind, "unknown")


def _relation_shape(action: Mapping[str, Any], memory_kind: str) -> dict[str, str]:
    relation = _mapping(action.get("relation_shape"))
    if relation:
        return {
            "subject_ref": _text(relation.get("subject_ref")),
            "predicate": _text(relation.get("predicate")),
            "object_ref": _text(relation.get("object_ref")),
            "direction": _text(relation.get("direction") or "forward"),
        }
    if memory_kind == "relation":
        return {
            "subject_ref": _text(action.get("subject_ref")),
            "predicate": _text(action.get("predicate") or action.get("target_slot")),
            "object_ref": _text(action.get("object_ref")),
            "direction": _text(action.get("direction") or "forward"),
        }
    return {"subject_ref": "", "predicate": "", "object_ref": "", "direction": "none"}


def _existing_matches(input_packet: Mapping[str, Any], action: Mapping[str, Any]) -> list[str]:
    stable_key = _text(action.get("stable_key") or action.get("target_slot"))
    value_fingerprint = _text(action.get("value_fingerprint") or action.get("normalized_value_hash"))
    matches: list[str] = []
    for ref in _list(input_packet.get("existing_memory_refs")):
        if not isinstance(ref, Mapping):
            continue
        ref_key = _text(ref.get("stable_key") or ref.get("target_slot") or ref.get("relation_id"))
        ref_value = _text(ref.get("value_fingerprint") or ref.get("normalized_value_hash"))
        if stable_key and ref_key == stable_key:
            if not value_fingerprint or not ref_value or ref_value == value_fingerprint:
                matches.append(_text(ref.get("memory_ref") or ref.get("stable_fact_id") or ref_key))
    return [item for item in matches if item]


def _has_conflict(input_packet: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    stable_key = _text(action.get("stable_key") or action.get("target_slot") or action.get("predicate"))
    graph_state = _mapping(input_packet.get("graph_state_summary"))
    for conflict in _list(graph_state.get("unresolved_conflicts")) + _list(graph_state.get("conflicts")):
        if not isinstance(conflict, Mapping):
            continue
        conflict_key = _text(conflict.get("stable_key") or conflict.get("target_slot") or conflict.get("predicate"))
        if stable_key and conflict_key == stable_key:
            return True
    return False


def _authority(source: Mapping[str, Any], blocked_by: list[str], memory_kind: str) -> dict[str, Any]:
    speaker = _text(source.get("assertion_speaker")).lower()
    if speaker in ASSISTANT_SPEAKERS:
        blocked_by.append("REJECTED_ASSISTANT_AUTHORED_TRUTH_ATTEMPT")
        return {
            "authority_class": "assistant_claim",
            "truth_eligible": False,
            "support_visibility": "inspect_only",
        }
    if (
        "REJECTED_MISSING_VERIFIED_SOURCE_SPAN" in blocked_by
        or "REJECTED_MISSING_VERIFIED_SOURCE_EVENT" in blocked_by
        or "REJECTED_SCOPE_MISMATCH" in blocked_by
    ):
        return {
            "authority_class": "donor_proposal",
            "truth_eligible": False,
            "support_visibility": "inspect_only",
        }
    if speaker in TRUTH_AUTHORITY_SPEAKERS and memory_kind != "support_context":
        authority_class = "user_explicit" if speaker == "user" else speaker
        return {
            "authority_class": authority_class,
            "truth_eligible": True,
            "support_visibility": "answer_evidence",
        }
    if memory_kind == "support_context":
        return {
            "authority_class": "support_only",
            "truth_eligible": False,
            "support_visibility": "support_context",
        }
    blocked_by.append("REJECTED_ASSERTION_SPEAKER_NOT_TRUTH_AUTHORITY")
    return {
        "authority_class": "unknown",
        "truth_eligible": False,
        "support_visibility": "inspect_only",
    }


def _lifecycle(input_packet: Mapping[str, Any], action: Mapping[str, Any], decision_class: str, matches: list[str]) -> dict[str, Any]:
    raw_action = _text(action.get("action")).lower()
    if decision_class in {"reject", "inspect_only", "clarification_required", "support_event"}:
        lifecycle_action = "reject" if decision_class == "reject" else "noop"
    elif decision_class == "conflict_review":
        lifecycle_action = "conflict_review"
    elif decision_class == "lifecycle_update_candidate":
        if raw_action in {"delete", "delete_or_supersede", "supersede"}:
            lifecycle_action = "supersession"
        elif raw_action in {"correct", "correction"}:
            lifecycle_action = "correction"
        elif raw_action in {"invalidate", "invalidation"}:
            lifecycle_action = "invalidation"
        elif raw_action in {"expire", "expiration"}:
            lifecycle_action = "expiration"
        elif raw_action in {"merge_alias", "alias_merge"}:
            lifecycle_action = "alias_merge"
        else:
            lifecycle_action = "update"
    elif matches and raw_action in {"create", "retain"}:
        lifecycle_action = "noop"
    elif matches:
        lifecycle_action = "update"
    else:
        lifecycle_action = "create"
    return {"action": lifecycle_action, "target_refs": matches}


def _semantic_value(decision_class: str, memory_kind: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    truth_eligible = bool(authority.get("truth_eligible"))
    if truth_eligible and decision_class in {"durable_fact_candidate", "relation_candidate", "lifecycle_update_candidate"}:
        if memory_kind in {"profile_fact", "style_rule"}:
            value_class = "stable_preference" if memory_kind == "style_rule" else "authority_critical"
            budget_hint = "always_active_candidate"
        elif memory_kind == "project_fact":
            value_class = "project_core_fact"
            budget_hint = "task_relevant_candidate"
        elif memory_kind in {"relation", "temporal_event"}:
            value_class = "temporal_context"
            budget_hint = "task_relevant_candidate"
        else:
            value_class = "authority_critical"
            budget_hint = "task_relevant_candidate"
        return {
            "semantic_value_class": value_class,
            "projection_budget_hint": budget_hint,
            "authority_critical": True,
        }
    if decision_class == "support_event":
        return {
            "semantic_value_class": "support_context",
            "projection_budget_hint": "retrieval_only",
            "authority_critical": False,
        }
    return {
        "semantic_value_class": "unknown" if decision_class == "clarification_required" else "low_value_noise",
        "projection_budget_hint": "inspect_only" if decision_class != "reject" else "archived",
        "authority_critical": False,
    }


def _receipt_requirement(decision_class: str) -> dict[str, Any]:
    if decision_class == "durable_fact_candidate":
        return {"required": True, "coverage": "durable_write"}
    if decision_class == "relation_candidate":
        return {"required": True, "coverage": "relation_write"}
    if decision_class == "lifecycle_update_candidate":
        return {"required": True, "coverage": "durable_write"}
    if decision_class == "conflict_review":
        return {"required": True, "coverage": "operator_resolution"}
    if decision_class == "support_event":
        return {"required": False, "coverage": "source_span"}
    return {"required": False, "coverage": "none"}


def _authority_for_decision(decision_class: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    adjusted = dict(authority)
    if decision_class in {"reject", "inspect_only", "clarification_required"}:
        adjusted["truth_eligible"] = False
        adjusted["support_visibility"] = "inspect_only"
    elif decision_class == "support_event":
        adjusted["truth_eligible"] = False
        adjusted["support_visibility"] = "support_context"
    elif decision_class == "conflict_review":
        adjusted["truth_eligible"] = False
        adjusted["support_visibility"] = "contradiction_only"
    return adjusted


def _decision_class(
    input_packet: Mapping[str, Any],
    action: Mapping[str, Any],
    memory_kind: str,
    authority: Mapping[str, Any],
    blocked_by: list[str],
    matches: list[str],
) -> str:
    target_slot = _text(action.get("target_slot"))
    relation_shape = _relation_shape(action, memory_kind)
    raw_action = _text(action.get("action")).lower()
    if "REJECTED_ASSISTANT_AUTHORED_TRUTH_ATTEMPT" in blocked_by:
        return "reject"
    if "REJECTED_SCOPE_MISMATCH" in blocked_by:
        return "reject"
    if (
        "REJECTED_MISSING_VERIFIED_SOURCE_SPAN" in blocked_by
        or "REJECTED_MISSING_VERIFIED_SOURCE_EVENT" in blocked_by
    ):
        return "inspect_only"
    if memory_kind == "unknown":
        return "clarification_required"
    if memory_kind != "relation" and not target_slot and memory_kind not in {"support_context"}:
        return "clarification_required"
    if memory_kind == "relation" and not all((relation_shape["subject_ref"], relation_shape["predicate"], relation_shape["object_ref"])):
        return "clarification_required"
    if memory_kind == "support_context":
        return "support_event"
    if raw_action in {"ignore", "failed_batch"}:
        return "inspect_only"
    if not bool(authority.get("truth_eligible")):
        return "inspect_only"
    if matches and raw_action in {"create", "retain"}:
        return "inspect_only"
    if _has_conflict(input_packet, action):
        return "conflict_review"
    if raw_action in {"update", "delete", "delete_or_supersede", "supersede", "correct", "correction", "invalidate", "invalidation", "expire", "expiration", "merge_alias", "alias_merge"}:
        return "lifecycle_update_candidate"
    if memory_kind == "relation":
        return "relation_candidate"
    return "durable_fact_candidate"


def _reason_code(
    decision_class: str,
    memory_kind: str,
    blocked_by: list[str],
    authority: Mapping[str, Any],
    lifecycle: Mapping[str, Any],
) -> str:
    if blocked_by:
        return blocked_by[0]
    if decision_class == "inspect_only" and lifecycle.get("action") == "noop" and _list(lifecycle.get("target_refs")):
        return "NOOP_DUPLICATE_ALREADY_CURRENT"
    if decision_class == "support_event":
        return "SUPPORT_EVENT_DONOR_PROPOSAL_NOT_TRUTH_AUTHORITY"
    if decision_class == "relation_candidate":
        return "RELATION_CANDIDATE_SOURCE_BACKED"
    if decision_class == "conflict_review":
        return "CONFLICT_REVIEW_REQUIRED_CURRENT_VALUE_MISMATCH"
    if decision_class == "lifecycle_update_candidate":
        return "LIFECYCLE_UPDATE_SUPERSEDES_PRIOR_FACT"
    if decision_class == "clarification_required":
        return "CLARIFICATION_REQUIRED_MEMORY_KIND_AMBIGUOUS" if memory_kind == "unknown" else "CLARIFICATION_REQUIRED_SCOPE_AMBIGUOUS"
    if decision_class == "durable_fact_candidate" and authority.get("authority_class") == "user_explicit":
        return "DURABLE_CANDIDATE_USER_EXPLICIT_SOURCE_BACKED"
    if decision_class == "durable_fact_candidate":
        return "DURABLE_CANDIDATE_TRUSTED_HOST_SOURCE_BACKED"
    if decision_class == "inspect_only":
        return "INSPECT_ONLY_UNVERIFIED_DONOR_PROPOSAL"
    return "REJECTED_ASSERTION_SPEAKER_NOT_TRUTH_AUTHORITY"


def _candidate_id(input_fingerprint: str, action: Mapping[str, Any], index: int) -> str:
    seed = {"input": input_fingerprint, "index": index, "proposal_id": action.get("proposal_id")}
    return "t2cand_" + _hash_json(seed, length=20).removeprefix("sha256:")


def build_tier2_decision_plan(input_packet: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic Tier2 proposal decision plan.

    This function is intentionally pure. It does not read storage, call models,
    route providers, execute graph logic, rank retrieval, or assemble packets.
    """

    policy_version = _text(input_packet.get("policy_version") or TIER2_DECISION_CORE_VERSION)
    input_fingerprint = _hash_json(input_packet)
    scope = _scope(input_packet)
    spans = _source_index(input_packet)
    proposal_batch = _mapping(input_packet.get("proposal_batch"))
    actions = [item for item in _list(proposal_batch.get("actions")) if isinstance(item, Mapping)]
    decisions: list[dict[str, Any]] = []
    counters = {
        "missing_verified_source": 0,
        "assistant_truth_attempt": 0,
        "scope_mismatch": 0,
        "unsupported_decision_class": 0,
        "nondeterministic_input": 0,
    }
    for index, action in enumerate(actions):
        source, blocked_by = _action_source(action, spans)
        blocked_by.extend(_scope_blockers(source, spans, scope))
        memory_kind = _memory_kind(action)
        if memory_kind == "support_context" and _has_source_refs(action):
            blocked_by = [item for item in blocked_by if item != "REJECTED_MISSING_VERIFIED_SOURCE_SPAN"]
        authority = _authority(source, blocked_by, memory_kind)
        matches = _existing_matches(input_packet, action)
        decision_class = _decision_class(input_packet, action, memory_kind, authority, blocked_by, matches)
        if decision_class not in DECISION_CLASSES:
            counters["unsupported_decision_class"] += 1
            decision_class = "inspect_only"
        authority = _authority_for_decision(decision_class, authority)
        relation_shape = _relation_shape(action, memory_kind)
        lifecycle = _lifecycle(input_packet, action, decision_class, matches)
        semantic_value = _semantic_value(decision_class, memory_kind, authority)
        receipt_requirement = _receipt_requirement(decision_class)
        reason_code = _reason_code(decision_class, memory_kind, blocked_by, authority, lifecycle)
        if (
            "REJECTED_MISSING_VERIFIED_SOURCE_SPAN" in blocked_by
            or "REJECTED_MISSING_VERIFIED_SOURCE_EVENT" in blocked_by
        ):
            counters["missing_verified_source"] += 1
        if "REJECTED_ASSISTANT_AUTHORED_TRUTH_ATTEMPT" in blocked_by:
            counters["assistant_truth_attempt"] += 1
        if "REJECTED_SCOPE_MISMATCH" in blocked_by:
            counters["scope_mismatch"] += 1
        decision = {
            "candidate_id": _candidate_id(input_fingerprint, action, index),
            "proposal_id": _text(action.get("proposal_id")),
            "decision_class": decision_class,
            "source": source,
            "scope": scope,
            "normalized_candidate": {
                "target_slot": _text(action.get("target_slot")),
                "relation_shape": relation_shape,
                "value_fingerprint": _text(action.get("value_fingerprint") or action.get("normalized_value_hash")),
            },
            "authority": authority,
            "memory_kind": memory_kind,
            "lifecycle": lifecycle,
            "semantic_value": semantic_value,
            "receipt_requirement": receipt_requirement,
            "reason_code": reason_code,
            "trace": {
                "stage_results": [
                    "source_scope_validation",
                    "candidate_normalization",
                    "authority_evaluation",
                    "memory_kind_classification",
                    "lifecycle_planning",
                    "semantic_value_projection_hint",
                    "receipt_requirement_building",
                ],
                "blocked_by": blocked_by,
            },
        }
        decisions.append(decision)
    return {
        "schema": TIER2_DECISION_PLAN_SCHEMA,
        "policy_version": policy_version,
        "input_fingerprint": input_fingerprint,
        "decision_plan_id": "t2plan_" + _hash_json({"input": input_fingerprint, "policy": policy_version}, length=24).removeprefix("sha256:"),
        "decisions": decisions,
        "critical_counters": counters,
        "trace_summary": {
            "decision_count": len(decisions),
            "blocked_count": sum(1 for item in decisions if item["trace"]["blocked_by"]),
            "truth_candidate_count": sum(1 for item in decisions if bool(item["authority"]["truth_eligible"])),
        },
    }


def validate_tier2_decision_plan(plan: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if plan.get("schema") != TIER2_DECISION_PLAN_SCHEMA:
        issues.append("schema_mismatch")
    for field in ("policy_version", "input_fingerprint", "decision_plan_id"):
        if not _text(plan.get(field)):
            issues.append(f"missing:{field}")
    if not isinstance(plan.get("decisions"), list):
        issues.append("missing:decisions")
        return issues
    for index, decision in enumerate(_list(plan.get("decisions"))):
        if not isinstance(decision, Mapping):
            issues.append(f"decision_not_mapping:{index}")
            continue
        decision_class = _text(decision.get("decision_class"))
        if decision_class not in DECISION_CLASSES:
            issues.append(f"unsupported_decision_class:{index}:{decision_class}")
        if _mapping(decision.get("authority")).get("truth_eligible") is False and decision_class in {
            "durable_fact_candidate",
            "relation_candidate",
            "lifecycle_update_candidate",
        }:
            issues.append(f"truth_ineligible_candidate:{index}")
        if "metadata" in decision:
            issues.append(f"free_form_metadata:{index}")
        if not _text(decision.get("reason_code")):
            issues.append(f"missing_reason_code:{index}")
    return issues


def semantic_conformance_issues(plan: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for index, decision in enumerate(_list(plan.get("decisions"))):
        if not isinstance(decision, Mapping):
            continue
        decision_class = _text(decision.get("decision_class"))
        authority = _mapping(decision.get("authority"))
        semantic_value = _mapping(decision.get("semantic_value"))
        if authority.get("truth_eligible") is False and authority.get("support_visibility") == "answer_evidence":
            issues.append(f"truth_ineligible_answer_evidence:{index}")
        if decision_class == "support_event" and authority.get("truth_eligible") is not False:
            issues.append(f"support_event_truth_eligible:{index}")
        if decision_class == "conflict_review" and authority.get("support_visibility") == "answer_evidence":
            issues.append(f"conflict_answer_evidence:{index}")
        if semantic_value.get("authority_critical") is True and authority.get("truth_eligible") is False:
            issues.append(f"authority_critical_without_truth:{index}")
    return issues


def render_ten_line_decision_trace(decision: Mapping[str, Any]) -> list[str]:
    source = _mapping(decision.get("source"))
    authority = _mapping(decision.get("authority"))
    normalized = _mapping(decision.get("normalized_candidate"))
    relation = _mapping(normalized.get("relation_shape"))
    lifecycle = _mapping(decision.get("lifecycle"))
    semantic = _mapping(decision.get("semantic_value"))
    receipt = _mapping(decision.get("receipt_requirement"))
    trace = _mapping(decision.get("trace"))
    scope = _mapping(decision.get("scope"))
    normalized_text = normalized.get("target_slot") or f"{relation.get('subject_ref')} {relation.get('predicate')} {relation.get('object_ref')}".strip()
    return [
        f"candidate_id: {_text(decision.get('candidate_id'))}",
        f"source: {','.join(_text(item) for item in _list(source.get('source_span_ids')))}, speaker={_text(source.get('assertion_speaker'))}, scope={_text(scope.get('principal_scope_key'))}",
        f"normalized: {_text(normalized_text)}, value={_text(normalized.get('value_fingerprint'))}",
        f"authority: {_text(authority.get('authority_class'))}, truth_eligible={bool(authority.get('truth_eligible'))}, visibility={_text(authority.get('support_visibility'))}",
        f"kind: {_text(decision.get('memory_kind'))}",
        f"existing: {','.join(_text(item) for item in _list(lifecycle.get('target_refs'))) or 'none'}",
        f"lifecycle: {_text(lifecycle.get('action'))}",
        f"value: {_text(semantic.get('semantic_value_class'))}, budget_hint={_text(semantic.get('projection_budget_hint'))}",
        f"receipt_required: {_text(receipt.get('coverage'))}",
        f"decision: {_text(decision.get('decision_class'))}, reason={_text(decision.get('reason_code'))}, blocked_by={','.join(_text(item) for item in _list(trace.get('blocked_by'))) or 'none'}",
    ]
