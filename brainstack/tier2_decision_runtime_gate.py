from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .tier2_consolidation import VERIFIED_USER_SPAN_PROOF_KEY
from .tier2_decision_core import (
    build_tier2_decision_plan,
    semantic_conformance_issues,
    validate_tier2_decision_plan,
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_tier2_source(source: str) -> bool:
    normalized = str(source or "").strip().lower()
    return normalized.startswith(("tier2:", "consolidation:"))


def _scope(base_metadata: Mapping[str, Any]) -> dict[str, str]:
    return {
        "tenant_id": _text(base_metadata.get("tenant_id") or "local"),
        "principal_scope_key": _text(base_metadata.get("principal_scope_key")),
        "workspace_scope_key": _text(base_metadata.get("workspace_scope_key")),
        "session_id": _text(base_metadata.get("session_id")),
        "project_id": _text(base_metadata.get("project_id")),
    }


def _verified_source_spans(candidate_metadata: Mapping[str, Any], base_metadata: Mapping[str, Any]) -> list[dict[str, Any]]:
    proof = candidate_metadata.get(VERIFIED_USER_SPAN_PROOF_KEY)
    if not isinstance(proof, Mapping) or str(proof.get("status") or "") != "verified":
        return []
    span_id = _text(proof.get("source_span_id") or candidate_metadata.get("source_span_id"))
    if not span_id:
        return []
    return [
        {
            "source_span_id": span_id,
            "source_event_id": _text(proof.get("source_event_id") or candidate_metadata.get("source_event_id")),
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "scope": _scope(base_metadata),
        }
    ]


def _action_name(raw_action: str) -> str:
    normalized = _text(raw_action).lower()
    if normalized in {"add", "create"}:
        return "create"
    if normalized in {"update", "supersede", "correct", "correction", "invalidate", "expire", "merge_alias"}:
        return normalized
    if normalized in {"none", "noop", "unchanged"}:
        return "retain"
    return normalized or "create"


def evaluate_tier2_decision_core_gate(
    *,
    kind: str,
    candidate_metadata: dict[str, Any],
    base_metadata: Mapping[str, Any],
    source: str,
    target_kind: str,
    target_slot: str,
    stable_key: str,
    normalized_value: Any,
    relation_shape: Mapping[str, Any] | None = None,
    existing_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Attach decision-core trace and return block action when Tier2 write is unsafe.

    This is an adapter/enforcement seam only. It does not write storage, call
    models, route providers, traverse graph, rank retrieval, or assemble packets.
    """

    if not _is_tier2_source(source):
        return None
    consolidation = candidate_metadata.get("consolidation") if isinstance(candidate_metadata.get("consolidation"), Mapping) else {}
    source_span_id = _text(candidate_metadata.get("source_span_id"))
    source_event_id = _text(candidate_metadata.get("source_event_id"))
    action = {
        "proposal_id": _text(consolidation.get("proposal_id") or candidate_metadata.get("trace_id")),
        "action": _action_name(str(consolidation.get("proposed_action") or "")),
        "target_kind": target_kind,
        "target_slot": target_slot,
        "stable_key": stable_key or target_slot,
        "source_span_ids": [source_span_id] if source_span_id else [],
        "source_event_ids": [source_event_id] if source_event_id else [],
        "assertion_speaker": _text(candidate_metadata.get("assertion_speaker")),
        "source_role": _text(candidate_metadata.get("source_role")),
        "normalized_value_hash": _json_fingerprint(normalized_value),
    }
    if relation_shape:
        action["relation_shape"] = dict(relation_shape)
    plan = build_tier2_decision_plan(
        {
            "policy_version": "brainstack.tier2_runtime_enforcement.v1",
            "scope": _scope(base_metadata),
            "verified_source_spans": _verified_source_spans(candidate_metadata, base_metadata),
            "existing_memory_refs": [dict(existing_ref)] if isinstance(existing_ref, Mapping) else [],
            "proposal_batch": {"actions": [action]},
        }
    )
    issues = validate_tier2_decision_plan(plan) + semantic_conformance_issues(plan)
    decision = plan["decisions"][0] if plan.get("decisions") else {}
    decision_class = _text(decision.get("decision_class"))
    authority = decision.get("authority") if isinstance(decision.get("authority"), Mapping) else {}
    candidate_metadata["tier2_decision_core"] = {
        "schema": str(plan.get("schema") or ""),
        "decision_plan_id": str(plan.get("decision_plan_id") or ""),
        "input_fingerprint": str(plan.get("input_fingerprint") or ""),
        "decision_class": decision_class,
        "reason_code": _text(decision.get("reason_code")),
        "truth_eligible": bool(authority.get("truth_eligible")),
        "issues": list(issues),
    }
    allowed_by_kind = {
        "profile": {"durable_fact_candidate", "lifecycle_update_candidate"},
        "style_contract": {"durable_fact_candidate", "lifecycle_update_candidate"},
        "state": {"relation_candidate", "lifecycle_update_candidate"},
        "relation": {"relation_candidate", "lifecycle_update_candidate"},
    }
    if not issues and decision_class in allowed_by_kind.get(kind, set()):
        return None
    return {
        "kind": kind,
        "action": "REJECT",
        "reason_code": "TIER2_DECISION_CORE_BLOCKED",
        "tier2_decision_class": decision_class,
        "tier2_decision_reason_code": _text(decision.get("reason_code")),
        "truth_eligible": False,
        "support_visibility": "inspect_only",
        "issues": list(issues),
    }

