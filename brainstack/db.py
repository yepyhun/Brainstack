from __future__ import annotations

from functools import wraps
import hashlib
import logging
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, TypeVar

from .behavior_policy import (
    BEHAVIOR_POLICY_COMPILER_VERSION,
    BEHAVIOR_POLICY_SCHEMA_VERSION,
    build_behavior_policy_snapshot,
    compile_behavior_policy,
)
from .corpus_backend import CorpusBackend, create_corpus_backend
from .graph_backend import GraphBackend, create_graph_backend
from .logistics_contract import derive_transcript_logistics_typed_entities
from .profile_contract import (
    COMMUNICATION_CANONICAL_SLOTS,
    derive_transcript_identity_profile_items,
    expand_communication_profile_items,
)
from .operating_context import build_operating_context_snapshot
from .operating_truth import OPERATING_RECORD_TYPES
from .provenance import merge_provenance
from .style_contract import (
    STYLE_CONTRACT_DOC_KIND,
    STYLE_CONTRACT_SLOT,
    apply_style_contract_rule_correction,
    build_style_contract_from_document,
    list_style_contract_rules,
    style_contract_cleanliness_issues,
    style_contract_source_rank,
)
from .task_memory import STATUS_OPEN
from .temporal import merge_temporal, normalize_temporal_fields, record_is_effective_at
from .usefulness import (
    apply_retrieval_telemetry,
    graph_priority_adjustment,
    profile_priority_adjustment,
)


F = TypeVar("F", bound=Callable[..., Any])
logger = logging.getLogger(__name__)
NUMERIC_TOKEN_RE = re.compile(r"\d+(?::\d+)?(?:\.\d+)?")
QUERY_TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)
PROFILE_SCOPE_DELIMITER = "::principal_scope::"
PRINCIPAL_SCOPED_PROFILE_CATEGORIES = {"identity", "preference"}
PRINCIPAL_SCOPE_KEY_FIELDS = ("platform", "user_id", "agent_identity", "agent_workspace")
PERSONAL_SCOPE_KEY_FIELDS = ("platform", "user_id")
MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1 = "canonical_communication_rows_v1"
MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1 = "explicit_identity_backfill_v1"
MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1 = "stable_logistics_typed_entities_v1"
MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2 = "stable_logistics_typed_entities_v2"
MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1 = "style_contract_profile_lane_v1"
MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1 = "behavior_contract_storage_v1"
MIGRATION_COMPILED_BEHAVIOR_POLICY_V1 = "compiled_behavior_policy_v1"
MIGRATION_COMPILED_BEHAVIOR_POLICY_V2 = "compiled_behavior_policy_v2"
BEHAVIOR_CONTRACT_ACTIVE_STATUS = "active"
BEHAVIOR_CONTRACT_SUPERSEDED_STATUS = "superseded"


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


def build_fts_query(query: str) -> str:
    tokens = _extract_query_terms(query, limit=12)
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens)


def build_like_tokens(query: str, *, limit: int = 8) -> List[str]:
    return [f"%{token.lower()}%" for token in _extract_query_terms(query, limit=limit)]


def _decode_json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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


def _task_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "stable_key": str(row["stable_key"] or ""),
        "principal_scope_key": str(row["principal_scope_key"] or ""),
        "item_type": str(row["item_type"] or ""),
        "title": str(row["title"] or ""),
        "due_date": str(row["due_date"] or ""),
        "date_scope": str(row["date_scope"] or ""),
        "optional": bool(int(row["optional"] or 0)),
        "status": str(row["status"] or ""),
        "owner": str(row["owner"] or ""),
        "source": str(row["source"] or ""),
        "source_session_id": str(row["source_session_id"] or ""),
        "source_turn_number": int(row["source_turn_number"] or 0),
        "metadata": _decode_json_object(row["metadata_json"]),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def _operating_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": int(row["id"]),
        "stable_key": str(row["stable_key"] or ""),
        "principal_scope_key": str(row["principal_scope_key"] or ""),
        "record_type": str(row["record_type"] or ""),
        "content": str(row["content"] or ""),
        "owner": str(row["owner"] or ""),
        "source": str(row["source"] or ""),
        "source_session_id": str(row["source_session_id"] or ""),
        "source_turn_number": int(row["source_turn_number"] or 0),
        "metadata": _decode_json_object(row["metadata_json"]),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


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
    payload: Dict[str, str] = {}
    for raw_part in str(scope_key or "").split("|"):
        part = str(raw_part or "").strip()
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = str(key or "").strip()
        normalized_value = str(value or "").strip()
        if normalized_key and normalized_value:
            payload[normalized_key] = normalized_value
    return payload


def _scope_key_from_payload(payload: Mapping[str, Any] | None, *, fields: Iterable[str]) -> str:
    if not isinstance(payload, Mapping):
        return ""
    parts: List[str] = []
    for key in fields:
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(f"{key}:{value}")
    return "|".join(parts)


def _principal_scope_key_from_metadata(metadata: Dict[str, Any] | None) -> str:
    if not isinstance(metadata, dict):
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
    if current_personal_scope_key and item_personal_scope_key == current_personal_scope_key:
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
        if row.get("is_current") and record_is_effective_at(row):
            return "explicit_state_current"
        return "explicit_state_prior"
    return row_type or "graph"


def _graph_fact_priority(row: Dict[str, Any]) -> int:
    fact_class = _graph_fact_class(row)
    priorities = {
        "explicit_state_current": 520,
        "explicit_relation": 430,
        "conflict": 390,
        "explicit_state_prior": 310,
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


def _locked(method: F) -> F:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class BrainstackStore:
    def __init__(
        self,
        db_path: str,
        *,
        graph_backend: str = "sqlite",
        graph_db_path: str | None = None,
        corpus_backend: str = "sqlite",
        corpus_db_path: str | None = None,
    ) -> None:
        self._db_path = str(db_path)
        self._graph_backend_name = str(graph_backend or "sqlite").strip().lower()
        default_graph_db = str(Path(self._db_path).with_suffix(".kuzu"))
        self._graph_db_path = str(graph_db_path or default_graph_db)
        self._corpus_backend_name = str(corpus_backend or "sqlite").strip().lower()
        default_corpus_db = str(Path(self._db_path).with_suffix(".chroma"))
        self._corpus_db_path = str(corpus_db_path or default_corpus_db)
        self._conn: sqlite3.Connection | None = None
        self._graph_backend: GraphBackend | None = None
        self._graph_backend_error = ""
        self._corpus_backend: CorpusBackend | None = None
        self._corpus_backend_error = ""
        self._lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BrainstackStore is not open")
        return self._conn

    @_locked
    def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()
        self._backfill_legacy_principal_scoped_profiles_if_needed()
        self._run_compatibility_migrations_if_needed()
        self._graph_backend = create_graph_backend(self._graph_backend_name, db_path=self._graph_db_path)
        if self._graph_backend is not None:
            try:
                self._graph_backend.open()
            except ModuleNotFoundError as exc:
                self._graph_backend_error = str(exc)
                self._graph_backend = None
            else:
                self._graph_backend_error = ""
                self._bootstrap_graph_backend_if_needed()
        self._corpus_backend = create_corpus_backend(self._corpus_backend_name, db_path=self._corpus_db_path)
        if self._corpus_backend is not None:
            try:
                self._corpus_backend.open()
            except ModuleNotFoundError as exc:
                self._corpus_backend_error = str(exc)
                self._corpus_backend = None
            else:
                self._corpus_backend_error = ""
                self._bootstrap_corpus_backend_if_needed()
                self._replay_corpus_publications_if_needed()

    @_locked
    def close(self) -> None:
        if self._corpus_backend is not None:
            self._corpus_backend.close()
            self._corpus_backend = None
        if self._graph_backend is not None:
            self._graph_backend.close()
            self._graph_backend = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _resolve_session_principal_scope(
        self,
        *,
        session_id: str,
    ) -> tuple[str, Dict[str, Any]]:
        session_key = str(session_id or "").strip()
        if not session_key:
            return "", {}
        rows = self.conn.execute(
            """
            SELECT metadata_json
            FROM transcript_entries
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT 64
            """,
            (session_key,),
        ).fetchall()
        scope_key = ""
        scope_payload: Dict[str, Any] = {}
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            candidate_scope_key = _principal_scope_key_from_metadata(metadata)
            if not candidate_scope_key:
                continue
            if not scope_key:
                scope_key = candidate_scope_key
                scope_payload = _principal_scope_payload_from_metadata(metadata)
                continue
            if candidate_scope_key != scope_key:
                return "", {}
            if not scope_payload:
                scope_payload = _principal_scope_payload_from_metadata(metadata)
        return scope_key, scope_payload

    @_locked
    def _backfill_legacy_principal_scoped_profiles_if_needed(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, source, metadata_json
            FROM profile_items
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()
        migrated = 0
        for row in rows:
            item = _profile_row_to_dict(row)
            stable_key = str(item.get("stable_key") or "").strip()
            category = str(item.get("category") or "").strip()
            if not _is_principal_scoped_profile(stable_key=stable_key, category=category):
                continue
            if str(item.get("principal_scope_key") or "").strip():
                continue
            metadata = dict(item.get("metadata") or {})
            provenance = metadata.get("provenance") if isinstance(metadata.get("provenance"), dict) else {}
            session_id = str(provenance.get("session_id") or "").strip()
            if not session_id:
                continue
            principal_scope_key, principal_scope = self._resolve_session_principal_scope(session_id=session_id)
            if not principal_scope_key:
                continue
            storage_key = str(item.get("storage_key") or row["stable_key"] or "").strip()
            scoped_storage_key = _profile_storage_key(
                stable_key=stable_key,
                category=category,
                principal_scope_key=principal_scope_key,
            )
            if not scoped_storage_key or scoped_storage_key == storage_key:
                continue
            migrated_metadata = dict(metadata)
            migrated_metadata.setdefault("principal_scope_key", principal_scope_key)
            if principal_scope:
                migrated_metadata.setdefault("principal_scope", dict(principal_scope))
            existing = self.conn.execute(
                "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
                (scoped_storage_key,),
            ).fetchone()
            if existing:
                merged_metadata = _merge_record_metadata(
                    existing["metadata_json"],
                    migrated_metadata,
                    source=str(row["source"] or ""),
                )
                self.conn.execute(
                    "UPDATE profile_items SET metadata_json = ? WHERE id = ?",
                    (
                        json.dumps(merged_metadata, ensure_ascii=True, sort_keys=True),
                        int(existing["id"]),
                    ),
                )
                self.conn.execute(
                    "UPDATE profile_items SET active = 0 WHERE id = ?",
                    (int(row["id"]),),
                )
                self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (int(row["id"]),))
            else:
                merged_metadata = _merge_record_metadata(
                    row["metadata_json"],
                    migrated_metadata,
                    source=str(row["source"] or ""),
                )
                self.conn.execute(
                    "UPDATE profile_items SET stable_key = ?, metadata_json = ? WHERE id = ?",
                    (
                        scoped_storage_key,
                        json.dumps(merged_metadata, ensure_ascii=True, sort_keys=True),
                        int(row["id"]),
                    ),
                )
            migrated += 1
        if migrated:
            self.conn.commit()
            logger.info("Backfilled %s legacy principal-scoped profile rows", migrated)

    @_locked
    def _run_compatibility_migrations_if_needed(self) -> None:
        if not self._migration_applied(MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1):
            self._apply_canonical_communication_rows_migration_v1()
        if not self._migration_applied(MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1):
            self._apply_explicit_identity_backfill_migration_v1()
        if not self._migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1):
            self._apply_stable_logistics_typed_entities_migration_v1()
        if not self._migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2):
            self._apply_stable_logistics_typed_entities_migration_v2()
        if not self._migration_applied(MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1):
            self._apply_style_contract_profile_lane_migration_v1()
        if not self._migration_applied(MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1):
            self._apply_behavior_contract_storage_migration_v1()
        if not self._migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V1):
            self._apply_compiled_behavior_policy_migration_v1()
        if not self._migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V2):
            self._apply_compiled_behavior_policy_migration_v2()

    def _migration_applied(self, name: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM applied_migrations WHERE name = ? LIMIT 1",
            (str(name or "").strip(),),
        ).fetchone()
        return row is not None

    def _mark_migration_applied(self, name: str) -> None:
        migration_name = str(name or "").strip()
        if not migration_name:
            return
        self.conn.execute(
            """
            INSERT INTO applied_migrations(name, applied_at)
            VALUES(?, ?)
            ON CONFLICT(name) DO UPDATE SET applied_at = excluded.applied_at
            """,
            (migration_name, utc_now_iso()),
        )

    @_locked
    def _apply_canonical_communication_rows_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json
            FROM profile_items
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()
        migrated = 0
        for row in rows:
            item = _profile_row_to_dict(row)
            stable_key = str(item.get("stable_key") or "").strip()
            if not stable_key.startswith("preference:"):
                continue
            if stable_key in COMMUNICATION_CANONICAL_SLOTS:
                continue
            principal_scope_key = str(item.get("principal_scope_key") or "").strip()
            if not principal_scope_key:
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            confidence = float(item.get("confidence") or 0.78)
            expanded = expand_communication_profile_items(
                category="preference",
                content=content,
                slot=stable_key,
                confidence=confidence,
                source="tier2_compat_backfill",
            )
            if not expanded:
                continue
            metadata = dict(item.get("metadata") or {})
            metadata.setdefault("principal_scope_key", principal_scope_key)
            for candidate in expanded:
                self.upsert_profile_item(
                    stable_key=str(candidate["slot"]),
                    category=str(candidate["category"]),
                    content=str(candidate["content"]),
                    source=str(candidate.get("source") or row["source"] or "tier2_compat_backfill"),
                    confidence=float(candidate.get("confidence") or confidence),
                    metadata=metadata,
                )
            self.conn.execute("UPDATE profile_items SET active = 0 WHERE id = ?", (int(row["id"]),))
            self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (int(row["id"]),))
            migrated += 1
        self._mark_migration_applied(MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s legacy communication contract rows", migrated)
        else:
            logger.info("Applied canonical communication compatibility migration with no legacy rows to rewrite")

    @_locked
    def _apply_explicit_identity_backfill_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            if self.get_profile_item(
                stable_key="identity:age",
                principal_scope_key=principal_scope_key,
            ):
                continue
            candidates = derive_transcript_identity_profile_items(
                entries,
                existing_items=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                if str(candidate.get("slot") or "").strip() != "identity:age":
                    continue
                metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    metadata["principal_scope"] = principal_scope
                self.upsert_profile_item(
                    stable_key="identity:age",
                    category=str(candidate.get("category") or "identity"),
                    content=str(candidate.get("content") or "").strip(),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    confidence=float(candidate.get("confidence") or 0.88),
                    metadata=metadata,
                )
                migrated += 1

        self._mark_migration_applied(MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s explicit identity rows from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied explicit identity compatibility migration with no eligible transcript rows")

    @_locked
    def _apply_stable_logistics_typed_entities_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            candidates = derive_transcript_logistics_typed_entities(
                entries,
                existing_entities=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    metadata["principal_scope"] = principal_scope
                if isinstance(candidate.get("temporal"), dict):
                    metadata["temporal"] = dict(candidate["temporal"])
                actions = self.upsert_typed_entity(
                    entity_name=str(candidate.get("name") or "").strip(),
                    entity_type=str(candidate.get("entity_type") or "").strip(),
                    subject_name=str(candidate.get("subject") or "User").strip() or "User",
                    attributes=dict(candidate.get("attributes") or {}),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    metadata=metadata,
                )
                if actions:
                    migrated += 1

        self._mark_migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s stable logistics typed entities from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied stable logistics compatibility migration with no eligible transcript rows")

    @_locked
    def _apply_stable_logistics_typed_entities_migration_v2(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            candidates = derive_transcript_logistics_typed_entities(
                entries,
                existing_entities=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    metadata["principal_scope"] = principal_scope
                if isinstance(candidate.get("temporal"), dict):
                    metadata["temporal"] = dict(candidate["temporal"])
                actions = self.upsert_typed_entity(
                    entity_name=str(candidate.get("name") or "").strip(),
                    entity_type=str(candidate.get("entity_type") or "").strip(),
                    subject_name=str(candidate.get("subject") or "User").strip() or "User",
                    attributes=dict(candidate.get("attributes") or {}),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    metadata=metadata,
                    supersede_existing=True,
                )
                if actions:
                    migrated += 1

        self._mark_migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2)
        self.conn.commit()
        if migrated:
            logger.info("Repaired %s stable logistics typed entities from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied stable logistics repair migration with no eligible transcript rows")

    @_locked
    def _apply_style_contract_profile_lane_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, title, metadata_json, updated_at, active
            FROM corpus_documents
            WHERE active = 1 AND doc_kind = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (STYLE_CONTRACT_DOC_KIND,),
        ).fetchall()
        grouped: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            grouped.setdefault(principal_scope_key, []).append(row)

        migrated = 0
        retired = 0
        for principal_scope_key, documents in grouped.items():
            active_profile = self.get_profile_item(
                stable_key=STYLE_CONTRACT_SLOT,
                principal_scope_key=principal_scope_key,
            )
            selected_document = documents[0] if documents else None
            if not active_profile and selected_document is not None:
                section_rows = self.conn.execute(
                    """
                    SELECT section_index, heading, content
                    FROM corpus_sections
                    WHERE document_id = ?
                    ORDER BY section_index ASC
                    """,
                    (int(selected_document["id"]),),
                ).fetchall()
                metadata = _decode_json_object(selected_document["metadata_json"])
                principal_scope = _principal_scope_payload_from_metadata(metadata)
                candidate = build_style_contract_from_document(
                    title=selected_document["title"],
                    sections=[dict(section) for section in section_rows],
                    source="tier2_compat_backfill",
                    confidence=0.9,
                )
                if candidate is not None:
                    merged_metadata: Dict[str, Any] = {
                        "principal_scope_key": principal_scope_key,
                        "provenance": {
                            "source_ids": [
                                f"migration:{MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1}",
                                f"corpus_document:{selected_document['stable_key']}",
                            ],
                            "tier": "migration",
                        },
                    }
                    if principal_scope:
                        merged_metadata["principal_scope"] = principal_scope
                    merged_metadata.update(dict(candidate.get("metadata") or {}))
                    self.upsert_profile_item(
                        stable_key=STYLE_CONTRACT_SLOT,
                        category=str(candidate.get("category") or "preference"),
                        content=str(candidate.get("content") or "").strip(),
                        source=str(candidate.get("source") or "tier2_compat_backfill"),
                        confidence=float(candidate.get("confidence") or 0.9),
                        metadata=merged_metadata,
                    )
                    migrated += 1
                    active_profile = self.get_profile_item(
                        stable_key=STYLE_CONTRACT_SLOT,
                        principal_scope_key=principal_scope_key,
                    )
            if not active_profile:
                continue
            for document in documents:
                if not bool(document["active"]):
                    continue
                self.conn.execute(
                    "UPDATE corpus_documents SET active = 0, updated_at = ? WHERE id = ?",
                    (utc_now_iso(), int(document["id"])),
                )
                retired += 1

        self._mark_migration_applied(MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1)
        self.conn.commit()
        if migrated or retired:
            logger.info(
                "Migrated %s style contracts into canonical profile lane and retired %s corpus documents",
                migrated,
                retired,
            )
        else:
            logger.info("Applied style-contract profile-lane migration with no eligible corpus documents")

    @_locked
    def _apply_behavior_contract_storage_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE active = 1
            ORDER BY updated_at ASC, id ASC
            """
        ).fetchall()
        migrated = 0
        retired = 0
        for row in rows:
            item = _profile_row_to_dict(row)
            if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT:
                continue
            self.upsert_behavior_contract(
                stable_key=STYLE_CONTRACT_SLOT,
                category=str(item.get("category") or "preference"),
                content=str(item.get("content") or ""),
                source=str(item.get("source") or ""),
                confidence=float(item.get("confidence") or 0.9),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                active=bool(item.get("active", True)),
            )
            storage_key = str(row["stable_key"] or "").strip()
            self.conn.execute(
                "UPDATE profile_items SET active = 0, updated_at = ? WHERE stable_key = ?",
                (utc_now_iso(), storage_key),
            )
            self.conn.execute(
                "DELETE FROM profile_fts WHERE rowid = ?",
                (int(row["id"]),),
            )
            migrated += 1
            retired += 1

        self._mark_migration_applied(MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1)
        self.conn.commit()
        if migrated:
            logger.info(
                "Migrated %s canonical style contracts into first-class behavior-contract storage and retired %s profile rows",
                migrated,
                retired,
            )
        else:
            logger.info("Applied behavior-contract storage migration with no eligible canonical style-contract rows")

    def _upsert_compiled_behavior_policy_record(
        self,
        *,
        principal_scope_key: str,
        compiled_policy: Dict[str, Any],
    ) -> None:
        scope_key = str(principal_scope_key or "").strip()
        if compiled_policy is None:
            return
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO compiled_behavior_policies (
                principal_scope_key,
                source_storage_key,
                source_contract_hash,
                source_contract_updated_at,
                schema_version,
                compiler_version,
                title,
                policy_json,
                projection_text,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(principal_scope_key) DO UPDATE SET
                source_storage_key = excluded.source_storage_key,
                source_contract_hash = excluded.source_contract_hash,
                source_contract_updated_at = excluded.source_contract_updated_at,
                schema_version = excluded.schema_version,
                compiler_version = excluded.compiler_version,
                title = excluded.title,
                policy_json = excluded.policy_json,
                projection_text = excluded.projection_text,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                scope_key,
                str(compiled_policy.get("source_storage_key") or "").strip(),
                str(compiled_policy.get("source_contract_hash") or "").strip(),
                str(compiled_policy.get("source_contract_updated_at") or "").strip(),
                int(compiled_policy.get("schema_version") or BEHAVIOR_POLICY_SCHEMA_VERSION),
                str(compiled_policy.get("compiler_version") or BEHAVIOR_POLICY_COMPILER_VERSION),
                str(compiled_policy.get("title") or "").strip(),
                json.dumps(compiled_policy, ensure_ascii=True, sort_keys=True),
                str(compiled_policy.get("projection_text") or "").strip(),
                str(compiled_policy.get("status") or "active").strip() or "active",
                now,
            ),
        )

    def _delete_compiled_behavior_policy_record(self, *, principal_scope_key: str) -> None:
        scope_key = str(principal_scope_key or "").strip()
        if not scope_key:
            return
        self.conn.execute(
            "DELETE FROM compiled_behavior_policies WHERE principal_scope_key = ?",
            (scope_key,),
        )

    def _rebuild_compiled_behavior_policy_from_behavior_contract_row(self, row: sqlite3.Row) -> bool:
        item = _behavior_contract_row_to_dict(row)
        if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT:
            return False
        compiled = compile_behavior_policy(
            raw_content=str(item.get("content") or ""),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            source_storage_key=str(item.get("storage_key") or ""),
            source_updated_at=str(item.get("updated_at") or ""),
        )
        if not compiled:
            self._delete_compiled_behavior_policy_record(
                principal_scope_key=str(item.get("principal_scope_key") or ""),
            )
            return False
        self._upsert_compiled_behavior_policy_record(
            principal_scope_key=str(item.get("principal_scope_key") or ""),
            compiled_policy=compiled,
        )
        return True

    @_locked
    def _apply_compiled_behavior_policy_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE status = ?
            ORDER BY revision_number DESC, id DESC
            """
            ,
            (BEHAVIOR_CONTRACT_ACTIVE_STATUS,),
        ).fetchall()
        rebuilt = 0
        for row in rows:
            if self._rebuild_compiled_behavior_policy_from_behavior_contract_row(row):
                rebuilt += 1
        self._mark_migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V1)
        self.conn.commit()
        if rebuilt:
            logger.info("Built %s compiled behavior policies from canonical behavior-contract rows", rebuilt)
        else:
            logger.info("Applied compiled behavior policy migration with no eligible behavior-contract rows")

    @_locked
    def _apply_compiled_behavior_policy_migration_v2(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE status = ?
            ORDER BY revision_number DESC, id DESC
            """
            ,
            (BEHAVIOR_CONTRACT_ACTIVE_STATUS,),
        ).fetchall()
        rebuilt = 0
        for row in rows:
            if self._rebuild_compiled_behavior_policy_from_behavior_contract_row(row):
                rebuilt += 1
        self._mark_migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V2)
        self.conn.commit()
        if rebuilt:
            logger.info("Rebuilt %s compiled behavior policies for compiler v2", rebuilt)
        else:
            logger.info("Applied compiled behavior policy v2 migration with no eligible style-contract rows")

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS continuity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_continuity_session_created
            ON continuity_events(session_id, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS continuity_fts USING fts5(
                content,
                session_id UNINDEXED,
                kind UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS transcript_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transcript_session_created
            ON transcript_entries(session_id, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                content,
                session_id UNINDEXED,
                kind UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS continuity_lifecycle_state (
                session_id TEXT PRIMARY KEY,
                current_frontier_turn_number INTEGER NOT NULL DEFAULT 0,
                last_snapshot_kind TEXT NOT NULL DEFAULT '',
                last_snapshot_turn_number INTEGER NOT NULL DEFAULT 0,
                last_snapshot_message_count INTEGER NOT NULL DEFAULT 0,
                last_snapshot_input_count INTEGER NOT NULL DEFAULT 0,
                last_snapshot_digest TEXT NOT NULL DEFAULT '',
                last_snapshot_at TEXT NOT NULL DEFAULT '',
                last_finalized_turn_number INTEGER NOT NULL DEFAULT 0,
                last_finalized_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_continuity_lifecycle_updated
            ON continuity_lifecycle_state(updated_at DESC);

            CREATE TABLE IF NOT EXISTS profile_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                first_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_profile_category_updated
            ON profile_items(category, updated_at DESC);

            CREATE TABLE IF NOT EXISTS behavior_contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                storage_key TEXT NOT NULL UNIQUE,
                principal_scope_key TEXT NOT NULL DEFAULT '',
                stable_key TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                source_contract_hash TEXT NOT NULL DEFAULT '',
                revision_number INTEGER NOT NULL DEFAULT 1,
                parent_revision_id INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                committed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_behavior_contract_active_scope
            ON behavior_contracts(principal_scope_key, stable_key)
            WHERE status = 'active';

            CREATE INDEX IF NOT EXISTS idx_behavior_contract_scope_revision
            ON behavior_contracts(principal_scope_key, stable_key, revision_number DESC, id DESC);

            CREATE TABLE IF NOT EXISTS compiled_behavior_policies (
                principal_scope_key TEXT PRIMARY KEY,
                source_storage_key TEXT NOT NULL DEFAULT '',
                source_contract_hash TEXT NOT NULL DEFAULT '',
                source_contract_updated_at TEXT NOT NULL DEFAULT '',
                schema_version INTEGER NOT NULL DEFAULT 1,
                compiler_version TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                policy_json TEXT NOT NULL DEFAULT '{}',
                projection_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                principal_scope_key TEXT NOT NULL DEFAULT '',
                item_type TEXT NOT NULL DEFAULT 'task',
                title TEXT NOT NULL,
                due_date TEXT NOT NULL DEFAULT '',
                date_scope TEXT NOT NULL DEFAULT 'none',
                optional INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'open',
                owner TEXT NOT NULL DEFAULT 'brainstack.task_memory',
                source TEXT NOT NULL,
                source_session_id TEXT NOT NULL DEFAULT '',
                source_turn_number INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_task_items_scope_due_status
            ON task_items(principal_scope_key, due_date, status, optional, updated_at DESC);

            CREATE TABLE IF NOT EXISTS operating_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                principal_scope_key TEXT NOT NULL DEFAULT '',
                record_type TEXT NOT NULL,
                content TEXT NOT NULL,
                owner TEXT NOT NULL DEFAULT 'brainstack.operating_truth',
                source TEXT NOT NULL,
                source_session_id TEXT NOT NULL DEFAULT '',
                source_turn_number INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_operating_records_scope_type_updated
            ON operating_records(principal_scope_key, record_type, updated_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS profile_fts USING fts5(
                content,
                category UNINDEXED,
                stable_key UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS operating_fts USING fts5(
                content,
                record_type UNINDEXED,
                stable_key UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS graph_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_entity_id INTEGER NOT NULL,
                predicate TEXT NOT NULL,
                object_entity_id INTEGER,
                object_text TEXT,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(subject_entity_id) REFERENCES graph_entities(id),
                FOREIGN KEY(object_entity_id) REFERENCES graph_entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_relations_subject
            ON graph_relations(subject_entity_id, predicate, created_at DESC);

            CREATE TABLE IF NOT EXISTS graph_inferred_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_entity_id INTEGER NOT NULL,
                predicate TEXT NOT NULL,
                object_entity_id INTEGER,
                object_text TEXT,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(subject_entity_id) REFERENCES graph_entities(id),
                FOREIGN KEY(object_entity_id) REFERENCES graph_entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_inferred_relations_subject
            ON graph_inferred_relations(subject_entity_id, predicate, updated_at DESC);

            CREATE TABLE IF NOT EXISTS graph_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                attribute TEXT NOT NULL,
                value_text TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                is_current INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(entity_id) REFERENCES graph_entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_states_entity_attribute
            ON graph_states(entity_id, attribute, is_current, valid_from DESC);

            CREATE TABLE IF NOT EXISTS graph_supersessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prior_state_id INTEGER NOT NULL,
                new_state_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(prior_state_id) REFERENCES graph_states(id),
                FOREIGN KEY(new_state_id) REFERENCES graph_states(id)
            );

            CREATE TABLE IF NOT EXISTS graph_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                attribute TEXT NOT NULL,
                current_state_id INTEGER NOT NULL,
                candidate_value_text TEXT NOT NULL,
                candidate_source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES graph_entities(id),
                FOREIGN KEY(current_state_id) REFERENCES graph_states(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_conflicts_entity
            ON graph_conflicts(entity_id, attribute, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS publish_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                object_kind TEXT NOT NULL,
                object_key TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                published_at TEXT,
                UNIQUE(target_name, object_kind, object_key)
            );

            CREATE INDEX IF NOT EXISTS idx_publish_journal_target_status
            ON publish_journal(target_name, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS corpus_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                doc_kind TEXT NOT NULL DEFAULT 'document',
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_corpus_documents_kind_updated
            ON corpus_documents(doc_kind, updated_at DESC);

            CREATE TABLE IF NOT EXISTS corpus_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                section_index INTEGER NOT NULL,
                heading TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                token_estimate INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES corpus_documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, section_index)
            );

            CREATE INDEX IF NOT EXISTS idx_corpus_sections_document
            ON corpus_sections(document_id, section_index);

            CREATE VIRTUAL TABLE IF NOT EXISTS corpus_section_fts USING fts5(
                title,
                heading,
                content,
                document_id UNINDEXED,
                section_index UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS applied_migrations (
                name TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def _bootstrap_graph_backend_if_needed(self) -> None:
        if self._graph_backend is None or not self._graph_backend.is_empty():
            return
        entity_ids = [
            int(row["id"])
            for row in self.conn.execute("SELECT id FROM graph_entities ORDER BY id ASC").fetchall()
        ]
        for entity_id in entity_ids:
            self._publish_entity_subgraph(entity_id)

    def _bootstrap_corpus_backend_if_needed(self) -> None:
        if self._corpus_backend is None or not self._corpus_backend.is_empty():
            return
        document_ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM corpus_documents WHERE active = 1 ORDER BY updated_at ASC, id ASC"
            ).fetchall()
        ]
        for document_id in document_ids:
            self._publish_corpus_document(document_id)
        transcript_ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM transcript_entries ORDER BY created_at ASC, id ASC"
            ).fetchall()
        ]
        for transcript_id in transcript_ids:
            self._publish_conversation_transcript(transcript_id, raise_on_error=False)

    def _replay_corpus_publications_if_needed(self) -> None:
        if self._corpus_backend is None:
            return
        pending = self.conn.execute(
            """
            SELECT object_kind, object_key
            FROM publish_journal
            WHERE target_name = ? AND object_kind IN ('corpus_document', 'conversation_transcript') AND status IN ('pending', 'failed')
            ORDER BY updated_at ASC, id ASC
            """,
            (self._corpus_backend.target_name,),
        ).fetchall()
        seen: set[tuple[str, str]] = set()
        for row in pending:
            object_kind = str(row["object_kind"] or "").strip()
            object_key = str(row["object_key"] or "").strip()
            composite = (object_kind, object_key)
            if not object_kind or not object_key or composite in seen:
                continue
            seen.add(composite)
            if object_kind == "corpus_document":
                document = self.conn.execute(
                    "SELECT id FROM corpus_documents WHERE stable_key = ? AND active = 1",
                    (object_key,),
                ).fetchone()
                if document:
                    self._publish_corpus_document(int(document["id"]))
                continue
            if object_kind == "conversation_transcript":
                transcript_id = self._parse_conversation_object_key(object_key)
                if transcript_id is None:
                    continue
                transcript_row = self.conn.execute(
                    "SELECT id FROM transcript_entries WHERE id = ?",
                    (transcript_id,),
                ).fetchone()
                if transcript_row:
                    self._publish_conversation_transcript(transcript_id, raise_on_error=False)

    def _upsert_publish_journal(
        self,
        *,
        target_name: str,
        object_kind: str,
        object_key: str,
        payload: Dict[str, Any],
        status: str = "pending",
        last_error: str = "",
        published: bool = False,
    ) -> None:
        now = utc_now_iso()
        published_at = now if published else None
        existing = self.conn.execute(
            """
            SELECT id, attempt_count FROM publish_journal
            WHERE target_name = ? AND object_kind = ? AND object_key = ?
            """,
            (target_name, object_kind, object_key),
        ).fetchone()
        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if existing:
            attempt_count = int(existing["attempt_count"] or 0)
            self.conn.execute(
                """
                UPDATE publish_journal
                SET payload_json = ?, status = ?, last_error = ?, updated_at = ?, published_at = ?,
                    attempt_count = CASE WHEN ? = 'failed' THEN ? + 1 ELSE attempt_count END
                WHERE id = ?
                """,
                (
                    payload_json,
                    status,
                    last_error,
                    now,
                    published_at,
                    status,
                    attempt_count,
                    int(existing["id"]),
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO publish_journal (
                    target_name, object_kind, object_key, payload_json, status,
                    attempt_count, last_error, created_at, updated_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_name,
                    object_kind,
                    object_key,
                    payload_json,
                    status,
                    0 if status != "failed" else 1,
                    last_error,
                    now,
                    now,
                    published_at,
                ),
            )
        self.conn.commit()

    def _conversation_semantic_object_key(self, transcript_id: int) -> str:
        return f"transcript:{int(transcript_id)}"

    def _parse_conversation_object_key(self, object_key: str) -> int | None:
        text = str(object_key or "").strip()
        if not text.startswith("transcript:"):
            return None
        try:
            return int(text.split(":", 1)[1])
        except (TypeError, ValueError):
            return None

    def _conversation_transcript_snapshot(self, transcript_id: int) -> Dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            WHERE id = ?
            """,
            (transcript_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Transcript entry {transcript_id} is missing")
        item = _row_to_dict(row)
        metadata = dict(item.get("metadata") or {})
        stable_key = (
            f"conversation:{item['session_id']}:{int(item.get('turn_number') or 0)}:{int(item['id'])}"
        )
        document = {
            "id": int(item["id"]),
            "stable_key": stable_key,
            "title": f"Conversation turn {int(item.get('turn_number') or 0)}",
            "doc_kind": "conversation",
            "source": str(item.get("source") or ""),
            "updated_at": str(item.get("created_at") or ""),
            "semantic_class": "conversation",
            "metadata": {
                **metadata,
                "semantic_class": "conversation",
                "session_id": str(item.get("session_id") or ""),
                "turn_number": int(item.get("turn_number") or 0),
                "record_kind": str(item.get("kind") or "turn"),
                "transcript_id": int(item["id"]),
                "created_at": str(item.get("created_at") or ""),
            },
        }
        sections = [
            {
                "section_id": int(item["id"]),
                "section_index": 0,
                "heading": str(item.get("kind") or "turn"),
                "content": str(item.get("content") or ""),
                "token_estimate": max(1, len(str(item.get("content") or "")) // 4),
                "metadata": {
                    **metadata,
                    "semantic_class": "conversation",
                    "session_id": str(item.get("session_id") or ""),
                    "turn_number": int(item.get("turn_number") or 0),
                    "record_kind": str(item.get("kind") or "turn"),
                    "transcript_id": int(item["id"]),
                    "created_at": str(item.get("created_at") or ""),
                },
            }
        ]
        return {"document": document, "sections": sections}

    def _publish_semantic_snapshot(
        self,
        *,
        object_kind: str,
        object_key: str,
        snapshot: Dict[str, Any],
        raise_on_error: bool,
    ) -> None:
        if self._corpus_backend is None:
            return
        target_name = self._corpus_backend.target_name
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind=object_kind,
            object_key=object_key,
            payload=snapshot,
            status="pending",
        )
        try:
            self._corpus_backend.publish_document(snapshot)
        except Exception as exc:
            self._corpus_backend_error = str(exc)
            self._upsert_publish_journal(
                target_name=target_name,
                object_kind=object_kind,
                object_key=object_key,
                payload=snapshot,
                status="failed",
                last_error=self._corpus_backend_error,
            )
            if raise_on_error:
                raise
            logger.warning(
                "Brainstack semantic publication failed for %s %s: %s",
                object_kind,
                object_key,
                exc,
            )
            return
        self._corpus_backend_error = ""
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind=object_kind,
            object_key=object_key,
            payload=snapshot,
            status="published",
            published=True,
        )

    def _publish_conversation_transcript(self, transcript_id: int, *, raise_on_error: bool) -> None:
        snapshot = self._conversation_transcript_snapshot(transcript_id)
        self._publish_semantic_snapshot(
            object_kind="conversation_transcript",
            object_key=self._conversation_semantic_object_key(transcript_id),
            snapshot=snapshot,
            raise_on_error=raise_on_error,
        )

    @_locked
    def list_publish_journal(self, *, target_name: str | None = None, status: str | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        where: List[str] = []
        params: List[Any] = []
        if target_name:
            where.append("target_name = ?")
            params.append(target_name)
        if status:
            where.append("status = ?")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
            SELECT id, target_name, object_kind, object_key, payload_json, status,
                   attempt_count, last_error, created_at, updated_at, published_at
            FROM publish_journal
            {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def _entity_snapshot(self, entity_id: int) -> Dict[str, Any]:
        entity_row = self.conn.execute(
            """
            SELECT id, canonical_name, normalized_name, COALESCE(updated_at, created_at) AS updated_at
            FROM graph_entities
            WHERE id = ?
            """,
            (entity_id,),
        ).fetchone()
        if not entity_row:
            raise RuntimeError(f"Missing graph entity for snapshot: {entity_id}")
        entity = dict(entity_row)

        state_rows = self.conn.execute(
            """
            SELECT 'state' AS row_type,
                   gs.id AS row_id,
                   ge.canonical_name AS subject,
                   gs.attribute AS predicate,
                   gs.value_text AS object_value,
                   gs.is_current AS is_current,
                   gs.valid_from AS happened_at,
                   gs.valid_to AS valid_to,
                   gs.source AS source,
                   gs.metadata_json AS metadata_json,
                   '' AS conflict_metadata_json,
                   '' AS conflict_source,
                   '' AS conflict_value,
                   1 AS active
            FROM graph_states gs
            JOIN graph_entities ge ON ge.id = gs.entity_id
            WHERE gs.entity_id = ?
            ORDER BY gs.valid_from DESC, gs.id DESC
            """,
            (entity_id,),
        ).fetchall()
        states = [_row_to_dict(row) for row in state_rows]

        conflict_rows = self.conn.execute(
            """
            SELECT 'conflict' AS row_type,
                   gc.id AS row_id,
                   ge.canonical_name AS subject,
                   gc.attribute AS predicate,
                   gs.value_text AS object_value,
                   1 AS is_current,
                   gc.updated_at AS happened_at,
                   '' AS valid_to,
                   gs.source AS source,
                   gs.metadata_json AS metadata_json,
                   gc.metadata_json AS conflict_metadata_json,
                   gc.candidate_source AS conflict_source,
                   gc.candidate_value_text AS conflict_value,
                   1 AS active,
                   gc.current_state_id AS current_state_id
            FROM graph_conflicts gc
            JOIN graph_entities ge ON ge.id = gc.entity_id
            JOIN graph_states gs ON gs.id = gc.current_state_id
            WHERE gc.entity_id = ? AND gc.status = 'open'
            ORDER BY gc.updated_at DESC, gc.id DESC
            """,
            (entity_id,),
        ).fetchall()
        conflicts = [_row_to_dict(row) for row in conflict_rows]

        relation_rows = self.conn.execute(
            """
            SELECT 'relation' AS row_type,
                   gr.id AS row_id,
                   ge.canonical_name AS subject,
                   gr.predicate AS predicate,
                   COALESCE(go.canonical_name, gr.object_text, '') AS object_value,
                   1 AS is_current,
                   gr.created_at AS happened_at,
                   '' AS valid_to,
                   gr.source AS source,
                   gr.metadata_json AS metadata_json,
                   '' AS conflict_metadata_json,
                   '' AS conflict_source,
                   '' AS conflict_value,
                   gr.active AS active,
                   go.id AS object_entity_id,
                   go.canonical_name AS object_canonical_name,
                   go.normalized_name AS object_normalized_name
            FROM graph_relations gr
            JOIN graph_entities ge ON ge.id = gr.subject_entity_id
            LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
            WHERE gr.subject_entity_id = ?
            ORDER BY gr.created_at DESC, gr.id DESC
            """,
            (entity_id,),
        ).fetchall()
        relations = []
        for row in relation_rows:
            item = _row_to_dict(row)
            item["object_entity"] = {
                "id": int(item.pop("object_entity_id") or 0),
                "canonical_name": str(item.pop("object_canonical_name") or item.get("object_value") or ""),
                "normalized_name": str(item.pop("object_normalized_name") or ""),
                "updated_at": "",
            }
            relations.append(item)

        inferred_rows = self.conn.execute(
            """
            SELECT 'inferred_relation' AS row_type,
                   gir.id AS row_id,
                   ge.canonical_name AS subject,
                   gir.predicate AS predicate,
                   COALESCE(go.canonical_name, gir.object_text, '') AS object_value,
                   1 AS is_current,
                   gir.updated_at AS happened_at,
                   '' AS valid_to,
                   gir.source AS source,
                   gir.metadata_json AS metadata_json,
                   '' AS conflict_metadata_json,
                   '' AS conflict_source,
                   '' AS conflict_value,
                   gir.active AS active,
                   go.id AS object_entity_id,
                   go.canonical_name AS object_canonical_name,
                   go.normalized_name AS object_normalized_name
            FROM graph_inferred_relations gir
            JOIN graph_entities ge ON ge.id = gir.subject_entity_id
            LEFT JOIN graph_entities go ON go.id = gir.object_entity_id
            WHERE gir.subject_entity_id = ?
            ORDER BY gir.updated_at DESC, gir.id DESC
            """,
            (entity_id,),
        ).fetchall()
        inferred_relations = []
        for row in inferred_rows:
            item = _row_to_dict(row)
            item["object_entity"] = {
                "id": int(item.pop("object_entity_id") or 0),
                "canonical_name": str(item.pop("object_canonical_name") or item.get("object_value") or ""),
                "normalized_name": str(item.pop("object_normalized_name") or ""),
                "updated_at": "",
            }
            inferred_relations.append(item)

        return {
            "entity": entity,
            "states": states,
            "conflicts": conflicts,
            "relations": relations,
            "inferred_relations": inferred_relations,
        }

    def _publish_entity_subgraph(self, entity_id: int) -> None:
        if self._graph_backend is None:
            return
        snapshot = self._entity_snapshot(entity_id)
        target_name = self._graph_backend.target_name
        object_key = str(entity_id)
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind="entity_subgraph",
            object_key=object_key,
            payload=snapshot,
            status="pending",
        )
        try:
            self._graph_backend.publish_entity_subgraph(snapshot)
        except Exception as exc:
            self._upsert_publish_journal(
                target_name=target_name,
                object_kind="entity_subgraph",
                object_key=object_key,
                payload=snapshot,
                status="failed",
                last_error=str(exc),
            )
            raise
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind="entity_subgraph",
            object_key=object_key,
            payload=snapshot,
            status="published",
            published=True,
        )

    def _corpus_document_snapshot(self, document_id: int) -> Dict[str, Any]:
        document_row = self.conn.execute(
            """
            SELECT id, stable_key, title, doc_kind, source, metadata_json, updated_at, active
            FROM corpus_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        if not document_row:
            raise RuntimeError(f"Missing corpus document for snapshot: {document_id}")
        document = _row_to_dict(document_row)
        section_rows = self.conn.execute(
            """
            SELECT
                id AS section_id,
                section_index,
                heading,
                content,
                token_estimate,
                metadata_json
            FROM corpus_sections
            WHERE document_id = ?
            ORDER BY section_index ASC, id ASC
            """,
            (document_id,),
        ).fetchall()
        sections = [_row_to_dict(row) for row in section_rows]
        return {"document": document, "sections": sections}

    def _publish_corpus_document(self, document_id: int) -> None:
        if self._corpus_backend is None:
            return
        snapshot = self._corpus_document_snapshot(document_id)
        document = dict(snapshot.get("document") or {})
        object_key = str(document.get("stable_key") or "").strip()
        if not object_key:
            raise RuntimeError(f"Corpus snapshot missing stable_key for document {document_id}")
        self._publish_semantic_snapshot(
            object_kind="corpus_document",
            object_key=object_key,
            snapshot=snapshot,
            raise_on_error=True,
        )

    @_locked
    def add_continuity_event(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        now = str(created_at or "").strip() or utc_now_iso()
        if created_at:
            metadata = dict(metadata or {})
            metadata.setdefault("observed_at", now)
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        normalized_metadata.setdefault("source_kind", "explicit")
        normalized_metadata.setdefault("graph_kind", "relation")
        cur = self.conn.execute(
            """
            INSERT INTO continuity_events (
                session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                turn_number,
                kind,
                content,
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        self.conn.execute(
            "INSERT INTO continuity_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
        return row_id

    @_locked
    def add_transcript_entry(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        now = str(created_at or "").strip() or utc_now_iso()
        if created_at:
            metadata = dict(metadata or {})
            metadata.setdefault("observed_at", now)
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        normalized_metadata.setdefault("source_kind", "explicit")
        normalized_metadata.setdefault("graph_kind", "relation")
        cur = self.conn.execute(
            """
            INSERT INTO transcript_entries (
                session_id, turn_number, kind, content, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                turn_number,
                kind,
                content,
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        self.conn.execute(
            "INSERT INTO transcript_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
        if self._corpus_backend is not None:
            self._publish_conversation_transcript(row_id, raise_on_error=False)
        return row_id

    @_locked
    def recent_continuity(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM continuity_events
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def get_continuity_lifecycle_state(self, *, session_id: str) -> Dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            FROM continuity_lifecycle_state
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    @_locked
    def record_continuity_snapshot_state(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        message_count: int = 0,
        input_message_count: int = 0,
        digest: str = "",
        created_at: str | None = None,
    ) -> Dict[str, Any]:
        now = str(created_at or "").strip() or utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO continuity_lifecycle_state (
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?)
            ON CONFLICT(session_id) DO UPDATE SET
                current_frontier_turn_number = MAX(
                    continuity_lifecycle_state.current_frontier_turn_number,
                    excluded.current_frontier_turn_number
                ),
                last_snapshot_kind = excluded.last_snapshot_kind,
                last_snapshot_turn_number = excluded.last_snapshot_turn_number,
                last_snapshot_message_count = excluded.last_snapshot_message_count,
                last_snapshot_input_count = excluded.last_snapshot_input_count,
                last_snapshot_digest = excluded.last_snapshot_digest,
                last_snapshot_at = excluded.last_snapshot_at,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                max(0, int(turn_number or 0)),
                str(kind or "").strip(),
                max(0, int(turn_number or 0)),
                max(0, int(message_count or 0)),
                max(0, int(input_message_count or 0)),
                str(digest or "").strip(),
                now,
                now,
            ),
        )
        self.conn.commit()
        state = self.get_continuity_lifecycle_state(session_id=session_id)
        assert state is not None
        return state

    @_locked
    def finalize_continuity_session_state(
        self,
        *,
        session_id: str,
        turn_number: int,
        created_at: str | None = None,
    ) -> Dict[str, Any]:
        now = str(created_at or "").strip() or utc_now_iso()
        finalized_turn = max(0, int(turn_number or 0))
        self.conn.execute(
            """
            INSERT INTO continuity_lifecycle_state (
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            ) VALUES (?, ?, '', 0, 0, 0, '', '', ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                current_frontier_turn_number = MAX(
                    continuity_lifecycle_state.current_frontier_turn_number,
                    excluded.current_frontier_turn_number
                ),
                last_finalized_turn_number = MAX(
                    continuity_lifecycle_state.last_finalized_turn_number,
                    excluded.last_finalized_turn_number
                ),
                last_finalized_at = excluded.last_finalized_at,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                finalized_turn,
                finalized_turn,
                now,
                now,
            ),
        )
        self.conn.commit()
        state = self.get_continuity_lifecycle_state(session_id=session_id)
        assert state is not None
        return state

    @_locked
    def search_temporal_continuity(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        row_limit = max(limit * 6, 24)
        current_principal_scope_key = str(principal_scope_key or "").strip()
        fts_query = build_fts_query(query)
        if fts_query:
            try:
                rows = self.conn.execute(
                    """
                    SELECT ce.id, ce.session_id, ce.turn_number, ce.kind, ce.content, ce.source, ce.metadata_json, ce.created_at
                    FROM continuity_fts fts
                    JOIN continuity_events ce ON ce.id = fts.rowid
                    WHERE ce.kind = 'temporal_event' AND continuity_fts MATCH ?
                    ORDER BY
                        CASE WHEN ce.session_id = ? THEN 0 ELSE 1 END,
                        bm25(continuity_fts),
                        ce.created_at DESC
                    LIMIT ?
                    """,
                    (fts_query, session_id, row_limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        else:
            rows = []
        keyword_rows = _attach_keyword_scores(_row_to_dict(row) for row in rows) if rows else []
        if not rows:
            rows = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM continuity_events
                WHERE kind = 'temporal_event'
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (row_limit,),
            ).fetchall()
        fallback_rows = [_row_to_dict(row) for row in rows] if not keyword_rows else []
        scored: List[Dict[str, Any]] = []
        for row in keyword_rows or fallback_rows:
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
            ):
                continue
            metadata = dict(item.get("metadata") or {})
            temporal_payload = metadata.get("temporal")
            temporal = temporal_payload if isinstance(temporal_payload, dict) else {}
            item["same_session"] = item["session_id"] == session_id
            item.setdefault("keyword_score", 0.0)
            item["semantic_score"] = 0.0
            item["retrieval_source"] = "continuity.temporal_keyword" if keyword_rows else "continuity.temporal_recent"
            item["match_mode"] = "keyword" if keyword_rows else "recent"
            item["_temporal_observed_at"] = str(
                temporal.get("observed_at")
                or temporal.get("valid_at")
                or item.get("created_at")
                or ""
            )
            scored.append(item)

        semantic_scorer = getattr(self._corpus_backend, "score_texts", None)
        if callable(semantic_scorer) and scored:
            try:
                semantic_scores = semantic_scorer(
                    query=query,
                    texts=[str(item.get("content") or "") for item in scored],
                )
            except Exception as exc:
                self._corpus_backend_error = str(exc)
                logger.warning("Brainstack temporal continuity semantic scoring failed: %s", exc)
            else:
                self._corpus_backend_error = ""
                for item, semantic_score in zip(scored, semantic_scores):
                    item["semantic_score"] = float(semantic_score or 0.0)

        scored.sort(
            key=lambda item: (
                1 if float(item.get("semantic_score") or 0.0) > 0.0 else 0,
                float(item.get("semantic_score") or 0.0),
                float(item.get("keyword_score") or 0.0),
                1 if item.get("same_session") else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("_temporal_observed_at") or ""),
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def search_continuity(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        current_principal_scope_key = str(principal_scope_key or "").strip()
        try:
            rows = self.conn.execute(
                """
                SELECT ce.id, ce.session_id, ce.turn_number, ce.kind, ce.content, ce.source, ce.metadata_json, ce.created_at
                FROM continuity_fts fts
                JOIN continuity_events ce ON ce.id = fts.rowid
                WHERE continuity_fts MATCH ?
                ORDER BY
                    CASE WHEN ce.session_id = ? THEN 0 ELSE 1 END,
                    bm25(continuity_fts),
                    ce.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM continuity_events
                WHERE content LIKE ?
                ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                (like, session_id, limit),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
            ):
                continue
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "continuity.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                float(item.get("keyword_score") or 0.0),
                1 if item["same_session"] else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def recent_transcript(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def search_transcript(self, *, query: str, session_id: str, limit: int) -> List[Dict[str, Any]]:
        tokens = _extract_query_terms(query, limit=8)
        if not tokens:
            return []

        candidate_limit = max(limit * 4, 8)
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:8])
        rows: List[sqlite3.Row]

        try:
            rows = self.conn.execute(
                """
                SELECT te.id, te.session_id, te.turn_number, te.kind, te.content, te.source, te.metadata_json, te.created_at
                FROM transcript_fts fts
                JOIN transcript_entries te ON te.id = fts.rowid
                WHERE transcript_fts MATCH ?
                  AND te.session_id = ?
                ORDER BY
                    bm25(transcript_fts),
                    te.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, candidate_limit),
            ).fetchall()
        except sqlite3.OperationalError:
            patterns = [f"%{token}%" for token in tokens[:8]]
            where = " OR ".join("lower(content) LIKE ?" for _ in patterns)
            rows = self.conn.execute(
                f"""
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM transcript_entries
                WHERE session_id = ? AND ({where})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple([session_id] + patterns + [candidate_limit]),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "transcript.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                1 if item["same_session"] else 0,
                float(item.get("keyword_score") or 0.0),
                int(item["turn_number"]),
                int(item["id"]),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def search_transcript_global(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        tokens = _extract_query_terms(query, limit=8)
        if not tokens:
            return []

        candidate_limit = max(limit * 6, 12)
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:8])
        rows: List[sqlite3.Row]
        current_principal_scope_key = str(principal_scope_key or "").strip()

        try:
            rows = self.conn.execute(
                """
                SELECT te.id, te.session_id, te.turn_number, te.kind, te.content, te.source, te.metadata_json, te.created_at
                FROM transcript_fts fts
                JOIN transcript_entries te ON te.id = fts.rowid
                WHERE transcript_fts MATCH ?
                ORDER BY
                    CASE WHEN te.session_id = ? THEN 0 ELSE 1 END,
                    bm25(transcript_fts),
                    te.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, candidate_limit),
            ).fetchall()
        except sqlite3.OperationalError:
            patterns = [f"%{token}%" for token in tokens[:8]]
            where = " OR ".join("lower(content) LIKE ?" for _ in patterns)
            rows = self.conn.execute(
                f"""
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM transcript_entries
                WHERE {where}
                ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                tuple(patterns + [session_id, candidate_limit]),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
            ):
                continue
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "transcript.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                float(item.get("keyword_score") or 0.0),
                1 if item["same_session"] else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("created_at") or ""),
                int(item["turn_number"]),
                int(item["id"]),
            ),
            reverse=True,
        )
        return scored[:limit]

    def _get_active_behavior_contract_row(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        principal_scope_key: str = "",
    ) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE principal_scope_key = ? AND stable_key = ? AND status = ?
            ORDER BY revision_number DESC, id DESC
            LIMIT 1
            """,
            (
                str(principal_scope_key or "").strip(),
                str(stable_key or "").strip() or STYLE_CONTRACT_SLOT,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS,
            ),
        ).fetchone()

    @_locked
    def upsert_behavior_contract(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        category: str,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        now = utc_now_iso()
        principal_scope_key = _principal_scope_key_from_metadata(metadata)
        logical_key = str(stable_key or "").strip() or STYLE_CONTRACT_SLOT
        existing = self._get_active_behavior_contract_row(
            stable_key=logical_key,
            principal_scope_key=principal_scope_key,
        )
        if existing is None and principal_scope_key:
            candidate_rows = self.conn.execute(
                """
                SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                       metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                       committed_at, updated_at
                FROM behavior_contracts
                WHERE stable_key = ? AND status = ?
                ORDER BY committed_at DESC, revision_number DESC, id DESC
                LIMIT 16
                """,
                (
                    logical_key,
                    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
                ),
            ).fetchall()
            fallback_existing: sqlite3.Row | None = None
            fallback_priority: tuple[int, float, str, int] | None = None
            for candidate_row in candidate_rows:
                item = _behavior_contract_row_to_dict(candidate_row)
                if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                    continue
                priority = _scoped_row_priority(item, principal_scope_key=principal_scope_key)
                if priority[0] <= 0:
                    continue
                if fallback_priority is None or priority > fallback_priority:
                    fallback_existing = candidate_row
                    fallback_priority = priority
            existing = fallback_existing
        normalized_metadata = _merge_record_metadata(
            existing["metadata_json"] if existing else None,
            metadata,
            source=source,
        )
        if existing and str(existing["content"] or "").strip() == str(content or "").strip():
            return int(existing["id"])
        if (
            existing
            and _should_preserve_existing_style_contract(
                existing_source=existing["source"],
                incoming_source=source,
                existing_content=existing["content"],
                existing_metadata=existing["metadata_json"],
                incoming_content=content,
                incoming_metadata=normalized_metadata,
            )
            and str(existing["content"] or "").strip() != str(content or "").strip()
        ):
            return int(existing["id"])
        metadata_json = json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True)
        if existing:
            existing_item = _behavior_contract_row_to_dict(existing)
            if (
                str(existing_item.get("content") or "").strip() == str(content or "").strip()
                and str(existing_item.get("source") or "").strip() == str(source or "").strip()
                and json.dumps(existing_item.get("metadata") or {}, ensure_ascii=True, sort_keys=True) == metadata_json
                and float(existing_item.get("confidence") or 0.0) == float(confidence)
                and bool(existing_item.get("active", False)) == bool(active)
            ):
                return int(existing_item["id"])
            parent_revision_id = int(existing_item["id"])
            revision_number = int(existing_item.get("revision_number") or 0) + 1
        else:
            parent_revision_id = 0
            revision_number = 1
        storage_key = _behavior_contract_storage_key(
            stable_key=logical_key,
            principal_scope_key=principal_scope_key,
            revision_number=revision_number,
        )
        compiled = None
        if active:
            compiled = compile_behavior_policy(
                raw_content=content,
                metadata=normalized_metadata,
                source_storage_key=storage_key,
                source_updated_at=now,
            )
            if compiled is None:
                raise ValueError("Behavior contract commit failed because compiled behavior policy could not be built")
        if existing:
            self.conn.execute(
                """
                UPDATE behavior_contracts
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
                    now,
                    int(existing["id"]),
                ),
            )
        cur = self.conn.execute(
            """
            INSERT INTO behavior_contracts (
                storage_key,
                principal_scope_key,
                stable_key,
                category,
                content,
                source,
                confidence,
                metadata_json,
                source_contract_hash,
                revision_number,
                parent_revision_id,
                status,
                committed_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                storage_key,
                str(principal_scope_key or "").strip(),
                logical_key,
                category,
                content,
                source,
                confidence,
                metadata_json,
                hashlib.sha256(str(content or "").encode("utf-8")).hexdigest() if str(content or "") else "",
                revision_number,
                parent_revision_id,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS if active else BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        if compiled is not None:
            self._upsert_compiled_behavior_policy_record(
                principal_scope_key=principal_scope_key,
                compiled_policy=compiled,
            )
        self.conn.commit()
        return row_id

    @_locked
    def upsert_profile_item(
        self,
        *,
        stable_key: str,
        category: str,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        if str(stable_key or "").strip() == STYLE_CONTRACT_SLOT:
            return self.upsert_behavior_contract(
                stable_key=stable_key,
                category=category,
                content=content,
                source=source,
                confidence=confidence,
                metadata=metadata,
                active=active,
            )
        now = utc_now_iso()
        principal_scope_key = _principal_scope_key_from_metadata(metadata)
        storage_key = _profile_storage_key(
            stable_key=stable_key,
            category=category,
            principal_scope_key=principal_scope_key,
        )
        existing = self.conn.execute(
            "SELECT id, content, source, metadata_json FROM profile_items WHERE stable_key = ?",
            (storage_key,),
        ).fetchone()
        normalized_metadata = _merge_record_metadata(
            existing["metadata_json"] if existing else None,
            metadata,
            source=source,
        )
        meta_json = json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True)

        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE profile_items
                SET category = ?, content = ?, source = ?, confidence = ?, metadata_json = ?,
                    updated_at = ?, active = ?
                WHERE id = ?
                """,
                (
                    category,
                    content,
                    source,
                    confidence,
                    meta_json,
                    now,
                    1 if active else 0,
                    row_id,
                ),
            )
            self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (row_id,))
        else:
            cur = self.conn.execute(
                """
                INSERT INTO profile_items (
                    stable_key, category, content, source, confidence,
                    metadata_json, first_seen_at, updated_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    storage_key,
                    category,
                    content,
                    source,
                    confidence,
                    meta_json,
                    now,
                    now,
                    1 if active else 0,
                ),
            )
            row_id = _cursor_lastrowid(cur)

        self.conn.execute(
            "INSERT INTO profile_fts(rowid, content, category, stable_key) VALUES (?, ?, ?, ?)",
            (row_id, content, category, stable_key),
        )
        self.conn.commit()
        return row_id

    @_locked
    def get_compiled_behavior_policy(self, *, principal_scope_key: str = "") -> Dict[str, Any] | None:
        requested_scope_key = str(principal_scope_key or "").strip()
        contract = self.get_behavior_contract(principal_scope_key=requested_scope_key)
        if contract and style_contract_cleanliness_issues(
            raw_text=str(contract.get("content") or ""),
            metadata=contract.get("metadata") if isinstance(contract.get("metadata"), dict) else None,
        ):
            polluted_scope_key = str(contract.get("principal_scope_key") or "").strip() or requested_scope_key
            self._delete_compiled_behavior_policy_record(principal_scope_key=polluted_scope_key)
            self.conn.commit()
            return None
        row = self.conn.execute(
            """
            SELECT principal_scope_key, source_storage_key, source_contract_hash, source_contract_updated_at,
                   schema_version, compiler_version, title, policy_json, projection_text, status, updated_at
            FROM compiled_behavior_policies
            WHERE principal_scope_key = ?
            LIMIT 1
            """,
            (requested_scope_key,),
        ).fetchone()
        if row:
            return _compiled_behavior_policy_row_to_dict(row)
        if not requested_scope_key:
            return None
        if not contract:
            return None
        fallback_scope_key = str(contract.get("principal_scope_key") or "").strip()
        if not fallback_scope_key or fallback_scope_key == requested_scope_key:
            return None
        fallback_row = self.conn.execute(
            """
            SELECT principal_scope_key, source_storage_key, source_contract_hash, source_contract_updated_at,
                   schema_version, compiler_version, title, policy_json, projection_text, status, updated_at
            FROM compiled_behavior_policies
            WHERE principal_scope_key = ?
            LIMIT 1
            """,
            (fallback_scope_key,),
        ).fetchone()
        return _compiled_behavior_policy_row_to_dict(fallback_row) if fallback_row else None

    @_locked
    def get_behavior_policy_snapshot(self, *, principal_scope_key: str = "") -> Dict[str, Any]:
        raw_contract = self.get_behavior_contract(principal_scope_key=principal_scope_key)
        compiled_policy = self.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
        snapshot = build_behavior_policy_snapshot(
            raw_contract_row=raw_contract,
            compiled_policy_record=compiled_policy,
        )
        snapshot["principal_scope_key"] = str(principal_scope_key or "").strip()
        return snapshot

    @_locked
    def get_operating_context_snapshot(
        self,
        *,
        principal_scope_key: str = "",
        session_id: str = "",
        stable_profile_limit: int = 4,
        continuity_limit: int = 12,
        decision_limit: int = 4,
    ) -> Dict[str, Any]:
        scope_key = str(principal_scope_key or "").strip()
        sid = str(session_id or "").strip()
        compiled_policy = self.get_compiled_behavior_policy(principal_scope_key=scope_key)
        profile_items = self.list_profile_items(
            limit=max(12, stable_profile_limit * 4),
            principal_scope_key=scope_key,
        )
        operating_rows = self.list_operating_records(
            principal_scope_key=scope_key,
            limit=16,
        )
        task_rows = self.list_task_items(
            principal_scope_key=scope_key,
            item_type="commitment",
            statuses=("open",),
            limit=8,
        )
        continuity_rows = self.recent_continuity(session_id=sid, limit=max(continuity_limit, decision_limit * 2)) if sid else []
        lifecycle_state = self.get_continuity_lifecycle_state(session_id=sid) if sid else None
        return build_operating_context_snapshot(
            principal_scope_key=scope_key,
            compiled_behavior_policy_record=compiled_policy,
            profile_items=profile_items,
            operating_rows=operating_rows,
            task_rows=task_rows,
            continuity_rows=continuity_rows,
            lifecycle_state=lifecycle_state,
            stable_profile_limit=stable_profile_limit,
            decision_limit=decision_limit,
        )

    @_locked
    def apply_behavior_policy_correction(
        self,
        *,
        principal_scope_key: str = "",
        rule_id: str,
        replacement_text: Any,
        source: str = "behavior_policy_correction",
    ) -> Dict[str, Any] | None:
        raw_contract = self.get_behavior_contract(principal_scope_key=principal_scope_key)
        if raw_contract is None:
            return None
        corrected = apply_style_contract_rule_correction(
            raw_text=raw_contract.get("content"),
            rule_id=rule_id,
            replacement_text=replacement_text,
            metadata=raw_contract.get("metadata"),
        )
        if corrected is None:
            return None
        metadata = dict(raw_contract.get("metadata") or {})
        metadata["style_contract_title"] = corrected["title"]
        metadata["style_contract_sections"] = corrected["sections"]
        if corrected["summary"]:
            metadata["style_contract_summary"] = corrected["summary"]
        else:
            metadata.pop("style_contract_summary", None)
        metadata["last_behavior_policy_correction"] = {
            "rule_id": corrected["updated_rule_id"],
            "source": str(source or "").strip() or "behavior_policy_correction",
            "rule_count": len(list_style_contract_rules(raw_text=corrected["content"], metadata=metadata)),
            "content_hash": hashlib.sha256(str(corrected["content"]).encode("utf-8")).hexdigest(),
        }
        self.upsert_behavior_contract(
            stable_key=STYLE_CONTRACT_SLOT,
            category=str(raw_contract.get("category") or "preference"),
            content=str(corrected["content"]),
            source=str(source or "").strip() or "behavior_policy_correction",
            confidence=float(raw_contract.get("confidence") or 0.9),
            metadata=metadata,
        )
        return self.get_behavior_policy_snapshot(principal_scope_key=principal_scope_key)

    @_locked
    def upsert_task_item(
        self,
        *,
        stable_key: str,
        principal_scope_key: str,
        item_type: str,
        title: str,
        due_date: str,
        date_scope: str,
        optional: bool,
        status: str,
        owner: str,
        source: str,
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM task_items WHERE stable_key = ?",
            (str(stable_key or "").strip(),),
        ).fetchone()
        meta_json = json.dumps(
            _merge_record_metadata(
                existing["metadata_json"] if existing else None,
                metadata,
                source=source,
            ),
            ensure_ascii=True,
            sort_keys=True,
        )
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE task_items
                SET principal_scope_key = ?, item_type = ?, title = ?, due_date = ?, date_scope = ?,
                    optional = ?, status = ?, owner = ?, source = ?, source_session_id = ?,
                    source_turn_number = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(principal_scope_key or "").strip(),
                    str(item_type or "").strip(),
                    str(title or "").strip(),
                    str(due_date or "").strip(),
                    str(date_scope or "").strip(),
                    1 if optional else 0,
                    str(status or STATUS_OPEN).strip() or STATUS_OPEN,
                    str(owner or "brainstack.task_memory").strip() or "brainstack.task_memory",
                    str(source or "").strip(),
                    str(source_session_id or "").strip(),
                    int(source_turn_number or 0),
                    meta_json,
                    now,
                    row_id,
                ),
            )
            self.conn.commit()
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO task_items (
                stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                optional, status, owner, source, source_session_id, source_turn_number,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(stable_key or "").strip(),
                str(principal_scope_key or "").strip(),
                str(item_type or "").strip(),
                str(title or "").strip(),
                str(due_date or "").strip(),
                str(date_scope or "").strip(),
                1 if optional else 0,
                str(status or STATUS_OPEN).strip() or STATUS_OPEN,
                str(owner or "brainstack.task_memory").strip() or "brainstack.task_memory",
                str(source or "").strip(),
                str(source_session_id or "").strip(),
                int(source_turn_number or 0),
                meta_json,
                now,
                now,
            ),
        )
        self.conn.commit()
        return _cursor_lastrowid(cur)

    @_locked
    def list_task_items(
        self,
        *,
        principal_scope_key: str,
        due_date: str = "",
        item_type: str = "",
        statuses: Iterable[str] | None = None,
        limit: int = 24,
    ) -> List[Dict[str, Any]]:
        scope_key = str(principal_scope_key or "").strip()
        params: list[Any] = [scope_key]
        sql = """
            SELECT
                id, stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                optional, status, owner, source, source_session_id, source_turn_number,
                metadata_json, created_at, updated_at
            FROM task_items
            WHERE principal_scope_key = ?
        """
        normalized_due_date = str(due_date or "").strip()
        if normalized_due_date:
            sql += " AND due_date = ?"
            params.append(normalized_due_date)
        normalized_item_type = str(item_type or "").strip()
        if normalized_item_type:
            sql += " AND item_type = ?"
            params.append(normalized_item_type)
        status_values = [str(value or "").strip() for value in (statuses or ()) if str(value or "").strip()]
        if status_values:
            sql += f" AND status IN ({','.join('?' for _ in status_values)})"
            params.extend(status_values)
        sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, due_date ASC, optional ASC, updated_at DESC, id DESC LIMIT ?"
        params.append(max(int(limit or 0), 1))
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [_task_row_to_dict(row) for row in rows]

    @_locked
    def upsert_operating_record(
        self,
        *,
        stable_key: str,
        principal_scope_key: str,
        record_type: str,
        content: str,
        owner: str,
        source: str,
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM operating_records WHERE stable_key = ?",
            (str(stable_key or "").strip(),),
        ).fetchone()
        meta_json = json.dumps(
            _merge_record_metadata(
                existing["metadata_json"] if existing else None,
                metadata,
                source=source,
            ),
            ensure_ascii=True,
            sort_keys=True,
        )
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE operating_records
                SET principal_scope_key = ?, record_type = ?, content = ?, owner = ?, source = ?,
                    source_session_id = ?, source_turn_number = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(principal_scope_key or "").strip(),
                    str(record_type or "").strip(),
                    str(content or "").strip(),
                    str(owner or "brainstack.operating_truth").strip() or "brainstack.operating_truth",
                    str(source or "").strip(),
                    str(source_session_id or "").strip(),
                    int(source_turn_number or 0),
                    meta_json,
                    now,
                    row_id,
                ),
            )
            self.conn.execute("DELETE FROM operating_fts WHERE rowid = ?", (row_id,))
            self.conn.execute(
                "INSERT INTO operating_fts(rowid, content, record_type, stable_key) VALUES (?, ?, ?, ?)",
                (
                    row_id,
                    str(content or "").strip(),
                    str(record_type or "").strip(),
                    str(stable_key or "").strip(),
                ),
            )
            self.conn.commit()
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO operating_records (
                stable_key, principal_scope_key, record_type, content, owner, source,
                source_session_id, source_turn_number, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(stable_key or "").strip(),
                str(principal_scope_key or "").strip(),
                str(record_type or "").strip(),
                str(content or "").strip(),
                str(owner or "brainstack.operating_truth").strip() or "brainstack.operating_truth",
                str(source or "").strip(),
                str(source_session_id or "").strip(),
                int(source_turn_number or 0),
                meta_json,
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        self.conn.execute(
            "INSERT INTO operating_fts(rowid, content, record_type, stable_key) VALUES (?, ?, ?, ?)",
            (
                row_id,
                str(content or "").strip(),
                str(record_type or "").strip(),
                str(stable_key or "").strip(),
            ),
        )
        self.conn.commit()
        return row_id

    @_locked
    def list_operating_records(
        self,
        *,
        principal_scope_key: str,
        record_types: Iterable[str] | None = None,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        candidate_limit = max(int(limit or 0) * 6, 24)
        params: List[Any] = []
        sql = """
            SELECT
                id, stable_key, principal_scope_key, record_type, content, owner, source,
                source_session_id, source_turn_number, metadata_json, created_at, updated_at
            FROM operating_records
            WHERE 1 = 1
        """
        normalized_record_types = [
            str(value or "").strip()
            for value in (record_types or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        if normalized_record_types:
            sql += f" AND record_type IN ({','.join('?' for _ in normalized_record_types)})"
            params.extend(normalized_record_types)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(candidate_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()

        scoped: Dict[str, Dict[str, Any]] = {}
        for candidate_row in rows:
            item = _operating_row_to_dict(candidate_row)
            if not _annotate_principal_scope(item, principal_scope_key=requested_scope_key):
                continue
            logical_key = str(item.get("stable_key") or "").strip() or f"row:{item.get('id')}"
            existing = scoped.get(logical_key)
            if existing is None or _scoped_row_priority(item, principal_scope_key=requested_scope_key) > _scoped_row_priority(
                existing,
                principal_scope_key=requested_scope_key,
            ):
                scoped[logical_key] = item
        output = sorted(
            scoped.values(),
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return output[: max(int(limit or 0), 1)]

    @_locked
    def search_operating_records(
        self,
        *,
        query: str,
        principal_scope_key: str,
        record_types: Iterable[str] | None = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        candidate_limit = max(int(limit or 0) * 8, 24)
        normalized_record_types = [
            str(value or "").strip()
            for value in (record_types or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        params: List[Any]
        rows: List[sqlite3.Row]
        sql = """
            SELECT
                o.id, o.stable_key, o.principal_scope_key, o.record_type, o.content, o.owner, o.source,
                o.source_session_id, o.source_turn_number, o.metadata_json, o.created_at, o.updated_at
            FROM operating_fts fts
            JOIN operating_records o ON o.id = fts.rowid
            WHERE operating_fts MATCH ?
        """
        params = [fts_query]
        if normalized_record_types:
            sql += f" AND o.record_type IN ({','.join('?' for _ in normalized_record_types)})"
            params.extend(normalized_record_types)
        sql += " ORDER BY bm25(operating_fts), o.updated_at DESC LIMIT ?"
        params.append(candidate_limit)
        try:
            rows = self.conn.execute(sql, tuple(params)).fetchall()
        except sqlite3.OperationalError:
            rows = []

        scored = _attach_keyword_scores(_operating_row_to_dict(row) for row in rows)
        filtered: List[Dict[str, Any]] = []
        for row in scored:
            if not _annotate_principal_scope(row, principal_scope_key=requested_scope_key):
                continue
            row["retrieval_source"] = "operating.keyword"
            row["match_mode"] = "keyword"
            filtered.append(row)
        filtered.sort(
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                float(item.get("keyword_score") or 0.0),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return filtered[: max(int(limit or 0), 1)]

    @_locked
    def list_profile_items(
        self,
        *,
        limit: int,
        categories: Iterable[str] | None = None,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        params: list[Any] = []
        fetch_limit = max(limit * 4, 16) if principal_scope_key else limit
        sql = """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
            FROM profile_items
            WHERE active = 1
        """
        if categories:
            cats = list(categories)
            sql += f" AND category IN ({','.join('?' for _ in cats)})"
            params.extend(cats)
        sql += " ORDER BY confidence DESC, updated_at DESC, id DESC LIMIT ?"
        params.append(fetch_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        parsed_by_key: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _profile_row_to_dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            logical_key = str(item.get("stable_key") or "").strip() or str(item.get("storage_key") or "")
            existing = parsed_by_key.get(logical_key)
            if existing is None or _scoped_row_priority(item, principal_scope_key=principal_scope_key) > _scoped_row_priority(
                existing,
                principal_scope_key=principal_scope_key,
            ):
                parsed_by_key[logical_key] = item
        parsed = sorted(
            parsed_by_key.values(),
            key=lambda item: _scoped_row_priority(item, principal_scope_key=principal_scope_key),
            reverse=True,
        )
        return parsed[:limit]

    @_locked
    def list_current_graph_states(
        self,
        *,
        limit: int,
        subjects: Iterable[str] | None = None,
        attributes: Iterable[str] | None = None,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        params: list[Any] = []
        fetch_limit = max(limit * 4, 16) if principal_scope_key else limit
        sql = """
            SELECT
                gs.id AS row_id,
                'state' AS row_type,
                e.canonical_name AS subject,
                gs.attribute AS predicate,
                gs.value_text AS object_value,
                gs.source,
                gs.metadata_json,
                gs.valid_from AS created_at,
                gs.valid_from,
                gs.valid_to,
                gs.is_current
            FROM graph_states gs
            JOIN graph_entities e ON e.id = gs.entity_id
            WHERE gs.is_current = 1
        """
        if subjects:
            normalized_subjects = [" ".join(str(value or "").strip().lower().split()) for value in subjects if str(value or "").strip()]
            if normalized_subjects:
                sql += f" AND lower(e.canonical_name) IN ({','.join('?' for _ in normalized_subjects)})"
                params.extend(normalized_subjects)
        if attributes:
            normalized_attributes = [" ".join(str(value or "").strip().lower().split()) for value in attributes if str(value or "").strip()]
            if normalized_attributes:
                sql += f" AND lower(gs.attribute) IN ({','.join('?' for _ in normalized_attributes)})"
                params.extend(normalized_attributes)
        sql += " ORDER BY gs.valid_from DESC, gs.id DESC LIMIT ?"
        params.append(fetch_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            if not record_is_effective_at(item):
                continue
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            parsed.append(item)
        return parsed[:limit]

    @_locked
    def get_profile_item(self, *, stable_key: str, principal_scope_key: str = "") -> Dict[str, Any] | None:
        if str(stable_key or "").strip() == STYLE_CONTRACT_SLOT:
            return self.get_behavior_contract(
                stable_key=stable_key,
                principal_scope_key=principal_scope_key,
            )
        storage_key = _profile_storage_key(
            stable_key=stable_key,
            principal_scope_key=principal_scope_key,
        )
        row = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE stable_key = ?
            LIMIT 1
            """,
            (storage_key,),
        ).fetchone()
        if row:
            return _profile_row_to_dict(row)
        if not principal_scope_key or not _is_principal_scoped_profile(stable_key=stable_key):
            return None
        like_pattern = f"{str(stable_key or '').strip()}{PROFILE_SCOPE_DELIMITER}%"
        candidate_rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE active = 1 AND stable_key LIKE ?
            ORDER BY confidence DESC, updated_at DESC, id DESC
            LIMIT 16
            """,
            (like_pattern,),
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for candidate_row in candidate_rows:
            item = _profile_row_to_dict(candidate_row)
            if _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: _scoped_row_priority(item, principal_scope_key=principal_scope_key),
            reverse=True,
        )
        return candidates[0]

    @_locked
    def get_behavior_contract(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        principal_scope_key: str = "",
    ) -> Dict[str, Any] | None:
        requested_scope_key = str(principal_scope_key or "").strip()
        row = self._get_active_behavior_contract_row(
            stable_key=stable_key,
            principal_scope_key=requested_scope_key,
        )
        if row:
            return _behavior_contract_row_to_dict(row)
        if not requested_scope_key:
            return None
        candidate_rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE stable_key = ? AND status = ?
            ORDER BY committed_at DESC, revision_number DESC, id DESC
            LIMIT 16
            """,
            (
                str(stable_key or "").strip() or STYLE_CONTRACT_SLOT,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS,
            ),
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for candidate_row in candidate_rows:
            item = _behavior_contract_row_to_dict(candidate_row)
            if _annotate_principal_scope(item, principal_scope_key=requested_scope_key):
                candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: _scoped_row_priority(item, principal_scope_key=requested_scope_key),
            reverse=True,
        )
        return candidates[0]

    @_locked
    def record_profile_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        for row in rows:
            logical_stable_key = str(row.get("stable_key") or "").strip()
            storage_key = str(row.get("storage_key") or "").strip()
            if not storage_key:
                storage_key = _profile_storage_key(
                    stable_key=logical_stable_key,
                    category=str(row.get("category") or ""),
                    principal_scope_key=str(row.get("principal_scope_key") or ""),
                )
            if not storage_key:
                continue
            existing = self.conn.execute(
                "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
                (storage_key,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=bool(row.get("matched")),
                fallback=bool(row.get("fallback")),
                served_at=now,
            )
            self.conn.execute(
                "UPDATE profile_items SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, int(existing["id"])),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated

    @_locked
    def search_profile(
        self,
        *,
        query: str,
        limit: int,
        principal_scope_key: str = "",
        target_slots: Iterable[str] | None = None,
        excluded_slots: Iterable[str] | None = None,
    ) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        rows: List[sqlite3.Row]
        candidate_limit = max(limit * 8, 16)
        targeted: List[Dict[str, Any]] = []
        seen_storage_keys: set[str] = set()
        excluded = {str(slot or "").strip() for slot in (excluded_slots or ()) if str(slot or "").strip()}
        for stable_key in target_slots or ():
            normalized_key = str(stable_key or "").strip()
            if not normalized_key:
                continue
            item = self.get_profile_item(
                stable_key=normalized_key,
                principal_scope_key=principal_scope_key,
            )
            if not item or not bool(item.get("active", True)):
                continue
            storage_key = str(item.get("storage_key") or "")
            if storage_key and storage_key in seen_storage_keys:
                continue
            seen_storage_keys.add(storage_key)
            item["keyword_score"] = 2.0
            item["retrieval_source"] = "profile.slot_target"
            item["match_mode"] = "slot"
            item["_direct_slot_match"] = True
            targeted.append(item)
        if not fts_query:
            rows = self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
                FROM profile_items
                WHERE active = 1
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (candidate_limit,),
            ).fetchall()
        else:
            try:
                rows = self.conn.execute(
                    """
                    SELECT pi.id, pi.stable_key, pi.category, pi.content, pi.source, pi.confidence, pi.metadata_json, pi.updated_at
                    FROM profile_fts fts
                    JOIN profile_items pi ON pi.id = fts.rowid
                    WHERE profile_fts MATCH ? AND pi.active = 1
                    ORDER BY bm25(profile_fts), pi.confidence DESC, pi.updated_at DESC
                    LIMIT ?
                    """,
                    (fts_query, candidate_limit),
                ).fetchall()
            except sqlite3.OperationalError:
                like = f"%{query.strip()}%"
                rows = self.conn.execute(
                    """
                    SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
                    FROM profile_items
                    WHERE active = 1 AND content LIKE ?
                    ORDER BY confidence DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (like, candidate_limit),
                ).fetchall()

        scored: List[Dict[str, Any]] = []
        scored.extend(targeted)
        for row in _attach_keyword_scores(_profile_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            if str(item.get("stable_key") or "").strip() in excluded:
                continue
            storage_key = str(item.get("storage_key") or "")
            if storage_key and storage_key in seen_storage_keys:
                continue
            item["retrieval_source"] = "profile.keyword"
            item["match_mode"] = "keyword"
            item["_direct_slot_match"] = False
            scored.append(item)

        scored.sort(
            key=lambda item: (
                1 if bool(item.get("_direct_slot_match")) else 0,
                float(item.get("keyword_score") or 0.0),
                profile_priority_adjustment(item),
                float(item.get("confidence") or 0.0),
                str(item.get("updated_at") or ""),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def upsert_corpus_document(
        self,
        *,
        stable_key: str,
        title: str,
        doc_kind: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        now = utc_now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        existing = self.conn.execute(
            "SELECT id FROM corpus_documents WHERE stable_key = ?",
            (stable_key,),
        ).fetchone()
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE corpus_documents
                SET title = ?, doc_kind = ?, source = ?, metadata_json = ?, updated_at = ?, active = ?
                WHERE id = ?
                """,
                (title, doc_kind, source, meta_json, now, 1 if active else 0, row_id),
            )
            self.conn.commit()
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO corpus_documents (
                stable_key, title, doc_kind, source, metadata_json, created_at, updated_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (stable_key, title, doc_kind, source, meta_json, now, now, 1 if active else 0),
        )
        self.conn.commit()
        return _cursor_lastrowid(cur)

    @_locked
    def replace_corpus_sections(
        self,
        *,
        document_id: int,
        title: str,
        sections: Iterable[Dict[str, Any]],
    ) -> int:
        existing_rows = self.conn.execute(
            "SELECT id FROM corpus_sections WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        for row in existing_rows:
            self.conn.execute("DELETE FROM corpus_section_fts WHERE rowid = ?", (int(row["id"]),))
        self.conn.execute("DELETE FROM corpus_sections WHERE document_id = ?", (document_id,))

        inserted = 0
        now = utc_now_iso()
        for index, section in enumerate(sections):
            heading = str(section.get("heading", "")).strip() or title
            content = str(section.get("content", "")).strip()
            if not content:
                continue
            token_estimate = int(section.get("token_estimate", max(1, len(content) // 4)))
            metadata_json = json.dumps(section.get("metadata", {}), ensure_ascii=True, sort_keys=True)
            cur = self.conn.execute(
                """
                INSERT INTO corpus_sections (
                    document_id, section_index, heading, content, token_estimate, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, index, heading, content, token_estimate, metadata_json, now),
            )
            row_id = _cursor_lastrowid(cur)
            self.conn.execute(
                """
                INSERT INTO corpus_section_fts(rowid, title, heading, content, document_id, section_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row_id, title, heading, content, document_id, index),
            )
            inserted += 1

        self.conn.commit()
        return inserted

    @_locked
    def ingest_corpus_document(
        self,
        *,
        stable_key: str,
        title: str,
        doc_kind: str,
        source: str,
        sections: Iterable[Dict[str, Any]],
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        document_id = self.upsert_corpus_document(
            stable_key=stable_key,
            title=title,
            doc_kind=doc_kind,
            source=source,
            metadata=metadata,
            active=True,
        )
        section_count = self.replace_corpus_sections(
            document_id=document_id,
            title=title,
            sections=sections,
        )
        if self._corpus_backend is not None:
            self._publish_corpus_document(document_id)
        return {"document_id": document_id, "section_count": section_count, "stable_key": stable_key}

    @_locked
    def search_corpus(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if fts_query:
            try:
                rows = self.conn.execute(
                    """
                    SELECT
                        cd.id AS document_id,
                        cd.title,
                        cd.doc_kind,
                        cd.source,
                        cs.id AS section_id,
                        cs.section_index,
                        cs.heading,
                        cs.content,
                        cs.token_estimate
                    FROM corpus_section_fts fts
                    JOIN corpus_sections cs ON cs.id = fts.rowid
                    JOIN corpus_documents cd ON cd.id = cs.document_id
                    WHERE corpus_section_fts MATCH ? AND cd.active = 1
                    ORDER BY bm25(corpus_section_fts), cs.token_estimate ASC, cs.id DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                output = [dict(row) for row in rows]
                for row in output:
                    row["retrieval_source"] = "corpus.keyword"
                    row["match_mode"] = "keyword"
                return output
            except sqlite3.OperationalError:
                pass

        patterns = build_like_tokens(query)
        if not patterns:
            return []
        title_where = " OR ".join("lower(cd.title) LIKE ?" for _ in patterns)
        heading_where = " OR ".join("lower(cs.heading) LIKE ?" for _ in patterns)
        content_where = " OR ".join("lower(cs.content) LIKE ?" for _ in patterns)
        rows = self.conn.execute(
            f"""
            SELECT
                cd.id AS document_id,
                cd.title,
                cd.doc_kind,
                cd.source,
                cs.id AS section_id,
                cs.section_index,
                cs.heading,
                cs.content,
                cs.token_estimate
            FROM corpus_sections cs
            JOIN corpus_documents cd ON cd.id = cs.document_id
            WHERE cd.active = 1
              AND (
                {title_where} OR
                {heading_where} OR
                {content_where}
              )
            ORDER BY cd.updated_at DESC, cs.section_index ASC
            LIMIT ?
            """,
            tuple(patterns + patterns + patterns + [limit]),
        ).fetchall()
        output = [dict(row) for row in rows]
        for row in output:
            row["retrieval_source"] = "corpus.keyword"
            row["match_mode"] = "keyword"
        return output

    @_locked
    def search_corpus_semantic(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        if self._corpus_backend is None:
            return []
        return self._search_semantic_backend(
            query=query,
            limit=limit,
            where={"semantic_class": "corpus"},
        )

    def _search_semantic_backend(
        self,
        *,
        query: str,
        limit: int,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        if self._corpus_backend is None:
            return []
        try:
            rows = self._corpus_backend.search_semantic(query=query, limit=limit, where=where)
        except Exception as exc:
            self._corpus_backend_error = str(exc)
            logger.warning("Brainstack corpus semantic search failed: %s", exc)
            return []
        self._corpus_backend_error = ""
        return rows

    @_locked
    def search_conversation_semantic(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._search_semantic_backend(
            query=query,
            limit=max(limit * 4, 8),
            where={"semantic_class": "conversation"},
        )
        output: List[Dict[str, Any]] = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            document_meta = dict(metadata.get("document") or {})
            transcript_id = int(document_meta.get("transcript_id") or row.get("section_id") or 0)
            if transcript_id <= 0:
                continue
            created_at = str(document_meta.get("created_at") or "")
            item = {
                "id": transcript_id,
                "session_id": str(document_meta.get("session_id") or ""),
                "turn_number": int(document_meta.get("turn_number") or 0),
                "kind": str(document_meta.get("record_kind") or "turn"),
                "content": str(row.get("content") or ""),
                "source": str(row.get("source") or ""),
                "metadata": {
                    **metadata,
                    "semantic_class": "conversation",
                    "transcript_id": transcript_id,
                },
                "created_at": created_at,
                "same_session": str(document_meta.get("session_id") or "") == session_id,
                "semantic_score": float(row.get("semantic_score") or 0.0),
                "keyword_score": 0.0,
                "retrieval_source": "conversation.semantic",
                "match_mode": "semantic",
            }
            if not _annotate_principal_scope(
                item,
                principal_scope_key=principal_scope_key,
                session_id=session_id,
            ):
                continue
            output.append(item)
        output.sort(
            key=lambda item: (
                float(item.get("semantic_score") or 0.0),
                1 if item["same_session"] else 0,
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return output[:limit]

    @_locked
    def corpus_semantic_channel_status(self) -> Dict[str, str]:
        if self._corpus_backend is None:
            return {
                "status": "degraded",
                "reason": "Semantic retrieval is disabled until a donor-aligned corpus backend is configured.",
            }
        if self._corpus_backend_error:
            return {
                "status": "degraded",
                "reason": f"Semantic retrieval backend is unhealthy: {self._corpus_backend_error}",
            }
        return {
            "status": "active",
            "reason": f"Semantic retrieval is served by {self._corpus_backend.target_name}.",
        }

    @_locked
    def graph_backend_channel_status(self) -> Dict[str, str]:
        if self._graph_backend is None:
            return {
                "status": "degraded",
                "reason": "Graph backend retrieval is disabled until a donor-aligned graph backend is configured.",
            }
        if self._graph_backend_error:
            return {
                "status": "degraded",
                "reason": f"Graph backend retrieval is unhealthy and fell back to SQLite: {self._graph_backend_error}",
            }
        return {
            "status": "active",
            "reason": f"Graph retrieval is served by {self._graph_backend.target_name}.",
        }

    def _normalize_entity_name(self, name: str) -> str:
        return " ".join(name.lower().split())

    @_locked
    def get_or_create_entity(self, name: str) -> Dict[str, Any]:
        now = utc_now_iso()
        normalized = self._normalize_entity_name(name)
        row = self.conn.execute(
            "SELECT id, canonical_name, normalized_name FROM graph_entities WHERE normalized_name = ?",
            (normalized,),
        ).fetchone()
        if row:
            return dict(row)
        cur = self.conn.execute(
            """
            INSERT INTO graph_entities (canonical_name, normalized_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), normalized, now, now),
        )
        self.conn.commit()
        return {
            "id": _cursor_lastrowid(cur),
            "canonical_name": name.strip(),
            "normalized_name": normalized,
        }

    @_locked
    def merge_entity_alias(self, *, alias_name: str, target_name: str) -> Dict[str, Any]:
        alias_normalized = self._normalize_entity_name(alias_name)
        target_normalized = self._normalize_entity_name(target_name)
        if not alias_normalized or not target_normalized or alias_normalized == target_normalized:
            return {"status": "noop"}
        now = utc_now_iso()

        alias = self.conn.execute(
            "SELECT id FROM graph_entities WHERE normalized_name = ?",
            (alias_normalized,),
        ).fetchone()
        if not alias:
            return {"status": "noop"}

        target = self.get_or_create_entity(target_name)
        alias_id = int(alias["id"])
        target_id = int(target["id"])

        self.conn.execute("UPDATE graph_states SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
        self.conn.execute("UPDATE graph_conflicts SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
        self.conn.execute("UPDATE graph_relations SET subject_entity_id = ? WHERE subject_entity_id = ?", (target_id, alias_id))
        self.conn.execute(
            "UPDATE graph_inferred_relations SET subject_entity_id = ? WHERE subject_entity_id = ?",
            (target_id, alias_id),
        )
        self.conn.execute(
            "UPDATE graph_relations SET object_entity_id = ?, object_text = ? WHERE object_entity_id = ?",
            (target_id, target_name.strip(), alias_id),
        )
        self.conn.execute(
            "UPDATE graph_inferred_relations SET object_entity_id = ?, object_text = ? WHERE object_entity_id = ?",
            (target_id, target_name.strip(), alias_id),
        )

        duplicate_groups = self.conn.execute(
            """
            SELECT subject_entity_id, predicate, object_entity_id, COUNT(*) AS relation_count
            FROM graph_relations
            WHERE active = 1
            GROUP BY subject_entity_id, predicate, object_entity_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for group in duplicate_groups:
            rows = self.conn.execute(
                """
                SELECT id
                FROM graph_relations
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                ORDER BY id DESC
                """,
                (int(group["subject_entity_id"]), str(group["predicate"]), int(group["object_entity_id"])),
            ).fetchall()
            for row in rows[1:]:
                self.conn.execute("UPDATE graph_relations SET active = 0 WHERE id = ?", (int(row["id"]),))

        inferred_duplicate_groups = self.conn.execute(
            """
            SELECT subject_entity_id, predicate, object_entity_id, COUNT(*) AS relation_count
            FROM graph_inferred_relations
            WHERE active = 1
            GROUP BY subject_entity_id, predicate, object_entity_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for group in inferred_duplicate_groups:
            rows = self.conn.execute(
                """
                SELECT id
                FROM graph_inferred_relations
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                ORDER BY id DESC
                """,
                (int(group["subject_entity_id"]), str(group["predicate"]), int(group["object_entity_id"])),
            ).fetchall()
            for row in rows[1:]:
                self.conn.execute("UPDATE graph_inferred_relations SET active = 0, updated_at = ? WHERE id = ?", (now, int(row["id"])))

        refs = self.conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM graph_states WHERE entity_id = ?) AS state_refs,
                (SELECT COUNT(*) FROM graph_conflicts WHERE entity_id = ?) AS conflict_refs,
                (SELECT COUNT(*) FROM graph_relations WHERE subject_entity_id = ? OR object_entity_id = ?) AS relation_refs,
                (SELECT COUNT(*) FROM graph_inferred_relations WHERE subject_entity_id = ? OR object_entity_id = ?) AS inferred_relation_refs
            """,
            (alias_id, alias_id, alias_id, alias_id, alias_id, alias_id),
        ).fetchone()
        if (
            refs
            and int(refs["state_refs"]) == 0
            and int(refs["conflict_refs"]) == 0
            and int(refs["relation_refs"]) == 0
            and int(refs["inferred_relation_refs"]) == 0
        ):
            self.conn.execute("DELETE FROM graph_entities WHERE id = ?", (alias_id,))

        self.conn.commit()
        return {"status": "merged", "alias_id": alias_id, "target_id": target_id}

    @_locked
    def _sqlite_add_graph_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        subject = self.get_or_create_entity(subject_name)
        obj = self.get_or_create_entity(object_name)
        existing = self.conn.execute(
            """
            SELECT id, metadata_json FROM graph_relations
            WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
            """,
            (subject["id"], predicate, obj["id"]),
        ).fetchone()
        if existing:
            merged = _merge_record_metadata(existing["metadata_json"], metadata, source=source)
            self.conn.execute(
                "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
            )
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET active = 0, updated_at = ?
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                """,
                (now, subject["id"], predicate, obj["id"]),
            )
            self.conn.commit()
            return int(existing["id"])
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        cur = self.conn.execute(
            """
            INSERT INTO graph_relations (
                subject_entity_id, predicate, object_entity_id, object_text, source, metadata_json, created_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                subject["id"],
                predicate,
                obj["id"],
                object_name.strip(),
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        self.conn.execute(
            """
            UPDATE graph_inferred_relations
            SET active = 0, updated_at = ?
            WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
            """,
            (now, subject["id"], predicate, obj["id"]),
        )
        self.conn.commit()
        return _cursor_lastrowid(cur)

    @_locked
    def _sqlite_upsert_graph_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        now = utc_now_iso()
        subject = self.get_or_create_entity(subject_name)
        obj = self.get_or_create_entity(object_name)
        existing = self.conn.execute(
            """
            SELECT id, metadata_json FROM graph_relations
            WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
            """,
            (subject["id"], predicate, obj["id"]),
        ).fetchone()
        if existing:
            merged = _merge_record_metadata(existing["metadata_json"], metadata, source=source)
            self.conn.execute(
                "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
            )
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET active = 0, updated_at = ?
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                """,
                (now, subject["id"], predicate, obj["id"]),
            )
            self.conn.commit()
            return {"status": "unchanged", "relation_id": int(existing["id"])}
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        cur = self.conn.execute(
            """
            INSERT INTO graph_relations (
                subject_entity_id, predicate, object_entity_id, object_text, source, metadata_json, created_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                subject["id"],
                predicate,
                obj["id"],
                object_name.strip(),
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        self.conn.execute(
            """
            UPDATE graph_inferred_relations
            SET active = 0, updated_at = ?
            WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
            """,
            (now, subject["id"], predicate, obj["id"]),
        )
        self.conn.commit()
        return {"status": "inserted", "relation_id": _cursor_lastrowid(cur)}

    @_locked
    def _sqlite_upsert_graph_inferred_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        now = utc_now_iso()
        subject = self.get_or_create_entity(subject_name)
        obj = self.get_or_create_entity(object_name)
        explicit = self.conn.execute(
            """
            SELECT id FROM graph_relations
            WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
            LIMIT 1
            """,
            (subject["id"], predicate, obj["id"]),
        ).fetchone()
        if explicit:
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET active = 0, updated_at = ?
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                """,
                (now, subject["id"], predicate, obj["id"]),
            )
            self.conn.commit()
            return {"status": "shadowed", "relation_id": int(explicit["id"])}

        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        normalized_metadata.setdefault("source_kind", "inferred")
        normalized_metadata.setdefault("graph_kind", "relation")
        existing = self.conn.execute(
            """
            SELECT id, metadata_json FROM graph_inferred_relations
            WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
            LIMIT 1
            """,
            (subject["id"], predicate, obj["id"]),
        ).fetchone()
        if existing:
            merged = _merge_record_metadata(existing["metadata_json"], normalized_metadata, source=source)
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), now, int(existing["id"])),
            )
            self.conn.commit()
            return {"status": "unchanged", "relation_id": int(existing["id"])}

        cur = self.conn.execute(
            """
            INSERT INTO graph_inferred_relations (
                subject_entity_id, predicate, object_entity_id, object_text,
                source, metadata_json, created_at, updated_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                subject["id"],
                predicate,
                obj["id"],
                object_name.strip(),
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
                now,
            ),
        )
        self.conn.commit()
        return {"status": "inserted", "relation_id": _cursor_lastrowid(cur)}

    @_locked
    def _sqlite_upsert_graph_state(
        self,
        *,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        supersede: bool = False,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        now = utc_now_iso()
        entity = self.get_or_create_entity(subject_name)
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        normalized_metadata.setdefault("source_kind", "explicit")
        normalized_metadata.setdefault("graph_kind", "state")
        temporal = merge_temporal(
            normalized_metadata.get("temporal"),
            {"observed_at": normalized_metadata.get("temporal", {}).get("observed_at") or now},
        )
        if temporal:
            normalized_metadata["temporal"] = temporal
        valid_from = str(normalized_metadata.get("temporal", {}).get("valid_from") or now)
        current = self.conn.execute(
            """
            SELECT id, value_text, source, metadata_json, valid_from, valid_to
            FROM graph_states
            WHERE entity_id = ? AND attribute = ? AND is_current = 1
            ORDER BY valid_from DESC, id DESC
            LIMIT 1
            """,
            (entity["id"], attribute),
        ).fetchone()
        normalized_new = " ".join(value_text.lower().split())

        if current and " ".join(str(current["value_text"]).lower().split()) == normalized_new:
            merged = _merge_record_metadata(current["metadata_json"], normalized_metadata, source=source)
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(current["id"])),
            )
            self.conn.commit()
            return {"status": "unchanged", "entity_id": entity["id"], "state_id": int(current["id"])}

        if current and not supersede and _should_auto_supersede_exact_value(current["value_text"], value_text):
            supersede = True
            normalized_metadata = _merge_record_metadata(
                None,
                {
                    **normalized_metadata,
                    "exact_value_update": True,
                    "status_reason": "numeric_exact_value_change",
                },
                source=source,
            )

        if current and not supersede:
            conflict = self.conn.execute(
                """
                SELECT id, metadata_json FROM graph_conflicts
                WHERE entity_id = ? AND attribute = ? AND current_state_id = ?
                  AND candidate_value_text = ? AND status = 'open'
                """,
                (entity["id"], attribute, int(current["id"]), value_text.strip()),
            ).fetchone()
            if conflict:
                merged = _merge_record_metadata(conflict["metadata_json"], normalized_metadata, source=source)
                self.conn.execute(
                    """
                    UPDATE graph_conflicts
                    SET metadata_json = ?, candidate_source = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(merged, ensure_ascii=True, sort_keys=True),
                        source,
                        now,
                        int(conflict["id"]),
                    ),
                )
                self.conn.commit()
                return {"status": "conflict", "entity_id": entity["id"], "conflict_id": int(conflict["id"])}
            conflict_metadata = _merge_record_metadata(
                None,
                normalized_metadata,
                source=source,
            )
            cur = self.conn.execute(
                """
                INSERT INTO graph_conflicts (
                    entity_id, attribute, current_state_id, candidate_value_text,
                    candidate_source, metadata_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    entity["id"],
                    attribute,
                    int(current["id"]),
                    value_text.strip(),
                    source,
                    json.dumps(conflict_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return {"status": "conflict", "entity_id": entity["id"], "conflict_id": _cursor_lastrowid(cur)}

        if current and supersede:
            prior_temporal = merge_temporal(
                _decode_json_object(current["metadata_json"]).get("temporal"),
                {"valid_to": valid_from},
            )
            prior_provenance = merge_provenance(
                _decode_json_object(current["metadata_json"]).get("provenance"),
                {"source_ids": [source]},
            )
            prior_metadata = _decode_json_object(current["metadata_json"])
            prior_metadata.setdefault("source_kind", "explicit")
            prior_metadata.setdefault("graph_kind", "state")
            if prior_temporal:
                prior_metadata["temporal"] = prior_temporal
            if prior_provenance:
                prior_metadata["provenance"] = prior_provenance
            self.conn.execute(
                """
                UPDATE graph_states
                SET is_current = 0, valid_to = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    valid_from,
                    json.dumps(prior_metadata, ensure_ascii=True, sort_keys=True),
                    int(current["id"]),
                ),
            )

        state_metadata = _merge_record_metadata(None, normalized_metadata, source=source)
        cur = self.conn.execute(
            """
            INSERT INTO graph_states (
                entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 1)
            """,
            (
                entity["id"],
                attribute,
                value_text.strip(),
                source,
                json.dumps(state_metadata, ensure_ascii=True, sort_keys=True),
                valid_from,
            ),
        )
        new_state_id = _cursor_lastrowid(cur)

        if current and supersede:
            updated_prior_metadata = _decode_json_object(current["metadata_json"])
            updated_prior_metadata.setdefault("source_kind", "explicit")
            updated_prior_metadata.setdefault("graph_kind", "state")
            updated_prior_metadata["temporal"] = merge_temporal(
                updated_prior_metadata.get("temporal"),
                {"valid_to": valid_from, "superseded_by": str(new_state_id)},
            )
            updated_prior_metadata["provenance"] = merge_provenance(
                updated_prior_metadata.get("provenance"),
                {"source_ids": [source], "replacement_record_id": str(new_state_id)},
            )
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(updated_prior_metadata, ensure_ascii=True, sort_keys=True),
                    int(current["id"]),
                ),
            )
            new_state_metadata = _merge_record_metadata(
                state_metadata,
                {
                    "temporal": {"supersedes": str(current["id"]), "valid_from": valid_from},
                    "provenance": {"replacement_record_id": str(current["id"])},
                },
                source=source,
            )
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(new_state_metadata, ensure_ascii=True, sort_keys=True),
                    new_state_id,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO graph_supersessions (prior_state_id, new_state_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(current["id"]), new_state_id, "superseded_by_new_current_state", valid_from),
            )
            self.conn.commit()
            return {
                "status": "superseded",
                "entity_id": entity["id"],
                "state_id": new_state_id,
                "prior_state_id": int(current["id"]),
            }

        self.conn.commit()
        return {"status": "inserted", "entity_id": entity["id"], "state_id": new_state_id}

    @_locked
    def _sqlite_list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT gc.id, ge.canonical_name AS entity_name, gc.attribute, gs.value_text AS current_value,
                   gc.candidate_value_text, gc.status, gc.updated_at, gc.metadata_json
            FROM graph_conflicts gc
            JOIN graph_entities ge ON ge.id = gc.entity_id
            JOIN graph_states gs ON gs.id = gc.current_state_id
            WHERE gc.status = 'open'
            ORDER BY gc.updated_at DESC, gc.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def find_continuity_event(
        self,
        *,
        session_id: str,
        kind: str,
        content: str,
    ) -> Dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM continuity_events
            WHERE session_id = ? AND kind = ? AND content = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (session_id, kind, content),
        ).fetchone()
        return _row_to_dict(row) if row else None

    @_locked
    def _sqlite_search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        patterns = build_like_tokens(query)
        if not patterns:
            raw_query = " ".join(str(query or "").split()).strip().lower()
            if not raw_query:
                return []
            patterns = [f"%{raw_query}%"]
        candidate_limit = max(limit * 8, 24)
        state_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gs.value_text) LIKE ? OR lower(gs.attribute) LIKE ?"
            for _ in patterns
        )
        relation_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(COALESCE(go.canonical_name, gr.object_text, '')) LIKE ? OR lower(gr.predicate) LIKE ?"
            for _ in patterns
        )
        conflict_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gc.attribute) LIKE ? OR lower(gc.candidate_value_text) LIKE ?"
            for _ in patterns
        )
        inferred_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(COALESCE(go.canonical_name, gir.object_text, '')) LIKE ? OR lower(gir.predicate) LIKE ?"
            for _ in patterns
        )
        params: List[Any] = []
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        rows = self.conn.execute(
            f"""
            WITH state_hits AS (
                SELECT 'state' AS row_type,
                       gs.id AS row_id,
                       ge.canonical_name AS subject,
                       gs.attribute AS predicate,
                       gs.value_text AS object_value,
                       gs.is_current AS is_current,
                       gs.valid_from AS happened_at,
                       gs.valid_to AS valid_to,
                       gs.source AS source,
                       gs.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
                WHERE {state_where}
            ),
            relation_hits AS (
                SELECT 'relation' AS row_type,
                       gr.id AS row_id,
                       ge.canonical_name AS subject,
                       gr.predicate AS predicate,
                       COALESCE(go.canonical_name, gr.object_text, '') AS object_value,
                       1 AS is_current,
                       gr.created_at AS happened_at,
                       '' AS valid_to,
                       gr.source AS source,
                       gr.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value
                FROM graph_relations gr
                JOIN graph_entities ge ON ge.id = gr.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
                WHERE {relation_where}
            ),
            conflict_hits AS (
                SELECT 'conflict' AS row_type,
                       gc.id AS row_id,
                       ge.canonical_name AS subject,
                       gc.attribute AS predicate,
                       gs.value_text AS object_value,
                       1 AS is_current,
                       gc.updated_at AS happened_at,
                       '' AS valid_to,
                       gs.source AS source,
                       gs.metadata_json AS metadata_json,
                       gc.metadata_json AS conflict_metadata_json,
                       gc.candidate_source AS conflict_source,
                       gc.candidate_value_text AS conflict_value
                FROM graph_conflicts gc
                JOIN graph_entities ge ON ge.id = gc.entity_id
                JOIN graph_states gs ON gs.id = gc.current_state_id
                WHERE gc.status = 'open'
                  AND ({conflict_where})
            ),
            inferred_relation_hits AS (
                SELECT 'inferred_relation' AS row_type,
                       gir.id AS row_id,
                       ge.canonical_name AS subject,
                       gir.predicate AS predicate,
                       COALESCE(go.canonical_name, gir.object_text, '') AS object_value,
                       1 AS is_current,
                       gir.updated_at AS happened_at,
                       '' AS valid_to,
                       gir.source AS source,
                       gir.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value
                FROM graph_inferred_relations gir
                JOIN graph_entities ge ON ge.id = gir.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gir.object_entity_id
                WHERE gir.active = 1
                  AND ({inferred_where})
            )
            SELECT * FROM (
                SELECT * FROM state_hits
                UNION ALL
                SELECT * FROM relation_hits
                UNION ALL
                SELECT * FROM conflict_hits
                UNION ALL
                SELECT * FROM inferred_relation_hits
            )
            ORDER BY happened_at DESC
            LIMIT ?
            """,
            tuple(params + [candidate_limit]),
        ).fetchall()
        parsed = _attach_keyword_scores(_row_to_dict(row) for row in rows)
        parsed = [item for item in parsed if _graph_sort_key(item)[0] > 0]
        parsed.sort(key=_graph_sort_key, reverse=True)
        return parsed[:limit]

    @_locked
    def add_graph_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        relation_id = self._sqlite_add_graph_relation(
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            metadata=metadata,
        )
        if self._graph_backend is not None:
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            self._publish_entity_subgraph(int(subject["id"]))
            self._publish_entity_subgraph(int(obj["id"]))
        return relation_id

    @_locked
    def upsert_graph_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        outcome = self._sqlite_upsert_graph_relation(
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            metadata=metadata,
        )
        if self._graph_backend is not None:
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            self._publish_entity_subgraph(int(subject["id"]))
            self._publish_entity_subgraph(int(obj["id"]))
        return outcome

    @_locked
    def upsert_graph_inferred_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        outcome = self._sqlite_upsert_graph_inferred_relation(
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            metadata=metadata,
        )
        if self._graph_backend is not None:
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            self._publish_entity_subgraph(int(subject["id"]))
            self._publish_entity_subgraph(int(obj["id"]))
        return outcome

    @_locked
    def upsert_graph_state(
        self,
        *,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        supersede: bool = False,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        outcome = self._sqlite_upsert_graph_state(
            subject_name=subject_name,
            attribute=attribute,
            value_text=value_text,
            source=source,
            supersede=supersede,
            metadata=metadata,
        )
        if self._graph_backend is not None and int(outcome.get("entity_id") or 0) > 0:
            self._publish_entity_subgraph(int(outcome["entity_id"]))
        return outcome

    @_locked
    def upsert_typed_entity(
        self,
        *,
        entity_name: str,
        entity_type: str,
        subject_name: str,
        attributes: Mapping[str, Any],
        source: str,
        metadata: Dict[str, Any] | None = None,
        confidence: float = 0.78,
        supersede_existing: bool = False,
    ) -> List[Dict[str, Any]]:
        normalized_entity_name = " ".join(str(entity_name or "").strip().split())
        normalized_entity_type = " ".join(str(entity_type or "").strip().lower().split())
        normalized_subject_name = " ".join(str(subject_name or "").strip().split()) or "User"
        if not normalized_entity_name or not normalized_entity_type:
            return []

        base_metadata = dict(metadata or {})
        base_metadata.setdefault("confidence", float(confidence))
        actions: List[Dict[str, Any]] = []
        state_candidates: List[tuple[str, str]] = [
            ("entity_type", normalized_entity_type),
            ("owner_subject", normalized_subject_name),
        ]
        for attribute, value in dict(attributes or {}).items():
            normalized_attribute = " ".join(str(attribute or "").strip().lower().split())
            normalized_value = " ".join(str(value or "").strip().split())
            if not normalized_attribute or not normalized_value:
                continue
            state_candidates.append((normalized_attribute, normalized_value))

        for attribute, value_text in state_candidates:
            outcome = self.upsert_graph_state(
                subject_name=normalized_entity_name,
                attribute=attribute,
                value_text=value_text,
                source=source,
                supersede=supersede_existing,
                metadata=base_metadata,
            )
            actions.append(
                {
                    "kind": "typed_entity",
                    "entity_name": normalized_entity_name,
                    "entity_type": normalized_entity_type,
                    "attribute": attribute,
                    "action": "NONE" if str(outcome.get("status", "")).lower() in {"unchanged", "shadowed"} else "ADD",
                    **outcome,
                }
            )
        return actions

    @_locked
    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        if self._graph_backend is None:
            return self._sqlite_list_graph_conflicts(limit=limit)
        try:
            rows = self._graph_backend.list_graph_conflicts(limit=limit)
        except Exception as exc:
            self._graph_backend_error = str(exc)
            logger.warning("Brainstack graph conflict lookup failed; falling back to SQLite: %s", exc)
            return self._sqlite_list_graph_conflicts(limit=limit)
        self._graph_backend_error = ""
        return rows

    @_locked
    def search_graph(self, *, query: str, limit: int, principal_scope_key: str = "") -> List[Dict[str, Any]]:
        if self._graph_backend is None:
            rows = self._sqlite_search_graph(query=query, limit=limit)
        else:
            try:
                rows = self._graph_backend.search_graph(query=query, limit=max(limit * 8, 24))
            except Exception as exc:
                self._graph_backend_error = str(exc)
                logger.warning("Brainstack graph search failed; falling back to SQLite: %s", exc)
                rows = self._sqlite_search_graph(query=query, limit=limit)
            else:
                self._graph_backend_error = ""
        keyword_rows = _attach_keyword_scores(rows)
        scored: List[Dict[str, Any]] = []
        for row in keyword_rows:
            item = dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            item.setdefault("retrieval_source", "graph.keyword")
            item.setdefault("match_mode", "keyword")
            if _graph_sort_key(item)[0] <= 0:
                continue
            scored.append(item)
        scored.sort(key=_graph_sort_key, reverse=True)
        return scored[:limit]

    @_locked
    def query_native_typed_metric_sum(
        self,
        *,
        owner_subject: str | None,
        entity_type: str | None,
        entity_type_contains: Iterable[str] | None = None,
        entity_type_excludes: Iterable[str] | None = None,
        metric_attribute: str,
        limit: int = 16,
    ) -> Dict[str, Any] | None:
        if self._graph_backend is None:
            return None
        query_method = getattr(self._graph_backend, "query_typed_metric_sum", None)
        if not callable(query_method):
            return None
        try:
            result = query_method(
                owner_subject=owner_subject,
                entity_type=entity_type,
                entity_type_contains=list(entity_type_contains or []),
                entity_type_excludes=list(entity_type_excludes or []),
                metric_attribute=metric_attribute,
                limit=max(1, int(limit)),
            )
        except Exception as exc:
            self._graph_backend_error = str(exc)
            logger.warning("Brainstack native typed metric query failed: %s", exc)
            return None
        self._graph_backend_error = ""
        return dict(result) if isinstance(result, dict) else None

    @_locked
    def record_graph_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        table_by_type = {
            "state": "graph_states",
            "relation": "graph_relations",
            "conflict": "graph_conflicts",
            "inferred_relation": "graph_inferred_relations",
        }
        for row in rows:
            row_type = str(row.get("row_type") or "").strip()
            row_id = int(row.get("row_id") or 0)
            table = table_by_type.get(row_type)
            if not table or row_id <= 0:
                continue
            existing = self.conn.execute(
                f"SELECT metadata_json FROM {table} WHERE id = ?",
                (row_id,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=True,
                fallback=False,
                served_at=now,
            )
            self.conn.execute(
                f"UPDATE {table} SET metadata_json = ?{', updated_at = ?' if table == 'graph_conflicts' else ''} WHERE id = ?",
                ((json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, row_id) if table == "graph_conflicts" else (json.dumps(metadata, ensure_ascii=True, sort_keys=True), row_id)),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated

    @_locked
    def record_corpus_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        for row in rows:
            section_id = int(row.get("section_id") or 0)
            if section_id <= 0:
                continue
            existing = self.conn.execute(
                "SELECT metadata_json FROM corpus_sections WHERE id = ?",
                (section_id,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=True,
                fallback=False,
                served_at=now,
            )
            self.conn.execute(
                "UPDATE corpus_sections SET metadata_json = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), section_id),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated
