from __future__ import annotations

from typing import Any, Dict, Mapping


MAINTENANCE_SCHEMA_VERSION = "brainstack.maintenance.v1"
MAINTENANCE_CLASS_SEMANTIC_INDEX = "semantic_index"
SUPPORTED_APPLY_CLASSES = {MAINTENANCE_CLASS_SEMANTIC_INDEX}


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


def build_maintenance_dry_run(store: Any) -> Dict[str, Any]:
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
    }


def run_bounded_maintenance(
    store: Any,
    *,
    apply: bool = False,
    maintenance_class: str = MAINTENANCE_CLASS_SEMANTIC_INDEX,
    principal_scope_key: str = "",
) -> Dict[str, Any]:
    dry_run = build_maintenance_dry_run(store)
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
    return receipt


def normalize_maintenance_args(args: Mapping[str, Any] | None) -> Dict[str, Any]:
    payload = dict(args or {}) if isinstance(args, Mapping) else {}
    apply_raw = payload.get("apply", False)
    maintenance_class = str(payload.get("maintenance_class") or MAINTENANCE_CLASS_SEMANTIC_INDEX).strip()
    return {
        "apply": apply_raw if isinstance(apply_raw, bool) else str(apply_raw).strip().lower() in {"1", "true", "yes"},
        "maintenance_class": maintenance_class or MAINTENANCE_CLASS_SEMANTIC_INDEX,
    }

