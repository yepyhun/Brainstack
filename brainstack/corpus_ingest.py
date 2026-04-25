from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from .corpus_taxonomy import build_corpus_taxonomy_metadata, public_source_uri


CORPUS_INGEST_SCHEMA_VERSION = "brainstack.corpus_ingest.v1"
CORPUS_SOURCE_ADAPTER_CONTRACT_VERSION = "corpus_source_adapter.v1"
CORPUS_NORMALIZER_VERSION = "plain_text_normalizer.v1"
CORPUS_SECTIONER_VERSION = "bounded_sectioner.v1"
CORPUS_EMBEDDER_VERSION = "semantic_evidence_terms.v1"
DEFAULT_SECTION_CHAR_LIMIT = 900


def _normalize_text(value: Any) -> str:
    return "\n".join(" ".join(line.strip().split()) for line in str(value or "").splitlines()).strip()


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _section_content_blocks(content: str, *, section_char_limit: int) -> list[str]:
    normalized = _normalize_text(content)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in normalized.split("\n") if part.strip()]
    sections: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if not current:
            current = paragraph
            continue
        if len(current) + 2 + len(paragraph) <= section_char_limit:
            current = f"{current}\n\n{paragraph}"
            continue
        sections.append(current)
        current = paragraph
    if current:
        sections.append(current)
    return sections


def normalize_corpus_source(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("corpus source payload must be a mapping")
    source_adapter = _normalize_text(payload.get("source_adapter") or payload.get("adapter") or "manual")
    explicit_stable_key = _normalize_text(payload.get("stable_key"))
    source_id = _normalize_text(payload.get("source_id") or explicit_stable_key)
    if not source_id:
        raise ValueError("corpus source requires source_id or stable_key")
    stable_key = explicit_stable_key or f"{source_adapter}:{source_id}"
    title = _normalize_text(payload.get("title") or stable_key)
    doc_kind = _normalize_text(payload.get("doc_kind") or "document")
    raw_source_uri = _normalize_text(payload.get("source_uri") or payload.get("source") or source_adapter)
    source_uri = public_source_uri(raw_source_uri, source_adapter=source_adapter, source_id=source_id)
    if not title:
        raise ValueError("corpus source requires stable_key/source_id and title")

    metadata = dict(payload.get("metadata") or {})
    taxonomy = build_corpus_taxonomy_metadata(
        source_adapter=source_adapter,
        source_id=source_id,
        stable_key=stable_key,
        title=title,
        doc_kind=doc_kind,
        source_uri=raw_source_uri,
    )
    metadata["corpus_taxonomy"] = taxonomy
    section_char_limit = max(240, int(payload.get("section_char_limit") or DEFAULT_SECTION_CHAR_LIMIT))
    raw_sections = payload.get("sections")
    normalized_sections: list[dict[str, Any]] = []
    if isinstance(raw_sections, Iterable) and not isinstance(raw_sections, (str, bytes, Mapping)):
        for index, raw_section in enumerate(raw_sections):
            if not isinstance(raw_section, Mapping):
                continue
            content = _normalize_text(raw_section.get("content"))
            if not content:
                continue
            heading = _normalize_text(raw_section.get("heading") or f"Section {index + 1}")
            section_metadata = dict(raw_section.get("metadata") or {})
            normalized_sections.append(
                {
                    "heading": heading,
                    "content": content,
                    "metadata": section_metadata,
                }
            )
    else:
        content = _normalize_text(payload.get("content"))
        for index, section_content in enumerate(_section_content_blocks(content, section_char_limit=section_char_limit)):
            normalized_sections.append(
                {
                    "heading": f"Section {index + 1}",
                    "content": section_content,
                    "metadata": {},
                }
            )
    if not normalized_sections:
        raise ValueError("corpus source produced no non-empty sections")

    section_payloads: list[dict[str, Any]] = []
    for index, section in enumerate(normalized_sections):
        section_hash = _stable_hash(
            {
                "heading": section["heading"],
                "content": section["content"],
                "section_index": index,
                "normalizer": CORPUS_NORMALIZER_VERSION,
                "sectioner": CORPUS_SECTIONER_VERSION,
            }
        )
        citation_id = f"{stable_key}#s{index}"
        section_metadata = {
            **dict(section.get("metadata") or {}),
            "corpus_ingest_schema": CORPUS_INGEST_SCHEMA_VERSION,
            "source_adapter": source_adapter,
            "source_id": source_id,
            "section_hash": section_hash,
            "citation_id": citation_id,
            "corpus_taxonomy": taxonomy,
        }
        if metadata.get("principal_scope_key"):
            section_metadata.setdefault("principal_scope_key", metadata.get("principal_scope_key"))
        section_payloads.append(
            {
                "heading": section["heading"],
                "content": section["content"],
                "token_estimate": max(1, len(section["content"]) // 4),
                "metadata": section_metadata,
            }
        )

    document_hash = _stable_hash(
        {
            "stable_key": stable_key,
            "title": title,
            "doc_kind": doc_kind,
            "source_adapter": source_adapter,
            "source_id": source_id,
            "sections": [
                {
                    "heading": section["heading"],
                    "section_hash": section["metadata"]["section_hash"],
                }
                for section in section_payloads
            ],
        }
    )
    fingerprint = _stable_hash(
        {
            "schema": CORPUS_INGEST_SCHEMA_VERSION,
            "adapter_contract": CORPUS_SOURCE_ADAPTER_CONTRACT_VERSION,
            "normalizer": CORPUS_NORMALIZER_VERSION,
            "sectioner": CORPUS_SECTIONER_VERSION,
            "embedder": CORPUS_EMBEDDER_VERSION,
            "source_adapter": source_adapter,
            "document_hash": document_hash,
        }
    )
    document_metadata = {
        **metadata,
        "corpus_ingest": {
            "schema": CORPUS_INGEST_SCHEMA_VERSION,
            "source_adapter_contract": CORPUS_SOURCE_ADAPTER_CONTRACT_VERSION,
            "normalizer": CORPUS_NORMALIZER_VERSION,
            "sectioner": CORPUS_SECTIONER_VERSION,
            "embedder": CORPUS_EMBEDDER_VERSION,
            "source_adapter": source_adapter,
            "source_id": source_id,
            "source_uri": source_uri,
            "document_hash": document_hash,
            "fingerprint": fingerprint,
            "section_count": len(section_payloads),
        },
    }
    for section in section_payloads:
        section["metadata"]["document_hash"] = document_hash
        section["metadata"]["corpus_fingerprint"] = fingerprint

    return {
        "stable_key": stable_key,
        "title": title,
        "doc_kind": doc_kind,
        "source": source_uri,
        "metadata": document_metadata,
        "sections": section_payloads,
        "document_hash": document_hash,
        "fingerprint": fingerprint,
        "source_adapter": source_adapter,
        "source_id": source_id,
        "citation_ids": [section["metadata"]["citation_id"] for section in section_payloads],
    }


def corpus_ingest_versions() -> dict[str, str]:
    return {
        "schema": CORPUS_INGEST_SCHEMA_VERSION,
        "adapter_contract": CORPUS_SOURCE_ADAPTER_CONTRACT_VERSION,
        "normalizer": CORPUS_NORMALIZER_VERSION,
        "sectioner": CORPUS_SECTIONER_VERSION,
        "embedder": CORPUS_EMBEDDER_VERSION,
    }
