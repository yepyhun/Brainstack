from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List, Mapping

from .behavior_policy import (
    DEFAULT_PINNED_BEHAVIOR_POLICY_CHAR_BUDGET,
    build_pinned_behavior_policy_view,
)
from .style_contract import STYLE_CONTRACT_DEFAULT_TITLE


ACTIVE_PREFERENCE_CONTRACT_SCHEMA = "brainstack.active_preference_contract.v1"
ACTIVE_PREFERENCE_DELIVERY_TRACE_SCHEMA = "brainstack.active_preference_delivery_trace.v1"

CONTRACT_STATUS_ACTIVE = "active"
CONTRACT_STATUS_DEGRADED = "degraded"
CONTRACT_STATUS_EMPTY = "empty"

DELIVERY_REASON_SESSION_START = "session_start"
DELIVERY_REASON_SESSION_RESET = "session_reset"
DELIVERY_REASON_THREAD_CHANGE = "thread_change"
DELIVERY_REASON_MODEL_OR_PROVIDER_CHANGE = "model_or_provider_change"
DELIVERY_REASON_CONTRACT_VERSION_CHANGED = "contract_version_changed"
DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT = "session_substrate_rebuilt"
DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD = "context_compaction_rebuild"
DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION = "prompt_rebuild_after_compaction"
DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION = "explicit_memory_inspection"

DELIVERY_REASON_CODES = {
    DELIVERY_REASON_SESSION_START,
    DELIVERY_REASON_SESSION_RESET,
    DELIVERY_REASON_THREAD_CHANGE,
    DELIVERY_REASON_MODEL_OR_PROVIDER_CHANGE,
    DELIVERY_REASON_CONTRACT_VERSION_CHANGED,
    DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT,
    DELIVERY_REASON_CONTEXT_COMPACTION_REBUILD,
    DELIVERY_REASON_PROMPT_REBUILD_AFTER_COMPACTION,
    DELIVERY_REASON_EXPLICIT_MEMORY_INSPECTION,
}

DROP_REASON_NO_ACTIVE_USER_PREFERENCES = "no_active_user_preferences"
DROP_REASON_DELIVERY_DISABLED = "delivery_disabled"

ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT = "brainstack.active_preference_card_size_warning_ack"
ACTIVE_PREFERENCE_CARD_SIZE_WARNING_TOKEN_THRESHOLD = 800
ACTIVE_PREFERENCE_CARD_SIZE_WARNING_HIGH_TOKEN_THRESHOLD = 5000
ACTIVE_PREFERENCE_CARD_SIZE_WARNING_REWARN_MULTIPLIER = 2.0
ACTIVE_PREFERENCE_CARD_SIZE_WARNING_TOKEN_CHAR_RATIO = 4


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _list_text(values: Any) -> List[str]:
    if not isinstance(values, Iterable) or isinstance(values, (str, bytes, bytearray)):
        return []
    output: List[str] = []
    for value in values:
        text = _text(value)
        if text:
            output.append(text)
    return output


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _estimated_tokens_from_chars(char_count: Any) -> int:
    count = max(0, _int_value(char_count))
    if count <= 0:
        return 0
    ratio = max(1, ACTIVE_PREFERENCE_CARD_SIZE_WARNING_TOKEN_CHAR_RATIO)
    return max(1, (count + ratio - 1) // ratio)


def _size_warning_acknowledged_token_estimate(ack_payload: Mapping[str, Any] | None) -> int:
    if not isinstance(ack_payload, Mapping):
        return 0
    for key in (
        "acknowledged_token_estimate",
        "active_preference_card_token_estimate",
        "card_token_estimate",
        "token_estimate",
    ):
        value = _int_value(ack_payload.get(key))
        if value > 0:
            return value
    metadata = ack_payload.get("metadata")
    if isinstance(metadata, Mapping):
        return _size_warning_acknowledged_token_estimate(metadata)
    return 0


def _active_card_size_warning(
    *,
    compiled_char_count: int,
    size_warning_ack: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    token_estimate = _estimated_tokens_from_chars(compiled_char_count)
    warn_threshold = ACTIVE_PREFERENCE_CARD_SIZE_WARNING_TOKEN_THRESHOLD
    high_threshold = ACTIVE_PREFERENCE_CARD_SIZE_WARNING_HIGH_TOKEN_THRESHOLD
    acknowledged_tokens = _size_warning_acknowledged_token_estimate(size_warning_ack)
    rewarn_threshold = int(max(acknowledged_tokens + 1, acknowledged_tokens * ACTIVE_PREFERENCE_CARD_SIZE_WARNING_REWARN_MULTIPLIER))
    acknowledged = acknowledged_tokens > 0 and token_estimate < rewarn_threshold
    should_warn = token_estimate >= warn_threshold and not acknowledged
    if token_estimate >= high_threshold and should_warn:
        severity = "high"
    elif should_warn:
        severity = "medium"
    else:
        severity = "none"
    if should_warn and acknowledged_tokens > 0:
        status = "warn_growth_since_user_ack"
    elif should_warn:
        status = "warn"
    elif acknowledged:
        status = "acknowledged_until_growth_doubles"
    else:
        status = "ok"
    return {
        "schema": "brainstack.active_preference_card_size_warning.v1",
        "status": status,
        "severity": severity,
        "should_warn_user": should_warn,
        "card_char_count": max(0, int(compiled_char_count or 0)),
        "estimated_token_count": token_estimate,
        "warning_token_threshold": warn_threshold,
        "high_warning_token_threshold": high_threshold,
        "user_acknowledged_token_estimate": acknowledged_tokens,
        "rewarn_token_threshold": rewarn_threshold if acknowledged_tokens else 0,
        "rewarn_multiplier": ACTIVE_PREFERENCE_CARD_SIZE_WARNING_REWARN_MULTIPLIER,
        "agent_safe_warning": (
            "The active behavior card is large and is injected at session start and after context compaction. "
            "Ask whether the user wants to keep it as-is or reduce it; if the user says it is fine, store a "
            "user-authorized size-warning acknowledgement and do not warn again until the card roughly doubles."
        )
        if should_warn
        else "",
        "agent_safe_ack_write": {
            "tool_name": "brainstack_remember",
            "requires_explicit_user_confirmation": True,
            "shelf": "profile",
            "stable_key": ACTIVE_PREFERENCE_CARD_SIZE_WARNING_ACK_SLOT,
            "category": "operating_preference",
            "content": "The user accepted the current active behavior-card size warning cadence.",
            "source_role": "user",
            "authority_class": "profile",
            "confidence": 0.99,
            "metadata": {
                "acknowledged_token_estimate": token_estimate,
                "acknowledgement_scope": "active_preference_card_size_warning",
            },
        }
        if should_warn
        else {},
    }


def _receipt_ids(raw_contract: Mapping[str, Any], compiled_policy: Mapping[str, Any]) -> List[str]:
    ids: List[str] = []
    for source in (
        raw_contract.get("source_receipt_ids"),
        raw_contract.get("receipt_ids"),
        compiled_policy.get("source_receipt_ids"),
    ):
        ids.extend(_list_text(source))
    for key in ("receipt_id", "memory_write_receipt_id", "behavior_contract_receipt_id"):
        text = _text(raw_contract.get(key) or compiled_policy.get(key))
        if text:
            ids.append(text)

    storage_key = _text(raw_contract.get("storage_key") or compiled_policy.get("source_storage_key"))
    revision = int(raw_contract.get("revision_number") or compiled_policy.get("source_revision_number") or 0)
    read_only_profile_lane = bool(raw_contract.get("read_only_projection") or compiled_policy.get("read_only_projection")) or (
        _text(raw_contract.get("source_lane") or compiled_policy.get("source_lane")) == "profile_style_contract"
    )
    if storage_key and not read_only_profile_lane:
        ids.append(f"behavior_contract_commit:{storage_key}:r{max(revision, 1)}")

    deduped: List[str] = []
    seen: set[str] = set()
    for receipt_id in ids:
        if receipt_id in seen:
            continue
        seen.add(receipt_id)
        deduped.append(receipt_id)
    return deduped


def _source_ref(raw_contract: Mapping[str, Any], compiled_policy: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "storage_key": _text(raw_contract.get("storage_key") or compiled_policy.get("source_storage_key")),
        "stable_key": _text(raw_contract.get("stable_key")),
        "revision_number": int(raw_contract.get("revision_number") or compiled_policy.get("source_revision_number") or 0),
        "content_hash": _text(raw_contract.get("content_hash") or compiled_policy.get("source_contract_hash")),
        "source_lane": _text(raw_contract.get("source_lane") or compiled_policy.get("source_lane")),
        "read_only_projection": bool(
            raw_contract.get("read_only_projection", compiled_policy.get("read_only_projection", False))
        ),
        "source_profile_stable_key": _text(raw_contract.get("source_profile_stable_key")),
        "source_rule_count": int(raw_contract.get("rule_count") or compiled_policy.get("raw_rule_count") or 0),
    }


def _compiled_rules(compiled_policy: Mapping[str, Any], included_rule_ids: set[str]) -> List[Dict[str, Any]]:
    clauses = compiled_policy.get("clauses")
    if not isinstance(clauses, Iterable) or isinstance(clauses, (str, bytes, bytearray)):
        return []
    rules: List[Dict[str, Any]] = []
    for clause in clauses:
        if not isinstance(clause, Mapping):
            continue
        clause_id = _text(clause.get("id"))
        if included_rule_ids and clause_id not in included_rule_ids:
            continue
        text = _text(clause.get("compiled_short_form") or clause.get("text"))
        if not text:
            continue
        rules.append(
            {
                "id": clause_id,
                "kind": _text(clause.get("kind")) or "custom_clause",
                "text": text,
                "status": _text(clause.get("status")) or CONTRACT_STATUS_ACTIVE,
            }
        )
    return rules


def _raw_contract_rules(raw_contract: Mapping[str, Any], included_rule_ids: set[str]) -> List[Dict[str, Any]]:
    raw_rules = raw_contract.get("rules")
    if not isinstance(raw_rules, Iterable) or isinstance(raw_rules, (str, bytes, bytearray)):
        return []
    rules: List[Dict[str, Any]] = []
    for index, rule in enumerate(raw_rules, start=1):
        if isinstance(rule, Mapping):
            rule_id = _text(rule.get("id")) or f"raw-rule-{index:02d}"
            text = _text(rule.get("text"))
        else:
            rule_id = f"raw-rule-{index:02d}"
            text = _text(rule)
        if included_rule_ids and rule_id not in included_rule_ids:
            continue
        if not text:
            continue
        rules.append(
            {
                "id": rule_id,
                "kind": "custom_clause",
                "text": text,
                "status": CONTRACT_STATUS_ACTIVE,
            }
        )
    return rules


def _render_compact_rules(
    rules: List[Dict[str, Any]],
    *,
    char_budget: int,
) -> tuple[str, bool, set[str], int]:
    lines: List[str] = []
    included_ids: set[str] = set()
    remaining = len(rules)
    for rule in rules:
        text = _text(rule.get("text"))
        rule_id = _text(rule.get("id"))
        if not text:
            remaining -= 1
            continue
        candidate_lines = [*lines, f"- {text}"]
        candidate = "\n".join(candidate_lines)
        if len(candidate) > max(120, int(char_budget)):
            break
        lines = candidate_lines
        if rule_id:
            included_ids.add(rule_id)
        remaining -= 1
    truncated = remaining > 0
    if truncated and lines:
        suffix = f"... ({remaining} additional compiled rules omitted)"
        while lines and len("\n".join([*lines, suffix])) > max(120, int(char_budget)):
            removed = lines.pop()
            if removed.startswith("- "):
                remaining += 1
                suffix = f"... ({remaining} additional compiled rules omitted)"
        if lines and len("\n".join([*lines, suffix])) <= max(120, int(char_budget)):
            lines.append(suffix)
    return "\n".join(lines).strip(), truncated, included_ids, len(rules)


def _contract_version(*, raw_contract: Mapping[str, Any], compiled_policy: Mapping[str, Any]) -> str:
    policy_hash = _text(compiled_policy.get("policy_hash"))
    if policy_hash:
        return f"apc:{policy_hash[:16]}"
    payload = {
        "source_contract_hash": _text(raw_contract.get("content_hash") or compiled_policy.get("source_contract_hash")),
        "source_revision_number": int(raw_contract.get("revision_number") or compiled_policy.get("source_revision_number") or 0),
        "compiler_version": _text(compiled_policy.get("compiler_version")),
    }
    digest = hashlib.sha256(repr(sorted(payload.items())).encode("utf-8")).hexdigest()
    return f"apc:{digest[:16]}"


def build_active_preference_contract(
    behavior_snapshot: Mapping[str, Any] | None,
    *,
    principal_scope_key: str = "",
    workspace_scope_key: str = "",
    char_budget: int = DEFAULT_PINNED_BEHAVIOR_POLICY_CHAR_BUDGET,
) -> Dict[str, Any]:
    snapshot: Mapping[str, Any] = behavior_snapshot if isinstance(behavior_snapshot, Mapping) else {}
    raw_contract_payload = snapshot.get("raw_contract")
    compiled_policy_payload = snapshot.get("compiled_policy")
    raw_contract: Mapping[str, Any] = raw_contract_payload if isinstance(raw_contract_payload, Mapping) else {}
    compiled_policy: Mapping[str, Any] = (
        compiled_policy_payload if isinstance(compiled_policy_payload, Mapping) else {}
    )
    if not bool(compiled_policy.get("active")):
        return {
            "schema": ACTIVE_PREFERENCE_CONTRACT_SCHEMA,
            "principal_scope_key": _text(principal_scope_key or snapshot.get("principal_scope_key")),
            "workspace_scope_key": _text(workspace_scope_key),
            "contract_version": "",
            "contract_status": CONTRACT_STATUS_EMPTY,
            "source_receipt_ids": [],
            "source_preference_refs": [],
            "compiled_rules": [],
            "omitted_or_compacted_rules": [],
            "conflict_resolution": [],
            "superseded_refs": [],
            "compiled_char_count": 0,
            "model_facing_default": True,
            "trace_safe": True,
            "projection_text": "",
            "drop_or_skip_reason_code": DROP_REASON_NO_ACTIVE_USER_PREFERENCES,
        }

    pinned_view = build_pinned_behavior_policy_view(compiled_policy, char_budget=char_budget)
    fallback_rules = _raw_contract_rules(raw_contract, set())
    if not isinstance(pinned_view, Mapping):
        if fallback_rules:
            projection_text, truncated, included_ids, total_rules = _render_compact_rules(
                fallback_rules,
                char_budget=char_budget,
            )
            omitted_count = max(0, total_rules - len(included_ids))
            status = CONTRACT_STATUS_DEGRADED if truncated or omitted_count else CONTRACT_STATUS_ACTIVE
            source_ref = _source_ref(raw_contract, compiled_policy)
            return {
                "schema": ACTIVE_PREFERENCE_CONTRACT_SCHEMA,
                "principal_scope_key": _text(principal_scope_key or snapshot.get("principal_scope_key")),
                "workspace_scope_key": _text(workspace_scope_key),
                "contract_version": _contract_version(raw_contract=raw_contract, compiled_policy=compiled_policy),
                "contract_status": status,
                "source_receipt_ids": _receipt_ids(raw_contract, compiled_policy),
                "source_preference_refs": [source_ref] if source_ref["storage_key"] else [],
                "compiled_rules": _raw_contract_rules(raw_contract, included_ids),
                "omitted_or_compacted_rules": [
                    {
                        "reason_code": "omitted_due_compact_budget",
                        "omitted_count": omitted_count,
                    }
                ]
                if omitted_count
                else [],
                "conflict_resolution": [],
                "superseded_refs": [],
                "compiled_char_count": len(projection_text),
                "model_facing_default": True,
                "trace_safe": True,
                "projection_text": projection_text,
                "drop_or_skip_reason_code": None,
            }
        return {
            "schema": ACTIVE_PREFERENCE_CONTRACT_SCHEMA,
            "principal_scope_key": _text(principal_scope_key or snapshot.get("principal_scope_key")),
            "workspace_scope_key": _text(workspace_scope_key),
            "contract_version": _contract_version(raw_contract=raw_contract, compiled_policy=compiled_policy),
            "contract_status": CONTRACT_STATUS_EMPTY,
            "source_receipt_ids": _receipt_ids(raw_contract, compiled_policy),
            "source_preference_refs": [],
            "compiled_rules": [],
            "omitted_or_compacted_rules": [],
            "conflict_resolution": [],
            "superseded_refs": [],
            "compiled_char_count": 0,
            "model_facing_default": True,
            "trace_safe": True,
            "projection_text": "",
            "drop_or_skip_reason_code": DROP_REASON_NO_ACTIVE_USER_PREFERENCES,
        }

    projection_text = _text(pinned_view.get("projection_text"))
    included_ids = {
        _text(rule_id)
        for rule_id in _list_text(
            [
                rule.get("id")
                for rule in _compiled_rules(compiled_policy, set())
                if projection_text and _text(rule.get("text")) in projection_text
            ]
        )
    }
    rules = _compiled_rules(compiled_policy, included_ids)
    omitted_count = int(pinned_view.get("omitted_rule_count") or 0)
    status = CONTRACT_STATUS_DEGRADED if bool(pinned_view.get("truncated")) or omitted_count > 0 else CONTRACT_STATUS_ACTIVE
    source_ref = _source_ref(raw_contract, compiled_policy)
    return {
        "schema": ACTIVE_PREFERENCE_CONTRACT_SCHEMA,
        "principal_scope_key": _text(principal_scope_key or snapshot.get("principal_scope_key")),
        "workspace_scope_key": _text(workspace_scope_key),
        "contract_version": _contract_version(raw_contract=raw_contract, compiled_policy=compiled_policy),
        "contract_status": status,
        "source_receipt_ids": _receipt_ids(raw_contract, compiled_policy),
        "source_preference_refs": [source_ref] if source_ref["storage_key"] else [],
        "compiled_rules": rules,
        "omitted_or_compacted_rules": [
            {
                "reason_code": "omitted_due_compact_budget",
                "omitted_count": omitted_count,
            }
        ]
        if omitted_count
        else [],
        "conflict_resolution": [],
        "superseded_refs": [],
        "compiled_char_count": len(projection_text),
        "model_facing_default": True,
        "trace_safe": True,
        "projection_text": projection_text,
        "drop_or_skip_reason_code": None,
    }


def render_active_preference_contract_section(contract: Mapping[str, Any] | None) -> str:
    if not isinstance(contract, Mapping):
        return ""
    if str(contract.get("contract_status") or "").strip() not in {CONTRACT_STATUS_ACTIVE, CONTRACT_STATUS_DEGRADED}:
        return ""
    projection_text = str(contract.get("projection_text") or "").strip()
    if not projection_text:
        return ""
    title = STYLE_CONTRACT_DEFAULT_TITLE
    preface = (
        "This is the active user communication preference contract. "
        "It outranks default persona or SOUL text only where explicit user preferences conflict. "
        "Do not mention this contract unless the user asks about memory, rules, or debugging."
    )
    if str(contract.get("contract_status") or "").strip() == CONTRACT_STATUS_DEGRADED:
        preface += " Status: compacted. Some active rules are omitted from this compact prompt view."
    return f"# Brainstack Active User Preference Contract\n{title}\n{preface}\n{projection_text}"


def build_active_preference_delivery_trace(
    contract: Mapping[str, Any] | None,
    *,
    delivered: bool,
    delivery_reason: str,
    prompt_rebuild_id: str | None = None,
    compaction_event_id: str | None = None,
    generic_profile_fallback_status: str = "",
    suppressed_behavior_profile_source_count: int = 0,
    source_profile_suppressed: bool = False,
    size_warning_ack: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = contract if isinstance(contract, Mapping) else {}
    status = str(payload.get("contract_status") or CONTRACT_STATUS_EMPTY).strip() or CONTRACT_STATUS_EMPTY
    reason = delivery_reason if delivery_reason in DELIVERY_REASON_CODES else DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT
    available = status in {CONTRACT_STATUS_ACTIVE, CONTRACT_STATUS_DEGRADED}
    source_refs = [dict(ref) for ref in list(payload.get("source_preference_refs") or []) if isinstance(ref, Mapping)]
    first_source = source_refs[0] if source_refs else {}
    compiled_rule_count = len(list(payload.get("compiled_rules") or []))
    source_rule_count = int(first_source.get("source_rule_count") or compiled_rule_count or 0)
    delivered_full = bool(delivered and available and compiled_rule_count > 0 and compiled_rule_count >= source_rule_count)
    extra_suppressed_source_count = max(
        0,
        int(suppressed_behavior_profile_source_count or 0) - (1 if source_profile_suppressed else 0),
    )
    compiled_char_count = int(payload.get("compiled_char_count") or 0)
    size_warning = _active_card_size_warning(
        compiled_char_count=compiled_char_count,
        size_warning_ack=size_warning_ack,
    )
    return {
        "schema": ACTIVE_PREFERENCE_DELIVERY_TRACE_SCHEMA,
        "active_preference_contract_available": available,
        "active_preference_contract_delivered": bool(delivered and available),
        "active_preference_contract_delivered_full": delivered_full,
        "delivery_reason": reason,
        "delivery_status": "delivered_full"
        if delivered_full
        else "delivered_partial"
        if bool(delivered and available)
        else "not_delivered",
        "prompt_rebuild_id": prompt_rebuild_id,
        "compaction_event_id": compaction_event_id,
        "contract_version": str(payload.get("contract_version") or ""),
        "contract_status": status,
        "source_receipt_count": len(list(payload.get("source_receipt_ids") or [])),
        "compiled_char_count": compiled_char_count,
        "estimated_token_count": int(size_warning.get("estimated_token_count") or 0),
        "compiled_rule_count": compiled_rule_count,
        "source_rule_count": source_rule_count,
        "source_storage_key": _text(first_source.get("storage_key")),
        "source_stable_key": _text(first_source.get("stable_key")),
        "source_lane": _text(first_source.get("source_lane")),
        "read_only_projection": bool(first_source.get("read_only_projection")),
        "source_profile_stable_key": _text(first_source.get("source_profile_stable_key")),
        "generic_profile_fallback_status": _text(generic_profile_fallback_status),
        "supplemental_profile_behavior_source_suppressed": int(suppressed_behavior_profile_source_count or 0) > 0,
        "suppressed_behavior_profile_source_count": int(suppressed_behavior_profile_source_count or 0),
        "extra_suppressed_behavior_profile_source_count": extra_suppressed_source_count,
        "active_card_size_warning": size_warning,
        "omitted_or_compacted_rule_count": len(list(payload.get("omitted_or_compacted_rules") or [])),
        "raw_private_text_in_trace": False,
        "drop_or_skip_reason_code": None
        if bool(delivered and available)
        else str(payload.get("drop_or_skip_reason_code") or DROP_REASON_DELIVERY_DISABLED),
    }


def build_active_preference_inspect_payload(contract: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = contract if isinstance(contract, Mapping) else {}
    rules = [
        {
            "id": _text(rule.get("id")),
            "kind": _text(rule.get("kind")) or "custom_clause",
            "text": _text(rule.get("text")),
        }
        for rule in list(payload.get("compiled_rules") or [])
        if isinstance(rule, Mapping) and _text(rule.get("text"))
    ]
    status = str(payload.get("contract_status") or CONTRACT_STATUS_EMPTY).strip() or CONTRACT_STATUS_EMPTY
    return {
        "schema": "brainstack.active_preference_contract_inspect.v1",
        "contract_status": status,
        "contract_version": str(payload.get("contract_version") or ""),
        "active_rule_count": len(rules),
        "active_rules": rules,
        "overflow_or_compacted": status == CONTRACT_STATUS_DEGRADED,
        "omitted_or_compacted_rules": list(payload.get("omitted_or_compacted_rules") or []),
        "source_preference_refs": list(payload.get("source_preference_refs") or []),
        "trace_safe": True,
    }


def build_active_preference_delivery_inspect_payload(
    contract: Mapping[str, Any] | None,
    delivery_trace: Mapping[str, Any] | None,
) -> Dict[str, Any]:
    payload = contract if isinstance(contract, Mapping) else {}
    trace = delivery_trace if isinstance(delivery_trace, Mapping) else {}
    source_refs = [dict(ref) for ref in list(payload.get("source_preference_refs") or []) if isinstance(ref, Mapping)]
    first_source = source_refs[0] if source_refs else {}
    status = str(payload.get("contract_status") or trace.get("contract_status") or CONTRACT_STATUS_EMPTY).strip() or CONTRACT_STATUS_EMPTY
    delivered_full = bool(trace.get("active_preference_contract_delivered_full"))
    suppressed_source_count = int(trace.get("suppressed_behavior_profile_source_count") or 0)
    extra_suppressed_source_count = int(trace.get("extra_suppressed_behavior_profile_source_count") or 0)
    active_rule_count = int(trace.get("compiled_rule_count") or len(list(payload.get("compiled_rules") or [])))
    source_rule_count = int(trace.get("source_rule_count") or first_source.get("source_rule_count") or 0)
    size_warning = trace.get("active_card_size_warning")
    if not isinstance(size_warning, Mapping):
        size_warning = _active_card_size_warning(compiled_char_count=int(trace.get("compiled_char_count") or 0))
    if delivered_full and extra_suppressed_source_count:
        authority_status = "canonical_card_delivered_full_with_suppressed_legacy_sources"
        recommended_action = "inspect_active_card_before_claiming_legacy_sources_are_integrated"
    elif delivered_full:
        authority_status = "canonical_card_delivered_full"
        recommended_action = "none"
    elif status in {CONTRACT_STATUS_ACTIVE, CONTRACT_STATUS_DEGRADED}:
        authority_status = "canonical_card_delivered_partial"
        recommended_action = "inspect_active_card_before_claiming_full_behavior_contract"
    elif suppressed_source_count:
        authority_status = "behavior_sources_suppressed_no_active_card"
        recommended_action = "ask_user_for_explicit_style_contract_then_write_with_brainstack_remember"
    else:
        authority_status = "no_active_behavior_card"
        recommended_action = "ask_user_for_explicit_style_contract_if_behavior_preferences_are_needed"
    return {
        "schema": "brainstack.active_preference_delivery_inspect.v1",
        "contract_status": status,
        "delivery_reason": str(trace.get("delivery_reason") or ""),
        "delivery_status": str(trace.get("delivery_status") or "not_delivered"),
        "delivered": bool(trace.get("active_preference_contract_delivered")),
        "delivered_full": delivered_full,
        "active_rule_count": active_rule_count,
        "source_rule_count": source_rule_count,
        "source_storage_key": str(trace.get("source_storage_key") or first_source.get("storage_key") or ""),
        "source_stable_key": str(trace.get("source_stable_key") or first_source.get("stable_key") or ""),
        "source_lane": str(trace.get("source_lane") or first_source.get("source_lane") or ""),
        "read_only_projection": bool(trace.get("read_only_projection", first_source.get("read_only_projection", False))),
        "source_profile_stable_key": str(
            trace.get("source_profile_stable_key") or first_source.get("source_profile_stable_key") or ""
        ),
        "source_receipt_count": int(trace.get("source_receipt_count") or 0),
        "compiled_char_count": int(trace.get("compiled_char_count") or 0),
        "estimated_token_count": int(trace.get("estimated_token_count") or size_warning.get("estimated_token_count") or 0),
        "active_card_size_warning": dict(size_warning),
        "prompt_rebuild_id_present": bool(trace.get("prompt_rebuild_id")),
        "compaction_event_id_present": bool(trace.get("compaction_event_id")),
        "generic_profile_fallback_status": str(trace.get("generic_profile_fallback_status") or ""),
        "supplemental_profile_behavior_source_suppressed": bool(
            trace.get("supplemental_profile_behavior_source_suppressed")
        ),
        "suppressed_behavior_profile_source_count": suppressed_source_count,
        "extra_suppressed_behavior_profile_source_count": extra_suppressed_source_count,
        "suppressed_behavior_sources_prompt_rendered": False,
        "behavior_card_authority_status": authority_status,
        "agent_safe_repair_action": recommended_action,
        "agent_safe_repair_requires_explicit_user_rules": recommended_action != "none",
        "raw_private_text_in_trace": bool(trace.get("raw_private_text_in_trace")),
        "trace_safe": True,
    }
