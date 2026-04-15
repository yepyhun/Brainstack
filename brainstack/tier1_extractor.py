from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List


_PREVIOUS_OCCUPATION_PATTERNS = (
    re.compile(
        r"\b(?:in|during)\s+my\s+previous\s+(?:role|occupation)\s+(?:i\s+worked\s+as|i\s+was|as)\s+([^.;!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bmy\s+previous\s+(?:role|occupation)\s+(?:was|as)\s+([^.;!?]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bi\s+used\s+to\s+work\s+as\s+([^.;!?]+)",
        re.IGNORECASE,
    ),
)


def build_profile_stable_key(category: str, content: str) -> str:
    normalized = " ".join(content.strip().lower().split())
    digest = hashlib.sha1(f"{category}:{normalized}".encode("utf-8")).hexdigest()
    return f"{category}:{digest[:16]}"


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[.!?\n]+", text)
    return [part.strip() for part in parts if part and part.strip()]


def _slotted_candidate(
    *,
    category: str,
    slot: str,
    content: str,
    confidence: float,
    source: str,
) -> Dict[str, Any]:
    return {
        "category": category,
        "slot": slot,
        "stable_key": f"{category}:{slot}",
        "content": content,
        "confidence": confidence,
        "source": source,
    }


def _extract_previous_occupation(sentence: str) -> str:
    for pattern in _PREVIOUS_OCCUPATION_PATTERNS:
        match = pattern.search(sentence)
        if not match:
            continue
        value = " ".join(str(match.group(1) or "").split()).strip(" ,.:;")
        if value:
            return value
    return ""


def extract_profile_candidates(text: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not text:
        return candidates

    for sentence in _split_sentences(text):
        lowered = sentence.lower()

        identity_match = re.search(
            r"\b(?:my name is|i am|i'm|call me|a nevem|én vagyok)\s+([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű0-9_-]{2,40})",
            sentence,
            re.IGNORECASE,
        )
        if identity_match:
            value = identity_match.group(1).strip()
            candidates.append(
                _slotted_candidate(
                    category="identity",
                    slot="identity:name",
                    content=value,
                    confidence=0.95,
                    source="heuristic_identity",
                )
            )

        age_match = re.search(
            r"\b([0-9]{1,3})\s*(?:years? old|éves)\b",
            lowered,
            re.IGNORECASE,
        )
        if age_match:
            candidates.append(
                _slotted_candidate(
                    category="identity",
                    slot="identity:age",
                    content=f"{age_match.group(1).strip()} years old",
                    confidence=0.9,
                    source="heuristic_identity",
                )
            )

        if "vibecoder" in lowered or "nem developer" in lowered or "not developer" in lowered:
            candidates.append(
                _slotted_candidate(
                    category="identity",
                    slot="identity:skill_level",
                    content="Vibecoder (not a professional developer)",
                    confidence=0.88,
                    source="heuristic_identity",
                )
            )

        previous_occupation = _extract_previous_occupation(sentence)
        if previous_occupation:
            candidates.append(
                _slotted_candidate(
                    category="identity",
                    slot="identity:previous_occupation",
                    content=f"Previous occupation: {previous_occupation}",
                    confidence=0.9,
                    source="heuristic_identity",
                )
            )

        if "emoji" in lowered or "emoj" in lowered:
            candidates.append(
                _slotted_candidate(
                    category="preference",
                    slot="preference:emoji_usage",
                    content="Minimize emoji usage; only use them if truly fitting or funny.",
                    confidence=0.9,
                    source="heuristic_preference",
                )
            )

        if (
            "szakzsargon" in lowered
            or "jargon" in lowered
            or "könnyen megérthetően" in lowered
            or "érthetően" in lowered
            or "accessible" in lowered
            or "easy-to-understand" in lowered
            or "not developer" in lowered
            or "nem developer" in lowered
        ):
            candidates.append(
                _slotted_candidate(
                    category="preference",
                    slot="preference:communication_style",
                    content="Avoid technical jargon and explain logic in an accessible, easy-to-understand way without being condescending.",
                    confidence=0.9,
                    source="heuristic_preference",
                )
            )

        if "humanizer" in lowered or "em dash" in lowered or "dash jele" in lowered or "—" in sentence:
            candidates.append(
                _slotted_candidate(
                    category="preference",
                    slot="preference:formatting",
                    content="Follow the 'humanizer' format: no em dashes, no marketing fluff, no repetitive triplets, no filler phrases, and no excessive validation/nodding.",
                    confidence=0.9,
                    source="heuristic_preference",
                )
            )

        if re.search(r"\b(i prefer|i like|i love|i hate|always|never|prefer|szeretem|nem szeretem|inkább|mindig|soha)\b", lowered):
            candidates.append(
                {
                    "category": "preference",
                    "content": sentence,
                    "confidence": 0.78,
                    "source": "heuristic_preference",
                }
            )

        if re.search(r"\b(we are working on|i am working on|i'm working on|we were working on|dolgozom|dolgozunk|ezen dolgozunk)\b", lowered):
            candidates.append(
                {
                    "category": "shared_work",
                    "content": sentence,
                    "confidence": 0.7,
                    "source": "heuristic_shared_work",
                }
            )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        key = item.get("stable_key") or build_profile_stable_key(item["category"], item["content"])
        if key in seen:
            continue
        seen.add(key)
        item["stable_key"] = key
        deduped.append(item)
    return deduped[:4]
