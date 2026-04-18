from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping


COMMUNICATION_CANONICAL_SLOTS = {
    "preference:communication_style",
    "preference:emoji_usage",
    "preference:dash_usage",
    "preference:formatting",
    "preference:message_structure",
    "preference:pronoun_capitalization",
    "preference:formatting_style",
    "preference:response_language",
    "preference:ai_name",
    "preference:ai_nickname",
}

PROFILE_SLOT_ALIASES = {
    "name": "identity:name",
    "identity_name": "identity:name",
    "identity:name": "identity:name",
    "user_name": "identity:user_name",
    "identity:user_name": "identity:user_name",
    "age": "identity:age",
    "identity_age": "identity:age",
    "identity:age": "identity:age",
    "skill_level": "identity:skill_level",
    "identity_skill_level": "identity:skill_level",
    "identity:skill_level": "identity:skill_level",
    "emoji": "preference:emoji_usage",
    "emojis": "preference:emoji_usage",
    "emoji_usage": "preference:emoji_usage",
    "preference:emoji_usage": "preference:emoji_usage",
    "preference:emojis": "preference:emoji_usage",
    "communication": "preference:communication_style",
    "communication_style": "preference:communication_style",
    "humanizer": "preference:communication_style",
    "humanizer_style": "preference:communication_style",
    "style_humanizer": "preference:communication_style",
    "preference:style:humanizer": "preference:communication_style",
    "preference:communication_style": "preference:communication_style",
    "formatting": "preference:formatting",
    "preference:formatting": "preference:formatting",
    "message_structure": "preference:message_structure",
    "new_lines": "preference:message_structure",
    "newline_formatting": "preference:message_structure",
    "line_breaks": "preference:message_structure",
    "preference:message_structure": "preference:message_structure",
    "formatting_style": "preference:formatting_style",
    "dash_usage": "preference:dash_usage",
    "no_dash": "preference:dash_usage",
    "no_dashes": "preference:dash_usage",
    "dash_style": "preference:dash_usage",
    "punctuation_dash": "preference:dash_usage",
    "preference:dash_usage": "preference:dash_usage",
    "pronoun_capitalization": "preference:pronoun_capitalization",
    "capitalized_pronouns": "preference:pronoun_capitalization",
    "uppercase_pronouns": "preference:pronoun_capitalization",
    "capitalize_pronouns": "preference:pronoun_capitalization",
    "preference:pronoun_capitalization": "preference:pronoun_capitalization",
    "preference:formatting_style": "preference:formatting_style",
    "language": "preference:response_language",
    "preferred_language": "preference:response_language",
    "response_language": "preference:response_language",
    "preference:response_language": "preference:response_language",
    "language_preference": "preference:response_language",
    "preference:language_preference": "preference:response_language",
    "ai_name": "preference:ai_name",
    "assistant_name": "preference:ai_name",
    "preference:ai_name": "preference:ai_name",
    "ai_nickname": "preference:ai_nickname",
    "assistant_nickname": "preference:ai_nickname",
    "preference:ai_nickname": "preference:ai_nickname",
}

_EXPLICIT_AGE_PATTERNS = (
    re.compile(r"\b(?:i am|i'm)\s+(\d{1,3})\s*(?:years?\s*old)?\b", re.IGNORECASE),
    re.compile(r"\bmy age is\s+(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*éves\s+vagyok\b", re.IGNORECASE),
    re.compile(r"\bvagyok\s+(\d{1,3})\s*éves\b", re.IGNORECASE),
)

_DIRECT_AGE_QUERY_PATTERNS = (
    re.compile(r"\bhow old am i\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is)? my age\b", re.IGNORECASE),
    re.compile(r"\bremind me how old i am\b", re.IGNORECASE),
    re.compile(r"\bh[aá]ny\s+éves\s+vagyok\b", re.IGNORECASE),
    re.compile(r"\bmennyi\s+id[őo]s\s+vagyok\b", re.IGNORECASE),
    re.compile(r"\bmi\s+az\s+életkorom\b", re.IGNORECASE),
)

_ASSISTANT_NAME_PATTERNS = (
    re.compile(r"\bassistant(?:'s)? name is\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\byour name is\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\brefer to yourself as\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\bcall yourself\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\bcalls?\s+the\s+ai\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\bcall\s+the\s+ai\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\ba te neved\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\basszisztens neve\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})\b", re.IGNORECASE),
    re.compile(r"\bhívj\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})(?:-?(?:nak|nek))?\b", re.IGNORECASE),
)


def normalize_compare_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def normalize_profile_slot(value: Any) -> str:
    normalized = normalize_compare_text(value).replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9:_-]+", "_", normalized).strip("_")
    return PROFILE_SLOT_ALIASES.get(normalized, normalized)


def resolve_direct_identity_profile_slots(query: str) -> tuple[str, ...]:
    text = normalize_compare_text(query)
    if not text:
        return ()
    if any(pattern.search(text) for pattern in _DIRECT_AGE_QUERY_PATTERNS):
        return ("identity:age",)
    return ()


def _extract_assistant_name(value: Any) -> str:
    text = " ".join(str(value or "").strip().split())
    if not text:
        return ""
    for pattern in _ASSISTANT_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        candidate = match.group(1).strip(" .,:;!?\"'`()[]{}")
        if candidate:
            return candidate
    return ""


def expand_communication_profile_items(
    *,
    category: str,
    content: str,
    slot: str,
    confidence: float,
    source: str,
) -> List[Dict[str, Any]]:
    slot = normalize_profile_slot(slot)
    lowered = normalize_compare_text(content)
    if not lowered:
        return []

    candidates: List[tuple[str, str]] = []
    if slot == "preference:response_language" or any(token in lowered for token in ("magyar", "hungarian")):
        candidates.append(("preference:response_language", "Always respond in Hungarian."))
    assistant_name = _extract_assistant_name(content)
    if slot in {"preference:ai_name", "preference:ai_nickname"} and assistant_name:
        candidates.append(("preference:ai_name", f"Assistant's name is {assistant_name}."))
    if slot == "preference:communication_style":
        candidates.append(("preference:communication_style", "Use the configured communication style: direct, concrete, natural, and low-fluff."))
    if slot == "preference:emoji_usage" or "emoji" in lowered or "emoj" in lowered:
        candidates.append(("preference:emoji_usage", "Do not use emojis."))
    if slot == "preference:message_structure" or any(
        token in lowered for token in ("new line", "new lines", "line break", "új sor", "külön sor")
    ):
        candidates.append(("preference:message_structure", "Put each new thought on a new line."))
    if slot in {"preference:formatting_style", "preference:pronoun_capitalization"} or any(
        token in lowered for token in ("capitalize pronouns", "capitalized pronouns", "nagybetű", "én", " te ", " ő ")
    ):
        candidates.append(
            ("preference:pronoun_capitalization", "Capitalize Én, Te, and Ő when used as pronouns.")
        )
    if slot == "preference:dash_usage" or any(
        token in lowered for token in ("em dash", "dash", "—", "kötőjel", "hyphen", "hyphens")
    ):
        candidates.append(("preference:dash_usage", "Do not use dash punctuation in replies."))

    deduped: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for stable_slot, stable_content in candidates:
        key = (stable_slot, stable_content)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "category": category,
                "content": stable_content,
                "confidence": confidence,
                "source": source,
                "slot": stable_slot,
            }
        )
    return deduped


def derive_transcript_communication_profile_items(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_items: Iterable[Mapping[str, Any]],
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    existing_slots = {str(item.get("slot") or "").strip() for item in existing_items}
    text = "\n".join(normalize_compare_text(row.get("content")) for row in transcript_entries if normalize_compare_text(row.get("content")))
    if not text:
        return []

    candidates: List[tuple[str, str]] = []
    if "preference:response_language" not in existing_slots and any(
        token in text for token in ("magyarul válaszolj", "always respond in hungarian", "respond in hungarian")
    ):
        candidates.append(("preference:response_language", "Always respond in Hungarian."))
    if "preference:ai_name" not in existing_slots:
        assistant_name = _extract_assistant_name(text)
        if assistant_name:
            candidates.append(("preference:ai_name", f"Assistant's name is {assistant_name}."))
    if "preference:emoji_usage" not in existing_slots and any(
        token in text for token in ("ne használj emoj", "do not use emoji", "no emoji")
    ):
        candidates.append(("preference:emoji_usage", "Do not use emojis."))
    if "preference:message_structure" not in existing_slots and any(
        token in text for token in ("új gondolat új sor", "new thought on new line", "külön sor")
    ):
        candidates.append(("preference:message_structure", "Put each new thought on a new line."))
    if "preference:pronoun_capitalization" not in existing_slots and (
        "nagybetű" in text and all(token in text for token in ("én", "te", "ő"))
    ):
        candidates.append(
            ("preference:pronoun_capitalization", "Capitalize Én, Te, and Ő when used as pronouns.")
        )
    if "preference:dash_usage" not in existing_slots and any(
        token in text for token in ("dash jele", "em dash", "dash punctuation", "kötőjel", "hyphen", "hyphens")
    ):
        candidates.append(("preference:dash_usage", "Do not use dash punctuation in replies."))

    return [
        {
            "category": "preference",
            "content": content,
            "confidence": 0.86,
            "source": source,
            "slot": slot,
        }
        for slot, content in candidates
    ]


def derive_transcript_identity_profile_items(
    transcript_entries: Iterable[Mapping[str, Any]],
    *,
    existing_items: Iterable[Mapping[str, Any]],
    source: str = "tier2_transcript_rule",
) -> List[Dict[str, Any]]:
    existing_slots = {str(item.get("slot") or "").strip() for item in existing_items}
    if "identity:age" in existing_slots:
        return []

    sentences: List[str] = []
    for row in transcript_entries:
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        sentences.extend(part.strip() for part in re.split(r"[.!?\n]+", content) if part and part.strip())

    for sentence in reversed(sentences):
        normalized = " ".join(sentence.split())
        for pattern in _EXPLICIT_AGE_PATTERNS:
            match = pattern.search(normalized)
            if not match:
                continue
            age = str(match.group(1) or "").strip()
            if not age:
                continue
            return [
                {
                    "category": "identity",
                    "content": f"{age} years old",
                    "confidence": 0.88,
                    "source": source,
                    "slot": "identity:age",
                }
            ]
    return []
