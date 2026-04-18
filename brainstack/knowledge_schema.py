"""Offline long-form knowledge pilot DTOs.

This schema is intentionally separate from the live chat-time memory kernel.
It describes a bounded, evidence-backed offline processing shape only.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


OFFLINE_KNOWLEDGE_SCHEMA_VERSION = 1
OFFLINE_DOCUMENT_PIPELINE_VERSION = "offline_document_pilot_v1"


@dataclass(frozen=True)
class OfflineSourceDocument:
    document_id: str
    title: str
    document_kind: str
    content_hash: str
    section_count: int
    chunk_count: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfflineDocumentSection:
    section_id: str
    document_id: str
    heading: str
    order: int
    start_offset: int
    end_offset: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfflineDocumentChunk:
    chunk_id: str
    document_id: str
    section_id: str
    order: int
    start_offset: int
    end_offset: int
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSpan:
    evidence_id: str
    document_id: str
    chunk_id: str
    start_offset: int
    end_offset: int
    excerpt: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClaimCandidate:
    subject: str
    predicate: str
    object_value: str
    evidence_snippet: str
    claim_type: str = "relation"
    claim_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfflineClaim:
    claim_id: str
    document_id: str
    claim_type: str
    subject: str
    predicate: str
    object_value: str
    evidence_id: str
    chunk_id: str
    status: str = "supported"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ConflictCandidate:
    conflict_id: str
    document_id: str
    subject: str
    predicate: str
    claim_ids: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfflineKnowledgePilot:
    schema_version: int
    pipeline_version: str
    document: OfflineSourceDocument
    sections: List[OfflineDocumentSection]
    chunks: List[OfflineDocumentChunk]
    evidence_spans: List[EvidenceSpan]
    claims: List[OfflineClaim]
    conflict_candidates: List[ConflictCandidate]
    offline_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "pipeline_version": self.pipeline_version,
            "offline_only": self.offline_only,
            "document": self.document.to_dict(),
            "sections": [item.to_dict() for item in self.sections],
            "chunks": [item.to_dict() for item in self.chunks],
            "evidence_spans": [item.to_dict() for item in self.evidence_spans],
            "claims": [item.to_dict() for item in self.claims],
            "conflict_candidates": [item.to_dict() for item in self.conflict_candidates],
        }
