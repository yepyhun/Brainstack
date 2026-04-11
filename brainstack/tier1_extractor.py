from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List


def build_profile_stable_key(category: str, content: str) -> str:
    normalized = " ".join(content.strip().lower().split())
    digest = hashlib.sha1(f"{category}:{normalized}".encode("utf-8")).hexdigest()
    return f"{category}:{digest[:16]}"


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[.!?\n]+", text)
    return [part.strip() for part in parts if part and part.strip()]


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
            content = f"User identity: {value}"
            candidates.append(
                {
                    "category": "identity",
                    "content": content,
                    "confidence": 0.95,
                    "source": "heuristic_identity",
                }
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
        key = build_profile_stable_key(item["category"], item["content"])
        if key in seen:
            continue
        seen.add(key)
        item["stable_key"] = key
        deduped.append(item)
    return deduped[:4]
