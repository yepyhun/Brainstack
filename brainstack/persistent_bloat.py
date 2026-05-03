from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .mempalace_budget_projection import project_canonical_events_to_mempalace_budget

PERSISTENT_BLOAT_REPORT_SCHEMA = "brainstack.persistent_bloat_report.v1"
PERSISTENT_BLOAT_POLICY_SCHEMA = "brainstack.persistent_bloat_policy.v1"

DEFAULT_BLOAT_THRESHOLDS: dict[str, float] = {
    "write_amplification_warn": 12.0,
    "write_amplification_fail": 30.0,
    "duplicate_strength_warn": 3.0,
    "duplicate_strength_fail": 10.0,
    "support_only_ratio_warn": 8.0,
    "support_only_ratio_fail": 25.0,
    "active_packet_tokens_warn": 800.0,
    "active_packet_tokens_fail": 1600.0,
    "stale_prior_ratio_warn": 5.0,
    "stale_prior_ratio_fail": 20.0,
    "projection_rebuild_events_warn": 2000.0,
    "projection_rebuild_events_fail": 10000.0,
}

RAW_TEXT_SENTINELS = (
    "raw_text",
    "raw_private_text",
    "full_prompt",
    "prompt_text",
    "message_text",
    "full_text",
    "raw_output",
    "private_value",
)


@dataclass(frozen=True)
class _MetricStatus:
    status: str
    issue_code: str


def _num(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: int | float, denominator: int | float) -> float:
    denom = float(denominator or 0)
    if denom <= 0:
        return float(numerator or 0)
    return round(float(numerator or 0) / denom, 4)


def _table_exists(store: Any, table_name: str) -> bool:
    row = store.conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (str(table_name),),
    ).fetchone()
    return row is not None


def _count(store: Any, table_name: str, where: str = "", params: Sequence[Any] = ()) -> int:
    if not _table_exists(store, table_name):
        return 0
    suffix = f" WHERE {where}" if where else ""
    row = store.conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}{suffix}", tuple(params)).fetchone()
    return _num(row["count"] if row is not None else 0)


def _scalar_count(store: Any, sql: str, params: Sequence[Any] = ()) -> int:
    row = store.conn.execute(sql, tuple(params)).fetchone()
    return _num(row["count"] if row is not None and "count" in row.keys() else 0)


def _metric_status(value: float, *, warn: float, fail: float, issue_prefix: str) -> _MetricStatus:
    if fail > 0 and value >= fail:
        return _MetricStatus("fail", f"{issue_prefix}_FAIL")
    if warn > 0 and value >= warn:
        return _MetricStatus("warn", f"{issue_prefix}_WARN")
    return _MetricStatus("pass", "")


def _canonical_events(store: Any, *, limit: int) -> list[dict[str, Any]]:
    if not hasattr(store, "list_canonical_memory_events"):
        return []
    try:
        return list(store.list_canonical_memory_events(limit=max(1, int(limit))))
    except Exception:
        return []


def _duplicate_group_count(store: Any, sql: str) -> int:
    try:
        row = store.conn.execute(f"SELECT COUNT(*) AS count FROM ({sql})").fetchone()
        return _num(row["count"] if row is not None else 0)
    except Exception:
        return 0


def _lane(
    *,
    row_count: int,
    hot_count: int = 0,
    cold_count: int = 0,
    issue_count: int = 0,
    policy_action: str,
    reason_codes: Sequence[str],
    preserves: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "row_count": int(row_count),
        "hot_count": int(hot_count),
        "cold_count": int(cold_count),
        "issue_count": int(issue_count),
        "policy_action": str(policy_action),
        "reason_codes": [str(item) for item in reason_codes],
        "preserves": [str(item) for item in preserves],
    }


def _policy_decision(
    *,
    lane: str,
    action: str,
    reason_code: str,
    candidate_count: int,
    apply_supported: bool,
    risk: str,
    preserves: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema": PERSISTENT_BLOAT_POLICY_SCHEMA,
        "lane": str(lane),
        "action": str(action),
        "reason_code": str(reason_code),
        "candidate_count": int(candidate_count),
        "apply_supported": bool(apply_supported),
        "risk": str(risk),
        "preserves": [str(item) for item in preserves],
    }


def _contains_raw_sentinel(value: Any) -> bool:
    if isinstance(value, Mapping):
        forbidden = set(RAW_TEXT_SENTINELS)
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in forbidden:
                return True
            if _contains_raw_sentinel(child):
                return True
    elif isinstance(value, list):
        return any(_contains_raw_sentinel(child) for child in value)
    return False


def build_persistent_bloat_report(
    store: Any,
    *,
    principal_scope_key: str = "",
    thresholds: Mapping[str, float] | None = None,
    max_projection_events: int = 2000,
    max_active_tokens: int = 120,
    derived_async_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public-safe, read-only persistent memory bloat report.

    The report is intentionally structural: it counts rows, projection cards,
    support visibility classes, and policy candidates. It does not emit raw
    transcript/profile/corpus text and it does not mutate storage.
    """

    merged_thresholds = {**DEFAULT_BLOAT_THRESHOLDS, **dict(thresholds or {})}
    scope_key = str(principal_scope_key or "").strip()

    profile_active = _count(store, "profile_items", "active = 1")
    profile_inactive = _count(store, "profile_items", "active = 0")
    profile_duplicate_groups = _duplicate_group_count(
        store,
        """
        SELECT category, content, COUNT(*) AS duplicate_count
        FROM profile_items
        WHERE active = 1
        GROUP BY category, content
        HAVING duplicate_count > 1
        """,
    )
    profile_duplicate_rows = _scalar_count(
        store,
        """
        SELECT COALESCE(SUM(duplicate_count - 1), 0) AS count
        FROM (
            SELECT category, content, COUNT(*) AS duplicate_count
            FROM profile_items
            WHERE active = 1
            GROUP BY category, content
            HAVING duplicate_count > 1
        )
        """,
    )

    canonical_total = _count(store, "canonical_memory_events")
    canonical_answer = _count(
        store,
        "canonical_memory_events",
        "truth_eligible = 1 AND support_visibility = 'answer_evidence'",
    )
    canonical_support = _count(
        store,
        "canonical_memory_events",
        "support_visibility IN ('normal', 'history_only', 'inspect_only', 'contradiction_only') OR truth_eligible = 0",
    )
    canonical_archived_or_prior = _count(
        store,
        "canonical_memory_events",
        "event_type IN ('corrected_false_event', 'proposal_rejected') OR support_visibility IN ('history_only', 'inspect_only', 'contradiction_only')",
    )
    canonical_duplicate_truth_groups = _duplicate_group_count(
        store,
        """
        SELECT stable_fact_id, COUNT(*) AS duplicate_count
        FROM canonical_memory_events
        WHERE stable_fact_id != '' AND truth_eligible = 1 AND support_visibility = 'answer_evidence'
        GROUP BY stable_fact_id
        HAVING duplicate_count > 1
        """,
    )

    receipt_count = _count(store, "admission_receipts")
    transcript_count = _count(store, "transcript_entries")
    continuity_count = _count(store, "continuity_events")
    continuity_frontier_count = _count(store, "continuity_lifecycle_state")
    corpus_documents = _count(store, "corpus_documents")
    corpus_sections = _count(store, "corpus_sections")
    semantic_rows = _count(store, "semantic_evidence_index")
    graph_states = _count(store, "graph_states")
    graph_prior_states = _count(store, "graph_states", "is_current = 0")
    graph_current_states = _count(store, "graph_states", "is_current = 1")
    graph_relations = _count(store, "graph_relations")
    graph_inferred_relations = _count(store, "graph_inferred_relations")
    graph_conflicts = _count(store, "graph_conflicts")
    graph_open_conflicts = _count(store, "graph_conflicts", "status != 'resolved'")
    graph_resolutions = _count(store, "graph_conflict_resolutions")
    proactive_events = _count(store, "proactive_events")
    proactive_pending = _count(store, "proactive_outbox", "delivery_state = 'pending'")
    proactive_suppressed = _count(store, "proactive_events", "state IN ('suppressed', 'rejected', 'expired', 'blocked')")
    operating_records = _count(store, "operating_records")
    recent_work_records = _count(store, "operating_records", "record_type = 'recent_work_summary'")
    task_items = _count(store, "task_items")
    publish_journal = _count(store, "publish_journal")
    tier2_runs = _count(store, "tier2_run_records")
    behavior_contracts = _count(store, "behavior_contracts")
    compiled_behavior = _count(store, "compiled_behavior_policies")

    events = _canonical_events(store, limit=max_projection_events)
    projection = project_canonical_events_to_mempalace_budget(events, max_active_tokens=max_active_tokens)
    projection_counters = dict(projection.get("critical_counters") or {})
    projection_card_count = (
        len(projection.get("active_cards") or [])
        + len(projection.get("retrieval_only") or [])
        + len(projection.get("support_only") or [])
        + len(projection.get("archived") or [])
    )
    selected_active_tokens = _num(projection.get("selected_active_tokens"))
    baseline_tokens = _num(projection.get("baseline_tokens"))
    active_card_count = len(projection.get("active_cards") or [])
    support_card_count = len(projection.get("support_only") or [])
    archived_card_count = len(projection.get("archived") or [])
    retrieval_card_count = len(projection.get("retrieval_only") or [])

    storage_rows = sum(
        [
            profile_active,
            profile_inactive,
            canonical_total,
            receipt_count,
            transcript_count,
            continuity_count,
            corpus_documents,
            corpus_sections,
            semantic_rows,
            graph_states,
            graph_relations,
            graph_inferred_relations,
            graph_conflicts,
            graph_resolutions,
            proactive_events,
            proactive_pending,
            operating_records,
            task_items,
            publish_journal,
            tier2_runs,
            behavior_contracts,
            compiled_behavior,
        ]
    )
    answer_denominator = max(canonical_answer + profile_active + graph_current_states, 1)
    write_amplification_ratio = _ratio(storage_rows, answer_denominator)
    duplicate_strength_total = profile_duplicate_groups + canonical_duplicate_truth_groups
    support_pressure = canonical_support + transcript_count + continuity_count + support_card_count
    support_only_ratio = _ratio(support_pressure, max(canonical_answer, 1))
    stale_prior_total = profile_inactive + graph_prior_states + graph_open_conflicts + canonical_archived_or_prior + proactive_suppressed
    stale_prior_ratio = _ratio(stale_prior_total, answer_denominator)
    derived_async = dict(derived_async_state or {})
    derived_counters = dict(derived_async.get("counters") or {}) if isinstance(derived_async, Mapping) else {}
    derived_queued = _num(derived_counters.get("queued_count"))
    derived_pending = _num(derived_counters.get("pending_count"))
    derived_failed = _num(derived_counters.get("failed_count"))
    derived_retry = _num(derived_counters.get("retry_count"))
    derived_hidden_readiness = _num(derived_counters.get("hidden_readiness_claim_count"))

    metrics = {
        "write_amplification": {
            "storage_rows": storage_rows,
            "answer_authority_rows": answer_denominator,
            "ratio": write_amplification_ratio,
        },
        "duplicate_strength_inflation": {
            "profile_duplicate_groups": profile_duplicate_groups,
            "profile_duplicate_rows": profile_duplicate_rows,
            "canonical_duplicate_truth_groups": canonical_duplicate_truth_groups,
            "total_duplicate_groups": duplicate_strength_total,
        },
        "support_only_accumulation": {
            "canonical_support_events": canonical_support,
            "transcript_rows": transcript_count,
            "continuity_rows": continuity_count,
            "support_projection_cards": support_card_count,
            "ratio_to_answer_events": support_only_ratio,
        },
        "active_packet_growth": {
            "baseline_tokens": baseline_tokens,
            "selected_active_tokens": selected_active_tokens,
            "active_card_count": active_card_count,
            "retrieval_only_card_count": retrieval_card_count,
            "support_only_card_count": support_card_count,
            "archived_card_count": archived_card_count,
            "fail_closed": bool(projection.get("fail_closed")),
        },
        "stale_prior_retention": {
            "inactive_profile_rows": profile_inactive,
            "graph_prior_states": graph_prior_states,
            "open_graph_conflicts": graph_open_conflicts,
            "canonical_archived_or_prior_events": canonical_archived_or_prior,
            "suppressed_proactive_events": proactive_suppressed,
            "ratio_to_answer_authority": stale_prior_ratio,
        },
        "projection_rebuild_size": {
            "canonical_event_count": canonical_total,
            "sampled_event_count": len(events),
            "projection_card_count": projection_card_count,
            "active_card_count": active_card_count,
            "decision_count": len(projection.get("budget_decisions") or []),
            "sample_truncated": canonical_total > len(events),
            "critical_counters": projection_counters,
        },
        "derived_async_queued_count": derived_queued,
        "derived_async_pending_count": derived_pending,
        "derived_async_failed_count": derived_failed,
        "derived_async_retry_count": derived_retry,
    }

    statuses = {
        "write_amplification": _metric_status(
            write_amplification_ratio,
            warn=_float(merged_thresholds["write_amplification_warn"]),
            fail=_float(merged_thresholds["write_amplification_fail"]),
            issue_prefix="WRITE_AMPLIFICATION",
        ),
        "duplicate_strength_inflation": _metric_status(
            float(duplicate_strength_total),
            warn=_float(merged_thresholds["duplicate_strength_warn"]),
            fail=_float(merged_thresholds["duplicate_strength_fail"]),
            issue_prefix="DUPLICATE_STRENGTH_INFLATION",
        ),
        "support_only_accumulation": _metric_status(
            support_only_ratio,
            warn=_float(merged_thresholds["support_only_ratio_warn"]),
            fail=_float(merged_thresholds["support_only_ratio_fail"]),
            issue_prefix="SUPPORT_ONLY_ACCUMULATION",
        ),
        "active_packet_growth": _metric_status(
            float(selected_active_tokens),
            warn=_float(merged_thresholds["active_packet_tokens_warn"]),
            fail=_float(merged_thresholds["active_packet_tokens_fail"]),
            issue_prefix="ACTIVE_PACKET_GROWTH",
        ),
        "stale_prior_retention": _metric_status(
            stale_prior_ratio,
            warn=_float(merged_thresholds["stale_prior_ratio_warn"]),
            fail=_float(merged_thresholds["stale_prior_ratio_fail"]),
            issue_prefix="STALE_PRIOR_RETENTION",
        ),
        "projection_rebuild_size": _metric_status(
            float(canonical_total),
            warn=_float(merged_thresholds["projection_rebuild_events_warn"]),
            fail=_float(merged_thresholds["projection_rebuild_events_fail"]),
            issue_prefix="PROJECTION_REBUILD_SIZE",
        ),
    }
    issues = [status.issue_code for status in statuses.values() if status.issue_code]
    if projection_counters and sum(_num(value) for value in projection_counters.values()) > 0:
        issues.append("PROJECTION_REBUILD_COUNTERS_NONZERO")
    if canonical_total > len(events):
        issues.append("PROJECTION_REBUILD_SAMPLE_TRUNCATED")

    lanes = {
        "durable_truth": _lane(
            row_count=profile_active + graph_current_states + canonical_answer,
            hot_count=profile_active + graph_current_states + canonical_answer,
            issue_count=duplicate_strength_total,
            policy_action="keep",
            reason_codes=["SOURCE_BACKED_TRUTH_PRESERVED"],
            preserves=["source_ref", "receipt", "answerability"],
        ),
        "canonical_events": _lane(
            row_count=canonical_total,
            hot_count=canonical_answer,
            cold_count=max(canonical_total - canonical_answer, 0),
            issue_count=canonical_archived_or_prior,
            policy_action="keep_with_projection_filter",
            reason_codes=["CANONICAL_EVENT_LOG_PRESERVED"],
            preserves=["source_ref", "receipt", "current_prior_truth"],
        ),
        "receipts": _lane(
            row_count=receipt_count,
            hot_count=receipt_count,
            policy_action="keep",
            reason_codes=["WRITE_RECEIPT_PRESERVED"],
            preserves=["receipt"],
        ),
        "transcript": _lane(
            row_count=transcript_count,
            cold_count=transcript_count,
            issue_count=transcript_count,
            policy_action="archive_candidate_review_only",
            reason_codes=["RAW_AUDIT_HISTORY_NOT_AUTO_DELETED"],
            preserves=["source_ref", "audit_history"],
        ),
        "continuity": _lane(
            row_count=continuity_count + continuity_frontier_count,
            hot_count=continuity_frontier_count,
            cold_count=continuity_count,
            issue_count=continuity_count,
            policy_action="archive_candidate_review_only",
            reason_codes=["CONTINUITY_HISTORY_NOT_AUTO_DELETED"],
            preserves=["source_ref", "current_prior_truth"],
        ),
        "corpus": _lane(
            row_count=corpus_documents + corpus_sections,
            hot_count=corpus_documents + corpus_sections,
            policy_action="keep_with_reingest_dedup",
            reason_codes=["CORPUS_SOURCE_SECTIONS_PRESERVED"],
            preserves=["source_ref"],
        ),
        "semantic_index": _lane(
            row_count=semantic_rows,
            hot_count=semantic_rows,
            policy_action="rebuild_derived_index_allowed",
            reason_codes=["DERIVED_INDEX_REBUILD_TRUTH_MUTATION_FALSE"],
            preserves=["source_ref", "answerability"],
        ),
        "graph": _lane(
            row_count=graph_states + graph_relations + graph_inferred_relations + graph_conflicts + graph_resolutions,
            hot_count=graph_current_states + graph_relations + graph_inferred_relations,
            cold_count=graph_prior_states + graph_resolutions,
            issue_count=graph_open_conflicts,
            policy_action="review_conflicts_keep_lineage",
            reason_codes=["GRAPH_CONFLICT_AUDIT_TRAIL_PRESERVED"],
            preserves=["source_ref", "current_prior_truth", "conflict_audit_trail"],
        ),
        "proactive": _lane(
            row_count=proactive_events + proactive_pending,
            hot_count=proactive_pending,
            cold_count=proactive_suppressed,
            issue_count=proactive_pending,
            policy_action="state_lifecycle_retention",
            reason_codes=["PROACTIVE_STATE_NOT_MEMORY_TRUTH"],
            preserves=["source_ref", "operator_state"],
        ),
        "operating_recent_work": _lane(
            row_count=operating_records + task_items,
            hot_count=recent_work_records + task_items,
            policy_action="review_recent_work_retention",
            reason_codes=["RECENT_WORK_AUTHORITY_REVIEW_REQUIRED"],
            preserves=["source_ref", "current_prior_truth"],
        ),
        "behavior_policy": _lane(
            row_count=behavior_contracts + compiled_behavior,
            hot_count=behavior_contracts + compiled_behavior,
            policy_action="keep_active_contracts",
            reason_codes=["BEHAVIOR_POLICY_CONTRACT_PRESERVED"],
            preserves=["source_ref", "answerability"],
        ),
        "publish_tier2": _lane(
            row_count=publish_journal + tier2_runs,
            cold_count=publish_journal + tier2_runs,
            policy_action="audit_log_review_only",
            reason_codes=["RUNTIME_AUDIT_HISTORY_NOT_AUTO_DELETED"],
            preserves=["source_ref", "audit_history"],
        ),
    }

    policy_preview = [
        _policy_decision(
            lane="durable_truth",
            action="keep",
            reason_code="SOURCE_BACKED_TRUTH_PRESERVED",
            candidate_count=profile_active + graph_current_states + canonical_answer,
            apply_supported=False,
            risk="truth_preservation",
            preserves=["source_ref", "receipt", "answerability"],
        ),
        _policy_decision(
            lane="semantic_index",
            action="rebuild_derived_index",
            reason_code="DERIVED_INDEX_REBUILD_TRUTH_MUTATION_FALSE",
            candidate_count=semantic_rows,
            apply_supported=True,
            risk="derived_index_only",
            preserves=["answerability"],
        ),
        _policy_decision(
            lane="profile_duplicate_content",
            action="review_only",
            reason_code="TRUTH_CONSOLIDATION_REQUIRES_REVIEW",
            candidate_count=profile_duplicate_groups,
            apply_supported=False,
            risk="truth_preservation_review_required",
            preserves=["source_ref", "receipt", "answerability"],
        ),
        _policy_decision(
            lane="transcript_continuity",
            action="archive_candidate_review_only",
            reason_code="RAW_HISTORY_ARCHIVE_REQUIRES_POLICY",
            candidate_count=transcript_count + continuity_count,
            apply_supported=False,
            risk="audit_history_preservation_required",
            preserves=["source_ref", "audit_history"],
        ),
        _policy_decision(
            lane="graph_conflicts",
            action="review_only",
            reason_code="CONFLICT_RESOLUTION_REQUIRES_AUTHORITY",
            candidate_count=graph_open_conflicts,
            apply_supported=False,
            risk="conflict_audit_trail_preservation_required",
            preserves=["current_prior_truth", "conflict_audit_trail"],
        ),
    ]

    aggregate_status = "pass"
    if any(status.status == "fail" for status in statuses.values()) or "PROJECTION_REBUILD_COUNTERS_NONZERO" in issues:
        aggregate_status = "fail"
    elif any(status.status == "warn" for status in statuses.values()) or issues:
        aggregate_status = "warn"

    report = {
        "schema": PERSISTENT_BLOAT_REPORT_SCHEMA,
        "status": aggregate_status,
        "read_only": True,
        "public_safe": True,
        "scope": {
            "principal_scope_key": scope_key,
            "scope_filter_applied": bool(scope_key),
            "scope_note": "M003 S01 reports structural persistent bloat; later slices may add scoped policy views.",
        },
        "thresholds": {key: float(value) for key, value in sorted(merged_thresholds.items())},
        "lanes": lanes,
        "metrics": metrics,
        "derived_async_state": derived_async,
        "metric_statuses": {
            key: {"status": value.status, "issue_code": value.issue_code} for key, value in statuses.items()
        },
        "policy_preview": policy_preview,
        "issues": issues,
        "issue_count": len(issues),
        "critical_counters": {
            "raw_private_text_leak": 0,
            "truth_cleanup_apply_supported": 0,
            "receipt_preservation_missing": 0,
            "projection_rebuild_counters_nonzero": 1 if "PROJECTION_REBUILD_COUNTERS_NONZERO" in issues else 0,
            "derived_async_hidden_readiness": derived_hidden_readiness,
        },
    }
    if _contains_raw_sentinel(report):
        report["public_safe"] = False
        report["status"] = "fail"
        report["issues"] = [*report["issues"], "PUBLIC_SAFE_SCHEMA_KEY_VIOLATION"]
        report["issue_count"] = len(report["issues"])
        report["critical_counters"]["raw_private_text_leak"] = 1
    return report


__all__ = [
    "DEFAULT_BLOAT_THRESHOLDS",
    "PERSISTENT_BLOAT_POLICY_SCHEMA",
    "PERSISTENT_BLOAT_REPORT_SCHEMA",
    "build_persistent_bloat_report",
]
