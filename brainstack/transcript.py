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

ROLE_PREFIX_RE = re.compile(r"^\s*(user|assistant|system|tool)\s*:\s*", re.IGNORECASE)


def trim_text_boundary(text: Any, *, max_len: int = 220, soft_overshoot: int = 24) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= max_len:
        return normalized

    upper_bound = min(len(normalized), max_len + max(0, soft_overshoot))
    forward_window = normalized[max_len:upper_bound]

    for index, char in enumerate(forward_window, start=max_len):
        if char in ".!?;:)]":
            snippet = normalized[: index + 1].rstrip()
            return snippet if len(snippet) >= len(normalized) else f"{snippet}..."

    for index, char in enumerate(forward_window, start=max_len):
        if char.isspace():
            snippet = normalized[:index].rstrip()
            return snippet if len(snippet) >= len(normalized) else f"{snippet}..."

    backward_window = normalized[:max_len]
    boundary = max(
        backward_window.rfind(" "),
        backward_window.rfind("."),
        backward_window.rfind(","),
        backward_window.rfind(";"),
        backward_window.rfind(":"),
        backward_window.rfind(")"),
    )
    if boundary >= int(max_len * 0.6):
        snippet = backward_window[:boundary].rstrip()
        return snippet if len(snippet) >= len(normalized) else f"{snippet}..."

    fallback = normalized[: max(0, max_len - 3)].rstrip()
    return fallback if len(fallback) >= len(normalized) else f"{fallback}..."


def format_turn_content(user_content: str, assistant_content: str) -> str:
    user = " ".join(str(user_content or "").split())
    assistant = " ".join(str(assistant_content or "").split())
    return f"User: {user}\nAssistant: {assistant}".strip()


def build_turn_summary(user_content: str, assistant_content: str, *, max_len: int = 220) -> str:
    user = trim_text_boundary(user_content, max_len=max_len)
    assistant = trim_text_boundary(assistant_content, max_len=max_len)
    return f"user: {user} | assistant: {assistant}".strip()


def build_transcript_snapshot(messages: List[Dict[str, Any]], *, label: str, max_items: int = 6) -> str:
    lines: List[str] = []
    for message in messages[-max_items:]:
        role = str(message.get("role", "unknown")).strip() or "unknown"
        content = trim_text_boundary(message.get("content", ""), max_len=220)
        if not content:
            continue
        lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return f"{label} | " + " | ".join(lines)


def count_role_prefixed_lines(text: str) -> int:
    return sum(1 for line in str(text or "").splitlines() if ROLE_PREFIX_RE.match(line))


def looks_like_role_transcript_dump(text: str) -> bool:
    lines = [line for line in str(text or "").splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    return count_role_prefixed_lines(text) >= 2


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
    for row in rows:
        if int(row.get("overlap_count", 0)) > 0:
            return True
        if str(row.get("match_mode") or "").strip() == "semantic" and float(row.get("semantic_score") or 0.0) > 0.0:
            return True
    return False
