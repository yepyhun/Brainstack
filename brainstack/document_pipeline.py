"""Offline long-form document pipeline pilot.

This module stays off the live chat graph/corpus write path. It only builds a
deterministic, evidence-backed offline pilot shape for later integration work.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, List, Sequence

from .knowledge_schema import (
    ClaimCandidate,
    ConflictCandidate,
    EvidenceSpan,
    OFFLINE_DOCUMENT_PIPELINE_VERSION,
    OFFLINE_KNOWLEDGE_SCHEMA_VERSION,
    OfflineClaim,
    OfflineDocumentChunk,
    OfflineDocumentSection,
    OfflineKnowledgePilot,
    OfflineSourceDocument,
)


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _slug(value: str) -> str:
    output = "".join(char.lower() if char.isalnum() else "-" for char in str(value or ""))
    while "--" in output:
        output = output.replace("--", "-")
    return output.strip("-") or "document"


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _trim_span(content: str, start_offset: int, end_offset: int) -> tuple[int, int, str]:
    start = max(0, int(start_offset))
    end = max(start, int(end_offset))
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end, content[start:end]


def _normalized_text_with_map(text: str) -> tuple[str, List[int]]:
    normalized_chars: List[str] = []
    index_map: List[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            if not normalized_chars or normalized_chars[-1] == " ":
                continue
            normalized_chars.append(" ")
            index_map.append(index)
            continue
        normalized_chars.append(char)
        index_map.append(index)
    if normalized_chars and normalized_chars[-1] == " ":
        normalized_chars.pop()
        index_map.pop()
    return "".join(normalized_chars), index_map


def _split_sections(document_id: str, content: str) -> List[OfflineDocumentSection]:
    lines = content.splitlines(keepends=True)
    sections: List[OfflineDocumentSection] = []
    current_heading = "Document"
    current_start = 0
    current_has_heading = False
    offset = 0

    def flush(end_offset: int) -> None:
        nonlocal current_heading, current_start, current_has_heading
        start, end, text = _trim_span(content, current_start, end_offset)
        if not text:
            return
        sections.append(
            OfflineDocumentSection(
                section_id=f"{document_id}:section:{len(sections) + 1}",
                document_id=document_id,
                heading=current_heading,
                order=len(sections) + 1,
                start_offset=start,
                end_offset=end,
                text=text,
            )
        )

    for line in lines:
        stripped = line.strip()
        is_heading = stripped.startswith("#") and stripped.lstrip("#").strip() != ""
        if is_heading:
            if current_has_heading or offset > current_start:
                flush(offset)
            current_heading = stripped.lstrip("#").strip()
            current_start = offset + len(line)
            current_has_heading = True
        offset += len(line)

    flush(len(content))
    if sections:
        return sections
    start, end, text = _trim_span(content, 0, len(content))
    if not text:
        return []
    return [
        OfflineDocumentSection(
            section_id=f"{document_id}:section:1",
            document_id=document_id,
            heading="Document",
            order=1,
            start_offset=start,
            end_offset=end,
            text=text,
        )
    ]


def _split_chunk_ranges(text: str, *, max_chars: int) -> List[tuple[int, int]]:
    paragraph_ranges: List[tuple[int, int]] = []
    start = 0
    length = len(text)
    while start < length:
        while start < length and text[start].isspace():
            start += 1
        if start >= length:
            break
        end = text.find("\n\n", start)
        if end == -1:
            end = length
        paragraph_ranges.append((start, end))
        start = end + 2

    if not paragraph_ranges:
        return []

    chunk_ranges: List[tuple[int, int]] = []
    current_start, current_end = paragraph_ranges[0]
    for para_start, para_end in paragraph_ranges[1:]:
        candidate_len = para_end - current_start
        if candidate_len <= max_chars:
            current_end = para_end
            continue
        chunk_ranges.append((current_start, current_end))
        current_start, current_end = para_start, para_end
    chunk_ranges.append((current_start, current_end))

    output: List[tuple[int, int]] = []
    for chunk_start, chunk_end in chunk_ranges:
        if chunk_end - chunk_start <= max_chars:
            output.append((chunk_start, chunk_end))
            continue
        split_start = chunk_start
        while split_start < chunk_end:
            split_end = min(chunk_end, split_start + max_chars)
            if split_end < chunk_end:
                sentence_break = text.rfind(". ", split_start, split_end)
                if sentence_break > split_start + 80:
                    split_end = sentence_break + 1
            output.append((split_start, split_end))
            split_start = split_end
    return output


def _build_chunks(document_id: str, sections: Sequence[OfflineDocumentSection], *, max_chunk_chars: int) -> List[OfflineDocumentChunk]:
    chunks: List[OfflineDocumentChunk] = []
    for section in sections:
        for start, end in _split_chunk_ranges(section.text, max_chars=max_chunk_chars):
            local_start, local_end, text = _trim_span(section.text, start, end)
            if not text:
                continue
            chunk_start = section.start_offset + local_start
            chunk_end = section.start_offset + local_end
            chunks.append(
                OfflineDocumentChunk(
                    chunk_id=f"{document_id}:chunk:{len(chunks) + 1}",
                    document_id=document_id,
                    section_id=section.section_id,
                    order=len(chunks) + 1,
                    start_offset=chunk_start,
                    end_offset=chunk_end,
                    text=text,
                )
            )
    return chunks


def _locate_evidence_span(content: str, evidence_snippet: str) -> tuple[int, int]:
    snippet = str(evidence_snippet or "")
    if not snippet.strip():
        raise ValueError("Claim candidate evidence_snippet must be non-empty.")
    direct_start = content.find(snippet)
    if direct_start != -1:
        return direct_start, direct_start + len(snippet)

    normalized_content, content_map = _normalized_text_with_map(content)
    normalized_snippet, _ = _normalized_text_with_map(snippet)
    normalized_start = normalized_content.find(normalized_snippet)
    if normalized_start == -1:
        raise ValueError(f"Could not locate evidence snippet in document: {snippet!r}")
    normalized_end = normalized_start + len(normalized_snippet)
    start_offset = content_map[normalized_start]
    end_offset = content_map[normalized_end - 1] + 1
    return start_offset, end_offset


def _find_chunk_for_span(chunks: Sequence[OfflineDocumentChunk], *, start_offset: int, end_offset: int) -> OfflineDocumentChunk:
    for chunk in chunks:
        if chunk.start_offset <= start_offset and end_offset <= chunk.end_offset:
            return chunk
    raise ValueError(f"Evidence span {start_offset}:{end_offset} is not contained in any chunk.")


def _normalize_claim_candidates(claim_candidates: Iterable[ClaimCandidate | dict]) -> List[ClaimCandidate]:
    normalized: List[ClaimCandidate] = []
    for index, raw in enumerate(claim_candidates, start=1):
        if isinstance(raw, ClaimCandidate):
            candidate = raw
        else:
            candidate = ClaimCandidate(
                claim_id=str(raw.get("claim_id") or "").strip(),
                claim_type=str(raw.get("claim_type") or "relation").strip() or "relation",
                subject=str(raw.get("subject") or "").strip(),
                predicate=str(raw.get("predicate") or "").strip(),
                object_value=str(raw.get("object_value") or "").strip(),
                evidence_snippet=str(raw.get("evidence_snippet") or "").strip(),
            )
        if not candidate.subject or not candidate.predicate or not candidate.object_value:
            raise ValueError(f"Claim candidate {index} is missing subject/predicate/object_value.")
        if not candidate.evidence_snippet:
            raise ValueError(f"Claim candidate {index} is missing evidence_snippet.")
        normalized.append(candidate)
    return normalized


def build_offline_document_pilot(
    *,
    title: str,
    content: str,
    claim_candidates: Iterable[ClaimCandidate | dict],
    document_kind: str = "text/markdown",
    max_chunk_chars: int = 480,
) -> OfflineKnowledgePilot:
    normalized_title = _normalize_text(title) or "Untitled document"
    normalized_content = str(content or "")
    if not normalized_content.strip():
        raise ValueError("Offline document pilot content must be non-empty.")

    document_hash = _hash_text(normalized_title + "\n" + normalized_content)
    document_id = f"doc:{_slug(normalized_title)}:{document_hash[:12]}"
    sections = _split_sections(document_id, normalized_content)
    if not sections:
        raise ValueError("Offline document pilot could not derive any sections.")
    chunks = _build_chunks(document_id, sections, max_chunk_chars=max_chunk_chars)
    if not chunks:
        raise ValueError("Offline document pilot could not derive any chunks.")

    normalized_claims = _normalize_claim_candidates(claim_candidates)
    evidence_spans: List[EvidenceSpan] = []
    claims: List[OfflineClaim] = []
    for index, candidate in enumerate(normalized_claims, start=1):
        start_offset, end_offset = _locate_evidence_span(normalized_content, candidate.evidence_snippet)
        chunk = _find_chunk_for_span(chunks, start_offset=start_offset, end_offset=end_offset)
        evidence = EvidenceSpan(
            evidence_id=f"{document_id}:evidence:{len(evidence_spans) + 1}",
            document_id=document_id,
            chunk_id=chunk.chunk_id,
            start_offset=start_offset,
            end_offset=end_offset,
            excerpt=normalized_content[start_offset:end_offset],
        )
        evidence_spans.append(evidence)
        claims.append(
            OfflineClaim(
                claim_id=candidate.claim_id or f"{document_id}:claim:{index}",
                document_id=document_id,
                claim_type=candidate.claim_type,
                subject=candidate.subject,
                predicate=candidate.predicate,
                object_value=candidate.object_value,
                evidence_id=evidence.evidence_id,
                chunk_id=chunk.chunk_id,
            )
        )

    conflict_candidates: List[ConflictCandidate] = []
    grouped: dict[tuple[str, str], List[OfflineClaim]] = {}
    for claim in claims:
        grouped.setdefault((claim.subject, claim.predicate), []).append(claim)
    for (subject, predicate), grouped_claims in grouped.items():
        object_values = {claim.object_value for claim in grouped_claims}
        if len(object_values) <= 1:
            continue
        conflict_candidates.append(
            ConflictCandidate(
                conflict_id=f"{document_id}:conflict:{len(conflict_candidates) + 1}",
                document_id=document_id,
                subject=subject,
                predicate=predicate,
                claim_ids=[claim.claim_id for claim in grouped_claims],
                reason="Multiple evidence-backed claims disagree on object_value for the same subject/predicate pair.",
            )
        )

    document = OfflineSourceDocument(
        document_id=document_id,
        title=normalized_title,
        document_kind=str(document_kind or "text/markdown"),
        content_hash=_hash_text(normalized_content),
        section_count=len(sections),
        chunk_count=len(chunks),
    )
    return OfflineKnowledgePilot(
        schema_version=OFFLINE_KNOWLEDGE_SCHEMA_VERSION,
        pipeline_version=OFFLINE_DOCUMENT_PIPELINE_VERSION,
        document=document,
        sections=sections,
        chunks=chunks,
        evidence_spans=evidence_spans,
        claims=claims,
        conflict_candidates=conflict_candidates,
    )
