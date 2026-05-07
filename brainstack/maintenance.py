from __future__ import annotations

from typing import Any, Dict, Mapping

from .persistent_bloat import build_persistent_bloat_report
from .style_source_hygiene import (
    STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
    run_style_source_hygiene_repair,
)


MAINTENANCE_SCHEMA_VERSION = "brainstack.maintenance.v1"
MAINTENANCE_CLASS_SEMANTIC_INDEX = "semantic_index"
MAINTENANCE_CLASS_PERSISTENT_BLOAT = "persistent_bloat"
UNSAFE_PERSISTENT_BLOAT_APPLY_CLASSES = {
    MAINTENANCE_CLASS_PERSISTENT_BLOAT,
    "profile_duplicate_content",
    "transcript_archive",
    "continuity_archive",
    "graph_conflict_review",
    "canonical_event_cleanup",
    "receipt_cleanup",
}
SUPPORTED_APPLY_CLASSES = {MAINTENANCE_CLASS_SEMANTIC_INDEX, STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS}


def _candidate(
    *,
    maintenance_class: str,
    reason: str,
    count: int,
    apply_supported: bool,
    risk: str,
) -> Dict[str, Any]:
    return {
        "maintenance_class": maintenance_class,
        "reason": reason,
        "candidate_count": max(0, int(count or 0)),
        "apply_supported": bool(apply_supported),
        "risk": risk,
    }


def build_maintenance_dry_run(store: Any, *, principal_scope_key: str = "") -> Dict[str, Any]:
    semantic_status = store.semantic_evidence_channel_status()
    stale_semantic_count = int(semantic_status.get("stale_count") or 0)
    profile_duplicate_rows = store.conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT category, content, COUNT(*) AS duplicate_count
            FROM profile_items
            WHERE active = 1
            GROUP BY category, content
            HAVING duplicate_count > 1
        )
        """
    ).fetchone()
    duplicate_profile_count = int(profile_duplicate_rows["count"] if profile_duplicate_rows is not None else 0)
    graph_conflicts = store.list_graph_conflicts(limit=25)
    persistent_bloat = build_persistent_bloat_report(store)
    bloat_policy_candidates = list(persistent_bloat.get("policy_preview") or [])
    bloat_candidate_count = sum(int(item.get("candidate_count") or 0) for item in bloat_policy_candidates)
    style_source_hygiene = run_style_source_hygiene_repair(
        store,
        principal_scope_key=str(principal_scope_key or "").strip(),
        apply=False,
        explicit_user_request=False,
    )

    candidates = [
        _candidate(
            maintenance_class=MAINTENANCE_CLASS_SEMANTIC_INDEX,
            reason="Derived semantic evidence index has stale rows or can be safely rebuilt.",
            count=stale_semantic_count,
            apply_supported=True,
            risk="derived_index_only",
        ),
        _candidate(
            maintenance_class="profile_duplicate_content",
            reason="Active profile rows have duplicate category/content groups. Apply is intentionally not automated.",
            count=duplicate_profile_count,
            apply_supported=False,
            risk="truth_preservation_review_required",
        ),
        _candidate(
            maintenance_class="graph_conflict_review",
            reason="Open graph conflicts require explicit review before cleanup.",
            count=len(graph_conflicts),
            apply_supported=False,
            risk="conflict_resolution_requires_authority",
        ),
        _candidate(
            maintenance_class=MAINTENANCE_CLASS_PERSISTENT_BLOAT,
            reason="Persistent bloat policy candidates require review unless the operation is derived-index-only.",
            count=bloat_candidate_count,
            apply_supported=False,
            risk="source_receipt_answerability_preservation_required",
        ),
        _candidate(
            maintenance_class=STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
            reason=(
                "Legacy behavior/style profile source rows may be demoted after a scoped canonical "
                "active style contract is proven unchanged."
            ),
            count=int(style_source_hygiene.get("candidate_count") or 0),
            apply_supported=True,
            risk="source_only_prompt_authority_hygiene_explicit_user_request_required",
        ),
    ]
    return {
        "schema": MAINTENANCE_SCHEMA_VERSION,
        "mode": "dry_run",
        "status": "ok",
        "candidates": candidates,
        "candidate_count": sum(item["candidate_count"] for item in candidates),
        "appliable_candidate_count": sum(
            item["candidate_count"] for item in candidates if item["apply_supported"]
        ),
        "persistent_bloat": persistent_bloat,
        "persistent_bloat_policy": bloat_policy_candidates,
    }


def run_bounded_maintenance(
    store: Any,
    *,
    apply: bool = False,
    maintenance_class: str = MAINTENANCE_CLASS_SEMANTIC_INDEX,
    principal_scope_key: str = "",
    explicit_user_request: bool = False,
) -> Dict[str, Any]:
    dry_run = build_maintenance_dry_run(
        store,
        principal_scope_key=str(principal_scope_key or "").strip(),
    )
    receipt: Dict[str, Any] = {
        "schema": MAINTENANCE_SCHEMA_VERSION,
        "mode": "apply" if apply else "dry_run",
        "status": "ok",
        "maintenance_class": maintenance_class,
        "dry_run": dry_run,
        "changes": [],
        "no_op_reasons": [],
    }
    if not apply:
        return receipt
    if maintenance_class not in SUPPORTED_APPLY_CLASSES:
        receipt["status"] = "rejected"
        receipt["no_op_reasons"].append("maintenance_class_apply_not_supported")
        if maintenance_class in UNSAFE_PERSISTENT_BLOAT_APPLY_CLASSES:
            receipt["no_op_reasons"].append("persistent_bloat_cleanup_requires_explicit_review")
            receipt["preservation_contract"] = {
                "truth_mutation": False,
                "raw_history_mutation": False,
                "preserves": [
                    "source_ref",
                    "receipt",
                    "answerability",
                    "current_prior_truth",
                    "conflict_audit_trail",
                    "audit_history",
                ],
            }
        return receipt
    if maintenance_class == MAINTENANCE_CLASS_SEMANTIC_INDEX:
        before = store.semantic_evidence_channel_status()
        result = store.rebuild_semantic_evidence_index(
            principal_scope_key=str(principal_scope_key or "").strip() or None
        )
        after = store.semantic_evidence_channel_status()
        receipt["changes"].append(
            {
                "maintenance_class": MAINTENANCE_CLASS_SEMANTIC_INDEX,
                "operation": "rebuild_semantic_evidence_index",
                "truth_mutation": False,
                "before": before,
                "result": result,
                "after": after,
            }
        )
        if not receipt["changes"]:
            receipt["no_op_reasons"].append("no_changes")
    if maintenance_class == STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS:
        result = run_style_source_hygiene_repair(
            store,
            principal_scope_key=str(principal_scope_key or "").strip(),
            apply=True,
            explicit_user_request=bool(explicit_user_request),
        )
        receipt["changes"].append(
            {
                "maintenance_class": STYLE_SOURCE_HYGIENE_MAINTENANCE_CLASS,
                "operation": "demote_legacy_behavior_profile_sources",
                "truth_mutation": False,
                "result": result,
            }
        )
        if result.get("status") != "applied":
            receipt["status"] = str(result.get("status") or "rejected")
            receipt["no_op_reasons"].extend(list(result.get("no_op_reasons") or []))
        if int(result.get("demoted_count") or 0) <= 0:
            receipt["no_op_reasons"].append("no_changes")
    return receipt


def normalize_maintenance_args(args: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(args or {}) if isinstance(args, Mapping) else {}
    apply_raw = payload.get("apply", False)
    maintenance_class = str(payload.get("maintenance_class") or MAINTENANCE_CLASS_SEMANTIC_INDEX).strip()
    if maintenance_class == "persistent_bloat_report":
        maintenance_class = MAINTENANCE_CLASS_PERSISTENT_BLOAT
    return {
        "apply": apply_raw if isinstance(apply_raw, bool) else str(apply_raw).strip().lower() in {"1", "true", "yes"},
        "maintenance_class": maintenance_class or MAINTENANCE_CLASS_SEMANTIC_INDEX,
        "explicit_user_request": bool(payload.get("explicit_user_request") is True),
    }
