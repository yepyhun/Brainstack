# ruff: noqa: F401
from __future__ import annotations

from functools import wraps
import hashlib
import logging
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, TypeVar

from ..behavior_policy import (
    BEHAVIOR_POLICY_COMPILER_VERSION,
    BEHAVIOR_POLICY_SCHEMA_VERSION,
    build_behavior_policy_snapshot,
    compile_behavior_policy,
)
from ..corpus_ingest import corpus_ingest_versions, normalize_corpus_source
from ..corpus_backend import CorpusBackend, create_corpus_backend
from ..db_row_codecs import (
    corpus_search_row_to_dict as _corpus_search_row_to_dict,
    decode_json_array as _decode_json_array,
    decode_json_object as _decode_json_object,
    operating_row_to_dict as _operating_row_to_dict,
    task_row_to_dict as _task_row_to_dict,
)
from ..db_migrations import (
    MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1,
    MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1,
    MIGRATION_COMPILED_BEHAVIOR_POLICY_V1,
    MIGRATION_COMPILED_BEHAVIOR_POLICY_V2,
    MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1,
    MIGRATION_GRAPH_SOURCE_LINEAGE_V1,
    MIGRATION_RECENT_WORK_AUTHORITY_V1,
    MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1,
    MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2,
    MIGRATION_STYLE_CONTRACT_BEHAVIOR_DEMOTION_V1,
    MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1,
    mark_migration_applied,
    migration_applied,
    run_compatibility_migrations,
)
from ..db_schema import initialize_schema
from ..graph_backend import GraphBackend, create_graph_backend
from ..graph_lineage import attach_graph_source_lineage
from ..logistics_contract import derive_transcript_logistics_typed_entities
from ..live_system_state import (
    build_live_system_state_snapshot,
    list_live_system_state_rows,
    search_live_system_state_rows,
)
from ..literal_index import enrich_metadata_with_literal_sidecar, user_turn_event_sidecar
from ..profile_contract import (
    COMMUNICATION_CANONICAL_SLOTS,
    derive_transcript_identity_profile_items,
    expand_communication_profile_items,
    normalize_profile_slot,
)
from ..operating_context import build_operating_context_snapshot
from ..operating_truth import (
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    OPERATING_RECORD_TYPES,
    normalize_operating_record_metadata,
)
from ..provenance import merge_provenance
from ..semantic_evidence import (
    SEMANTIC_EVIDENCE_INDEX_VERSION,
    decode_semantic_metadata,
    normalize_semantic_terms,
    semantic_evidence_fingerprint,
    semantic_similarity,
)
from ..scope_identity import (
    PERSONAL_SCOPE_KEY_FIELDS,
    PRINCIPAL_SCOPE_KEY_FIELDS,
    scope_key_from_payload,
    scope_payload_from_key,
)
from ..style_contract import (
    STYLE_CONTRACT_DOC_KIND,
    STYLE_CONTRACT_SLOT,
    apply_style_contract_rule_correction,
    build_style_contract_from_document,
    list_style_contract_rules,
    style_contract_cleanliness_issues,
    style_contract_source_rank,
)
from ..task_memory import STATUS_OPEN
from ..temporal import (
    infer_relative_duration_valid_to,
    is_background_relative_duration_source,
    is_unbounded_background_volatile_state,
    merge_temporal,
    normalize_temporal_fields,
    record_is_effective_at,
    record_temporal_status,
)
from ..usefulness import (
    apply_retrieval_telemetry,
    graph_priority_adjustment,
    profile_priority_adjustment,
)
from ..write_contract import build_write_decision_trace


F = TypeVar("F", bound=Callable[..., Any])
logger = logging.getLogger(__name__)


def _env_truthy(name: str, *, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


NUMERIC_TOKEN_RE = re.compile(r"\d+(?::\d+)?(?:\.\d+)?")
QUERY_TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)
PROFILE_SCOPE_DELIMITER = "::principal_scope::"
PRINCIPAL_SCOPED_PROFILE_CATEGORIES = {"identity", "preference"}
VOLATILE_OPERATING_RECORD_TYPES = {"session_state"}
VOLATILE_OPERATING_MIN_SEMANTIC_SCORE = 0.5
TRANSCRIPT_HYGIENE_MARKERS = (
    "Assistant: Operation interrupted:",
    "Assistant: Session reset.",
)
BEHAVIOR_CONTRACT_ACTIVE_STATUS = "active"
BEHAVIOR_CONTRACT_SUPERSEDED_STATUS = "superseded"
BEHAVIOR_CONTRACT_QUARANTINED_STATUS = "quarantined"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_query_terms(query: str, *, limit: int) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for token in QUERY_TOKEN_RE.findall(str(query or "").casefold()):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        output.append(token)
        if len(output) >= limit:
            break
    return output


def _keyword_score_for_rank(rank: int) -> float:
    return 1.0 / float(max(1, rank))


def _attach_keyword_scores(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    annotated: List[Dict[str, Any]] = []
    for rank, row in enumerate(rows, start=1):
        payload = dict(row)
        payload["keyword_score"] = max(float(payload.get("keyword_score") or 0.0), _keyword_score_for_rank(rank))
        annotated.append(payload)
    return annotated


def _query_token_set(value: Any) -> set[str]:
    return {
        token
        for token in QUERY_TOKEN_RE.findall(str(value or "").casefold())
        if len(token) >= 3
    }


def _operating_relevance_text(row: Mapping[str, Any]) -> str:
    parts = [str(row.get("content") or "")]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        for semantic_text in decode_semantic_metadata(metadata):
            parts.append(str(semantic_text or ""))
    return " ".join(part for part in parts if part)


def _volatile_operating_keyword_match(row: Mapping[str, Any], *, query: str) -> bool:
    if str(row.get("record_type") or "").strip() not in VOLATILE_OPERATING_RECORD_TYPES:
        return True
    query_tokens = _query_token_set(query)
    if len(query_tokens) <= 1:
        return True
    row_tokens = _query_token_set(_operating_relevance_text(row))
    overlap = len(query_tokens & row_tokens)
    return overlap >= min(2, len(query_tokens))


def _volatile_operating_semantic_match(row: Mapping[str, Any]) -> bool:
    if str(row.get("record_type") or "").strip() not in VOLATILE_OPERATING_RECORD_TYPES:
        return True
    return float(row.get("semantic_score") or 0.0) >= VOLATILE_OPERATING_MIN_SEMANTIC_SCORE


def build_fts_query(query: str) -> str:
    tokens = _extract_query_terms(query, limit=12)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def build_like_tokens(query: str, *, limit: int = 8) -> List[str]:
    return [f"%{token.lower()}%" for token in _extract_query_terms(query, limit=limit)]


def _numeric_signature(value: Any) -> tuple[str, ...]:
    return tuple(NUMERIC_TOKEN_RE.findall(str(value or "")))


def _should_auto_supersede_exact_value(current_value: Any, new_value: Any) -> bool:
    current_text = " ".join(str(current_value or "").strip().split())
    new_text = " ".join(str(new_value or "").strip().split())
    if not current_text or not new_text or current_text == new_text:
        return False
    if len(current_text) > 96 or len(new_text) > 96:
        return False
    current_signature = _numeric_signature(current_text)
    new_signature = _numeric_signature(new_text)
    if not current_signature or not new_signature:
        return False
    return current_signature != new_signature


def _normalize_record_metadata(metadata: Dict[str, Any] | None, *, source: str = "") -> Dict[str, Any]:
    payload = dict(metadata or {})

    nested_temporal = payload.pop("temporal", None)
    temporal_payload: Dict[str, Any] = {}
    if isinstance(nested_temporal, dict):
        temporal_payload.update(nested_temporal)
    for key in ("observed_at", "valid_at", "valid_from", "valid_to", "supersedes", "superseded_by", "episode_id"):
        if key in payload:
            temporal_payload[key] = payload.pop(key)
    temporal = normalize_temporal_fields(**temporal_payload)

    nested_provenance = payload.pop("provenance", None)
    provenance_seed: Dict[str, Any] = {}
    if source:
        provenance_seed["source_ids"] = [source]
    for key in (
        "session_id",
        "turn_number",
        "tier",
        "target",
        "admission_reason",
        "origin",
        "status_reason",
        "trace_id",
        "correlation_id",
    ):
        if key in payload:
            provenance_seed[key] = payload.pop(key)
    provenance = merge_provenance(provenance_seed, nested_provenance)

    normalized: Dict[str, Any] = dict(payload)
    if temporal:
        normalized["temporal"] = temporal
    if provenance:
        normalized["provenance"] = provenance
    return normalized


def _cursor_lastrowid(cur: sqlite3.Cursor) -> int:
    row_id = cur.lastrowid
    if row_id is None:
        raise RuntimeError("sqlite cursor did not expose lastrowid")
    return int(row_id)


def _task_search_projection(row: Mapping[str, Any]) -> str:
    metadata = _decode_json_object(row.get("metadata"))
    parts = [
        str(row.get("title") or "").strip(),
        str(row.get("item_type") or "").strip(),
        str(row.get("due_date") or "").strip(),
        str(row.get("date_scope") or "").strip(),
        str(row.get("status") or "").strip(),
        str(row.get("owner") or "").strip(),
        str(row.get("source") or "").strip(),
        str(metadata.get("input_excerpt") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _task_match_score(
    row: Mapping[str, Any],
    *,
    query_tokens: Iterable[str],
    numeric_tokens: Iterable[str],
) -> tuple[float, int]:
    projection = _task_search_projection(row).casefold()
    if not projection:
        return 0.0, 0

    overlap = 0
    score = 0.0
    for token in query_tokens:
        if token and token in projection:
            overlap += 1
            score += 1.0

    numeric_matches = 0
    if numeric_tokens:
        row_numeric_tokens = set(NUMERIC_TOKEN_RE.findall(projection))
        for token in numeric_tokens:
            if token and token in row_numeric_tokens:
                numeric_matches += 1
        score += numeric_matches * 0.75

    if str(row.get("status") or "").strip() == "open":
        score += 0.15
    if str(row.get("due_date") or "").strip():
        score += 0.05
    return score, overlap + numeric_matches


def _merge_record_metadata(
    existing_metadata_json: Any,
    incoming_metadata: Dict[str, Any] | None,
    *,
    source: str = "",
) -> Dict[str, Any]:
    existing = _decode_json_object(existing_metadata_json)
    incoming = _normalize_record_metadata(incoming_metadata, source=source)

    merged: Dict[str, Any] = {}
    for payload in (existing, incoming):
        for key, value in payload.items():
            if key in {"temporal", "provenance"}:
                continue
            merged[key] = value

    temporal = merge_temporal(existing.get("temporal"), incoming.get("temporal"))
    provenance = merge_provenance(existing.get("provenance"), incoming.get("provenance"))
    if temporal:
        merged["temporal"] = temporal
    if provenance:
        merged["provenance"] = provenance
    return merged


def _normalize_graph_record_metadata(
    metadata: Dict[str, Any] | None,
    *,
    source: str,
    graph_kind: str,
) -> Dict[str, Any]:
    normalized = _normalize_record_metadata(metadata, source=source)
    normalized.setdefault("source_kind", "explicit" if graph_kind != "inferred_relation" else "inferred")
    normalized.setdefault("graph_kind", "relation" if graph_kind in {"relation", "inferred_relation"} else graph_kind)
    return attach_graph_source_lineage(
        normalized,
        source=source,
        graph_kind=graph_kind,
    )


def _merge_graph_record_metadata(
    existing_metadata_json: Any,
    incoming_metadata: Dict[str, Any] | None,
    *,
    source: str,
    graph_kind: str,
) -> Dict[str, Any]:
    merged = _merge_record_metadata(existing_metadata_json, incoming_metadata, source=source)
    return attach_graph_source_lineage(
        merged,
        source=source,
        graph_kind=graph_kind,
    )


def _style_contract_rule_count(*, content: Any, metadata: Any) -> int:
    rules = list_style_contract_rules(
        raw_text=content,
        metadata=_decode_json_object(metadata) if not isinstance(metadata, dict) else metadata,
    )
    return len(rules)


def _should_preserve_existing_style_contract(
    *,
    existing_source: Any,
    incoming_source: Any,
    existing_content: Any = "",
    existing_metadata: Any = None,
    incoming_content: Any = "",
    incoming_metadata: Any = None,
) -> bool:
    existing_rank = style_contract_source_rank(existing_source)
    incoming_rank = style_contract_source_rank(incoming_source)
    if existing_rank > incoming_rank:
        return True

    incoming_source_text = str(incoming_source or "").strip().lower()
    if "tier2" not in incoming_source_text:
        return False

    existing_rules = _style_contract_rule_count(content=existing_content, metadata=existing_metadata)
    incoming_rules = _style_contract_rule_count(content=incoming_content, metadata=incoming_metadata)
    if existing_rules > incoming_rules:
        return True
    existing_length = len(str(existing_content or "").strip())
    incoming_length = len(str(incoming_content or "").strip())
    return existing_rules == incoming_rules and existing_length > incoming_length


def _is_principal_scoped_profile(*, stable_key: str = "", category: str = "") -> bool:
    normalized_category = str(category or "").strip().lower()
    if normalized_category in PRINCIPAL_SCOPED_PROFILE_CATEGORIES:
        return True
    key_prefix = str(stable_key or "").strip().split(":", 1)[0].lower()
    return key_prefix in PRINCIPAL_SCOPED_PROFILE_CATEGORIES


def _profile_storage_key(*, stable_key: str, category: str = "", principal_scope_key: str = "") -> str:
    logical_key = str(stable_key or "").strip()
    scope_key = str(principal_scope_key or "").strip()
    if not logical_key:
        return ""
    if not scope_key or not _is_principal_scoped_profile(stable_key=logical_key, category=category):
        return logical_key
    return f"{logical_key}{PROFILE_SCOPE_DELIMITER}{scope_key}"


def _split_profile_storage_key(storage_key: str) -> tuple[str, str]:
    raw_key = str(storage_key or "").strip()
    if PROFILE_SCOPE_DELIMITER not in raw_key:
        return raw_key, ""
    logical_key, scope_key = raw_key.rsplit(PROFILE_SCOPE_DELIMITER, 1)
    return logical_key, scope_key


def _profile_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = _row_to_dict(row)
    storage_key = str(item.get("stable_key") or "").strip()
    logical_key, embedded_scope_key = _split_profile_storage_key(storage_key)
    item["storage_key"] = storage_key
    item["stable_key"] = logical_key
    item["principal_scope_key"] = _principal_scope_key_from_metadata(item.get("metadata")) or embedded_scope_key
    return item


def _behavior_contract_storage_key(
    *,
    stable_key: str,
    principal_scope_key: str = "",
    revision_number: int = 0,
) -> str:
    logical_key = str(stable_key or "").strip() or STYLE_CONTRACT_SLOT
    scope_key = str(principal_scope_key or "").strip() or "_global"
    revision = max(int(revision_number or 0), 1)
    return f"behavior_contract::{logical_key}::{scope_key}::r{revision}"


def _behavior_contract_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = _row_to_dict(row)
    item["stable_key"] = str(item.get("stable_key") or STYLE_CONTRACT_SLOT).strip() or STYLE_CONTRACT_SLOT
    item["principal_scope_key"] = str(
        item.get("principal_scope_key")
        or _principal_scope_key_from_metadata(item.get("metadata"))
        or ""
    ).strip()
    item["storage_key"] = str(item.get("storage_key") or "").strip() or _behavior_contract_storage_key(
        stable_key=item["stable_key"],
        principal_scope_key=item["principal_scope_key"],
        revision_number=int(item.get("revision_number") or 1),
    )
    item["personal_scope_key"] = _personal_scope_key_from_metadata(item.get("metadata")) or _personal_scope_key_from_principal_scope_key(
        item["principal_scope_key"]
    )
    item["active"] = str(item.get("status") or "").strip() == BEHAVIOR_CONTRACT_ACTIVE_STATUS
    return item


def _compiled_behavior_policy_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    item["policy"] = _decode_json_object(item.pop("policy_json", "{}"))
    return item


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    if "metadata_json" in item:
        item["metadata"] = _decode_json_object(item.pop("metadata_json"))
    if "conflict_metadata_json" in item:
        item["conflict_metadata"] = _decode_json_object(item.pop("conflict_metadata_json"))
    return item


def _scope_payload_from_key(scope_key: str) -> Dict[str, str]:
    return scope_payload_from_key(scope_key)


def _scope_key_from_payload(payload: Mapping[str, Any] | None, *, fields: Iterable[str]) -> str:
    return scope_key_from_payload(payload, fields=fields)


def _principal_scope_key_from_metadata(metadata: Mapping[str, Any] | None) -> str:
    if not isinstance(metadata, Mapping):
        return ""
    direct = str(metadata.get("principal_scope_key") or "").strip()
    if direct:
        return direct
    nested = metadata.get("principal_scope")
    if not isinstance(nested, dict):
        for container_key in ("document", "section"):
            container = metadata.get(container_key)
            if isinstance(container, dict):
                scoped = _principal_scope_key_from_metadata(container)
                if scoped:
                    return scoped
        return ""
    return _scope_key_from_payload(nested, fields=PRINCIPAL_SCOPE_KEY_FIELDS)


def _enrich_record_metadata_with_literals(
    metadata: Mapping[str, Any] | None,
    *,
    text: str,
    row_id: int | None = None,
    session_id: str = "",
    turn_number: int = 0,
    kind: str = "",
    include_event: bool = False,
) -> Dict[str, Any]:
    event = (
        user_turn_event_sidecar(
            row_id=row_id,
            session_id=session_id,
            turn_number=turn_number,
            kind=kind,
            content=text,
            metadata=metadata,
        )
        if include_event
        else None
    )
    return enrich_metadata_with_literal_sidecar(metadata, text=text, event=event)


def _principal_scope_payload_from_metadata(metadata: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}
    nested = metadata.get("principal_scope")
    if isinstance(nested, dict):
        return dict(nested)
    return {}


def _personal_scope_key_from_scope_payload(payload: Mapping[str, Any] | None) -> str:
    return _scope_key_from_payload(payload, fields=PERSONAL_SCOPE_KEY_FIELDS)


def _personal_scope_key_from_principal_scope_key(scope_key: str) -> str:
    return _personal_scope_key_from_scope_payload(_scope_payload_from_key(scope_key))


def _personal_scope_key_from_metadata(metadata: Dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
        return ""
    direct = str(metadata.get("personal_scope_key") or "").strip()
    if direct:
        return direct
    nested = _principal_scope_payload_from_metadata(metadata)
    scoped = _personal_scope_key_from_scope_payload(nested)
    if scoped:
        return scoped
    return _personal_scope_key_from_principal_scope_key(_principal_scope_key_from_metadata(metadata))


def _scope_match_priority(
    *,
    current_principal_scope_key: str,
    item_principal_scope_key: str,
    current_personal_scope_key: str = "",
    item_personal_scope_key: str = "",
    session_id: str | None = None,
    item_session_id: str = "",
) -> int:
    if current_principal_scope_key and item_principal_scope_key == current_principal_scope_key:
        return 3
    if current_personal_scope_key and item_personal_scope_key == current_personal_scope_key:
        return 2
    if session_id is not None and item_session_id == session_id:
        return 1
    return 0


def _annotate_principal_scope(
    item: Dict[str, Any],
    *,
    principal_scope_key: str,
    session_id: str | None = None,
    allow_personal_scope_fallback: bool = True,
) -> bool:
    current_principal_scope_key = str(principal_scope_key or "").strip()
    current_personal_scope_key = _personal_scope_key_from_principal_scope_key(current_principal_scope_key)
    item_scope_key = _principal_scope_key_from_metadata(item.get("metadata"))
    if not item_scope_key:
        item_scope_key = str(item.get("principal_scope_key") or "").strip()
    if not item_scope_key:
        storage_key = str(item.get("storage_key") or item.get("stable_key") or "").strip()
        _, item_scope_key = _split_profile_storage_key(storage_key)
    item_personal_scope_key = _personal_scope_key_from_metadata(item.get("metadata")) or _personal_scope_key_from_principal_scope_key(
        item_scope_key
    )
    item["principal_scope_key"] = item_scope_key
    item["personal_scope_key"] = item_personal_scope_key
    item["same_principal"] = bool(current_principal_scope_key) and item_scope_key == current_principal_scope_key
    item["same_personal_scope"] = bool(current_personal_scope_key) and item_personal_scope_key == current_personal_scope_key
    if not current_principal_scope_key:
        return True
    if not item_scope_key:
        return not _is_principal_scoped_profile(
            stable_key=str(item.get("stable_key") or ""),
            category=str(item.get("category") or ""),
        )
    if item_scope_key == current_principal_scope_key:
        return True
    if allow_personal_scope_fallback and current_personal_scope_key and item_personal_scope_key == current_personal_scope_key:
        return True
    if session_id is not None and str(item.get("session_id") or "") == session_id:
        return True
    return False


def _scoped_row_priority(item: Mapping[str, Any], *, principal_scope_key: str, session_id: str | None = None) -> tuple[int, float, str, int]:
    annotated = dict(item)
    _annotate_principal_scope(annotated, principal_scope_key=principal_scope_key, session_id=session_id)
    return (
        _scope_match_priority(
            current_principal_scope_key=str(principal_scope_key or "").strip(),
            item_principal_scope_key=str(annotated.get("principal_scope_key") or "").strip(),
            current_personal_scope_key=_personal_scope_key_from_principal_scope_key(principal_scope_key),
            item_personal_scope_key=str(annotated.get("personal_scope_key") or "").strip(),
            session_id=session_id,
            item_session_id=str(annotated.get("session_id") or "").strip(),
        ),
        float(annotated.get("confidence") or 0.0),
        str(annotated.get("updated_at") or annotated.get("committed_at") or ""),
        int(annotated.get("id") or 0),
    )


def _graph_metadata_confidence(metadata: Dict[str, Any] | None) -> float:
    try:
        return max(0.0, min(1.0, float((metadata or {}).get("confidence", 0.0) or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _graph_match_text(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("subject") or "").strip(),
        str(row.get("matched_alias") or "").strip(),
        str(row.get("predicate") or "").strip(),
        str(row.get("object_value") or "").strip(),
        str(row.get("conflict_value") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _graph_fact_class(row: Dict[str, Any]) -> str:
    row_type = str(row.get("row_type") or "").strip()
    if row_type == "conflict":
        return "conflict"
    if row_type == "inferred_relation":
        return "inferred_relation"
    if row_type == "relation":
        return "explicit_relation"
    if row_type == "state":
        temporal_status = record_temporal_status(row)
        if row.get("is_current") and temporal_status == "current" and record_is_effective_at(row):
            return "explicit_state_current"
        if row.get("is_current") and temporal_status == "expired":
            return "explicit_state_expired"
        return "explicit_state_prior"
    return row_type or "graph"


def _graph_fact_priority(row: Dict[str, Any]) -> int:
    fact_class = _graph_fact_class(row)
    priorities = {
        "explicit_state_current": 520,
        "explicit_relation": 430,
        "conflict": 390,
        "explicit_state_prior": 310,
        "explicit_state_expired": 260,
        "inferred_relation": 180,
    }
    return priorities.get(fact_class, 0)


def _graph_sort_key(row: Dict[str, Any]) -> tuple[int, float, int, int, str]:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if str(row.get("row_type") or "") == "conflict" and isinstance(row.get("conflict_metadata"), dict):
        metadata = row.get("conflict_metadata") or metadata
    row["fact_class"] = _graph_fact_class(row)
    keyword_score = float(row.get("keyword_score") or 0.0)
    confidence_score = int(round(_graph_metadata_confidence(metadata) * 100))
    telemetry_score = int(round(graph_priority_adjustment(row) * 100))
    return (
        _graph_fact_priority(row),
        keyword_score,
        confidence_score,
        telemetry_score,
        str(row.get("happened_at") or ""),
    )


def _graph_structured_field_match_score(row: Mapping[str, Any], *, query: str) -> float:
    query_tokens = _query_token_set(query)
    if not query_tokens:
        return 0.0
    score = 0.0
    for field, weight in (
        ("predicate", 1.5),
        ("subject", 1.0),
        ("object_value", 1.0),
        ("matched_alias", 1.0),
        ("conflict_value", 1.0),
    ):
        field_tokens = _query_token_set(row.get(field))
        if not field_tokens:
            continue
        overlap = len(query_tokens & field_tokens)
        if overlap:
            score += float(overlap) * weight
    return score


def _locked(method: F) -> F:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
