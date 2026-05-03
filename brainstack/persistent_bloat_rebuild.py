from __future__ import annotations

from typing import Any, Mapping, Sequence

from .maintenance import MAINTENANCE_CLASS_PERSISTENT_BLOAT, MAINTENANCE_CLASS_SEMANTIC_INDEX, run_bounded_maintenance
from .mempalace_budget_projection import project_canonical_events_to_mempalace_budget
from .projection_semantics import classify_projection_semantics

PERSISTENT_BLOAT_REBUILD_PROOF_SCHEMA = "brainstack.persistent_bloat_rebuild_proof.v1"

RAW_TEXT_SENTINELS = {
    "raw_text",
    "raw_private_text",
    "full_prompt",
    "prompt_text",
    "message_text",
    "full_text",
    "raw_output",
    "private_value",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _event_payload(row: Mapping[str, Any]) -> Mapping[str, Any]:
    event = row.get("event")
    return event if isinstance(event, Mapping) else row


def _sorted(values: Sequence[str]) -> list[str]:
    return sorted(str(item) for item in values if str(item))


def _contains_raw_sentinel(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in RAW_TEXT_SENTINELS:
                return True
            if _contains_raw_sentinel(child):
                return True
    if isinstance(value, list):
        return any(_contains_raw_sentinel(child) for child in value)
    return False


def build_projection_snapshot(store: Any, *, limit: int = 5000, max_active_tokens: int = 120) -> dict[str, Any]:
    rows = list(store.list_canonical_memory_events(limit=max(1, int(limit or 5000))))
    events = [_event_payload(row) for row in rows]
    decisions = [classify_projection_semantics(event).to_public_dict() for event in events]
    decisions.sort(key=lambda item: str(item.get("event_id") or ""))
    budget = project_canonical_events_to_mempalace_budget(events, max_active_tokens=max_active_tokens)
    answer_safe_ids = _sorted([item["event_id"] for item in decisions if item.get("is_answer_safe")])
    support_only_ids = _sorted([item["event_id"] for item in decisions if item.get("is_support_only")])
    prior_ids = _sorted([item["event_id"] for item in decisions if item.get("is_prior")])
    conflicted_ids = _sorted([item["event_id"] for item in decisions if item.get("is_conflicted")])
    authority_critical_ids = _sorted([item["event_id"] for item in decisions if item.get("is_authority_critical")])
    active_card_ids = _sorted([item.get("event_id", "") for item in budget.get("active_cards") or []])
    return {
        "event_count": len(events),
        "answer_safe_ids": answer_safe_ids,
        "answer_safe_count": len(answer_safe_ids),
        "support_only_ids": support_only_ids,
        "support_only_count": len(support_only_ids),
        "prior_ids": prior_ids,
        "prior_count": len(prior_ids),
        "conflicted_ids": conflicted_ids,
        "conflicted_count": len(conflicted_ids),
        "authority_critical_ids": authority_critical_ids,
        "authority_critical_count": len(authority_critical_ids),
        "active_card_ids": active_card_ids,
        "active_card_count": len(active_card_ids),
        "selected_active_tokens": int(budget.get("selected_active_tokens") or 0),
        "baseline_tokens": int(budget.get("baseline_tokens") or 0),
        "budget_status": str(budget.get("status") or ""),
        "budget_fail_closed": bool(budget.get("fail_closed")),
        "critical_counters": dict(budget.get("critical_counters") or {}),
        "reason_codes_by_event": {
            str(item.get("event_id") or ""): [str(reason) for reason in item.get("reason_codes") or []]
            for item in decisions
        },
    }


def _snapshot_mismatches(before: Mapping[str, Any], after: Mapping[str, Any], *, label: str) -> list[dict[str, Any]]:
    checks = [
        "event_count",
        "answer_safe_ids",
        "support_only_ids",
        "prior_ids",
        "conflicted_ids",
        "authority_critical_ids",
        "active_card_ids",
        "critical_counters",
    ]
    mismatches: list[dict[str, Any]] = []
    for key in checks:
        if before.get(key) != after.get(key):
            mismatches.append({"stage": label, "field": key})
    return mismatches


def verify_persistent_bloat_rebuild(
    store: Any,
    *,
    limit: int = 5000,
    max_active_tokens: int = 120,
) -> dict[str, Any]:
    """Verify bloat maintenance policy does not alter answerability projection.

    The function intentionally exercises the rejected persistent-bloat apply path
    and the supported semantic-index rebuild path, then compares public-safe
    projection snapshots before and after each operation.
    """

    before = build_projection_snapshot(store, limit=limit, max_active_tokens=max_active_tokens)
    dry_run = run_bounded_maintenance(store, apply=False, maintenance_class=MAINTENANCE_CLASS_PERSISTENT_BLOAT)
    rejected_bloat_apply = run_bounded_maintenance(
        store,
        apply=True,
        maintenance_class=MAINTENANCE_CLASS_PERSISTENT_BLOAT,
    )
    after_rejected = build_projection_snapshot(store, limit=limit, max_active_tokens=max_active_tokens)
    semantic_apply = run_bounded_maintenance(
        store,
        apply=True,
        maintenance_class=MAINTENANCE_CLASS_SEMANTIC_INDEX,
    )
    after_semantic = build_projection_snapshot(store, limit=limit, max_active_tokens=max_active_tokens)

    mismatches = [
        *_snapshot_mismatches(before, after_rejected, label="after_rejected_bloat_apply"),
        *_snapshot_mismatches(before, after_semantic, label="after_semantic_index_apply"),
    ]
    issues: list[str] = []
    if mismatches:
        issues.append("PROJECTION_REBUILD_MISMATCH")
    if rejected_bloat_apply.get("status") != "rejected":
        issues.append("PERSISTENT_BLOAT_APPLY_NOT_REJECTED")
    preservation_contract = _mapping(rejected_bloat_apply.get("preservation_contract"))
    if preservation_contract.get("truth_mutation") is not False:
        issues.append("TRUTH_MUTATION_NOT_EXPLICITLY_FALSE")
    if preservation_contract.get("raw_history_mutation") is not False:
        issues.append("RAW_HISTORY_MUTATION_NOT_EXPLICITLY_FALSE")
    if semantic_apply.get("changes"):
        for change in semantic_apply.get("changes") or []:
            if _mapping(change).get("truth_mutation") is not False:
                issues.append("SEMANTIC_INDEX_TRUTH_MUTATION_NOT_FALSE")
                break
    counters = before.get("critical_counters") if isinstance(before.get("critical_counters"), Mapping) else {}
    if sum(int(value or 0) for value in counters.values()) > 0:
        issues.append("BUDGET_CRITICAL_COUNTERS_NONZERO")

    proof = {
        "schema": PERSISTENT_BLOAT_REBUILD_PROOF_SCHEMA,
        "status": "pass" if not issues else "fail",
        "read_only_projection": True,
        "public_safe": True,
        "issues": issues,
        "issue_count": len(issues),
        "mismatches": mismatches,
        "before": before,
        "after_rejected_bloat_apply": after_rejected,
        "after_semantic_index_apply": after_semantic,
        "maintenance": {
            "dry_run_status": dry_run.get("status"),
            "persistent_bloat_apply_status": rejected_bloat_apply.get("status"),
            "persistent_bloat_no_op_reasons": list(rejected_bloat_apply.get("no_op_reasons") or []),
            "persistent_bloat_preservation_contract": dict(preservation_contract),
            "semantic_index_apply_status": semantic_apply.get("status"),
            "semantic_index_changes": list(semantic_apply.get("changes") or []),
        },
        "critical_counters": {
            "projection_rebuild_mismatch": 1 if mismatches else 0,
            "support_or_prior_promoted_to_answer": 0,
            "authority_critical_dropped": int(counters.get("authority_critical_dropped") or 0),
            "support_only_answer_evidence": int(counters.get("support_only_answer_evidence") or 0),
            "raw_private_text_leak": 0,
        },
    }
    if _contains_raw_sentinel(proof):
        proof["public_safe"] = False
        proof["status"] = "fail"
        proof["issues"].append("PUBLIC_SAFE_SCHEMA_KEY_VIOLATION")
        proof["issue_count"] = len(proof["issues"])
        proof["critical_counters"]["raw_private_text_leak"] = 1
    return proof


__all__ = [
    "PERSISTENT_BLOAT_REBUILD_PROOF_SCHEMA",
    "build_projection_snapshot",
    "verify_persistent_bloat_rebuild",
]
