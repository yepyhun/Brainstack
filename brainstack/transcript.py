from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "az",
    "be",
    "by",
    "did",
    "do",
    "for",
    "from",
    "how",
    "i",
    "is",
    "it",
    "mi",
    "mit",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "van",
    "volt",
    "was",
    "we",
    "what",
    "when",
    "who",
    "why",
}


def format_turn_content(user_content: str, assistant_content: str) -> str:
    user = " ".join(str(user_content or "").split())
    assistant = " ".join(str(assistant_content or "").split())
    return f"User: {user}\nAssistant: {assistant}".strip()


def build_turn_summary(user_content: str, assistant_content: str, *, max_len: int = 140) -> str:
    user = " ".join(str(user_content or "").split())
    assistant = " ".join(str(assistant_content or "").split())
    if len(user) > max_len:
        user = user[: max_len - 3].rstrip() + "..."
    if len(assistant) > max_len:
        assistant = assistant[: max_len - 3].rstrip() + "..."
    return f"user: {user} | assistant: {assistant}".strip()


def build_transcript_snapshot(messages: List[Dict[str, Any]], *, label: str, max_items: int = 6) -> str:
    lines: List[str] = []
    for message in messages[-max_items:]:
        role = str(message.get("role", "unknown")).strip() or "unknown"
        content = " ".join(str(message.get("content", "")).split())
        if not content:
            continue
        if len(content) > 220:
            content = content[:217].rstrip() + "..."
        lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return f"{label} | " + " | ".join(lines)


def tokenize_match_text(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9ÁÉÍÓÖŐÚÜŰáéíóöőúüű_-]+", str(text or "").lower())
    seen: Set[str] = set()
    cleaned: List[str] = []
    for token in tokens:
        if len(token) < 3 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return cleaned


def count_overlap(query: str, content: str) -> int:
    query_tokens = tokenize_match_text(query)
    if not query_tokens:
        return 0
    content_lower = str(content or "").lower()
    return sum(1 for token in query_tokens if token in content_lower)


def has_meaningful_transcript_evidence(query: str, rows: Iterable[Dict[str, Any]]) -> bool:
    return any(int(row.get("overlap_count", 0)) > 0 for row in rows)
