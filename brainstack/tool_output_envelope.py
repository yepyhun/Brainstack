"""Capability-preserving tool output envelopes.

The model sees a bounded summary. Full output stays available through an
inspectable handle when an artifact directory is provided.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import re
import time
from typing import Any


SCHEMA_VERSION = "brainstack.tool_output_envelope.v1"
DEFAULT_INLINE_CHAR_BUDGET = 2_400
DEFAULT_ARTIFACT_THRESHOLD_CHARS = 3_200
SECRET_SHAPED_RE = re.compile(
    r"(?i)(sk-[a-z0-9_-]{12,}|api[_-]?key|token|secret|password|bearer\s+[a-z0-9._-]{12,})"
)


def _safe_slug(value: str, *, limit: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "tool")).strip("_")
    return (slug or "tool")[:limit]


def _redact_preview(text: str) -> str:
    return SECRET_SHAPED_RE.sub("[REDACTED_SECRET_SHAPED]", text)


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class ToolOutputEnvelope:
    schema: str
    tool_name: str
    content_hash: str
    raw_chars: int
    raw_lines: int
    inline_chars: int
    omitted_chars: int
    truncated: bool
    model_facing_text: str
    full_output_ref: str | None
    expansion_instruction: str
    error_hint: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_tool_output_artifact(
    *,
    artifact_dir: Path,
    tool_name: str,
    output: str,
    content_hash: str | None = None,
) -> str:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    digest = content_hash or _hash_text(output)
    path = artifact_dir / f"{int(time.time())}_{_safe_slug(tool_name)}_{digest[:12]}.txt"
    path.write_text(output, encoding="utf-8", errors="replace")
    return str(path)


def build_tool_output_envelope(
    *,
    tool_name: str,
    output: str,
    inline_char_budget: int = DEFAULT_INLINE_CHAR_BUDGET,
    artifact_threshold_chars: int = DEFAULT_ARTIFACT_THRESHOLD_CHARS,
    artifact_dir: Path | None = None,
) -> ToolOutputEnvelope:
    raw = str(output or "")
    digest = _hash_text(raw)
    raw_chars = len(raw)
    raw_lines = len(raw.splitlines())
    error_hint = bool(re.search(r"\b(error|failed|traceback|exception|timeout|critical)\b", raw, re.I))

    truncated = raw_chars > inline_char_budget
    if truncated:
        head_budget = max(200, inline_char_budget // 2)
        tail_budget = max(200, inline_char_budget - head_budget - 160)
        preview = (
            raw[:head_budget].rstrip()
            + "\n\n[... tool output omitted ...]\n\n"
            + raw[-tail_budget:].lstrip()
        )
    else:
        preview = raw

    full_ref: str | None = None
    if raw_chars > artifact_threshold_chars and artifact_dir is not None:
        full_ref = write_tool_output_artifact(
            artifact_dir=artifact_dir,
            tool_name=tool_name,
            output=raw,
            content_hash=digest,
        )

    omitted = max(0, raw_chars - len(preview))
    instruction = (
        "Use the inline preview for triage. Open full_output_ref when exact omitted lines, "
        "full logs, or complete evidence are required."
        if full_ref
        else "Full output is inline or no artifact directory was provided; rerun/refine the tool if exact omitted content is required."
    )
    return ToolOutputEnvelope(
        schema=SCHEMA_VERSION,
        tool_name=str(tool_name or "unknown_tool"),
        content_hash=digest,
        raw_chars=raw_chars,
        raw_lines=raw_lines,
        inline_chars=len(preview),
        omitted_chars=omitted,
        truncated=truncated,
        model_facing_text=_redact_preview(preview),
        full_output_ref=full_ref,
        expansion_instruction=instruction,
        error_hint=error_hint,
    )

