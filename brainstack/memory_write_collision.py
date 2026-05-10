from __future__ import annotations

from typing import Any, Mapping


MEMORY_WRITE_COLLISION_SCHEMA = "brainstack.memory_write_collision.v1"

COLLISION_DUPLICATE_CANDIDATE = "duplicate_candidate"
COLLISION_UNSAFE_AUTHORITY_SHRINK = "unsafe_authority_shrink"
COLLISION_STALE_UPDATE = "stale_update"
COLLISION_SOURCE_INTEGRITY_VIOLATION = "source_integrity_violation"
COLLISION_SCOPE_AMBIGUOUS = "scope_ambiguous"
COLLISION_CONFLICT_REQUIRES_REVIEW = "conflict_requires_review"
COLLISION_AUTHORITY_DOWNGRADE_BLOCKED = "authority_downgrade_blocked"
COLLISION_LOCKED_SOURCE_UPDATE_BLOCKED = "locked_source_update_blocked"
COLLISION_FINAL_STATE_NOT_AGENT_FACING = "final_state_not_agent_facing"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def build_memory_write_collision(
    *,
    code: str,
    reason: str,
    affected_authority: str,
    mutation_status: str,
    next_safe_action: str,
    existing_ref: str = "",
    candidate_ref: str = "",
) -> dict[str, Any]:
    return {
        "schema": MEMORY_WRITE_COLLISION_SCHEMA,
        "code": _text(code),
        "reason": _text(reason),
        "affected_authority": _text(affected_authority),
        "mutation_status": _text(mutation_status),
        "next_safe_action": _text(next_safe_action),
        "existing_ref": _text(existing_ref),
        "candidate_ref": _text(candidate_ref),
        "receipt_is_final_success": False,
        "agent_facing": True,
        "raw_private_payload_in_collision": False,
    }


def _collision_from_style_materialization(materialization: Mapping[str, Any]) -> dict[str, Any] | None:
    reason_code = _text(materialization.get("reason_code"))
    if reason_code == "would_shrink_existing_style_contract":
        return build_memory_write_collision(
            code=COLLISION_UNSAFE_AUTHORITY_SHRINK,
            reason="A smaller style-contract candidate would shrink the active behavior card.",
            affected_authority="behavior_card",
            mutation_status="blocked_no_mutation",
            next_safe_action="ask_user_for_explicit_replace_or_full_rule_pack",
            existing_ref="preference:style_contract",
        )
    if reason_code == "source_role_not_user_authority":
        return build_memory_write_collision(
            code=COLLISION_AUTHORITY_DOWNGRADE_BLOCKED,
            reason="Non-user source role cannot materialize behavior-card authority.",
            affected_authority="behavior_card",
            mutation_status="blocked_no_mutation",
            next_safe_action="ask_user_to_confirm_exact_rules_before_materializing",
            existing_ref="preference:style_contract",
        )
    if reason_code == "not_explicit_style_contract":
        return build_memory_write_collision(
            code=COLLISION_FINAL_STATE_NOT_AGENT_FACING,
            reason="Profile write was stored, but it did not become the canonical active behavior card.",
            affected_authority="behavior_card",
            mutation_status="stored_source_only",
            next_safe_action="inspect_active_behavior_card_before_claiming_delivery",
            existing_ref="preference:style_contract",
        )
    return None


def collision_from_tool_rejection(rejection: Mapping[str, Any]) -> dict[str, Any] | None:
    errors = rejection.get("errors")
    if not isinstance(errors, list):
        return None
    codes = {_text(item.get("code")) for item in errors if isinstance(item, Mapping)}
    if "missing_scope" in codes or "missing_principal_scope" in codes:
        return build_memory_write_collision(
            code=COLLISION_SCOPE_AMBIGUOUS,
            reason="The write did not have a stable principal scope.",
            affected_authority="durable_memory",
            mutation_status="blocked_no_mutation",
            next_safe_action="retry_with_stable_profile_scope",
        )
    if codes:
        return build_memory_write_collision(
            code=COLLISION_FINAL_STATE_NOT_AGENT_FACING,
            reason="The write was rejected by schema validation and no final memory state changed.",
            affected_authority="durable_memory",
            mutation_status="blocked_no_mutation",
            next_safe_action="repair_payload_then_retry",
        )
    return None


def attach_write_collision_if_any(receipt: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(receipt)
    collision: dict[str, Any] | None = None
    materialization = enriched.get("style_contract_materialization")
    if isinstance(materialization, Mapping):
        collision = _collision_from_style_materialization(materialization)
    if collision is None and _text(enriched.get("status")) == "rejected":
        collision = collision_from_tool_rejection(enriched)
    if collision is not None:
        enriched["write_collision"] = collision
        enriched["final_state_success"] = False
    else:
        enriched.setdefault("final_state_success", _text(enriched.get("status")) in {"committed", "ok"})
    return enriched
