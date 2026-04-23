from __future__ import annotations

import re
from typing import Any, Dict, List

ROLE_PREFIX_RE = re.compile(r"^\s*(user|assistant|system|tool)\s*:\s*", re.IGNORECASE)


def normalize_multiline_text(value: Any) -> str:
    lines = []
    for raw_line in str(value or "").splitlines():
        cleaned = " ".join(raw_line.split())
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


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


def split_turn_content(content: Any) -> Dict[str, str]:
    parts: Dict[str, List[str]] = {
        "user": [],
        "assistant": [],
        "system": [],
        "tool": [],
        "other": [],
    }
    current = "other"
    for raw_line in str(content or "").splitlines():
        cleaned = " ".join(raw_line.split())
        if not cleaned:
            continue
        matched_role = None
        for role in ("user", "assistant", "system", "tool"):
            prefix = f"{role}:"
            if cleaned.casefold().startswith(prefix):
                matched_role = role
                body = cleaned[len(prefix):].strip()
                current = role
                if body:
                    parts[role].append(body)
                break
        if matched_role is None:
            parts[current].append(cleaned)
    return {key: "\n".join(lines).strip() for key, lines in parts.items()}


def primary_user_turn_content(content: Any) -> str:
    parts = split_turn_content(content)
    user = parts.get("user", "").strip()
    if user:
        return user
    return normalize_multiline_text(content)


def format_turn_content(user_content: str, assistant_content: str) -> str:
    user = normalize_multiline_text(user_content)
    assistant = normalize_multiline_text(assistant_content)
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
