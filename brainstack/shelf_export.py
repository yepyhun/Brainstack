from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from .db import BrainstackStore
from .db_ops import migration_dry_run_report


EXPORT_SCHEMA = "brainstack.shelf_export_bundle.v1"
IMPORT_DRY_RUN_SCHEMA = "brainstack.shelf_import_dry_run.v1"
REDACTION_SCHEMA = "brainstack.shelf_export_redaction.v1"

DEFAULT_SHELVES = ("profile", "continuity", "operating", "task", "graph", "corpus")

SECRET_KEY_MARKERS = (
    "api_key",
    "apikey",
    "auth",
    "bearer",
    "cookie",
    "credential",
    "login",
    "password",
    "secret",
    "session_token",
    "token",
)

SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("secret_like_openai_key", re.compile(r"sk-[A-Za-z0-9_-]{12,}")),
    ("secret_like_assignment", re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+")),
)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def _brainstack_version() -> str:
    plugin_yaml = Path(__file__).resolve().parent / "plugin.yaml"
    try:
        text = plugin_yaml.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    match = re.search(r"(?m)^version:\s*(\S+)\s*$", text)
    return match.group(1) if match else "unknown"


def _payload_checksum(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8", "surrogatepass")).hexdigest()


def _is_private_path(value: str) -> bool:
    text = value.strip()
    lowered = text.casefold()
    return (
        text.startswith("/")
        or text.startswith("~/")
        or lowered.startswith("file:")
        or bool(re.match(r"^[a-z]:[\\/]", text, flags=re.IGNORECASE))
    )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _json_or_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _record_redaction(report: dict[str, Any], *, reason_code: str) -> None:
    counts = report.setdefault("reason_counts", {})
    counts[reason_code] = int(counts.get(reason_code) or 0) + 1


def redact_export_value(value: Any, *, key_path: str, report: dict[str, Any]) -> Any:
    lowered_key = key_path.casefold()
    if any(marker in lowered_key for marker in SECRET_KEY_MARKERS):
        _record_redaction(report, reason_code="secret_key_redacted")
        return "<redacted:secret_key>"
    if isinstance(value, Mapping):
        return {str(key): redact_export_value(item, key_path=f"{key_path}.{key}", report=report) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_export_value(item, key_path=f"{key_path}[]", report=report) for item in value]
    if isinstance(value, str):
        for reason_code, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                _record_redaction(report, reason_code=reason_code)
                return f"<redacted:{reason_code}>"
        if _is_private_path(value):
            _record_redaction(report, reason_code="private_path_redacted")
            return f"private:path:{_hash_text(value)}"
    return value


def _redact_rows(rows: Iterable[Mapping[str, Any]], *, shelf: str, report: dict[str, Any]) -> list[dict[str, Any]]:
    redacted: list[dict[str, Any]] = []
    for row in rows:
        normalized = {key: _json_or_text(value) for key, value in row.items()}
        redacted.append(
            {
                str(key): redact_export_value(value, key_path=f"{shelf}.{key}", report=report)
                for key, value in normalized.items()
            }
        )
    return redacted


def _fetch_rows(store: BrainstackStore, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for row in store.conn.execute(query, params).fetchall()]


def _export_profile(store: BrainstackStore, principal_scope_key: str) -> list[dict[str, Any]]:
    rows = _fetch_rows(
        store,
        """
        SELECT stable_key, category, content, source, confidence, active, metadata_json, first_seen_at, updated_at
        FROM profile_items
        ORDER BY stable_key
        """,
    )
    if not principal_scope_key:
        return rows
    return [row for row in rows if principal_scope_key in str(row.get("metadata_json") or "")]


def _export_continuity(store: BrainstackStore, principal_scope_key: str) -> list[dict[str, Any]]:
    rows = _fetch_rows(
        store,
        """
        SELECT session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
        FROM continuity_events
        ORDER BY id
        """,
    )
    if not principal_scope_key:
        return rows
    return [row for row in rows if principal_scope_key in str(row.get("metadata_json") or "")]


def _export_operating(store: BrainstackStore, principal_scope_key: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        store,
        """
        SELECT stable_key, principal_scope_key, record_type, content, owner, source,
               source_session_id, source_turn_number, metadata_json, created_at, updated_at
        FROM operating_records
        WHERE (? = '' OR principal_scope_key = ?)
        ORDER BY stable_key
        """,
        (principal_scope_key, principal_scope_key),
    )


def _export_task(store: BrainstackStore, principal_scope_key: str) -> list[dict[str, Any]]:
    return _fetch_rows(
        store,
        """
        SELECT stable_key, principal_scope_key, item_type, title, due_date, date_scope, optional,
               status, owner, source, source_session_id, source_turn_number, metadata_json, created_at, updated_at
        FROM task_items
        WHERE (? = '' OR principal_scope_key = ?)
        ORDER BY stable_key
        """,
        (principal_scope_key, principal_scope_key),
    )


def _export_graph(store: BrainstackStore, principal_scope_key: str) -> dict[str, list[dict[str, Any]]]:
    del principal_scope_key
    return {
        "entities": _fetch_rows(
            store,
            "SELECT id, canonical_name, normalized_name, created_at, updated_at FROM graph_entities ORDER BY id",
        ),
        "relations": _fetch_rows(
            store,
            """
            SELECT id, subject_entity_id, predicate, object_entity_id, object_text, source, metadata_json, created_at, active
            FROM graph_relations
            ORDER BY id
            """,
        ),
        "states": _fetch_rows(
            store,
            """
            SELECT id, entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current
            FROM graph_states
            ORDER BY id
            """,
        ),
        "conflicts": _fetch_rows(
            store,
            """
            SELECT id, entity_id, attribute, current_state_id, candidate_value_text, candidate_source,
                   metadata_json, status, created_at, updated_at
            FROM graph_conflicts
            ORDER BY id
            """,
        ),
    }


def _export_corpus(store: BrainstackStore, principal_scope_key: str) -> dict[str, list[dict[str, Any]]]:
    del principal_scope_key
    return {
        "documents": _fetch_rows(
            store,
            """
            SELECT id, stable_key, title, doc_kind, source, metadata_json, created_at, updated_at, active
            FROM corpus_documents
            ORDER BY stable_key
            """,
        ),
        "sections": _fetch_rows(
            store,
            """
            SELECT document_id, section_index, heading, content, token_estimate, metadata_json, created_at
            FROM corpus_sections
            ORDER BY document_id, section_index
            """,
        ),
    }


def _shelf_rows(store: BrainstackStore, shelf: str, *, principal_scope_key: str) -> Any:
    if shelf == "profile":
        return _export_profile(store, principal_scope_key)
    if shelf == "continuity":
        return _export_continuity(store, principal_scope_key)
    if shelf == "operating":
        return _export_operating(store, principal_scope_key)
    if shelf == "task":
        return _export_task(store, principal_scope_key)
    if shelf == "graph":
        return _export_graph(store, principal_scope_key)
    if shelf == "corpus":
        return _export_corpus(store, principal_scope_key)
    raise ValueError(f"unsupported shelf for export: {shelf}")


def _count_payload(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, Mapping):
        return sum(len(value) for value in payload.values() if isinstance(value, list))
    return 0


def export_shelf_bundle(
    store: BrainstackStore,
    *,
    shelves: Iterable[str] = DEFAULT_SHELVES,
    principal_scope_key: str = "",
) -> dict[str, Any]:
    db_path = Path(str(getattr(store, "_db_path", "")))
    redaction_report: dict[str, Any] = {"schema": REDACTION_SCHEMA, "reason_counts": {}}
    shelf_payload: dict[str, Any] = {}
    receipts: list[dict[str, Any]] = []
    checksums: dict[str, str] = {}
    shelf_list = tuple(dict.fromkeys(str(shelf).strip() for shelf in shelves if str(shelf).strip()))
    for shelf in shelf_list:
        raw_payload = _shelf_rows(store, shelf, principal_scope_key=principal_scope_key)
        redacted_payload: Any
        if isinstance(raw_payload, Mapping):
            redacted_payload = {
                key: _redact_rows(value, shelf=f"{shelf}.{key}", report=redaction_report)
                for key, value in raw_payload.items()
                if isinstance(value, list)
            }
        else:
            redacted_payload = _redact_rows(raw_payload, shelf=shelf, report=redaction_report)
        shelf_payload[shelf] = redacted_payload
        checksums[shelf] = _payload_checksum(redacted_payload)
        receipts.append({"shelf": shelf, "row_count": _count_payload(redacted_payload)})

    migration = migration_dry_run_report(db_path) if db_path.exists() else {}
    migration_redacted = redact_export_value(migration, key_path="migration_ledger", report=redaction_report)
    source_store_redacted = redact_export_value(str(db_path), key_path="source_store.path", report=redaction_report)
    return {
        "schema": EXPORT_SCHEMA,
        "manifest": {
            "schema": "brainstack.shelf_export_manifest.v1",
            "exported_at": datetime.now(UTC).isoformat(),
            "brainstack_version": _brainstack_version(),
            "source_store": {"path": source_store_redacted},
            "shelves": list(shelf_list),
            "principal_scope_key": principal_scope_key,
            "row_counts": {receipt["shelf"]: receipt["row_count"] for receipt in receipts},
            "checksums": checksums,
            "migration_ledger": migration_redacted,
            "redaction_report": redaction_report,
            "write_import_supported": False,
            "write_import_blocker": "write_import_deferred_until_shelf_roundtrip_proof",
        },
        "receipts": receipts,
        "shelves": shelf_payload,
    }


def write_shelf_export_bundle(bundle: Mapping[str, Any], output_path: str | Path) -> dict[str, Any]:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "schema": "brainstack.shelf_export_receipt.v1",
        "status": "completed",
        "bundle_path": str(path),
        "bytes": path.stat().st_size,
        "mutates_store": False,
    }


def load_shelf_export_bundle(path: str | Path) -> dict[str, Any]:
    try:
        bundle = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"invalid shelf export bundle: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("schema") != EXPORT_SCHEMA:
        raise ValueError("unsupported shelf export bundle schema")
    manifest = bundle.get("manifest")
    shelves = bundle.get("shelves")
    if not isinstance(manifest, Mapping) or not isinstance(shelves, Mapping):
        raise ValueError("corrupt shelf export bundle")
    return bundle


def _target_counts(target_path: Path) -> dict[str, int]:
    if not target_path.exists():
        return {}
    uri = f"file:{target_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        counts: dict[str, int] = {}
        for shelf, table in {
            "profile": "profile_items",
            "continuity": "continuity_events",
            "operating": "operating_records",
            "task": "task_items",
            "graph": "graph_states",
            "corpus": "corpus_documents",
        }.items():
            try:
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            except sqlite3.Error:
                counts[shelf] = -1
                continue
            counts[shelf] = int(row["count"] if row else 0)
        return counts
    finally:
        conn.close()


def dry_run_import_shelf_bundle(bundle: Mapping[str, Any], *, target_path: str | Path) -> dict[str, Any]:
    if not target_path:
        raise ValueError("shelf import dry-run requires explicit target_path")
    if bundle.get("schema") != EXPORT_SCHEMA:
        raise ValueError("unsupported shelf export bundle schema")
    manifest = bundle.get("manifest")
    if not isinstance(manifest, Mapping):
        raise ValueError("corrupt shelf export bundle: missing manifest")
    shelves = bundle.get("shelves")
    if not isinstance(shelves, Mapping):
        raise ValueError("corrupt shelf export bundle: missing shelves")

    target = Path(target_path)
    exported_counts = {
        str(shelf): _count_payload(payload)
        for shelf, payload in shelves.items()
    }
    existing_counts = _target_counts(target)
    duplicate_shelves = sorted(
        shelf
        for shelf, count in existing_counts.items()
        if count > 0 and int(exported_counts.get(shelf) or 0) > 0
    )
    return {
        "schema": IMPORT_DRY_RUN_SCHEMA,
        "status": "blocked_write_import",
        "mutates": False,
        "target_path": str(target),
        "write_import_supported": False,
        "blocker": str(manifest.get("write_import_blocker") or "write_import_deferred_until_shelf_roundtrip_proof"),
        "exported_counts": exported_counts,
        "existing_counts": existing_counts,
        "duplicate_shelves": duplicate_shelves,
        "migration_ledger_status": str(
            (manifest.get("migration_ledger") or {}).get("status")
            if isinstance(manifest.get("migration_ledger"), Mapping)
            else ""
        ),
    }
