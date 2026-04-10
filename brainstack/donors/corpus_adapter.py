from __future__ import annotations

from typing import Any, Dict

from ..corpus import build_document_stable_key, split_corpus_sections


def prepare_corpus_payload(
    *,
    title: str,
    content: str,
    source: str,
    doc_kind: str,
    metadata: Dict[str, Any] | None,
    section_max_chars: int,
) -> Dict[str, Any]:
    stable_key = build_document_stable_key(
        title=title,
        source=source,
        doc_kind=doc_kind,
        metadata=metadata,
    )
    sections = split_corpus_sections(
        title=title,
        content=content,
        max_chars=section_max_chars,
    )
    return {
        "stable_key": stable_key,
        "sections": sections,
    }
