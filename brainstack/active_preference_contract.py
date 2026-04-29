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
    if storage_key:
        ids.append(f"behavior_contract_commit:{storage_key}:r{max(revision, 1)}")

    deduped: List[str] = []
    seen: set[str] = set()
    for receipt_id in ids:
        if receipt_id in seen:
            continue
        seen.add(receipt_id)
        deduped.append(receipt_id)
    return deduped


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
    snapshot = behavior_snapshot if isinstance(behavior_snapshot, Mapping) else {}
    raw_contract = snapshot.get("raw_contract") if isinstance(snapshot.get("raw_contract"), Mapping) else {}
    compiled_policy = snapshot.get("compiled_policy") if isinstance(snapshot.get("compiled_policy"), Mapping) else {}
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
            source_ref = {
                "storage_key": _text(raw_contract.get("storage_key") or compiled_policy.get("source_storage_key")),
                "stable_key": _text(raw_contract.get("stable_key")),
                "revision_number": int(raw_contract.get("revision_number") or compiled_policy.get("source_revision_number") or 0),
                "content_hash": _text(raw_contract.get("content_hash") or compiled_policy.get("source_contract_hash")),
            }
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
    source_ref = {
        "storage_key": _text(raw_contract.get("storage_key") or compiled_policy.get("source_storage_key")),
        "stable_key": _text(raw_contract.get("stable_key")),
        "revision_number": int(raw_contract.get("revision_number") or compiled_policy.get("source_revision_number") or 0),
        "content_hash": _text(raw_contract.get("content_hash") or compiled_policy.get("source_contract_hash")),
    }
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
) -> Dict[str, Any]:
    payload = contract if isinstance(contract, Mapping) else {}
    status = str(payload.get("contract_status") or CONTRACT_STATUS_EMPTY).strip() or CONTRACT_STATUS_EMPTY
    reason = delivery_reason if delivery_reason in DELIVERY_REASON_CODES else DELIVERY_REASON_SESSION_SUBSTRATE_REBUILT
    available = status in {CONTRACT_STATUS_ACTIVE, CONTRACT_STATUS_DEGRADED}
    return {
        "schema": ACTIVE_PREFERENCE_DELIVERY_TRACE_SCHEMA,
        "active_preference_contract_available": available,
        "active_preference_contract_delivered": bool(delivered and available),
        "delivery_reason": reason,
        "prompt_rebuild_id": prompt_rebuild_id,
        "compaction_event_id": compaction_event_id,
        "contract_version": str(payload.get("contract_version") or ""),
        "contract_status": status,
        "source_receipt_count": len(list(payload.get("source_receipt_ids") or [])),
        "compiled_rule_count": len(list(payload.get("compiled_rules") or [])),
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
