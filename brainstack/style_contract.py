from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


STYLE_CONTRACT_SLOT = "preference:style_contract"
STYLE_CONTRACT_DOC_KIND = "style_contract"
STYLE_CONTRACT_CATEGORY = "preference"
STYLE_CONTRACT_DEFAULT_TITLE = "User style contract"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _coerce_confidence(value: Any, *, default: float = 0.86) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


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
    if not first_line.endswith(":") and not first_line.startswith("-"):
        title = first_line
        index = 1

    sections: List[Dict[str, Any]] = []
    current_heading = ""
    current_lines: List[str] = []
    saw_heading = False
    bullet_line_count = 0

    def _flush() -> None:
        nonlocal current_heading, current_lines
        lines = _normalize_rule_lines(current_lines)
        if current_heading or lines:
            sections.append({"heading": current_heading, "lines": lines})
        current_heading = ""
        current_lines = []

    for line in normalized_lines[index:]:
        if line.endswith(":") and not line.startswith("-"):
            saw_heading = True
            _flush()
            current_heading = line[:-1].strip()
            continue
        if line.startswith("-"):
            bullet_line_count += 1
            current_lines.append(line[1:].strip())
        else:
            current_lines.append(line)

    _flush()

    if not sections and index < len(normalized_lines):
        fallback_lines = _normalize_rule_lines(normalized_lines[index:])
        if fallback_lines:
            sections = [{"heading": "Rules", "lines": fallback_lines}]

    total_rules = sum(len(section.get("lines") or []) for section in sections)
    if total_rules == 0:
        return None
    if not saw_heading and bullet_line_count < 2:
        return None
    if not saw_heading and total_rules < 3:
        return None

    return {
        "title": title,
        "summary": "",
        "sections": sections,
    }


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
    merged_metadata.update(
        {
            "memory_class": "style_contract",
            "style_contract_title": parsed["title"],
            "style_contract_sections": parsed["sections"],
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
