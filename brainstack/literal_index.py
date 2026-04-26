from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any, Mapping

LITERAL_INDEX_SCHEMA = "brainstack.literal_index.v1"
EVENT_INDEX_SCHEMA = "brainstack.user_turn_event_index.v1"

ANSWER_LITERAL_CLASSES = {"safe_identifier", "version", "filename", "citation_id"}
SUPPORT_ONLY_LITERAL_CLASSES = {"private_path", "secret_shaped", "unknown"}

_PATH_RE = re.compile(r"(?:/[\w .@+-]+){2,}(?:/[\w .@+-]+)?")
_WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\(?:[^\\\s]+\\?)+")
_TOKEN_RE = re.compile(r"(?<![\w@])[\w][\w.+:-]{2,}[\w](?![\w@])", re.UNICODE)
_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+){1,4}(?:[-+][A-Za-z0-9_.-]+)?$")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,8}$")
_CITATION_RE = re.compile(r"^(?:[A-Z]{1,8}[-_:])?\d{1,6}(?:[-_:][A-Z0-9]{1,8})?$")
_SECRET_RE = re.compile(
    r"(?i)^(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|xox[baprs]-[A-Za-z0-9-]{12,}|"
    r"[A-Za-z0-9_-]{32,})$"
)


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:16]


def _shape_for(value: str) -> dict[str, Any]:
    stripped = str(value or "")
    return {
        "length": len(stripped),
        "prefix": stripped[:3] if len(stripped) >= 3 else stripped,
        "suffix": stripped[-1:] if stripped else "",
        "has_digit": any(ch.isdigit() for ch in stripped),
        "has_alpha": any(ch.isalpha() for ch in stripped),
        "has_separator": any(ch in stripped for ch in ("-", "_", ".", ":", "/")),
    }


def classify_literal(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        return "unknown"
    if _SECRET_RE.match(token):
        return "secret_shaped"
    if token.startswith(("/home/", "/Users/", "/root/", "/tmp/")) or _WINDOWS_PATH_RE.match(token):
        return "private_path"
    if token.startswith(("/", "\\")):
        return "public_path" if not token.startswith(("/home/", "/Users/", "/root/", "/tmp/")) else "private_path"
    if _VERSION_RE.match(token):
        return "version"
    if _FILENAME_RE.match(token):
        return "filename"
    if _CITATION_RE.match(token) and any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
        return "citation_id"
    if len(token) >= 5 and any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token):
        return "safe_identifier"
    if len(token) >= 6 and any(ch in token for ch in ("_", "-", ":")):
        return "safe_identifier"
    return "unknown"


def _model_value(value: str, literal_class: str) -> str:
    if literal_class == "secret_shaped":
        return f"[secret:{_hash_value(value)}]"
    if literal_class == "private_path":
        return f"[private_path:{_hash_value(value)}]"
    return value


def detect_literal_tokens(text: str, *, limit: int = 12) -> list[dict[str, Any]]:
    """Extract exact literal sidecars without language-specific keyword logic."""
    value_by_seen: dict[str, str] = {}
    for match in [*_PATH_RE.finditer(str(text or "")), *_WINDOWS_PATH_RE.finditer(str(text or ""))]:
        value = match.group(0).strip().rstrip(".,;)")
        if value:
            value_by_seen.setdefault(value, value)
    for match in _TOKEN_RE.finditer(str(text or "")):
        value = match.group(0).strip().rstrip(".,;)")
        if len(value) < 4:
            continue
        literal_class = classify_literal(value)
        if literal_class == "unknown":
            continue
        value_by_seen.setdefault(value, value)
        if len(value_by_seen) >= limit:
            break

    tokens: list[dict[str, Any]] = []
    for raw_value in value_by_seen.values():
        literal_class = classify_literal(raw_value)
        if literal_class == "unknown":
            continue
        tokens.append(
            {
                "value": _model_value(raw_value, literal_class),
                "class": literal_class,
                "case_sensitive": any(ch.isalpha() and ch.isupper() for ch in raw_value),
                "shape": _shape_for(raw_value),
                "raw_hash": _hash_value(raw_value),
                "model_facing": literal_class in ANSWER_LITERAL_CLASSES or literal_class in {"public_path"},
            }
        )
        if len(tokens) >= limit:
            break
    return tokens


def redact_literal_text(text: str, *, literal_tokens: list[Mapping[str, Any]] | None = None) -> str:
    """Redact high-risk literals from model-facing snippets."""
    output = str(text or "")
    for match in [*_PATH_RE.finditer(output), *_WINDOWS_PATH_RE.finditer(output), *_TOKEN_RE.finditer(output)]:
        raw = match.group(0).strip().rstrip(".,;)")
        literal_class = classify_literal(raw)
        if literal_class not in {"private_path", "secret_shaped"}:
            continue
        output = output.replace(raw, _model_value(raw, literal_class))
    for token in literal_tokens or []:
        literal_class = str(token.get("class") or "")
        value = str(token.get("value") or "")
        if literal_class in {"private_path", "secret_shaped"} and value and value not in output:
            continue
    return output


def semantic_anchor_text(text: str, *, literal_tokens: Sequence[Mapping[str, Any]] | None = None, limit: int = 160) -> str:
    anchor = str(text or "")
    for token in literal_tokens or detect_literal_tokens(anchor):
        value = str(token.get("value") or "")
        if value and not value.startswith("["):
            anchor = anchor.replace(value, " ")
    anchor = redact_literal_text(anchor)
    anchor = " ".join(anchor.split())
    return anchor[: max(32, int(limit))]


def _terms(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[^\W_]+", str(value or ""), flags=re.UNICODE) if len(token) >= 3}


def _query_shape_hints(query: str) -> dict[str, set[str]]:
    tokens = [token.casefold() for token in re.findall(r"[^\W_]+", str(query or ""), flags=re.UNICODE) if token]
    return {
        "prefixes": {token for token in tokens if token.isdigit() and len(token) >= 2},
        "suffixes": {token for token in tokens if len(token) == 1 and token.isalpha()},
    }


def literal_slot_match(
    *,
    query: str,
    text: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect literal-slot matches without language-specific phrase lists."""
    metadata = metadata if isinstance(metadata, Mapping) else {}
    literal_index = metadata.get("literal_index")
    literal_index = literal_index if isinstance(literal_index, Mapping) else literal_sidecar_for_text(text)
    tokens = [token for token in list(literal_index.get("literal_tokens") or []) if isinstance(token, Mapping)]
    if not tokens:
        return {"matched": False, "reason": "no_literal_tokens"}

    anchor = str(literal_index.get("semantic_anchor_text") or semantic_anchor_text(text, literal_tokens=tokens))
    anchor_overlap = sorted(_terms(query) & _terms(anchor))
    if not anchor_overlap:
        return {"matched": False, "reason": "no_anchor_overlap"}

    hints = _query_shape_hints(query)
    matched_values: list[str] = []
    for token in tokens:
        raw_shape = token.get("shape")
        shape = raw_shape if isinstance(raw_shape, Mapping) else {}
        prefix = str(shape.get("prefix") or "").casefold()
        suffix = str(shape.get("suffix") or "").casefold()
        if prefix and any(prefix.startswith(hint) for hint in hints["prefixes"]):
            matched_values.append(str(token.get("value") or ""))
            continue
        if suffix and suffix in hints["suffixes"]:
            matched_values.append(str(token.get("value") or ""))

    if not matched_values:
        return {"matched": False, "reason": "anchor_without_shape", "anchor_overlap": anchor_overlap}
    return {
        "matched": True,
        "reason": "anchor_and_literal_shape",
        "anchor_overlap": anchor_overlap,
        "literal_values": matched_values[:4],
    }


def literal_sidecar_for_text(text: str) -> dict[str, Any]:
    tokens = detect_literal_tokens(text)
    return {
        "schema": LITERAL_INDEX_SCHEMA,
        "literal_tokens": tokens,
        "semantic_anchor_text": semantic_anchor_text(text, literal_tokens=tokens),
    }


def event_type_for_turn(kind: str, metadata: Mapping[str, Any] | None = None) -> str:
    metadata = metadata if isinstance(metadata, Mapping) else {}
    explicit = str(metadata.get("event_type") or "").strip()
    if explicit in {"user_question", "user_request", "user_assertion", "user_correction", "assistant_response"}:
        return explicit
    normalized = str(kind or "").casefold()
    if "assistant" in normalized:
        return "assistant_response"
    if "question" in normalized:
        return "user_question"
    if "request" in normalized or "command" in normalized:
        return "user_request"
    if "correction" in normalized:
        return "user_correction"
    if "user" in normalized:
        return "user_turn"
    return "turn"


def safe_preview(text: str, *, limit: int = 240) -> str:
    redacted = redact_literal_text(text)
    redacted = " ".join(redacted.split())
    return redacted[: max(32, int(limit))]


def user_turn_event_sidecar(
    *,
    row_id: int | None,
    session_id: str,
    turn_number: int,
    kind: str,
    content: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    tokens = detect_literal_tokens(content)
    raw_hash = hashlib.sha256(str(content or "").encode("utf-8", "replace")).hexdigest()
    event_type = event_type_for_turn(kind, metadata)
    return {
        "schema": EVENT_INDEX_SCHEMA,
        "event_id": f"{session_id}:{turn_number}:{row_id or 0}:{event_type}",
        "transcript_row_id": int(row_id or 0),
        "session_id": str(session_id or ""),
        "turn_number": int(turn_number or 0),
        "event_type": event_type,
        "raw_text_hash": raw_hash,
        "safe_preview": safe_preview(content),
        "literal_tokens": tokens,
        "semantic_anchor_text": semantic_anchor_text(content, literal_tokens=tokens),
        "bounded_scope_only": True,
    }


def enrich_metadata_with_literal_sidecar(
    metadata: Mapping[str, Any] | None,
    *,
    text: str,
    event: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload["literal_index"] = literal_sidecar_for_text(text)
    if event is not None:
        payload["conversation_event"] = dict(event)
    return payload
