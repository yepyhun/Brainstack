from __future__ import annotations

from dataclasses import dataclass, field
import re

from .transcript import looks_like_role_transcript_dump


_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"(?:^|[^a-z])(sk|pk|ghp)[-_][a-z0-9]{20,}", re.IGNORECASE)),
    ("password_assignment", re.compile(r"password\s*[=:]\s*\S{6,}", re.IGNORECASE)),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("private_key", re.compile(r"-----BEGIN\s+\S+\s+PRIVATE KEY-----")),
)
_STACKTRACE_HINT_RE = re.compile(r"\b(traceback|stack trace|exception:)\b", re.IGNORECASE)
_STACKTRACE_LINE_RE = re.compile(
    r"(?:^|\n)\s*at\s+[A-Za-z0-9_.:$<>]+(?:\.[A-Za-z0-9_.:$<>]+)*(?:\s*\(|:\d)",
    re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"```|~~~")
_CODEY_LINE_RE = re.compile(r"^\s*(?:def |class |function |\{|\}|\$ |#include|import |from |return |if |for |while )")
_PIPE_TABLE_RE = re.compile(r"^\s*\|.+\|\s*$")
_PIPE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){1,}\s*$")
_BULLET_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEADING_LINE_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_QUOTE_LINE_RE = re.compile(r"^\s*>\s+")


@dataclass(frozen=True)
class StableMemoryAdmissionDecision:
    allowed: bool
    reason: str
    secret_pattern: str | None = None
    matched_rules: tuple[str, ...] = field(default_factory=tuple)


def _compact_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in str(text or "").strip().splitlines())


def detect_secret_pattern(text: str) -> str | None:
    value = str(text or "")
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            return name
    return None


def _nonempty_lines(text: str) -> list[str]:
    return [line for line in str(text or "").splitlines() if line.strip()]


def _looks_like_markdown_table(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    pipe_rows = [line for line in lines if _PIPE_TABLE_RE.match(line)]
    if len(pipe_rows) < 2:
        return False
    return any(_PIPE_SEPARATOR_RE.match(line) for line in lines)


def _looks_like_code_blob(text: str, lines: list[str]) -> bool:
    if _CODE_FENCE_RE.search(text):
        return True
    codey_lines = sum(1 for line in lines if _CODEY_LINE_RE.match(line))
    long_indented = sum(1 for line in lines if len(line) > 32 and line.startswith("    "))
    return codey_lines >= 3 or long_indented >= 3


def _looks_like_uploaded_document_wrapper(text: str, lines: list[str]) -> bool:
    lowered = text.lower()
    wrapper_hits = 0
    for hint in (
        "attached file",
        "uploaded file",
        "document excerpt",
        "source url",
        "filename:",
        "file name:",
        "pages:",
        "page ",
        "section ",
        "appendix",
        "excerpt:",
    ):
        if hint in lowered:
            wrapper_hits += 1
    return wrapper_hits >= 2 and (len(lines) >= 4 or len(text) > 260)


def _looks_like_structured_technical_blob(text: str, lines: list[str]) -> bool:
    if len(lines) < 5:
        return False
    structured_lines = sum(1 for line in lines if _BULLET_LINE_RE.match(line) or _HEADING_LINE_RE.match(line) or _QUOTE_LINE_RE.match(line))
    punctuation = sum(text.count(ch) for ch in ("|", "`", "{", "}", "[", "]"))
    return structured_lines >= 4 or (len(text) > 260 and punctuation >= 8)


def should_admit_stable_memory(*, fact_text: str) -> StableMemoryAdmissionDecision:
    text = _compact_text(fact_text)
    if not text:
        return StableMemoryAdmissionDecision(False, "empty_fact")

    secret = detect_secret_pattern(text)
    if secret:
        return StableMemoryAdmissionDecision(False, "secret_detected", secret_pattern=secret, matched_rules=("secret",))

    if len(text) > 800:
        return StableMemoryAdmissionDecision(False, "too_long", matched_rules=("length",))

    if _STACKTRACE_HINT_RE.search(text) or _STACKTRACE_LINE_RE.search(text):
        return StableMemoryAdmissionDecision(False, "stacktrace_like", matched_rules=("stacktrace",))

    lines = _nonempty_lines(text)

    if _looks_like_markdown_table(lines):
        return StableMemoryAdmissionDecision(False, "markdown_table", matched_rules=("markdown_table",))

    if _looks_like_code_blob(text, lines):
        return StableMemoryAdmissionDecision(False, "code_blob", matched_rules=("code_blob",))

    quote_lines = sum(1 for line in lines if _QUOTE_LINE_RE.match(line))
    if looks_like_role_transcript_dump(text) or quote_lines >= 3:
        return StableMemoryAdmissionDecision(False, "quoted_transcript_dump", matched_rules=("transcript_dump",))

    if _looks_like_uploaded_document_wrapper(text, lines):
        return StableMemoryAdmissionDecision(False, "document_wrapper", matched_rules=("document_wrapper",))

    if _looks_like_structured_technical_blob(text, lines):
        return StableMemoryAdmissionDecision(False, "structured_technical_blob", matched_rules=("structured_blob",))

    if len(text.split()) < 3:
        return StableMemoryAdmissionDecision(False, "too_short", matched_rules=("length",))

    return StableMemoryAdmissionDecision(True, "allowed")
