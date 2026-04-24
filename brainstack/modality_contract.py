from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MODALITY_EVIDENCE_SCHEMA_VERSION = "brainstack.modality_evidence.v1"
SUPPORTED_MODALITIES = {"image", "file", "audio", "extracted_document"}
RAW_PAYLOAD_FIELDS = {"raw_bytes", "raw_binary", "base64", "content_base64", "blob"}


def modality_evidence_contract() -> dict[str, Any]:
    return {
        "schema": MODALITY_EVIDENCE_SCHEMA_VERSION,
        "supported_modalities": sorted(SUPPORTED_MODALITIES),
        "required_fields": ["schema", "modality", "source_ref", "content_hash"],
        "optional_fields": ["mime_type", "extractor", "extracted_text_ref", "derived_text", "metadata"],
        "raw_payload_fields_disallowed": sorted(RAW_PAYLOAD_FIELDS),
        "storage_rule": "Store references, hashes, and extracted evidence metadata; do not store raw binary payloads in memory recall records.",
        "execution_rule": "This contract validates evidence shape only and does not perform extraction, scheduling, or tool execution.",
    }


def validate_modality_evidence_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return _reject("payload_not_mapping")
    schema = str(payload.get("schema") or payload.get("schema_version") or "").strip()
    if schema != MODALITY_EVIDENCE_SCHEMA_VERSION:
        return _reject("schema_mismatch")
    modality = str(payload.get("modality") or "").strip()
    if modality not in SUPPORTED_MODALITIES:
        return _reject("unsupported_modality")
    present_raw_fields = sorted(field for field in RAW_PAYLOAD_FIELDS if field in payload and payload.get(field) not in {None, ""})
    if present_raw_fields:
        return _reject("raw_payload_not_allowed", raw_fields=present_raw_fields)
    source_ref = str(payload.get("source_ref") or "").strip()
    content_hash = str(payload.get("content_hash") or "").strip()
    if not source_ref:
        return _reject("source_ref_required")
    if not content_hash:
        return _reject("content_hash_required")
    return {
        "schema": "brainstack.modality_evidence_validation.v1",
        "status": "accepted",
        "reason": "typed modality evidence reference is valid",
        "modality": modality,
        "source_ref": source_ref,
        "content_hash": content_hash,
        "read_only": True,
    }


def _reject(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": "brainstack.modality_evidence_validation.v1",
        "status": "rejected",
        "reason": reason,
        "read_only": True,
        **extra,
    }
