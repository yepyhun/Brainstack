from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List


def build_document_stable_key(
    *,
    title: str,
    source: str,
    doc_kind: str,
    metadata: Dict[str, Any] | None = None,
) -> str:
    meta_part = ""
    if metadata:
        meta_part = "|".join(
            f"{key}={metadata[key]}"
            for key in sorted(metadata)
            if metadata[key] is not None
        )
    seed = f"{doc_kind}:{title.strip().lower()}:{source.strip().lower()}:{meta_part}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"corpus:{digest[:20]}"


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _estimate_tokens(text: str) -> int:
    return max(1, int(math.ceil(len(text) / 4)))


def _split_long_text(text: str, *, max_chars: int) -> List[str]:
    words = text.split()
    if not words:
        return []
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for word in words:
        addition = len(word) + (1 if current else 0)
        if current and current_len + addition > max_chars:
            chunks.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += addition
    if current:
        chunks.append(" ".join(current))
    return chunks


def split_corpus_sections(*, title: str, content: str, max_chars: int = 900) -> List[Dict[str, Any]]:
    max_chars = max(240, int(max_chars))
    heading = title.strip() or "Document"
    blocks: List[Dict[str, str]] = []
    paragraph_lines: List[str] = []

    def flush_paragraph(active_heading: str) -> None:
        paragraph = _normalize_text(" ".join(paragraph_lines))
        paragraph_lines.clear()
        if paragraph:
            blocks.append({"heading": active_heading, "content": paragraph})

    for raw_line in str(content).splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph(heading)
            continue
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", raw_line)
        if heading_match:
            flush_paragraph(heading)
            heading = _normalize_text(heading_match.group(1)) or heading
            continue
        paragraph_lines.append(line)
    flush_paragraph(heading)

    if not blocks:
        normalized = _normalize_text(str(content))
        if normalized:
            blocks = [{"heading": heading, "content": normalized}]

    sections: List[Dict[str, Any]] = []
    pending_heading = ""
    pending_parts: List[str] = []
    pending_len = 0

    def flush_section() -> None:
        nonlocal pending_heading, pending_parts, pending_len
        body = _normalize_text(" ".join(pending_parts))
        if body:
            sections.append(
                {
                    "heading": pending_heading or title.strip() or "Document",
                    "content": body,
                    "token_estimate": _estimate_tokens(body),
                }
            )
        pending_heading = ""
        pending_parts = []
        pending_len = 0

    for block in blocks:
        block_heading = block["heading"]
        for piece in _split_long_text(block["content"], max_chars=max_chars):
            piece_len = len(piece) + (1 if pending_parts else 0)
            if pending_parts and (block_heading != pending_heading or pending_len + piece_len > max_chars):
                flush_section()
            if not pending_parts:
                pending_heading = block_heading
            pending_parts.append(piece)
            pending_len += piece_len

    flush_section()

    for index, section in enumerate(sections):
        section["section_index"] = index
    return sections
