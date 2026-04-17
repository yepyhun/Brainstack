from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


STYLE_CONTRACT_SLOT = "preference:style_contract"
STYLE_CONTRACT_DOC_KIND = "style_contract"
STYLE_CONTRACT_CATEGORY = "preference"
STYLE_CONTRACT_DEFAULT_TITLE = "Humanizer style contract"


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
    title = _normalize_text(payload.get("title")) or STYLE_CONTRACT_DEFAULT_TITLE
    summary = _normalize_text(payload.get("summary"))
    confidence = _coerce_confidence(payload.get("confidence"), default=0.9)
    sections: List[Dict[str, Any]] = []
    for raw_section in payload.get("sections") or ():
        if not isinstance(raw_section, Mapping):
            continue
        heading = _normalize_text(raw_section.get("heading"))
        lines = _normalize_rule_lines(raw_section.get("lines"))
        if not heading and not lines:
            continue
        sections.append({"heading": heading, "lines": lines})
    content = render_style_contract_content(title=title, summary=summary, sections=sections)
    if not content or not sections:
        return None
    metadata: Dict[str, Any] = {
        "memory_class": "style_contract",
        "style_contract_title": title,
        "style_contract_sections": sections,
    }
    if summary:
        metadata["style_contract_summary"] = summary
    return {
        "category": STYLE_CONTRACT_CATEGORY,
        "slot": STYLE_CONTRACT_SLOT,
        "content": content,
        "confidence": confidence,
        "source": "tier2_llm",
        "metadata": metadata,
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
