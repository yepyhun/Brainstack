from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping


STYLE_CONTRACT_SLOT = "preference:style_contract"
STYLE_CONTRACT_DOC_KIND = "style_contract"
STYLE_CONTRACT_CATEGORY = "preference"
STYLE_CONTRACT_DEFAULT_TITLE = "User style contract"
_RULE_BULLET_RE = re.compile(r"^(?:[-*•]|\d{1,3}\s*[.)-])\s+(?P<content>.+)$")
_INLINE_RULE_RE = re.compile(r"^(?P<label>.+?)\s+(?:-|–|—)\s+(?P<detail>.+)$")
_STYLE_CONTRACT_SOURCE_RANKS = (
    ("behavior_policy_correction", 400),
    ("prefetch:style_contract_patch", 350),
    ("memory_write:style_contract_patch", 350),
    ("sync_turn:user_style_contract_patch", 350),
    ("prefetch:style_contract", 300),
    ("memory_write:style_contract", 300),
    ("sync_turn:user_style_contract", 300),
    ("tier2_llm", 100),
)
_PATCH_TOKEN_RE = re.compile(r"[0-9A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]{2,}", re.UNICODE)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _coerce_confidence(value: Any, *, default: float = 0.86) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def _tokenize_patch_text(value: Any) -> List[str]:
    return [token.casefold() for token in _PATCH_TOKEN_RE.findall(_normalize_text(value))]


def _normalize_rule_lines(values: Any) -> List[str]:
    if isinstance(values, str):
        raw_items = values.splitlines()
    elif isinstance(values, Iterable):
        raw_items = list(values)
    else:
        raw_items = []
    lines: List[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = _normalize_text(raw)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        lines.append(text)
    return lines


def _slug(value: Any) -> str:
    output = "".join(char.lower() if str(char).isalnum() else "-" for char in str(value or ""))
    while "--" in output:
        output = output.replace("--", "-")
    return output.strip("-") or "rules"


def _extract_rule_bullet(line: str) -> str | None:
    match = _RULE_BULLET_RE.match(_normalize_text(line))
    if not match:
        return None
    content = _normalize_text(match.group("content"))
    return content or None


def _extract_inline_rule(line: str) -> str | None:
    normalized = _normalize_text(line)
    if not normalized or _extract_rule_bullet(normalized) is not None:
        return None
    match = _INLINE_RULE_RE.match(normalized)
    if not match:
        return None
    label = _normalize_text(match.group("label"))
    detail = _normalize_text(match.group("detail"))
    if not label or not detail:
        return None
    if label.endswith(":"):
        return None
    return f"{label} - {detail}"


def _is_heading_line(line: str) -> bool:
    normalized = _normalize_text(line)
    return bool(normalized) and normalized.endswith(":") and _extract_rule_bullet(normalized) is None


def style_contract_source_rank(source: Any) -> int:
    normalized = _normalize_text(source).casefold()
    if not normalized:
        return 0
    for marker, rank in _STYLE_CONTRACT_SOURCE_RANKS:
        if normalized.startswith(marker):
            return rank
    if "tier2" in normalized:
        return 100
    return 200


def _sections_from_metadata(metadata: Mapping[str, Any] | None) -> tuple[str, str, List[Dict[str, Any]]]:
    if not isinstance(metadata, Mapping):
        return "", "", []
    title = _normalize_text(metadata.get("style_contract_title")) or STYLE_CONTRACT_DEFAULT_TITLE
    summary = _normalize_text(metadata.get("style_contract_summary"))
    raw_sections = metadata.get("style_contract_sections")
    sections: List[Dict[str, Any]] = []
    if isinstance(raw_sections, Iterable):
        for raw_section in raw_sections:
            if not isinstance(raw_section, Mapping):
                continue
            heading = _normalize_text(raw_section.get("heading"))
            lines = _normalize_rule_lines(raw_section.get("lines"))
            if not heading and not lines:
                continue
            sections.append({"heading": heading, "lines": lines})
    return title, summary, sections


def extract_style_contract_parts(
    raw_text: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any] | None:
    title, summary, sections = _sections_from_metadata(metadata)
    if not sections:
        parsed = parse_style_contract_text(raw_text)
        if parsed is None:
            return None
        title = _normalize_text(parsed.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE
        summary = _normalize_text(parsed.get("summary"))
        sections = [
            {
                "heading": _normalize_text(section.get("heading")),
                "lines": _normalize_rule_lines(section.get("lines")),
            }
            for section in parsed.get("sections") or ()
            if isinstance(section, Mapping)
        ]
    if not sections:
        return None
    return {
        "title": title or STYLE_CONTRACT_DEFAULT_TITLE,
        "summary": summary,
        "sections": sections,
    }


def list_style_contract_rules(
    *,
    raw_text: Any,
    metadata: Mapping[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    parts = extract_style_contract_parts(raw_text, metadata=metadata)
    if parts is None:
        return []
    rules: List[Dict[str, Any]] = []
    order = 0
    for section_index, section in enumerate(parts["sections"], start=1):
        heading = _normalize_text(section.get("heading")) or f"Rules {section_index}"
        section_slug = _slug(heading)
        for line_index, line in enumerate(section.get("lines") or (), start=1):
            text = _normalize_text(line)
            if not text:
                continue
            order += 1
            rules.append(
                {
                    "rule_id": f"{section_slug}-{line_index:02d}",
                    "order": order,
                    "section": heading,
                    "section_slug": section_slug,
                    "line_index": line_index,
                    "text": text,
                }
            )
    return rules


def apply_style_contract_rule_correction(
    *,
    raw_text: Any,
    rule_id: str,
    replacement_text: Any,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any] | None:
    normalized_rule_id = _normalize_text(rule_id)
    if not normalized_rule_id:
        return None
    parts = extract_style_contract_parts(raw_text, metadata=metadata)
    if parts is None:
        return None
    sections = [
        {
            "heading": _normalize_text(section.get("heading")),
            "lines": _normalize_rule_lines(section.get("lines")),
        }
        for section in parts["sections"]
    ]
    normalized_replacement = _normalize_text(replacement_text)
    applied = False
    corrected_sections: List[Dict[str, Any]] = []
    for section_index, section in enumerate(sections, start=1):
        heading = section["heading"] or f"Rules {section_index}"
        section_slug = _slug(heading)
        lines: List[str] = []
        for line_index, line in enumerate(section.get("lines") or (), start=1):
            current_rule_id = f"{section_slug}-{line_index:02d}"
            if current_rule_id == normalized_rule_id:
                applied = True
                if normalized_replacement:
                    lines.append(normalized_replacement)
                continue
            lines.append(_normalize_text(line))
        if lines:
            corrected_sections.append({"heading": heading, "lines": lines})
    if not applied:
        return None
    content = render_style_contract_content(
        title=str(parts["title"] or STYLE_CONTRACT_DEFAULT_TITLE),
        summary=str(parts["summary"] or ""),
        sections=corrected_sections,
    )
    return {
        "title": str(parts["title"] or STYLE_CONTRACT_DEFAULT_TITLE),
        "summary": str(parts["summary"] or ""),
        "sections": corrected_sections,
        "content": content,
        "updated_rule_id": normalized_rule_id,
    }


def parse_style_contract_patch_text(raw_text: Any) -> List[str]:
    normalized_lines = [_normalize_text(line) for line in str(raw_text or "").splitlines() if _normalize_text(line)]
    if not normalized_lines or len(normalized_lines) > 3:
        return []
    patch_lines: List[str] = []
    for line in normalized_lines:
        if line.endswith("?"):
            return []
        bullet = _extract_rule_bullet(line)
        inline_rule = _extract_inline_rule(line)
        candidate = bullet or inline_rule or line
        if len(_tokenize_patch_text(candidate)) < 3:
            return []
        patch_lines.append(candidate)
    return patch_lines


def apply_style_contract_patch(
    *,
    raw_text: Any,
    patch_text: Any,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any] | None:
    patch_lines = parse_style_contract_patch_text(patch_text)
    if not patch_lines:
        return None

    rules = list_style_contract_rules(raw_text=raw_text, metadata=metadata)
    if not rules:
        return None

    replacement_map: Dict[str, str] = {}
    for patch_line in patch_lines:
        patch_tokens = set(_tokenize_patch_text(patch_line))
        if not patch_tokens:
            return None
        scored: List[tuple[int, str]] = []
        for rule in rules:
            rule_id = str(rule.get("rule_id") or "").strip()
            if not rule_id:
                continue
            rule_tokens = set(_tokenize_patch_text(rule.get("text")))
            overlap = len(rule_tokens & patch_tokens)
            if overlap > 0:
                scored.append((overlap, rule_id))
        if not scored:
            return None
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        best_score, best_rule_id = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else -1
        if best_score < 2 or best_score == second_score:
            return None
        replacement_map[best_rule_id] = patch_line

    updated_rule_ids: List[str] = []
    current_content = str(raw_text or "")
    current_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "").strip()
        if rule_id not in replacement_map:
            continue
        corrected = apply_style_contract_rule_correction(
            raw_text=current_content,
            rule_id=rule_id,
            replacement_text=replacement_map[rule_id],
            metadata=current_metadata,
        )
        if corrected is None:
            return None
        current_content = str(corrected["content"])
        current_metadata = {
            **current_metadata,
            "style_contract_title": corrected["title"],
            "style_contract_sections": corrected["sections"],
        }
        updated_rule_ids.append(rule_id)

    if not updated_rule_ids or _normalize_text(current_content) == _normalize_text(raw_text):
        return None

    parts = extract_style_contract_parts(current_content, metadata=current_metadata)
    if parts is None:
        return None
    return {
        "title": str(parts["title"] or STYLE_CONTRACT_DEFAULT_TITLE),
        "summary": str(parts.get("summary") or ""),
        "sections": list(parts["sections"]),
        "content": current_content,
        "updated_rule_ids": updated_rule_ids,
        "patch_rule_count": len(updated_rule_ids),
    }


def render_style_contract_content(
    *,
    title: str,
    summary: str = "",
    sections: Iterable[Mapping[str, Any]] = (),
) -> str:
    normalized_title = _normalize_text(title) or STYLE_CONTRACT_DEFAULT_TITLE
    normalized_summary = _normalize_text(summary)
    blocks: List[str] = [normalized_title]
    if normalized_summary:
        blocks.extend(["", normalized_summary])
    for raw_section in sections:
        heading = _normalize_text(raw_section.get("heading"))
        lines = _normalize_rule_lines(raw_section.get("lines"))
        if not heading and not lines:
            continue
        blocks.append("")
        if heading:
            blocks.append(f"{heading}:")
        blocks.extend(f"- {line}" for line in lines)
    return "\n".join(blocks).strip()


def normalize_style_contract_payload(payload: Any) -> Dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    slot = _normalize_text(payload.get("slot"))
    title = (
        _normalize_text(payload.get("title"))
        or _normalize_text(metadata.get("style_contract_title"))
        or STYLE_CONTRACT_DEFAULT_TITLE
    )
    summary = _normalize_text(payload.get("summary")) or _normalize_text(metadata.get("style_contract_summary"))
    confidence = _coerce_confidence(payload.get("confidence"), default=0.9)
    section_source = payload.get("sections")
    if not section_source:
        section_source = metadata.get("style_contract_sections")
    sections: List[Dict[str, Any]] = []
    for raw_section in section_source or ():
        if not isinstance(raw_section, Mapping):
            continue
        heading = _normalize_text(raw_section.get("heading"))
        lines = _normalize_rule_lines(raw_section.get("lines"))
        if not heading and not lines:
            continue
        sections.append({"heading": heading, "lines": lines})
    if slot and slot != STYLE_CONTRACT_SLOT:
        return None
    content = render_style_contract_content(title=title, summary=summary, sections=sections)
    if not content or not sections:
        return None
    normalized_metadata: Dict[str, Any] = {
        "memory_class": "style_contract",
        "style_contract_title": title,
        "style_contract_sections": sections,
    }
    if summary:
        normalized_metadata["style_contract_summary"] = summary
    return {
        "category": STYLE_CONTRACT_CATEGORY,
        "slot": STYLE_CONTRACT_SLOT,
        "content": content,
        "confidence": confidence,
        "source": _normalize_text(payload.get("source")) or "tier2_llm",
        "metadata": normalized_metadata,
    }


def build_style_contract_from_document(
    *,
    title: Any,
    sections: Iterable[Mapping[str, Any]],
    source: str,
    confidence: float = 0.9,
) -> Dict[str, Any] | None:
    normalized_sections: List[Dict[str, Any]] = []
    for raw_section in sections:
        heading = _normalize_text(raw_section.get("heading"))
        lines = _normalize_rule_lines(raw_section.get("content"))
        if not heading and not lines:
            continue
        normalized_sections.append({"heading": heading, "lines": lines})
    content = render_style_contract_content(
        title=_normalize_text(title) or STYLE_CONTRACT_DEFAULT_TITLE,
        sections=normalized_sections,
    )
    if not content or not normalized_sections:
        return None
    return {
        "category": STYLE_CONTRACT_CATEGORY,
        "slot": STYLE_CONTRACT_SLOT,
        "content": content,
        "confidence": _coerce_confidence(confidence, default=0.9),
        "source": source,
        "metadata": {
            "memory_class": "style_contract",
            "style_contract_title": _normalize_text(title) or STYLE_CONTRACT_DEFAULT_TITLE,
            "style_contract_sections": normalized_sections,
        },
    }


def parse_style_contract_text(raw_text: Any) -> Dict[str, Any] | None:
    text = str(raw_text or "")
    if not text.strip() or "\n" not in text:
        return None

    normalized_lines = [_normalize_text(line) for line in text.splitlines() if _normalize_text(line)]
    if not normalized_lines:
        return None

    title = STYLE_CONTRACT_DEFAULT_TITLE
    index = 0
    first_line = normalized_lines[0]
    if (
        not _is_heading_line(first_line)
        and _extract_rule_bullet(first_line) is None
        and _extract_inline_rule(first_line) is None
    ):
        title = first_line
        index = 1

    sections: List[Dict[str, Any]] = []
    current_heading = ""
    current_lines: List[str] = []
    saw_heading = False
    bullet_line_count = 0
    inline_rule_count = 0

    def _flush() -> None:
        nonlocal current_heading, current_lines
        lines = _normalize_rule_lines(current_lines)
        if current_heading or lines:
            sections.append({"heading": current_heading, "lines": lines})
        current_heading = ""
        current_lines = []

    for line in normalized_lines[index:]:
        if _is_heading_line(line):
            saw_heading = True
            _flush()
            current_heading = line[:-1].strip()
            continue
        bullet = _extract_rule_bullet(line)
        if bullet is not None:
            bullet_line_count += 1
            current_lines.append(bullet)
            continue
        inline_rule = _extract_inline_rule(line)
        if inline_rule is not None:
            inline_rule_count += 1
            current_lines.append(inline_rule)
            continue
        current_lines.append(line)

    _flush()

    if not sections and index < len(normalized_lines):
        fallback_lines = _normalize_rule_lines(normalized_lines[index:])
        if fallback_lines:
            sections = [{"heading": "Rules", "lines": fallback_lines}]

    total_rules = sum(len(section.get("lines") or []) for section in sections)
    if total_rules == 0:
        return None
    structured_rule_lines = bullet_line_count + inline_rule_count
    if not saw_heading and structured_rule_lines < 3:
        return None
    if not saw_heading and total_rules < 3:
        return None

    return {
        "title": title,
        "summary": "",
        "sections": sections,
    }


def looks_like_style_contract_teaching(raw_text: Any) -> bool:
    parsed = parse_style_contract_text(raw_text)
    if parsed is None:
        return False

    normalized_lines = [_normalize_text(line) for line in str(raw_text or "").splitlines() if _normalize_text(line)]
    has_leading_title = bool(
        normalized_lines
        and not _is_heading_line(normalized_lines[0])
        and _extract_rule_bullet(normalized_lines[0]) is None
    )
    sections = [
        section
        for section in parsed.get("sections") or ()
        if isinstance(section, Mapping)
    ]
    total_rules = sum(
        len(section.get("lines") or [])
        for section in sections
    )
    section_count = len(sections)
    headed_section_count = sum(1 for section in sections if _normalize_text(section.get("heading")))

    if total_rules >= 10:
        return True
    if section_count >= 2 and total_rules >= 3:
        return True
    if has_leading_title and total_rules >= 3:
        return True
    return headed_section_count >= 1 and total_rules >= 5


def build_style_contract_from_text(
    *,
    raw_text: Any,
    source: str,
    confidence: float = 0.9,
    metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any] | None:
    parsed = parse_style_contract_text(raw_text)
    if parsed is None:
        return None

    merged_metadata = dict(metadata) if isinstance(metadata, Mapping) else {}
    rules = list_style_contract_rules(
        raw_text=raw_text,
        metadata={
            **merged_metadata,
            "style_contract_title": parsed["title"],
            "style_contract_sections": parsed["sections"],
        },
    )
    merged_metadata.update(
        {
            "memory_class": "style_contract",
            "style_contract_title": parsed["title"],
            "style_contract_sections": parsed["sections"],
            "style_contract_rules": rules,
            "style_contract_rule_count": len(rules),
        }
    )
    content = render_style_contract_content(
        title=parsed["title"],
        summary=parsed["summary"],
        sections=parsed["sections"],
    )
    return {
        "category": STYLE_CONTRACT_CATEGORY,
        "slot": STYLE_CONTRACT_SLOT,
        "content": content,
        "confidence": _coerce_confidence(confidence, default=0.9),
        "source": source,
        "metadata": merged_metadata,
    }
