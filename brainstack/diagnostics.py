from __future__ import annotations

from typing import Any, Dict, Mapping

from .adaptive_evidence_broker import build_broker_trace
from .active_preference_contract import build_active_preference_delivery_inspect_payload
from .control_plane import build_working_memory_packet
from .current_truth_view import rebuild_current_truth_view
from .db import BrainstackStore
from .db_diagnostics import build_db_substrate_snapshot
from .graph_lineage import compact_graph_source_lineage
from .literal_index import detect_literal_tokens, redact_literal_text, semantic_anchor_text
from .answerability import build_memory_answerability
from .backend_health_contract import build_backend_health_contract
from .retrieval_candidate import build_candidate_trace
from .source_sync_spine import build_source_sync_status
from .trace_tiering import build_compact_query_trace
from .working_memory_allocator import build_global_allocator_shadow


DIAGNOSTIC_TERMS: Dict[str, str] = {
    "requested": "A capability or channel was configured or explicitly asked for.",
    "active": "The requested capability is available for use.",
    "degraded": "The capability was requested but is only partially available or fell back.",
    "unavailable": "The capability is not available and was not usable for this path.",
    "selected": "Evidence was included in the final packet or inspect output.",
    "suppressed": "Evidence was found but intentionally excluded by policy, route, authority, or budget.",
    "dropped": "Evidence was discarded because it was duplicate, stale, invalid, or over budget.",
    "no-op": "The operation ran safely and intentionally made no durable change.",
    "failed": "The operation could not complete its intended contract.",
}

_COUNT_TABLES: tuple[str, ...] = (
    "continuity_events",
    "transcript_entries",
    "profile_items",
    "behavior_contracts",
    "compiled_behavior_policies",
    "task_items",
    "operating_records",
    "graph_entities",
    "graph_relations",
    "graph_inferred_relations",
    "graph_states",
    "graph_conflicts",
    "publish_journal",
    "corpus_documents",
    "corpus_sections",
    "source_sync_runs",
    "semantic_evidence_index",
    "tier2_run_records",
    "canonical_memory_events",
)

_LAST_WRITE_COLUMNS: dict[str, str] = {
    "continuity_events": "updated_at",
    "transcript_entries": "created_at",
    "profile_items": "updated_at",
    "behavior_contracts": "updated_at",
    "compiled_behavior_policies": "updated_at",
    "task_items": "updated_at",
    "operating_records": "updated_at",
    "graph_entities": "updated_at",
    "graph_relations": "created_at",
    "graph_inferred_relations": "updated_at",
    "graph_states": "valid_from",
    "graph_conflicts": "updated_at",
    "publish_journal": "updated_at",
    "corpus_documents": "updated_at",
    "corpus_sections": "created_at",
    "source_sync_runs": "created_at",
    "semantic_evidence_index": "updated_at",
    "tier2_run_records": "updated_at",
    "canonical_memory_events": "created_at",
}


def _safe_count(store: BrainstackStore, table: str) -> int:
    try:
        row = store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    except Exception:
        return 0
    return int(row["count"] if row is not None else 0)


def _safe_max(store: BrainstackStore, table: str, column: str) -> str:
    try:
        row = store.conn.execute(f"SELECT MAX({column}) AS value FROM {table}").fetchone()
    except Exception:
        return ""
    return str(row["value"] or "") if row is not None else ""


def _external_backend_requested(name: Any) -> bool:
    return str(name or "").strip().lower() not in {"", "none", "sqlite"}


def _backend_capability(
    *,
    kind: str,
    requested_name: Any,
    active_backend: Any,
    error: Any,
    fallback_reason: str,
) -> Dict[str, Any]:
    requested = str(requested_name or "sqlite").strip().lower()
    external_requested = _external_backend_requested(requested)
    backend_object_active = active_backend is not None
    active = backend_object_active or not external_requested
    error_text = str(error or "").strip()
    error_class = ""
    if error_text:
        lowered_error = error_text.casefold()
        if "std::bad_alloc" in lowered_error or "memoryerror" in lowered_error:
            error_class = "backend_open_memory_error"
        elif "chroma default embedding is disabled" in lowered_error:
            error_class = "backend_embedding_config_missing"
        elif "permission denied" in lowered_error or "operation not permitted" in lowered_error:
            error_class = "backend_permission_error"
        elif "could not set lock on file" in lowered_error or "docs.kuzudb.com/concurrency" in lowered_error:
            error_class = "backend_active_runtime_lock_expected"
        elif "no module" in lowered_error or "import" in lowered_error:
            error_class = "backend_dependency_missing"
        else:
            error_class = "backend_unavailable"
    target_name = str(getattr(active_backend, "target_name", "") or "")
    if backend_object_active and not error_text:
        status = "active"
        reason = f"{kind} backend is active: {target_name or requested}."
    elif external_requested:
        status = "degraded"
        reason = error_text or f"{kind} backend {requested!r} was requested but is not active."
    else:
        status = "active"
        reason = fallback_reason
    return {
        "kind": kind,
        "requested": requested,
        "external_requested": external_requested,
        "active": active,
        "active_backend": target_name or ("sqlite" if not external_requested else ""),
        "sqlite_fallback_active": external_requested and not backend_object_active,
        "status": status,
        "target_name": target_name,
        "reason": reason,
        "error": error_text,
        "error_class": error_class,
    }


def _tier2_capability(tier2_state: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(tier2_state, Mapping):
        return {
            "kind": "tier2",
            "requested": False,
            "active": False,
            "status": "unavailable",
            "reason": "Tier-2 state was not supplied to the doctor surface.",
            "reason_code": "TIER2_STATE_UNAVAILABLE",
        }
    enabled = bool(tier2_state.get("enabled"))
    running = bool(tier2_state.get("running"))
    raw_last_result = tier2_state.get("last_result")
    last_result: Mapping[str, Any] = raw_last_result if isinstance(raw_last_result, Mapping) else {}
    last_status = str(last_result.get("status") or "").strip().lower()
    runtime_route = tier2_state.get("runtime_route")
    route: Mapping[str, Any] = runtime_route if isinstance(runtime_route, Mapping) else {}
    binding_status = str(route.get("binding_status") or "").strip().lower()
    if not enabled:
        status = "unavailable"
        reason = "Tier-2 extraction is disabled by configuration."
        reason_code = "TIER2_DISABLED"
    elif binding_status == "configured_unbound":
        status = "unavailable"
        reason = "Tier-2 runtime is configured but not bound to the actual worker path."
        reason_code = "TIER2_RUNTIME_CONFIGURED_UNBOUND"
    elif running:
        status = "active"
        reason = "Tier-2 worker is currently running."
        reason_code = "TIER2_WORKER_RUNNING"
    elif last_status in {"failed", "error"}:
        status = "degraded"
        reason = "The latest Tier-2 run failed."
        reason_code = "TIER2_LAST_RESULT_FAILED"
    else:
        status = "active"
        reason = "Tier-2 extraction is enabled."
        reason_code = "TIER2_ENABLED"
    return {
        "kind": "tier2",
        "requested": enabled,
        "active": enabled and status == "active",
        "status": status,
        "reason": reason,
        "reason_code": reason_code,
        "pending_turns": int(tier2_state.get("pending_turns") or 0),
        "last_schedule": dict(tier2_state.get("last_schedule") or {}),
        "last_result": dict(last_result),
        "history_count": int(tier2_state.get("history_count") or 0),
        "runtime_route": dict(route),
    }


def _public_tier2_run_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    no_op_reasons = record.get("no_op_reasons") if isinstance(record.get("no_op_reasons"), list) else []
    extracted_counts = record.get("extracted_counts") if isinstance(record.get("extracted_counts"), Mapping) else {}
    action_counts = record.get("action_counts") if isinstance(record.get("action_counts"), Mapping) else {}
    return {
        "run_id": str(record.get("run_id") or ""),
        "turn_number": int(record.get("turn_number") or 0),
        "trigger_reason": str(record.get("trigger_reason") or ""),
        "request_status": str(record.get("request_status") or ""),
        "parse_status": str(record.get("parse_status") or ""),
        "status": str(record.get("status") or ""),
        "transcript_count": int(record.get("transcript_count") or 0),
        "extracted_counts": dict(extracted_counts),
        "action_counts": dict(action_counts),
        "writes_performed": int(record.get("writes_performed") or 0),
        "no_op_reasons": [str(item) for item in no_op_reasons[:8] if str(item or "").strip()],
        "duration_ms": int(record.get("duration_ms") or 0),
        "error_recorded": bool(str(record.get("error_reason") or "").strip()),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }


def _tier2_record_failed(record: Mapping[str, Any]) -> bool:
    request_status = str(record.get("request_status") or "").strip().lower()
    status = str(record.get("status") or "").strip().lower()
    return request_status in {"failed", "error"} or status in {"failed", "error"}


def _tier2_record_route_unavailable(record: Mapping[str, Any]) -> bool:
    status = str(record.get("status") or "").strip().lower()
    reasons = record.get("no_op_reasons") if isinstance(record.get("no_op_reasons"), list) else []
    return status == "skipped_background_task_unavailable" or "background_consolidation_route_unavailable" in {
        str(reason) for reason in reasons
    }


def _apply_persistent_tier2_health(tier2: dict[str, Any], recent_records: list[Mapping[str, Any]]) -> None:
    if not recent_records:
        tier2["persistent_run_health"] = {
            "status": "no_runs",
            "sample_size": 0,
            "failed_count": 0,
            "route_unavailable_count": 0,
        }
        return

    summaries = [_public_tier2_run_summary(record) for record in recent_records]
    latest = recent_records[0]
    latest_failed = _tier2_record_failed(latest)
    latest_route_unavailable = _tier2_record_route_unavailable(latest)
    failed_count = sum(1 for record in recent_records if _tier2_record_failed(record))
    route_unavailable_count = sum(1 for record in recent_records if _tier2_record_route_unavailable(record))

    tier2["latest_persistent_run"] = summaries[0]
    tier2["recent_persistent_runs"] = summaries[:3]
    tier2["persistent_run_health"] = {
        "status": "failed" if latest_failed else ("route_unavailable" if latest_route_unavailable else "ok"),
        "sample_size": len(recent_records),
        "failed_count": failed_count,
        "route_unavailable_count": route_unavailable_count,
        "latest_failed": latest_failed,
        "latest_route_unavailable": latest_route_unavailable,
        "public_safe": True,
    }

    if not tier2.get("requested"):
        return
    if latest_route_unavailable:
        tier2["active"] = False
        tier2["status"] = "unavailable"
        tier2["reason"] = "The latest persisted Tier-2 run could not use a configured background route."
        tier2["reason_code"] = "TIER2_PERSISTED_ROUTE_UNAVAILABLE"
    elif latest_failed and tier2.get("status") == "active":
        tier2["active"] = False
        tier2["status"] = "degraded"
        tier2["reason"] = "The latest persisted Tier-2 run failed."
        tier2["reason_code"] = "TIER2_PERSISTED_RUN_FAILED"


def _graph_candidate_counts(record: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(record, Mapping):
        return {"relations": 0, "inferred_relations": 0, "typed_entities": 0, "total": 0}
    raw_counts = record.get("extracted_counts")
    counts = raw_counts if isinstance(raw_counts, Mapping) else {}
    output = {
        "relations": int(counts.get("relations") or 0),
        "inferred_relations": int(counts.get("inferred_relations") or 0),
        "typed_entities": int(counts.get("typed_entities") or 0),
    }
    output["total"] = sum(output.values())
    return output


def _graph_action_counts(record: Mapping[str, Any] | None) -> dict[str, int]:
    if not isinstance(record, Mapping):
        return {"accepted": 0, "rejected": 0, "noop": 0}
    raw_counts = record.get("action_counts")
    counts = raw_counts if isinstance(raw_counts, Mapping) else {}
    accepted = sum(int(counts.get(action) or 0) for action in ("ADD", "UPDATE", "MERGE_ALIAS"))
    rejected = sum(
        int(counts.get(action) or 0)
        for action in (
            "QUARANTINE_PROPOSAL",
            "REJECT_ASSISTANT_AUTHORED",
            "REJECT_LOW_CONFIDENCE",
            "MARK_CORRECTED_FALSE_EVENT",
            "BLOCK_DERIVED_TRUTH",
        )
    )
    noop = int(counts.get("NONE") or 0)
    return {"accepted": accepted, "rejected": rejected, "noop": noop}


def _graph_producer_capability(
    *,
    row_counts: Mapping[str, int],
    recent_tier2_runs: list[Mapping[str, Any]],
) -> dict[str, Any]:
    graph_rows = {
        "entities": int(row_counts.get("graph_entities") or 0),
        "relations": int(row_counts.get("graph_relations") or 0),
        "inferred_relations": int(row_counts.get("graph_inferred_relations") or 0),
        "states": int(row_counts.get("graph_states") or 0),
        "conflicts": int(row_counts.get("graph_conflicts") or 0),
    }
    graph_row_total = sum(graph_rows.values())
    latest = recent_tier2_runs[0] if recent_tier2_runs else {}
    candidate_counts = _graph_candidate_counts(latest)
    action_counts = _graph_action_counts(latest)
    latest_status = str(latest.get("status") or "").strip().lower() if isinstance(latest, Mapping) else ""
    no_op_reasons = latest.get("no_op_reasons") if isinstance(latest.get("no_op_reasons"), list) else []
    requested = bool(graph_row_total or recent_tier2_runs)
    capability = {
        "kind": "graph_producer",
        "requested": requested,
        "active": True,
        "status": "active",
        "producer_state": "no_input",
        "reason_code": "GRAPH_PRODUCER_NO_INPUT",
        "reason": "No accepted typed graph input has been observed yet.",
        "latest_run_id": str(latest.get("run_id") or "") if isinstance(latest, Mapping) else "",
        "latest_status": latest_status,
        "latest_graph_candidate_counts": candidate_counts,
        "latest_action_counts": action_counts,
        "graph_row_counts": graph_rows,
        "public_safe": True,
    }
    if graph_row_total:
        capability.update(
            {
                "producer_state": "projected",
                "reason_code": "GRAPH_PRODUCER_PROJECTED_TYPED_INPUT",
                "reason": "Accepted typed graph input has projected graph rows.",
            }
        )
        return capability
    if not recent_tier2_runs:
        capability["requested"] = False
        return capability
    if latest_status == "failed":
        capability.update(
            {
                "active": False,
                "status": "degraded",
                "producer_state": "failed",
                "reason_code": "GRAPH_PRODUCER_BLOCKED_BY_TIER2_FAILURE",
                "reason": "The latest persisted Tier-2 producer run failed before graph projection.",
            }
        )
        return capability
    if "background_consolidation_route_unavailable" in {str(reason) for reason in no_op_reasons}:
        capability.update(
            {
                "active": False,
                "status": "degraded",
                "producer_state": "route_unavailable",
                "reason_code": "GRAPH_PRODUCER_ROUTE_UNAVAILABLE",
                "reason": "The typed graph producer route was not available.",
            }
        )
        return capability
    if candidate_counts["total"] <= 0:
        capability.update(
            {
                "producer_state": "no_graph_candidates",
                "reason_code": "GRAPH_PRODUCER_NO_TYPED_GRAPH_CANDIDATES",
                "reason": "The latest Tier-2 run emitted no typed graph candidates.",
            }
        )
        return capability
    if action_counts["accepted"] > 0:
        capability.update(
            {
                "active": False,
                "status": "degraded",
                "producer_state": "accepted_no_projection",
                "reason_code": "GRAPH_PRODUCER_ACCEPTED_WITHOUT_PROJECTION",
                "reason": "Typed graph input was accepted but no graph rows are visible.",
            }
        )
        return capability
    capability.update(
        {
            "producer_state": "rejected",
            "reason_code": "GRAPH_PRODUCER_TYPED_INPUT_REJECTED",
            "reason": "Typed graph candidates were rejected or quarantined before graph projection.",
        }
    )
    return capability


def _capability_issue_severity(capability: Mapping[str, Any]) -> str:
    status = str(capability.get("status") or "unavailable").strip()
    kind = str(capability.get("kind") or "").strip()
    if kind == "db_substrate" and status != "active":
        return "fatal"
    if status == "unavailable" and capability.get("requested"):
        return "error"
    if status == "degraded":
        return "warn"
    return "info"


def _named_backend_health(capability: Mapping[str, Any], *, backend_name: str) -> Dict[str, Any]:
    requested = str(capability.get("requested") or "").strip().lower()
    expected = str(backend_name or "").strip().lower()
    if requested != expected:
        return {
            "kind": expected,
            "requested": False,
            "active": False,
            "status": "not_requested",
            "reason": f"{expected} backend was not requested for this query path.",
        }
    return {
        "kind": expected,
        "requested": True,
        "active": bool(capability.get("active")),
        "status": str(capability.get("status") or "unavailable"),
        "reason": str(capability.get("reason") or ""),
        "error": str(capability.get("error") or ""),
        "error_class": str(capability.get("error_class") or ""),
    }


def _query_capability_health(store: BrainstackStore) -> Dict[str, Any]:
    doctor = build_memory_kernel_doctor(store, strict=False)
    capabilities = doctor.get("capabilities")
    capability_map: Mapping[str, Any] = capabilities if isinstance(capabilities, Mapping) else {}
    raw_graph = capability_map.get("graph")
    raw_corpus = capability_map.get("corpus")
    graph: Mapping[str, Any] = raw_graph if isinstance(raw_graph, Mapping) else {}
    corpus: Mapping[str, Any] = raw_corpus if isinstance(raw_corpus, Mapping) else {}
    db_substrate_raw = capability_map.get("db_substrate")
    semantic_index_raw = capability_map.get("semantic_index")
    graph_recall_raw = capability_map.get("graph_recall")
    graph_producer_raw = capability_map.get("graph_producer")
    source_sync_raw = capability_map.get("source_sync_spine")
    db_substrate: Mapping[str, Any] = db_substrate_raw if isinstance(db_substrate_raw, Mapping) else {}
    semantic_index: Mapping[str, Any] = semantic_index_raw if isinstance(semantic_index_raw, Mapping) else {}
    graph_recall: Mapping[str, Any] = graph_recall_raw if isinstance(graph_recall_raw, Mapping) else {}
    graph_producer: Mapping[str, Any] = graph_producer_raw if isinstance(graph_producer_raw, Mapping) else {}
    source_sync: Mapping[str, Any] = source_sync_raw if isinstance(source_sync_raw, Mapping) else {}
    backend_health = build_backend_health_contract(
        {
            "graph": graph,
            "corpus": corpus,
            "db_substrate": db_substrate,
            "semantic_index": semantic_index,
            "graph_recall": graph_recall,
        }
    )
    return {
        "schema": "brainstack.query_capability_health.v1",
        "verdict": str(doctor.get("verdict") or "degraded"),
        "backend_health": backend_health,
        "sqlite": dict(db_substrate),
        "graph": dict(graph),
        "corpus": dict(corpus),
        "kuzu": _named_backend_health(graph, backend_name="kuzu"),
        "chroma": _named_backend_health(corpus, backend_name="chroma"),
        "semantic_index": dict(semantic_index),
        "graph_recall": dict(graph_recall),
        "graph_producer": dict(graph_producer),
        "source_sync_spine": dict(source_sync),
        "lexical_index": {
            "kind": "lexical_index",
            "requested": True,
            "active": True,
            "status": "active",
            "reason": "SQLite FTS/LIKE lexical fallback is available for scoped local recall.",
        },
        "issues": list(doctor.get("issues") or []),
    }


def build_memory_kernel_doctor(
    store: BrainstackStore,
    *,
    strict: bool = False,
    tier2_state: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a bounded read-only health snapshot for the Brainstack kernel."""
    row_counts = {table: _safe_count(store, table) for table in _COUNT_TABLES}
    last_writes = {
        table: _safe_max(store, table, column)
        for table, column in _LAST_WRITE_COLUMNS.items()
    }
    graph = _backend_capability(
        kind="graph",
        requested_name=getattr(store, "_graph_backend_name", "sqlite"),
        active_backend=getattr(store, "_graph_backend", None),
        error=getattr(store, "_graph_backend_error", ""),
        fallback_reason="No external graph backend was requested; SQLite graph storage/search is the active mode.",
    )
    corpus = _backend_capability(
        kind="corpus",
        requested_name=getattr(store, "_corpus_backend_name", "sqlite"),
        active_backend=getattr(store, "_corpus_backend", None),
        error=getattr(store, "_corpus_backend_error", ""),
        fallback_reason="No external corpus backend was requested; SQLite corpus storage/search is the active mode.",
    )
    tier2 = _tier2_capability(tier2_state)
    db_substrate = build_db_substrate_snapshot(store.conn)
    recent_tier2_runs: list[Mapping[str, Any]] = []
    try:
        if hasattr(store, "recent_tier2_run_records"):
            recent_tier2_runs = list(store.recent_tier2_run_records(limit=5))
        else:
            latest_tier2_run = store.latest_tier2_run_record()
            if latest_tier2_run:
                recent_tier2_runs = [latest_tier2_run]
    except Exception:
        recent_tier2_runs = []
    _apply_persistent_tier2_health(tier2, recent_tier2_runs)
    semantic_index = dict(store.semantic_evidence_channel_status())
    semantic_index.update(
        {
            "kind": "semantic_index",
            "requested": bool(semantic_index.get("active_count") or semantic_index.get("stale_count")),
            "active": str(semantic_index.get("status") or "") == "active",
        }
    )
    graph_recall = dict(store.graph_recall_channel_status())
    graph_recall.update(
        {
            "kind": "graph_recall",
            "requested": bool(graph_recall.get("graph_row_count")),
            "active": str(graph_recall.get("status") or "") == "active",
        }
    )
    graph_producer = _graph_producer_capability(
        row_counts=row_counts,
        recent_tier2_runs=recent_tier2_runs,
    )
    source_sync = build_source_sync_status(store)
    source_sync.update(
        {
            "kind": "source_sync_spine",
            "requested": bool(source_sync.get("run_count") or source_sync.get("active_document_count")),
            "active": str(source_sync.get("status") or "") in {"active", "idle"},
        }
    )
    issues: list[Dict[str, str]] = []
    for capability in (
        db_substrate,
        graph,
        corpus,
        tier2,
        semantic_index,
        graph_recall,
        graph_producer,
        source_sync,
    ):
        if capability.get("requested") and capability.get("status") != "active":
            issues.append(
                {
                    "capability": str(capability.get("kind") or "tier2"),
                    "status": str(capability.get("status") or "unavailable"),
                    "severity": _capability_issue_severity(capability),
                    "reason": str(capability.get("reason") or ""),
                    "reason_code": str(capability.get("reason_code") or ""),
                }
            )
    verdict = "pass"
    if strict and issues:
        verdict = "fail"
    elif issues:
        verdict = "degraded"
    capabilities = {
        "db_substrate": db_substrate,
        "graph": graph,
        "corpus": corpus,
        "semantic_index": semantic_index,
        "graph_recall": graph_recall,
        "graph_producer": graph_producer,
        "source_sync_spine": source_sync,
        "tier2": tier2,
    }
    backend_health = build_backend_health_contract(capabilities)
    return {
        "schema": "brainstack.memory_kernel_doctor.v1",
        "strict": bool(strict),
        "verdict": verdict,
        "terms": dict(DIAGNOSTIC_TERMS),
        "capabilities": capabilities,
        "backend_health": backend_health,
        "row_counts": row_counts,
        "last_writes": last_writes,
        "issues": issues,
    }


def _evidence_key(shelf: str, row: Mapping[str, Any]) -> str:
    for key in ("stable_key", "storage_key", "key"):
        value = str(row.get(key) or "").strip()
        if value:
            return f"{shelf}:{value}"
    if shelf == "corpus":
        return f"corpus:{row.get('document_id', 0)}:{row.get('section_index', 0)}"
    if shelf == "graph":
        return f"graph:{row.get('row_type', '')}:{row.get('id', row.get('row_id', 0))}"
    return f"{shelf}:{row.get('id', row.get('row_id', 0))}"


def _candidate_evidence_key(shelf: str, candidate: Mapping[str, Any]) -> str:
    key = str(candidate.get("key") or "").strip()
    if key:
        if shelf and key.startswith(f"{shelf}:"):
            return key
        return f"{shelf}:{key}" if shelf else key
    return _evidence_key(shelf, candidate)


def _summarize_rows(shelf: str, rows: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    output: list[Dict[str, Any]] = []
    for row in rows:
        raw_metadata = row.get("metadata")
        metadata: Dict[str, Any] = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
        lineage_metadata = metadata
        if shelf == "graph" and str(row.get("row_type") or "") == "conflict":
            raw_conflict_metadata = row.get("conflict_metadata")
            lineage_metadata = dict(raw_conflict_metadata) if isinstance(raw_conflict_metadata, dict) else metadata
        raw_temporal = metadata.get("temporal")
        temporal: Dict[str, Any] = dict(raw_temporal) if isinstance(raw_temporal, dict) else {}
        raw_corpus_taxonomy = metadata.get("corpus_taxonomy")
        corpus_taxonomy: Dict[str, Any] = dict(raw_corpus_taxonomy) if isinstance(raw_corpus_taxonomy, dict) else {}
        raw_text = str(
            row.get("content")
            or row.get("title")
            or row.get("value_text")
            or row.get("object_text")
            or row.get("heading")
            or ""
        )
        literal_index = metadata.get("literal_index")
        literal_index = dict(literal_index) if isinstance(literal_index, dict) else {}
        explicit_truth_parity = metadata.get("explicit_truth_parity")
        explicit_truth_parity = dict(explicit_truth_parity) if isinstance(explicit_truth_parity, dict) else {}
        literal_tokens = list(literal_index.get("literal_tokens") or detect_literal_tokens(raw_text))
        conversation_event = metadata.get("conversation_event")
        conversation_event = dict(conversation_event) if isinstance(conversation_event, dict) else {}
        redacted_excerpt = redact_literal_text(raw_text, literal_tokens=literal_tokens)[:220]
        output.append(
            {
                "evidence_key": _evidence_key(shelf, row),
                "shelf": shelf,
                "id": row.get("id", row.get("row_id", "")),
                "row_id": row.get("row_id", ""),
                "row_type": row.get("row_type", ""),
                "stable_key": row.get("stable_key", ""),
                "category": row.get("category", ""),
                "source": row.get("source", ""),
                "record_type": row.get("record_type", row.get("kind", "")),
                "fact_class": row.get("fact_class", ""),
                "subject": row.get("subject", ""),
                "predicate": row.get("predicate", row.get("attribute", "")),
                "object_value": row.get("object_value", row.get("value_text", "")),
                "conflict_value": row.get("conflict_value", ""),
                "conflict_source": row.get("conflict_source", ""),
                "matched_alias": row.get("matched_alias", ""),
                "entity_resolution_source": row.get("entity_resolution_source", ""),
                "entity_resolution_reason": row.get("entity_resolution_reason", ""),
                "entity_resolution_confidence": float(row.get("entity_resolution_confidence") or 0.0),
                "entity_resolution_merge_eligible": bool(row.get("entity_resolution_merge_eligible")),
                "happened_at": row.get("happened_at", ""),
                "valid_to": row.get("valid_to", temporal.get("valid_to", "")),
                "retrieval_source": row.get("retrieval_source", ""),
                "match_mode": row.get("match_mode", ""),
                "graph_backend_requested": row.get("graph_backend_requested", ""),
                "graph_backend_status": row.get("graph_backend_status", ""),
                "graph_fallback_reason": row.get("graph_fallback_reason", ""),
                "graph_source_lineage": compact_graph_source_lineage(lineage_metadata) if shelf == "graph" else {},
                "graph_authority_status": lineage_metadata.get("graph_authority_status", "") if shelf == "graph" else "",
                "keyword_score": float(row.get("keyword_score") or 0.0),
                "semantic_score": float(row.get("semantic_score") or 0.0),
                "query_token_overlap": int(row.get("_brainstack_query_token_overlap") or 0),
                "query_token_count": int(row.get("_brainstack_query_token_count") or 0),
                "literal_slot_match": dict(row.get("_brainstack_literal_slot_match") or {}),
                "rrf_score": float(row.get("_brainstack_rrf_score") or 0.0),
                "channels": list(row.get("_brainstack_channels") or []),
                "channel_ranks": dict(row.get("_brainstack_channel_ranks") or {}),
                "selection_status": "selected" if row.get("_brainstack_channels") else "",
                "selection_reason": "selected_by_fusion_and_budget" if row.get("_brainstack_channels") else "",
                "authority_floor": int(row.get("_brainstack_authority_floor") or 0),
                "authority_floor_applied": bool(row.get("_brainstack_authority_floor_applied")),
                "same_session": bool(row.get("same_session")),
                "same_principal": bool(row.get("same_principal")),
                "suppression_reason": row.get("_brainstack_suppression_reason", ""),
                "authority_level": metadata.get("authority_level", ""),
                "workstream_id": metadata.get("workstream_id", ""),
                "owner_role": metadata.get("owner_role", ""),
                "source_kind": metadata.get("source_kind", ""),
                "current_assignment_authority": bool(metadata.get("current_assignment_authority")),
                "current_assignment_authority_schema": metadata.get("current_assignment_authority_schema", ""),
                "consolidation_source": dict(metadata.get("consolidation_source") or {})
                if isinstance(metadata.get("consolidation_source"), dict)
                else {},
                "recap_surface": bool(row.get("_brainstack_recap_surface")),
                "supporting_evidence_only": bool(row.get("_brainstack_supporting_evidence_only")),
                "runtime_state_only": bool(row.get("_brainstack_runtime_state_only")),
                "workstream_recap_reason": row.get("_brainstack_workstream_recap_reason", ""),
                "citation_id": row.get("citation_id", ""),
                "document_hash": row.get("document_hash", ""),
                "section_hash": row.get("section_hash", ""),
                "corpus_taxonomy": corpus_taxonomy if shelf == "corpus" else {},
                "source_display_id": corpus_taxonomy.get("display_source_id", "") if shelf == "corpus" else "",
                "public_source_uri": corpus_taxonomy.get("public_source_uri", "") if shelf == "corpus" else "",
                "literal_index_schema": literal_index.get("schema", ""),
                "literal_tokens": literal_tokens,
                "semantic_anchor_text": literal_index.get("semantic_anchor_text")
                or semantic_anchor_text(raw_text, literal_tokens=literal_tokens),
                "explicit_truth_parity": explicit_truth_parity,
                "projection_status": explicit_truth_parity.get("projection_status", ""),
                "divergence_status": explicit_truth_parity.get("divergence_status", ""),
                "parity_observable": explicit_truth_parity.get("parity_observable", ""),
                "conversation_event": conversation_event,
                "event_type": conversation_event.get("event_type", ""),
                "event_id": conversation_event.get("event_id", ""),
                "bounded_scope_only": bool(conversation_event.get("bounded_scope_only")),
                "corpus_retrieval_trace": dict(row.get("_brainstack_corpus_retrieval_trace") or {})
                if shelf == "corpus"
                else {},
                "created_at": row.get("created_at", row.get("updated_at", "")),
                "excerpt": redacted_excerpt,
            }
        )
    return output


def _selected_by_shelf_from_packet(packet: Mapping[str, Any]) -> dict[str, list[Dict[str, Any]]]:
    return {
        "profile": _summarize_rows("profile", list(packet.get("profile_items") or [])),
        "task": _summarize_rows("task", list(packet.get("task_rows") or [])),
        "operating": _summarize_rows("operating", list(packet.get("operating_rows") or [])),
        "continuity_match": _summarize_rows("continuity_match", list(packet.get("matched") or [])),
        "continuity_recent": _summarize_rows("continuity_recent", list(packet.get("recent") or [])),
        "transcript": _summarize_rows("transcript", list(packet.get("transcript_rows") or [])),
        "graph": _summarize_rows("graph", list(packet.get("graph_rows") or [])),
        "corpus": _summarize_rows("corpus", list(packet.get("corpus_rows") or [])),
    }


def _selected_evidence_keys(selected_by_shelf: Mapping[str, list[Dict[str, Any]]]) -> set[str]:
    return {
        item["evidence_key"]
        for rows in selected_by_shelf.values()
        for item in rows
        if item.get("evidence_key")
    }


def _suppressed_evidence_from_packet(packet: Mapping[str, Any], *, selected_keys: set[str]) -> list[Dict[str, Any]]:
    suppressed: list[Dict[str, Any]] = []
    for candidate in list(packet.get("fused_candidates") or [])[:40]:
        shelf = str(candidate.get("shelf") or "")
        evidence_key = _candidate_evidence_key(shelf, candidate)
        if evidence_key in selected_keys:
            continue
        suppressed.append(
            {
                "evidence_key": evidence_key,
                "shelf": shelf,
                "reason": "Candidate was not selected by route, authority, dedupe, or packet budget.",
                "suppression_reason": str(candidate.get("suppression_reason") or ""),
                "retrieval_source": str(candidate.get("retrieval_source") or ""),
                "match_mode": str(candidate.get("match_mode") or ""),
                "row_type": str(candidate.get("row_type") or ""),
                "fact_class": str(candidate.get("fact_class") or ""),
                "matched_alias": str(candidate.get("matched_alias") or ""),
                "entity_resolution_source": str(candidate.get("entity_resolution_source") or ""),
                "entity_resolution_reason": str(candidate.get("entity_resolution_reason") or ""),
                "entity_resolution_confidence": float(candidate.get("entity_resolution_confidence") or 0.0),
                "entity_resolution_merge_eligible": bool(candidate.get("entity_resolution_merge_eligible")),
                "graph_backend_status": str(candidate.get("graph_backend_status") or ""),
                "graph_backend_requested": str(candidate.get("graph_backend_requested") or ""),
                "graph_fallback_reason": str(candidate.get("graph_fallback_reason") or ""),
                "authority_level": str(candidate.get("operating_authority_level") or ""),
                "workstream_id": str(candidate.get("workstream_id") or ""),
                "owner_role": str(candidate.get("operating_owner_role") or ""),
                "recap_surface": bool(candidate.get("recap_surface")),
                "supporting_evidence_only": bool(candidate.get("supporting_evidence_only")),
                "runtime_state_only": bool(candidate.get("runtime_state_only")),
                "workstream_recap_reason": str(candidate.get("workstream_recap_reason") or ""),
                "channel_ranks": dict(candidate.get("channel_ranks") or {}),
                "selection_status": str(candidate.get("selection_status") or ""),
                "selection_reason": str(candidate.get("selection_reason") or ""),
                "keyword_score": float(candidate.get("keyword_score") or 0.0),
                "semantic_score": float(candidate.get("semantic_score") or 0.0),
                "query_token_overlap": int(candidate.get("query_token_overlap") or 0),
                "query_token_count": int(candidate.get("query_token_count") or 0),
                "excerpt": str(candidate.get("content_excerpt") or "")[:220],
            }
        )
    return suppressed


def _packet_sections(block: str) -> list[str]:
    return [line[3:].strip() for line in block.splitlines() if line.startswith("## ")]


def _explicit_truth_parity_from_selected(selected_by_shelf: Mapping[str, list[Dict[str, Any]]]) -> list[Dict[str, Any]]:
    return [
        dict(item.get("explicit_truth_parity") or {})
        for rows in selected_by_shelf.values()
        for item in rows
        if isinstance(item.get("explicit_truth_parity"), dict) and item.get("explicit_truth_parity")
    ]


def _final_packet_diagnostic_payload(
    *,
    block: str,
    sections: list[str],
    policy_snapshot: Mapping[str, Any],
    packet_answerability: Mapping[str, Any],
    explicit_truth_parity: list[Dict[str, Any]],
    selected_by_shelf: Mapping[str, list[Dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "char_count": len(block),
        "section_count": len(sections),
        "sections": sections,
        "preview": block[:1600],
        "policy": dict(policy_snapshot),
        "memory_answerability": dict(packet_answerability),
        "explicit_truth_parity": explicit_truth_parity,
        "diagnostic_evidence_count": sum(len(rows) for rows in selected_by_shelf.values()),
        "answerable_evidence_count": len(packet_answerability.get("answer_evidence_ids") or []),
    }


def build_query_inspect(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str = "",
    timezone_name: str = "UTC",
    route_resolver: Any = None,
    profile_match_limit: int = 4,
    continuity_recent_limit: int = 4,
    continuity_match_limit: int = 4,
    transcript_match_limit: int = 2,
    transcript_char_budget: int = 560,
    evidence_item_budget: int = 8,
    graph_limit: int = 6,
    corpus_limit: int = 4,
    corpus_char_budget: int = 700,
    operating_match_limit: int = 3,
    system_substrate: Mapping[str, Any] | None = None,
    render_ordinary_contract: bool = False,
    trace_mode: str = "full",
) -> Dict[str, Any]:
    """Inspect one query path without writing retrieval telemetry."""
    packet = build_working_memory_packet(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        profile_match_limit=profile_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        evidence_item_budget=evidence_item_budget,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
        operating_match_limit=operating_match_limit,
        route_resolver=route_resolver,
        timezone_name=timezone_name,
        system_substrate=dict(system_substrate or {}),
        render_ordinary_contract=render_ordinary_contract,
        record_retrievals=False,
    )
    selected_by_shelf = _selected_by_shelf_from_packet(packet)
    selected_keys = _selected_evidence_keys(selected_by_shelf)
    suppressed = _suppressed_evidence_from_packet(packet, selected_keys=selected_keys)
    block = str(packet.get("block") or "")
    sections = _packet_sections(block)
    candidate_trace = build_candidate_trace(
        selected_by_shelf=selected_by_shelf,
        suppressed_rows=suppressed,
        suppressed_limit=40,
    )
    adaptive_evidence_broker = build_broker_trace(retrieval_trace=candidate_trace)
    policy_snapshot = dict(packet.get("policy") or {})
    capability_health = _query_capability_health(store)
    candidate_answerability = build_memory_answerability(
        query=str(query or ""),
        analysis=dict(packet.get("analysis") or {}),
        selected_by_shelf=selected_by_shelf,
    )
    packet_answerability = build_memory_answerability(
        query=str(query or ""),
        analysis=dict(packet.get("analysis") or {}),
        selected_by_shelf=selected_by_shelf,
        packet_text=block,
    )
    active_preference_delivery = build_active_preference_delivery_inspect_payload(
        system_substrate.get("active_preference_contract") if isinstance(system_substrate, Mapping) else None,
        system_substrate.get("active_preference_delivery_trace") if isinstance(system_substrate, Mapping) else None,
    )
    explicit_truth_parity = _explicit_truth_parity_from_selected(selected_by_shelf)
    canonical_events = []
    if hasattr(store, "list_canonical_memory_events"):
        canonical_events = [
            row.get("event", {})
            for row in store.list_canonical_memory_events(limit=100)
            if isinstance(row.get("event"), Mapping)
        ]
    current_truth_view = rebuild_current_truth_view(canonical_events)
    report = {
        "schema": "brainstack.query_inspect.v1",
        "query": str(query or ""),
        "session_id": str(session_id or ""),
        "principal_scope_key": str(principal_scope_key or ""),
        "analysis": dict(packet.get("analysis") or {}),
        "routing": dict(packet.get("routing") or {}),
        "channels": list(packet.get("channels") or []),
        "entity_resolution": dict(packet.get("entity_resolution") or {}),
        "associative_expansion": dict(packet.get("associative_expansion") or {}),
        "selected_evidence": selected_by_shelf,
        "suppressed_evidence": suppressed,
        "retrieval_candidates": candidate_trace,
        "adaptive_evidence_broker": adaptive_evidence_broker,
        "adaptive_route_plan": dict(packet.get("adaptive_route_plan") or {}),
        "current_truth_view": {
            "schema": current_truth_view.get("schema"),
            "status": current_truth_view.get("status"),
            "rebuild": dict(current_truth_view.get("rebuild") or {}),
            "source_event_span": dict(current_truth_view.get("source_event_span") or {}),
            "receipt_coverage": dict(current_truth_view.get("receipt_coverage") or {}),
            "counters": dict(current_truth_view.get("counters") or {}),
            "deep_graph_path": dict(current_truth_view.get("deep_graph_path") or {}),
            "public_safety": dict(current_truth_view.get("public_safety") or {}),
            "current_truth_row_count": len(current_truth_view.get("current_truth_rows") or []),
            "non_answerable_row_count": len(current_truth_view.get("non_answerable_rows") or []),
        },
        "candidate_answerability": candidate_answerability,
        "packet_answerability": packet_answerability,
        "memory_answerability": packet_answerability,
        "active_preference_delivery": active_preference_delivery,
        "explicit_truth_parity": explicit_truth_parity,
        "global_allocator_shadow": build_global_allocator_shadow(
            candidate_trace,
            candidate_budget=int(policy_snapshot.get("evidence_item_budget") or evidence_item_budget or 1),
            enabled=True,
        ),
        "capability_health": capability_health,
        "final_packet": _final_packet_diagnostic_payload(
            block=block,
            sections=sections,
            policy_snapshot=policy_snapshot,
            packet_answerability=packet_answerability,
            explicit_truth_parity=explicit_truth_parity,
            selected_by_shelf=selected_by_shelf,
        ),
    }
    if str(trace_mode or "full").strip().casefold() == "compact":
        return build_compact_query_trace(report)
    report["trace_mode"] = "full"
    report["compact_trace_available"] = True
    return report
