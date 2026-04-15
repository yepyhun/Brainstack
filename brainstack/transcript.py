from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set


STRUCTURAL_TOKENS = {
    "assistant",
    "system",
    "tool",
    "user",
}
RETRIEVAL_QUERY_STOPWORDS = {
    "and",
    "about",
    "am",
    "are",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "give",
    "had",
    "has",
    "have",
    "how",
    "into",
    "is",
    "know",
    "past",
    "please",
    "that",
    "the",
    "their",
    "them",
    "these",
    "this",
    "tell",
    "then",
    "through",
    "to",
    "took",
    "with",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "would",
}
TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)

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
    tokens = TOKEN_RE.findall(str(text or "").casefold())
    seen: Set[str] = set()
    cleaned: List[str] = []
    for token in tokens:
        if len(token) < 3 or token in STRUCTURAL_TOKENS or token in seen:
            continue
        seen.add(token)
        cleaned.append(token)
    return cleaned


def tokenize_retrieval_query(text: str) -> List[str]:
    cleaned = [token for token in tokenize_match_text(text) if token not in RETRIEVAL_QUERY_STOPWORDS]
    expanded: List[str] = []
    seen: Set[str] = set()
    for token in cleaned:
        variants = [token]
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            variants.append(token[:-1])
        for variant in variants:
            if variant in seen:
                continue
            seen.add(variant)
            expanded.append(variant)
    return expanded


def count_overlap(query: str, content: str) -> int:
    query_tokens = tokenize_retrieval_query(query)
    if not query_tokens:
        return 0
    content_tokens = set(tokenize_match_text(content))
    return sum(1 for token in query_tokens if token in content_tokens)


def has_meaningful_transcript_evidence(query: str, rows: Iterable[Dict[str, Any]]) -> bool:
    for row in rows:
        if int(row.get("overlap_count", 0)) > 0:
            return True
        if str(row.get("match_mode") or "").strip() == "semantic" and float(row.get("semantic_score") or 0.0) > 0.0:
            return True
        if (
            str(row.get("match_mode") or "").strip() == "support"
            and str(row.get("retrieval_source") or "").strip() == "transcript.session_support"
            and bool(row.get("same_principal"))
        ):
            return True
    return False
