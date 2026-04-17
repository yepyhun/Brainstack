from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping


_DECLARATION_HINTS = (" címe", " cime", " address")
_STOP_CUES = (
    "jegyezd meg",
    "ha kérdezem",
    "ha kerdezem",
    "remember this",
    "if i ask",
    "most megyek",
    "i'm going",
    "im going",
    "megyek",
    "chronva",
    "csinálj értesítőt",
    "csinalj ertesitot",
    "emlékeztetőt",
    "emlekeztetot",
)
_PROVIDER_PARENS_RE = re.compile(r"\(([^()\n]{2,40})\)")
_CATEGORY_RE = re.compile(r"\b(?:ez a|this is(?: the)?)\s+(.+?)\s+c[ií]me\b", re.IGNORECASE)
_PROVIDER_NAME_RE = re.compile(r"\b(.+?)\s+c[ií]me\b", re.IGNORECASE)
_LABELED_ADDRESS_RE = re.compile(r"\b(?:c[ií]m|address)\s*[:\-]\s*([^.!?\n]+)", re.IGNORECASE)
_TRANSCRIPT_USER_SEGMENT_RE = re.compile(
    r"^(?:User|Assistant|System|Tool)\s*:\s*(?:\[[^\]]+\]\s*)?",
    re.IGNORECASE,
)
_TRANSCRIPT_NEXT_ROLE_RE = re.compile(r"\b(?:Assistant|System|Tool)\s*:", re.IGNORECASE)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_compare_text(value: Any) -> str:
    return _normalize_text(value).lower()


def _primary_user_segment(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    match = _TRANSCRIPT_NEXT_ROLE_RE.search(text)
    if match:
        text = text[: match.start()].strip()
    text = _TRANSCRIPT_USER_SEGMENT_RE.sub("", text).strip()
    return _normalize_text(text)


def _looks_like_location_fragment(value: str) -> bool:
    text = _normalize_text(value)
    if len(text) < 8 or len(text) > 140:
        return False
    if not any(char.isalpha() for char in text):
        return False
    if not any(char.isdigit() for char in text):
        return False
    return True


def _extract_provider_name(text: str) -> str:
    paren_match = _PROVIDER_PARENS_RE.search(text)
    if paren_match:
        return _normalize_text(paren_match.group(1)).rstrip(".,;:!?")

    lowered = _normalize_compare_text(text)
    provider_match = _PROVIDER_NAME_RE.search(text)
    if not provider_match:
        return ""
    candidate = _normalize_text(provider_match.group(1))
    if candidate.lower().startswith(("ez a ", "this is ", "this is the ")):
        return ""
    if any(hint in lowered for hint in _DECLARATION_HINTS):
        return candidate.rstrip(".,;:!?")
    return ""


def _extract_category(text: str) -> str:
    match = _CATEGORY_RE.search(text)
    if not match:
        return ""
    candidate = _normalize_text(match.group(1)).rstrip(".,;:!?")
    candidate = re.sub(r"^(?:a|az|the)\s+", "", candidate, flags=re.IGNORECASE)
    return candidate


def _extract_location_details(text: str) -> str:
    labeled = _LABELED_ADDRESS_RE.search(text)
    if labeled:
        candidate = _normalize_text(labeled.group(1)).rstrip(".,;:!?")
        if _looks_like_location_fragment(candidate):
            return candidate

    normalized = _normalize_text(text)
    lowered = normalized.lower()
    prefix = normalized
    for cue in _STOP_CUES:
        index = lowered.find(cue)
        if index > 0:
            prefix = normalized[:index].strip(" ,.;:!?")
            lowered = prefix.lower()
            break

    if _looks_like_location_fragment(prefix):
        return prefix
    return ""


def derive_transcript_logistics_typed_entities(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_entities: Iterable[Mapping[str, Any]],
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    existing_keys = {
        (
            _normalize_compare_text(item.get("name")),
            _normalize_compare_text(item.get("entity_type")),
        )
        for item in existing_entities
        if _normalize_text(item.get("name")) and _normalize_text(item.get("entity_type"))
    }

    derived: List[Dict[str, Any]] = []
    for row in transcript_entries:
        content = _primary_user_segment(row.get("content"))
        if not content:
            continue
        lowered = content.lower()
        if not any(hint in lowered for hint in _DECLARATION_HINTS):
            continue

        provider_name = _extract_provider_name(content)
        location_details = _extract_location_details(content)
        if not provider_name or not location_details:
            continue

        key = (_normalize_compare_text(provider_name), "service_provider")
        if key in existing_keys:
            continue

        try:
            turn_number = int(row.get("turn_number") or 0)
        except (TypeError, ValueError):
            turn_number = 0
        created_at = _normalize_text(row.get("created_at"))
        category = _extract_category(content)
        attributes: Dict[str, str] = {"address": location_details}
        if category:
            attributes["category"] = category

        item: Dict[str, Any] = {
            "turn_number": turn_number,
            "name": provider_name,
            "entity_type": "service_provider",
            "subject": "User",
            "attributes": attributes,
            "confidence": 0.86,
            "metadata": {"event_turn_number": turn_number, "source": source},
        }
        if created_at:
            item["temporal"] = {"observed_at": created_at}
        derived.append(item)
        existing_keys.add(key)

    return derived[:4]
