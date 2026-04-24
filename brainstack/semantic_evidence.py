from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping


SEMANTIC_EVIDENCE_SCHEMA_VERSION = "semantic_evidence_document.v1"
SEMANTIC_EVIDENCE_NORMALIZER_VERSION = "local_terms.v1"
SEMANTIC_EVIDENCE_SCORER_VERSION = "weighted_overlap.v2"
SEMANTIC_EVIDENCE_INDEX_VERSION = "semantic_evidence_index.v1"

TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)


def semantic_evidence_fingerprint() -> str:
    payload = {
        "schema": SEMANTIC_EVIDENCE_SCHEMA_VERSION,
        "normalizer": SEMANTIC_EVIDENCE_NORMALIZER_VERSION,
        "scorer": SEMANTIC_EVIDENCE_SCORER_VERSION,
        "index": SEMANTIC_EVIDENCE_INDEX_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def decode_semantic_metadata(metadata: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(metadata, Mapping):
        return []
    raw = metadata.get("semantic_terms")
    if raw is None:
        raw = metadata.get("semantic_text")
    values: list[str] = []
    if isinstance(raw, str):
        values.append(raw)
    elif isinstance(raw, (list, tuple, set)):
        for item in raw:
            if isinstance(item, (str, int, float)):
                values.append(str(item))
    return values


def normalize_semantic_terms(*values: Any) -> list[str]:
    terms: set[str] = set()
    for value in values:
        text = str(value or "").casefold()
        for token in TOKEN_RE.findall(text):
            normalized = token.strip("-_")
            if len(normalized) >= 2:
                terms.add(normalized)
            for part in re.split(r"[-_]", normalized):
                if len(part) >= 2:
                    terms.add(part)
    return sorted(terms)


def _term_matches(query_term: str, document_term: str) -> bool:
    if query_term == document_term:
        return True
    if min(len(query_term), len(document_term)) < 4:
        return False
    return query_term in document_term or document_term in query_term


def semantic_similarity(query_terms: Iterable[str], document_terms: Iterable[str]) -> float:
    query_set = {str(term or "").strip() for term in query_terms if str(term or "").strip()}
    document_set = {str(term or "").strip() for term in document_terms if str(term or "").strip()}
    if not query_set or not document_set:
        return 0.0
    overlap = {
        query_term
        for query_term in query_set
        if any(_term_matches(query_term, document_term) for document_term in document_set)
    }
    if not overlap:
        return 0.0
    recall = len(overlap) / len(query_set)
    precision = len(overlap) / len(document_set)
    return round((0.72 * recall) + (0.28 * precision), 6)
