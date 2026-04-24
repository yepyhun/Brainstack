"""SQLite row codecs for BrainstackStore.

These helpers convert storage rows into Brainstack dictionaries. They do not
open databases, mutate state, rank retrieval results, or make authority
decisions.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Mapping

from .operating_truth import normalize_operating_record_metadata


def decode_json_object(value: Any) -> Dict[str, Any]:
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


def decode_json_array(value: Any) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    text = str(value or "").strip()
    if not text:
        return []
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def corpus_search_row_to_dict(row: sqlite3.Row | Mapping[str, Any]) -> Dict[str, Any]:
    item = dict(row)
    document_metadata = decode_json_object(item.pop("document_metadata_json", {}))
    section_metadata = decode_json_object(item.pop("section_metadata_json", {}))
    ingest_metadata = document_metadata.get("corpus_ingest") if isinstance(document_metadata, Mapping) else {}
    if not isinstance(ingest_metadata, Mapping):
        ingest_metadata = {}
    stable_key = str(item.get("stable_key") or "").strip()
    section_index = int(item.get("section_index") or 0)
    citation_id = str(section_metadata.get("citation_id") or "").strip() or f"{stable_key or item.get('document_id')}#s{section_index}"
    item["metadata"] = section_metadata
    item["document_metadata"] = document_metadata
    item["stable_key"] = stable_key
    item["citation_id"] = citation_id
    item["document_hash"] = str(ingest_metadata.get("document_hash") or section_metadata.get("document_hash") or "")
    item["section_hash"] = str(section_metadata.get("section_hash") or "")
    item["corpus_fingerprint"] = str(ingest_metadata.get("fingerprint") or section_metadata.get("corpus_fingerprint") or "")
    item["source_adapter"] = str(ingest_metadata.get("source_adapter") or section_metadata.get("source_adapter") or "")
    item["source_id"] = str(ingest_metadata.get("source_id") or section_metadata.get("source_id") or "")
    return item


def task_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
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
        "metadata": decode_json_object(row["metadata_json"]),
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }


def operating_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    record_type = str(row["record_type"] or "")
    stable_key = str(row["stable_key"] or "")
    source = str(row["source"] or "")
    metadata = normalize_operating_record_metadata(
        record_type=record_type,
        stable_key=stable_key,
        source=source,
        metadata=decode_json_object(row["metadata_json"]),
    )
    return {
        "id": int(row["id"]),
        "stable_key": stable_key,
        "principal_scope_key": str(row["principal_scope_key"] or ""),
        "record_type": record_type,
        "content": str(row["content"] or ""),
        "owner": str(row["owner"] or ""),
        "source": source,
        "source_session_id": str(row["source_session_id"] or ""),
        "source_turn_number": int(row["source_turn_number"] or 0),
        "metadata": metadata,
        "created_at": str(row["created_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
    }
