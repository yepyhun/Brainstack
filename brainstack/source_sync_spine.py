from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .db_row_codecs import decode_json_array, decode_json_object
from .file_corpus_source import FileCorpusSourceConfig, collect_file_corpus_sources
from .source_integrity import build_source_integrity_envelope, public_source_integrity_status


SOURCE_SYNC_SCHEMA = "brainstack.source_sync_spine.v1"
SOURCE_SYNC_RUN_SCHEMA = "brainstack.source_sync_run.v1"
SOURCE_SYNC_STATUS_SCHEMA = "brainstack.source_sync_status.v1"
SOURCE_SYNC_CONNECTOR_LOCAL_FOLDER = "local_folder"
DELETION_RETAIN_MISSING = "retain_missing"
DELETION_DEACTIVATE_MISSING = "deactivate_missing"
SUPPORTED_DELETION_POLICIES = {DELETION_RETAIN_MISSING, DELETION_DEACTIVATE_MISSING}


@dataclass(frozen=True)
class SourceSyncConfig:
    source_root: Path
    allow_patterns: tuple[str, ...]
    source_set_id: str = ""
    source_adapter: str = "source_sync_local"
    principal_scope_key: str = ""
    mode: str = "manual"
    deletion_policy: str = DELETION_RETAIN_MISSING
    max_file_bytes: int = 128_000
    max_sections: int = 24
    section_char_limit: int = 900


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _compact_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _safe_source_set_id(config: SourceSyncConfig, *, root: Path) -> str:
    explicit = _compact_text(config.source_set_id)
    if explicit:
        lowered = explicit.casefold()
        if "/" in explicit or "\\" in explicit or explicit.startswith("~") or lowered.startswith("file:"):
            return f"{_compact_text(config.source_adapter) or 'source_sync'}:private:{_hash_payload(explicit)[:20]}"
        return explicit
    digest = _hash_payload(
        {
            "schema": SOURCE_SYNC_SCHEMA,
            "root": str(root),
            "allow_patterns": list(config.allow_patterns),
            "principal_scope_key": config.principal_scope_key,
            "source_adapter": config.source_adapter,
        }
    )[:20]
    return f"{_compact_text(config.source_adapter) or 'source_sync'}:private:{digest}"


def _source_handle(*, source_set_id: str, relative_path: str, content_hash: str) -> str:
    digest = _hash_payload(
        {
            "source_set_id": source_set_id,
            "relative_path": relative_path,
        }
    )[:20]
    return f"source:{digest}"


def _public_skip(item: Mapping[str, Any]) -> dict[str, Any]:
    raw_path = _compact_text(item.get("path"))
    payload: dict[str, Any] = {
        "reason": _compact_text(item.get("reason")) or "skipped",
        "path_hash": _hash_payload(raw_path)[:16] if raw_path else "",
    }
    for key in ("byte_count", "skipped_section_count"):
        if key in item:
            try:
                payload[key] = int(item[key])
            except (TypeError, ValueError):
                pass
    return payload


def _safe_title(source: Mapping[str, Any], *, source_handle: str) -> str:
    title = _compact_text(source.get("title"))
    if title and "/" not in title and "\\" not in title and len(title) <= 96:
        return title
    return f"Source document {source_handle.removeprefix('source:')[:8]}"


def _source_file_metadata(source: Mapping[str, Any]) -> dict[str, Any]:
    metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
    file_meta = metadata.get("file_corpus_source") if isinstance(metadata.get("file_corpus_source"), Mapping) else {}
    return dict(file_meta)


def _sanitize_section_metadata(section: Mapping[str, Any], *, source_sync: Mapping[str, Any]) -> dict[str, Any]:
    metadata = dict(section.get("metadata") if isinstance(section.get("metadata"), Mapping) else {})
    file_meta = metadata.get("file_corpus_source") if isinstance(metadata.get("file_corpus_source"), Mapping) else {}
    clean_file_meta = {
        "schema": _compact_text(file_meta.get("schema")),
        "relative_path_hash": source_sync["relative_path_hash"],
        "content_hash": _compact_text(file_meta.get("content_hash")),
        "section_index": int(file_meta.get("section_index") or 0),
    }
    metadata["file_corpus_source"] = clean_file_meta
    metadata["source_sync_spine"] = dict(source_sync)
    return metadata


def _prepare_source_payloads(config: SourceSyncConfig, *, root: Path, source_set_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    collected = collect_file_corpus_sources(
        FileCorpusSourceConfig(
            source_root=root,
            allow_patterns=config.allow_patterns,
            source_adapter=config.source_adapter,
            doc_kind="source_sync_document",
            principal_scope_key=config.principal_scope_key,
            max_file_bytes=config.max_file_bytes,
            max_sections=config.max_sections,
            section_char_limit=config.section_char_limit,
        )
    )
    prepared: list[dict[str, Any]] = []
    for source in collected["sources"]:
        file_meta = _source_file_metadata(source)
        relative_path = _compact_text(file_meta.get("relative_path"))
        content_hash = _compact_text(file_meta.get("content_hash"))
        handle = _source_handle(source_set_id=source_set_id, relative_path=relative_path, content_hash=content_hash)
        relative_path_hash = _hash_payload(relative_path)[:16] if relative_path else ""
        source_sync = {
            "schema": SOURCE_SYNC_SCHEMA,
            "connector": SOURCE_SYNC_CONNECTOR_LOCAL_FOLDER,
            "source_set_id": source_set_id,
            "source_handle": handle,
            "relative_path_hash": relative_path_hash,
            "content_hash": content_hash,
            "bounded_expand": {
                "available": True,
                "modes": ["corpus_section_by_citation"],
                "max_tokens": 800,
            },
        }
        source_integrity = build_source_integrity_envelope(
            source_handle=handle,
            source_adapter=config.source_adapter,
            source_scope=config.principal_scope_key,
            content_hash=content_hash,
            truth_eligible=False,
        )
        source_sync["source_integrity"] = public_source_integrity_status(source_integrity)
        sections = []
        for section in source.get("sections") or []:
            if not isinstance(section, Mapping):
                continue
            sections.append(
                {
                    "heading": _compact_text(section.get("heading")) or "Section",
                    "content": str(section.get("content") or ""),
                    "metadata": _sanitize_section_metadata(section, source_sync=source_sync),
                }
            )
        prepared.append(
            {
                "source_adapter": config.source_adapter,
                "source_id": handle,
                "stable_key": f"{config.source_adapter}:{handle}",
                "title": _safe_title(source, source_handle=handle),
                "doc_kind": "source_sync_document",
                "source_uri": str(root / relative_path) if relative_path else str(root),
                "sections": sections,
                "metadata": {
                    "principal_scope_key": config.principal_scope_key,
                    "authority_class": "corpus_supporting",
                    "canonical": False,
                    "source_sync_spine": source_sync,
                },
            }
        )
    return prepared, [_public_skip(item) for item in collected["skipped"]]


def _ensure_source_sync_schema(store: Any) -> None:
    store.conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL UNIQUE,
            source_set_id TEXT NOT NULL,
            connector TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'manual',
            deletion_policy TEXT NOT NULL DEFAULT 'retain_missing',
            status TEXT NOT NULL,
            cursor TEXT NOT NULL DEFAULT '',
            fingerprint TEXT NOT NULL DEFAULT '',
            counts_json TEXT NOT NULL DEFAULT '{}',
            issue_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """
    )
    store.conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_source_sync_runs_source_created
        ON source_sync_runs(source_set_id, created_at DESC)
        """
    )
    store.conn.commit()


def _source_sync_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    payload = metadata.get("source_sync_spine")
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def _active_synced_documents(store: Any, *, source_set_id: str, principal_scope_key: str = "") -> dict[str, dict[str, Any]]:
    rows = store.conn.execute(
        """
        SELECT stable_key, metadata_json
        FROM corpus_documents
        WHERE active = 1
        ORDER BY stable_key ASC
        """
    ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    requested_scope = _compact_text(principal_scope_key)
    for row in rows:
        metadata = decode_json_object(row["metadata_json"])
        sync_meta = _source_sync_metadata(metadata)
        if _compact_text(sync_meta.get("source_set_id")) != source_set_id:
            continue
        scope = _compact_text(metadata.get("principal_scope_key"))
        if requested_scope and scope not in {"", requested_scope}:
            continue
        output[str(row["stable_key"] or "")] = {"metadata": metadata, "source_sync_spine": sync_meta}
    return output


def _cursor_for_sources(source_set_id: str, sources: list[Mapping[str, Any]]) -> str:
    source_entries = []
    for source in sources:
        sync_meta = _source_sync_metadata(source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {})
        source_entries.append(
            {
                "stable_key": _compact_text(source.get("stable_key")),
                "source_handle": _compact_text(sync_meta.get("source_handle")),
                "content_hash": _compact_text(sync_meta.get("content_hash")),
            }
        )
    return _hash_payload({"source_set_id": source_set_id, "sources": sorted(source_entries, key=lambda item: item["stable_key"])})


def _record_run(
    store: Any,
    *,
    source_set_id: str,
    connector: str,
    mode: str,
    deletion_policy: str,
    status: str,
    cursor: str,
    fingerprint: str,
    counts: Mapping[str, int],
    issues: list[Mapping[str, Any]],
    metadata: Mapping[str, Any],
) -> str:
    _ensure_source_sync_schema(store)
    created_at = _utc_now_iso()
    run_id = f"source_sync:{_hash_payload({'source_set_id': source_set_id, 'cursor': cursor, 'created_at': created_at})[:24]}"
    store.conn.execute(
        """
        INSERT INTO source_sync_runs (
            run_id, source_set_id, connector, mode, deletion_policy, status, cursor, fingerprint,
            counts_json, issue_json, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source_set_id,
            connector,
            mode,
            deletion_policy,
            status,
            cursor,
            fingerprint,
            json.dumps(dict(counts), ensure_ascii=True, sort_keys=True),
            json.dumps([dict(issue) for issue in issues], ensure_ascii=True, sort_keys=True),
            json.dumps(dict(metadata), ensure_ascii=True, sort_keys=True),
            created_at,
        ),
    )
    store.conn.commit()
    return run_id


def run_source_sync(store: Any, config: SourceSyncConfig) -> dict[str, Any]:
    root = config.source_root.expanduser().resolve()
    deletion_policy = _compact_text(config.deletion_policy) or DELETION_RETAIN_MISSING
    if deletion_policy not in SUPPORTED_DELETION_POLICIES:
        raise ValueError(f"unsupported source sync deletion policy: {deletion_policy}")
    source_set_id = _safe_source_set_id(config, root=root)
    sources, skipped = _prepare_source_payloads(config, root=root, source_set_id=source_set_id)
    cursor = _cursor_for_sources(source_set_id, sources)
    fingerprint = _hash_payload(
        {
            "schema": SOURCE_SYNC_RUN_SCHEMA,
            "source_set_id": source_set_id,
            "cursor": cursor,
            "deletion_policy": deletion_policy,
            "connector": SOURCE_SYNC_CONNECTOR_LOCAL_FOLDER,
        }
    )
    existing = _active_synced_documents(
        store,
        source_set_id=source_set_id,
        principal_scope_key=config.principal_scope_key,
    )
    present_keys = {_compact_text(source.get("stable_key")) for source in sources}
    missing_keys = sorted(key for key in existing if key and key not in present_keys)
    receipts: list[dict[str, Any]] = []
    counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "deactivated": 0,
        "retained_missing": 0,
        "skipped": len(skipped),
        "failed": 0,
        "source_count": len(sources),
        "missing_count": len(missing_keys),
    }
    issues: list[dict[str, Any]] = []

    for source in sources:
        receipt = dict(store.ingest_corpus_source(source))
        receipts.append(receipt)
        status = _compact_text(receipt.get("status")) or "unknown"
        if status in counts:
            counts[status] += 1
        elif status == "inserted":
            counts["inserted"] += 1
        elif status == "updated":
            counts["updated"] += 1
        elif status == "unchanged":
            counts["unchanged"] += 1
        else:
            counts["failed"] += 1
            issues.append({"reason_code": "SOURCE_SYNC_INGEST_UNEXPECTED_STATUS", "status": status})

    deletion_receipts: list[dict[str, Any]] = []
    if missing_keys and deletion_policy == DELETION_DEACTIVATE_MISSING:
        for stable_key in missing_keys:
            receipt = dict(store.deactivate_corpus_source(stable_key=stable_key))
            deletion_receipts.append(
                {
                    "status": _compact_text(receipt.get("status")),
                    "stable_key_hash": _hash_payload(stable_key)[:16],
                    "semantic_backend_status": _compact_text(receipt.get("semantic_backend_status")),
                }
            )
            if receipt.get("status") in {"deactivated", "unchanged"}:
                counts["deactivated"] += 1 if receipt.get("status") == "deactivated" else 0
            else:
                counts["failed"] += 1
                issues.append({"reason_code": "SOURCE_SYNC_DELETE_FAILED", "stable_key_hash": _hash_payload(stable_key)[:16]})
    elif missing_keys:
        counts["retained_missing"] = len(missing_keys)
        issues.append({"reason_code": "SOURCE_SYNC_MISSING_RETAINED", "missing_count": len(missing_keys)})

    changed_count = counts["inserted"] + counts["updated"] + counts["deactivated"]
    if counts["failed"]:
        status = "degraded"
    elif changed_count:
        status = "changed"
    elif counts["source_count"] == 0 and not counts["retained_missing"]:
        status = "no_input"
    else:
        status = "unchanged"

    public_receipts = [
        {
            "status": _compact_text(receipt.get("status")),
            "stable_key_hash": _hash_payload(receipt.get("stable_key"))[:16],
            "section_count": int(receipt.get("section_count") or 0),
            "citation_count": len(receipt.get("citation_ids") or []),
        }
        for receipt in receipts
    ]
    run_id = _record_run(
        store,
        source_set_id=source_set_id,
        connector=SOURCE_SYNC_CONNECTOR_LOCAL_FOLDER,
        mode=_compact_text(config.mode) or "manual",
        deletion_policy=deletion_policy,
        status=status,
        cursor=cursor,
        fingerprint=fingerprint,
        counts=counts,
        issues=issues,
        metadata={
            "schema": SOURCE_SYNC_RUN_SCHEMA,
            "public_safe": True,
            "raw_private_source_in_status": False,
            "principal_scope_key": _compact_text(config.principal_scope_key),
            "allow_pattern_count": len(config.allow_patterns),
        },
    )
    return {
        "schema": SOURCE_SYNC_RUN_SCHEMA,
        "status": status,
        "run_id": run_id,
        "source_set_id": source_set_id,
        "connector": SOURCE_SYNC_CONNECTOR_LOCAL_FOLDER,
        "mode": _compact_text(config.mode) or "manual",
        "deletion_policy": deletion_policy,
        "cursor": cursor,
        "fingerprint": fingerprint,
        "counts": counts,
        "issues": issues,
        "skipped": skipped[:20],
        "receipts": public_receipts[:20],
        "deletion_receipts": deletion_receipts[:20],
        "public_safe": True,
        "raw_private_source_in_status": False,
        "truth_authority": "admission_receipts_only",
        "connector_writes_durable_truth": False,
    }


def build_source_sync_status(
    store: Any,
    *,
    source_set_id: str = "",
    principal_scope_key: str = "",
) -> dict[str, Any]:
    _ensure_source_sync_schema(store)
    requested_source = _compact_text(source_set_id)
    requested_scope = _compact_text(principal_scope_key)
    params: tuple[Any, ...]
    where = ""
    if requested_source:
        where = "WHERE source_set_id = ?"
        params = (requested_source,)
    else:
        params = ()
    candidate_limit = 50 if requested_scope else 5
    candidate_rows = store.conn.execute(
        f"""
        SELECT run_id, source_set_id, connector, mode, deletion_policy, status, cursor, fingerprint,
               counts_json, issue_json, metadata_json, created_at
        FROM source_sync_runs
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, candidate_limit),
    ).fetchall()
    rows = []
    for row in candidate_rows:
        if requested_scope:
            metadata = decode_json_object(row["metadata_json"])
            if _compact_text(metadata.get("principal_scope_key")) != requested_scope:
                continue
        rows.append(row)
        if len(rows) >= 5:
            break
    latest = rows[0] if rows else None
    if latest is not None:
        active_docs = _active_synced_documents(
            store,
            source_set_id=str(latest["source_set_id"] or ""),
            principal_scope_key=principal_scope_key,
        )
    else:
        active_docs = {}
    latest_counts = decode_json_object(latest["counts_json"]) if latest is not None else {}
    latest_issues = decode_json_array(latest["issue_json"]) if latest is not None else []
    if latest is None:
        status = "idle"
        reason_code = "SOURCE_SYNC_NO_RUNS"
        reason = "No source sync runs are recorded."
    elif str(latest["status"] or "") == "degraded":
        status = "degraded"
        reason_code = "SOURCE_SYNC_LATEST_RUN_DEGRADED"
        reason = "The latest source sync run had failed items."
    else:
        status = "active"
        reason_code = "SOURCE_SYNC_LATEST_RUN_AVAILABLE"
        reason = "The latest source sync run is available and public-safe."
    return {
        "schema": SOURCE_SYNC_STATUS_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "reason": reason,
        "run_count": len(rows),
        "latest_run": {
            "run_id": str(latest["run_id"] or "") if latest is not None else "",
            "source_set_id": str(latest["source_set_id"] or "") if latest is not None else requested_source,
            "connector": str(latest["connector"] or "") if latest is not None else "",
            "mode": str(latest["mode"] or "") if latest is not None else "",
            "deletion_policy": str(latest["deletion_policy"] or "") if latest is not None else "",
            "status": str(latest["status"] or "") if latest is not None else "",
            "cursor": str(latest["cursor"] or "") if latest is not None else "",
            "fingerprint": str(latest["fingerprint"] or "") if latest is not None else "",
            "counts": latest_counts,
            "issue_count": len(latest_issues),
            "created_at": str(latest["created_at"] or "") if latest is not None else "",
        },
        "active_document_count": len(active_docs),
        "public_safe": True,
        "raw_private_source_in_status": False,
        "truth_authority": "admission_receipts_only",
        "bounded_expand_handles": True,
    }
