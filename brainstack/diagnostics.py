from __future__ import annotations

from typing import Any, Dict, Mapping

from .control_plane import build_working_memory_packet
from .db import BrainstackStore


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
    "semantic_evidence_index",
    "tier2_run_records",
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
    "semantic_evidence_index": "updated_at",
    "tier2_run_records": "updated_at",
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
        }
    enabled = bool(tier2_state.get("enabled"))
    running = bool(tier2_state.get("running"))
    raw_last_result = tier2_state.get("last_result")
    last_result: Mapping[str, Any] = raw_last_result if isinstance(raw_last_result, Mapping) else {}
    last_status = str(last_result.get("status") or "").strip().lower()
    if not enabled:
        status = "unavailable"
        reason = "Tier-2 extraction is disabled by configuration."
    elif running:
        status = "active"
        reason = "Tier-2 worker is currently running."
    elif last_status in {"failed", "error"}:
        status = "degraded"
        reason = "The latest Tier-2 run failed."
    else:
        status = "active"
        reason = "Tier-2 extraction is enabled."
    return {
        "kind": "tier2",
        "requested": enabled,
        "active": enabled and status == "active",
        "status": status,
        "reason": reason,
        "pending_turns": int(tier2_state.get("pending_turns") or 0),
        "last_schedule": dict(tier2_state.get("last_schedule") or {}),
        "last_result": dict(last_result),
        "history_count": int(tier2_state.get("history_count") or 0),
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
    latest_tier2_run = store.latest_tier2_run_record()
    if latest_tier2_run:
        tier2["latest_persistent_run"] = latest_tier2_run
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
    issues: list[Dict[str, str]] = []
    for capability in (graph, corpus, tier2, semantic_index, graph_recall):
        if capability.get("requested") and capability.get("status") != "active":
            issues.append(
                {
                    "capability": str(capability.get("kind") or "tier2"),
                    "status": str(capability.get("status") or "unavailable"),
                    "reason": str(capability.get("reason") or ""),
                }
            )
    verdict = "pass"
    if strict and issues:
        verdict = "fail"
    elif issues:
        verdict = "degraded"
    return {
        "schema": "brainstack.memory_kernel_doctor.v1",
        "strict": bool(strict),
        "verdict": verdict,
        "terms": dict(DIAGNOSTIC_TERMS),
        "capabilities": {
            "graph": graph,
            "corpus": corpus,
            "semantic_index": semantic_index,
            "graph_recall": graph_recall,
            "tier2": tier2,
        },
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
        output.append(
            {
                "evidence_key": _evidence_key(shelf, row),
                "shelf": shelf,
                "id": row.get("id", row.get("row_id", "")),
                "stable_key": row.get("stable_key", ""),
                "source": row.get("source", ""),
                "record_type": row.get("record_type", row.get("kind", "")),
                "retrieval_source": row.get("retrieval_source", ""),
                "match_mode": row.get("match_mode", ""),
                "keyword_score": float(row.get("keyword_score") or 0.0),
                "semantic_score": float(row.get("semantic_score") or 0.0),
                "query_token_overlap": int(row.get("_brainstack_query_token_overlap") or 0),
                "query_token_count": int(row.get("_brainstack_query_token_count") or 0),
                "same_session": bool(row.get("same_session")),
                "same_principal": bool(row.get("same_principal")),
                "suppression_reason": row.get("_brainstack_suppression_reason", ""),
                "citation_id": row.get("citation_id", ""),
                "document_hash": row.get("document_hash", ""),
                "section_hash": row.get("section_hash", ""),
                "created_at": row.get("created_at", row.get("updated_at", "")),
                "excerpt": str(
                    row.get("content")
                    or row.get("title")
                    or row.get("value_text")
                    or row.get("object_text")
                    or row.get("heading")
                    or ""
                )[:220],
            }
        )
    return output


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
    selected_by_shelf = {
        "profile": _summarize_rows("profile", list(packet.get("profile_items") or [])),
        "task": _summarize_rows("task", list(packet.get("task_rows") or [])),
        "operating": _summarize_rows("operating", list(packet.get("operating_rows") or [])),
        "continuity_match": _summarize_rows("continuity_match", list(packet.get("matched") or [])),
        "continuity_recent": _summarize_rows("continuity_recent", list(packet.get("recent") or [])),
        "transcript": _summarize_rows("transcript", list(packet.get("transcript_rows") or [])),
        "graph": _summarize_rows("graph", list(packet.get("graph_rows") or [])),
        "corpus": _summarize_rows("corpus", list(packet.get("corpus_rows") or [])),
    }
    selected_keys = {
        item["evidence_key"]
        for rows in selected_by_shelf.values()
        for item in rows
        if item.get("evidence_key")
    }
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
                "channel_ranks": dict(candidate.get("channel_ranks") or {}),
                "keyword_score": float(candidate.get("keyword_score") or 0.0),
                "semantic_score": float(candidate.get("semantic_score") or 0.0),
                "query_token_overlap": int(candidate.get("query_token_overlap") or 0),
                "query_token_count": int(candidate.get("query_token_count") or 0),
                "excerpt": str(candidate.get("content_excerpt") or "")[:220],
            }
        )
    block = str(packet.get("block") or "")
    sections = [line[3:].strip() for line in block.splitlines() if line.startswith("## ")]
    return {
        "schema": "brainstack.query_inspect.v1",
        "query": str(query or ""),
        "session_id": str(session_id or ""),
        "principal_scope_key": str(principal_scope_key or ""),
        "analysis": dict(packet.get("analysis") or {}),
        "routing": dict(packet.get("routing") or {}),
        "channels": list(packet.get("channels") or []),
        "associative_expansion": dict(packet.get("associative_expansion") or {}),
        "selected_evidence": selected_by_shelf,
        "suppressed_evidence": suppressed,
        "final_packet": {
            "char_count": len(block),
            "section_count": len(sections),
            "sections": sections,
            "preview": block[:1200],
            "policy": dict(packet.get("policy") or {}),
        },
    }
