from __future__ import annotations

from collections.abc import Mapping
from typing import Any


BACKEND_HEALTH_REASON_CODES = {
    "BACKEND_ACTIVE",
    "BACKEND_NOT_REQUESTED",
    "BACKEND_SQLITE_ACTIVE",
    "BACKEND_SQLITE_FALLBACK_ACTIVE",
    "BACKEND_DEPENDENCY_MISSING",
    "BACKEND_EMBEDDING_CONFIG_MISSING",
    "BACKEND_PERMISSION_ERROR",
    "BACKEND_OPEN_MEMORY_ERROR",
    "BACKEND_ACTIVE_RUNTIME_LOCK_EXPECTED",
    "BACKEND_UNAVAILABLE",
    "SEMANTIC_INDEX_ACTIVE",
    "SEMANTIC_INDEX_DEGRADED",
    "GRAPH_RECALL_ACTIVE",
    "GRAPH_RECALL_DEGRADED",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _classify_backend(capability: Mapping[str, Any]) -> tuple[str, str]:
    kind = _text(capability.get("kind"))
    status = _text(capability.get("status")).lower()
    requested = _text(capability.get("requested")).lower()
    external_requested = bool(capability.get("external_requested"))
    active_backend = _text(capability.get("active_backend"))
    error = _text(capability.get("error"))
    error_class = _text(capability.get("error_class"))
    lowered_error = error.casefold()

    if kind == "semantic_index":
        if not bool(capability.get("requested")):
            return "BACKEND_NOT_REQUESTED", "Semantic index has no active rows yet."
        if status == "active":
            return "SEMANTIC_INDEX_ACTIVE", "Semantic index is available."
        return "SEMANTIC_INDEX_DEGRADED", "Semantic index is not fully available."
    if kind == "graph_recall":
        if not bool(capability.get("requested")):
            return "BACKEND_NOT_REQUESTED", "Graph recall has no current graph rows yet."
        if status == "active":
            return "GRAPH_RECALL_ACTIVE", "Graph recall is available."
        return "GRAPH_RECALL_DEGRADED", "Graph recall is not fully available."
    if not external_requested and requested in {"", "false", "none", "sqlite"}:
        return "BACKEND_SQLITE_ACTIVE", f"{kind or 'backend'} uses SQLite as the active supported mode."
    if status == "active":
        return "BACKEND_ACTIVE", f"{kind or 'backend'} backend is active: {active_backend or requested}."
    if not external_requested:
        return "BACKEND_NOT_REQUESTED", f"{kind or 'backend'} external backend was not requested."
    if error_class == "backend_dependency_missing":
        return "BACKEND_DEPENDENCY_MISSING", f"{kind or 'backend'} external backend dependency is missing."
    if error_class == "backend_embedding_config_missing" or "chroma default embedding is disabled" in lowered_error:
        return (
            "BACKEND_EMBEDDING_CONFIG_MISSING",
            f"{kind or 'backend'} external backend needs embedding configuration before it can run.",
        )
    if error_class == "backend_open_memory_error":
        return "BACKEND_OPEN_MEMORY_ERROR", f"{kind or 'backend'} external backend could not open because of memory/open failure."
    if "permission denied" in lowered_error or "operation not permitted" in lowered_error:
        return "BACKEND_PERMISSION_ERROR", f"{kind or 'backend'} external backend has a permission or ownership problem."
    if "could not set lock on file" in lowered_error or "docs.kuzudb.com/concurrency" in lowered_error:
        return (
            "BACKEND_ACTIVE_RUNTIME_LOCK_EXPECTED",
            f"{kind or 'backend'} external probe is blocked by an active embedded database owner.",
        )
    if bool(capability.get("sqlite_fallback_active")):
        return "BACKEND_SQLITE_FALLBACK_ACTIVE", f"{kind or 'backend'} external backend is degraded; SQLite fallback is active."
    return "BACKEND_UNAVAILABLE", f"{kind or 'backend'} external backend is not available."


def _backend_card(capability: Mapping[str, Any]) -> dict[str, Any]:
    reason_code, safe_reason = _classify_backend(capability)
    return {
        "kind": _text(capability.get("kind")),
        "requested": _text(capability.get("requested")),
        "external_requested": bool(capability.get("external_requested")),
        "active": bool(capability.get("active")),
        "status": _text(capability.get("status")) or "unavailable",
        "active_backend": _text(capability.get("active_backend")),
        "sqlite_fallback_active": bool(capability.get("sqlite_fallback_active")),
        "reason_code": reason_code,
        "safe_reason": safe_reason,
        "error_class": _text(capability.get("error_class")),
    }


def build_backend_health_contract(capabilities: Mapping[str, Any]) -> dict[str, Any]:
    graph_raw = capabilities.get("graph")
    corpus_raw = capabilities.get("corpus")
    semantic_raw = capabilities.get("semantic_index")
    graph_recall_raw = capabilities.get("graph_recall")
    db_raw = capabilities.get("db_substrate")

    graph = _backend_card(graph_raw if isinstance(graph_raw, Mapping) else {})
    corpus = _backend_card(corpus_raw if isinstance(corpus_raw, Mapping) else {})
    semantic = _backend_card(semantic_raw if isinstance(semantic_raw, Mapping) else {"kind": "semantic_index"})
    graph_recall = _backend_card(graph_recall_raw if isinstance(graph_recall_raw, Mapping) else {"kind": "graph_recall"})
    db_substrate = db_raw if isinstance(db_raw, Mapping) else {}

    cards = [graph, corpus, semantic, graph_recall]
    degraded = [
        card
        for card in cards
        if card["status"] not in {"active", "not_requested", "idle"}
        and card["reason_code"] != "BACKEND_NOT_REQUESTED"
    ]
    status = "active" if not degraded else "degraded"
    if _text(db_substrate.get("status")) not in {"", "active"}:
        status = "fail"

    summary_parts = []
    for card in cards:
        if card["status"] == "active":
            summary_parts.append(f"{card['kind']}: active")
        elif card["status"] == "not_requested" or card["reason_code"] == "BACKEND_NOT_REQUESTED":
            summary_parts.append(f"{card['kind']}: not requested")
        else:
            summary_parts.append(f"{card['kind']}: degraded ({card['reason_code']})")

    db_status = _text(db_substrate.get("status")) or "active"
    return {
        "schema": "brainstack.backend_health_contract.v1",
        "status": status,
        "backends": {
            "graph": graph,
            "corpus": corpus,
            "semantic_index": semantic,
            "graph_recall": graph_recall,
        },
        "fallback_channels": {
            "sqlite_storage": {
                "active": db_status == "active",
                "status": db_status,
                "safe_reason": "SQLite durable memory substrate is available."
                if db_status == "active"
                else "SQLite durable memory substrate is degraded.",
            },
            "lexical_index": {
                "active": True,
                "status": "active",
                "safe_reason": "Lexical local recall fallback is available.",
            },
        },
        "agent_summary": "; ".join(summary_parts),
        "reason_code_registry": sorted(BACKEND_HEALTH_REASON_CODES),
        "raw_private_data_included": False,
    }
