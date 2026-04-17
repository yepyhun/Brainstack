from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

from .corpus import build_document_stable_key


STYLE_CONTRACT_DOC_KIND = "style_contract"
STYLE_CONTRACT_KIND = "humanizer"
STYLE_CONTRACT_TITLE = "Humanizer style contract"
STYLE_CONTRACT_SOURCE = "brainstack.style_contract"

_DIRECT_STYLE_QUERY_PATTERNS = (
    re.compile(r"\bhumanizer\w*\b.*\b(?:rule|rules|szab[áa]ly\w*)\b", re.IGNORECASE),
    re.compile(r"\b(?:rule|rules|szab[áa]ly\w*)\b.*\bhumanizer\w*\b", re.IGNORECASE),
    re.compile(r"\b(?:29|huszonkilenc)\b.*\b(?:rule|rules|szab[áa]ly\w*)\b", re.IGNORECASE),
    re.compile(r"\b(?:all|mind(?:et)?|összes)\b.*\b(?:29|huszonkilenc)\b.*\b(?:rule|rules|szab[áa]ly\w*)\b", re.IGNORECASE),
)

_SECTION_HEADERS = (
    "tartalmi minták",
    "nyelvi minták",
    "kommunikációs minták",
    "töltelék",
    "stílus minták",
    "content patterns",
    "language patterns",
    "communication patterns",
    "filler",
    "style patterns",
)

_CANONICAL_SECTION_TITLES = (
    ("tartalmi minták", "Tartalmi minták"),
    ("nyelvi minták", "Nyelvi minták"),
    ("kommunikációs minták", "Kommunikációs minták"),
    ("töltelék", "Töltelék"),
    ("stílus minták", "Stílus minták"),
    ("content patterns", "Content patterns"),
    ("language patterns", "Language patterns"),
    ("communication patterns", "Communication patterns"),
    ("filler", "Filler"),
    ("style patterns", "Style patterns"),
)

_CANONICAL_SECTION_ORDER = (
    "Tartalmi minták",
    "Nyelvi minták",
    "Kommunikációs minták",
    "Töltelék",
    "Stílus minták",
    "Content patterns",
    "Language patterns",
    "Communication patterns",
    "Filler",
    "Style patterns",
)

_META_NOISE_HINTS = (
    "persona.md",
    "skill.md",
    "memory.md",
    "user.md",
    "~/.hermes",
    "humanizer skill",
    "blader/humanizer",
    "prompt",
    "loaded",
)

_ROLE_PREFIX_RE = re.compile(r"^\s*(?:User|Assistant|System|Tool)\s*:\s*(?:\[[^\]]+\]\s*)?", re.IGNORECASE)
_NEXT_ROLE_RE = re.compile(r"\b(?:Assistant|System|Tool)\s*:", re.IGNORECASE)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_compare_text(value: Any) -> str:
    return _normalize_text(value).lower()


def _primary_user_segment_preserve_lines(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    cleaned_lines: List[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if re.match(r"^\s*(?:Assistant|System|Tool)\s*:", raw_line, re.IGNORECASE):
            break
        cleaned = _ROLE_PREFIX_RE.sub("", raw_line).rstrip()
        cleaned_lines.append(cleaned)

    candidate = "\n".join(cleaned_lines).strip()
    if not candidate:
        return ""

    next_role = _NEXT_ROLE_RE.search(candidate)
    if next_role:
        candidate = candidate[: next_role.start()].rstrip()
    return candidate.strip()


def resolve_direct_style_contract_targets(query: str) -> tuple[str, ...]:
    normalized = _normalize_compare_text(query)
    if not normalized:
        return ()
    if any(pattern.search(normalized) for pattern in _DIRECT_STYLE_QUERY_PATTERNS):
        return (STYLE_CONTRACT_KIND,)
    return ()


def is_style_contract_meta_row(*, category: str, stable_key: str = "", content: str) -> bool:
    if _normalize_compare_text(category) != "shared_work":
        return False
    lowered = _normalize_compare_text(" ".join(filter(None, (stable_key, content))))
    if "humanizer" not in lowered and "persona.md" not in lowered and "skill.md" not in lowered:
        return False
    return any(hint in lowered for hint in _META_NOISE_HINTS)


def build_style_contract_metadata(
    *,
    principal_scope_key: str,
    principal_scope: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "principal_scope_key": str(principal_scope_key or "").strip(),
        "contract_kind": STYLE_CONTRACT_KIND,
        "memory_class": "style_contract",
    }
    if isinstance(principal_scope, Mapping) and principal_scope:
        metadata["principal_scope"] = dict(principal_scope)
    return metadata


def build_style_contract_stable_key(*, principal_scope_key: str) -> str:
    metadata = {
        "principal_scope_key": str(principal_scope_key or "").strip(),
        "contract_kind": STYLE_CONTRACT_KIND,
    }
    return build_document_stable_key(
        title=STYLE_CONTRACT_TITLE,
        source=STYLE_CONTRACT_SOURCE,
        doc_kind=STYLE_CONTRACT_DOC_KIND,
        metadata=metadata,
    )


def _looks_like_style_contract_segment(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) < 180:
        return False
    lowered = text.lower()
    section_hits = sum(1 for header in _SECTION_HEADERS if header in lowered)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if section_hits >= 2 and len(lines) >= 8:
        return True
    if section_hits >= 3:
        return True
    if "humanizer" in lowered and section_hits >= 2:
        return True
    if "humanizer" in lowered and section_hits >= 1 and len(lines) >= 8:
        return True
    return False


def _extract_style_contract_sections(value: str) -> List[tuple[str, str]]:
    text = str(value or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    matches: List[tuple[int, int, str]] = []
    seen_positions: set[tuple[int, str]] = set()
    for needle, canonical_title in _CANONICAL_SECTION_TITLES:
        pattern = re.compile(
            rf"(?i)(?<!\w)({re.escape(needle)}(?:\s*\([^)]+\))?)\s*:"
        )
        for match in pattern.finditer(text):
            key = (int(match.start()), canonical_title)
            if key in seen_positions:
                continue
            seen_positions.add(key)
            matches.append((int(match.start()), int(match.end()), canonical_title))

    matches.sort(key=lambda item: item[0])
    if len(matches) < 2:
        return []

    sections: List[tuple[str, str]] = []
    seen_titles: set[str] = set()
    for index, (start, end, title) in enumerate(matches):
        body_end = matches[index + 1][0] if index + 1 < len(matches) else len(text)
        body = text[end:body_end].strip(" \n\t:")
        if not body:
            continue
        normalized_body = _normalize_style_contract_content(body)
        if not normalized_body:
            continue
        title_key = _normalize_compare_text(title)
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        sections.append((title, normalized_body))
    return sections


def _normalize_style_contract_content(value: str) -> str:
    lines = [line.rstrip() for line in str(value or "").replace("\r\n", "\n").splitlines()]
    normalized: List[str] = []
    previous_blank = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if previous_blank:
                continue
            normalized.append("")
            previous_blank = True
            continue
        normalized.append(stripped)
        previous_blank = False
    return "\n".join(normalized).strip()


def derive_transcript_style_contract_artifact(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_content: str = "",
    source: str = "tier2_transcript_rule",
) -> Dict[str, Any] | None:
    segments: List[str] = []
    seen: set[str] = set()
    section_bodies: Dict[str, str] = {}
    for row in transcript_entries:
        segment = _primary_user_segment_preserve_lines(row.get("content"))
        if not segment or not _looks_like_style_contract_segment(segment):
            continue
        sections = _extract_style_contract_sections(segment)
        if sections:
            for title, body in sections:
                existing_body = section_bodies.get(title, "")
                if len(body.strip()) > len(existing_body.strip()):
                    section_bodies[title] = body
            continue
        normalized_segment = _normalize_style_contract_content(segment)
        fingerprint = _normalize_compare_text(normalized_segment)
        if not normalized_segment or fingerprint in seen:
            continue
        seen.add(fingerprint)
        segments.append(normalized_segment)

    ordered_sections = [
        f"{title}:\n{section_bodies[title]}"
        for title in _CANONICAL_SECTION_ORDER
        if str(section_bodies.get(title) or "").strip()
    ]
    if ordered_sections:
        segments.insert(0, _normalize_style_contract_content("\n\n".join(ordered_sections)))

    if not segments:
        return None

    content = _normalize_style_contract_content("\n\n".join(segments))
    if not content:
        return None
    if _normalize_compare_text(content) == _normalize_compare_text(existing_content):
        return None

    return {
        "title": STYLE_CONTRACT_TITLE,
        "doc_kind": STYLE_CONTRACT_DOC_KIND,
        "content": content,
        "source": source,
        "confidence": 0.9,
    }


def build_style_contract_document(
    *,
    principal_scope_key: str,
    principal_scope: Mapping[str, Any] | None,
    content: str,
    source: str,
) -> Dict[str, Any]:
    normalized_content = _normalize_style_contract_content(content)
    metadata = build_style_contract_metadata(
        principal_scope_key=principal_scope_key,
        principal_scope=principal_scope,
    )
    stable_key = build_style_contract_stable_key(principal_scope_key=principal_scope_key)
    return {
        "stable_key": stable_key,
        "title": STYLE_CONTRACT_TITLE,
        "doc_kind": STYLE_CONTRACT_DOC_KIND,
        "source": source,
        "metadata": metadata,
        "sections": [
            {
                "heading": STYLE_CONTRACT_TITLE,
                "content": normalized_content,
                "token_estimate": max(1, len(normalized_content) // 4),
                "metadata": {"contract_kind": STYLE_CONTRACT_KIND},
            }
        ],
    }
