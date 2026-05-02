"""Public-safe EvoMap/evolver signal classification.

Evolver is an external self-evolving developer engine. This module does not
install, run, or reimplement Evolver. It only classifies health/output signals
that a Hermes-owned proactive bridge may inspect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


EVOLVER_SIGNAL_SCHEMA = "hermes_proactive.evolver_signal.v1"
EVOLVER_SIGNAL_FILE_SCHEMA = "hermes_proactive.evolver_signal_file.v1"
MAX_SIGNAL_BYTES = 256 * 1024
MAX_STDOUT_CHARS = 16 * 1024
MAX_METADATA_KEYS = 64
MAX_HASH_CHARS = 64 * 1024

_SESSIONS_SPAWN_RE = re.compile(r"\bsessions_spawn\s*\(", re.IGNORECASE)
_PRIVATE_KEY_RE = re.compile(r"(secret|token|password|api[_-]?key|credential|private|prompt|content|text|error|exception|trace)", re.IGNORECASE)
_RAW_TEXT_KEYS = {
    "stdout",
    "stderr",
    "output",
    "log",
    "logs",
    "message",
    "messages",
    "details",
    "payload",
    "raw",
    "traceback",
}
_PUBLIC_SCALAR_KEYS = {"running", "pid", "exit_code", "version", "status", "uptime_seconds"}


def _hash_text(value: str) -> str:
    bounded = value[:MAX_HASH_CHARS]
    return hashlib.sha256(bounded.encode("utf-8", errors="replace")).hexdigest()[:16]


def _safe_str(value: Any, *, max_len: int = 80) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _public_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return {"redacted": True, "hash": _hash_text(value), "length": len(value)} if value else ""
    if isinstance(value, list | tuple):
        return {"type": "list", "count": len(value)}
    if isinstance(value, Mapping):
        return {"type": "object", "key_count": len(value)}
    return {"type": type(value).__name__}


def _public_metadata(raw: Mapping[str, Any]) -> dict[str, Any]:
    public: dict[str, Any] = {}
    for index, (key, value) in enumerate(raw.items()):
        if index >= MAX_METADATA_KEYS:
            public["metadata_truncated"] = True
            public["metadata_key_count"] = len(raw)
            break
        key_text = str(key)
        normalized_key = key_text.lower()
        if normalized_key in _RAW_TEXT_KEYS or _PRIVATE_KEY_RE.search(key_text):
            public[f"{key_text}_redacted"] = True
            if isinstance(value, str) and value:
                public[f"{key_text}_hash"] = _hash_text(value)
                public[f"{key_text}_length"] = len(value)
            continue
        if normalized_key in _PUBLIC_SCALAR_KEYS:
            public[key_text] = _public_value(value)
            continue
        public[f"{key_text}_redacted"] = True
        if isinstance(value, str) and value:
            public[f"{key_text}_hash"] = _hash_text(value)
            public[f"{key_text}_length"] = len(value)
        elif isinstance(value, (list, tuple, Mapping)):
            public[f"{key_text}_shape"] = _public_value(value)
    return public


def _raw_output_text(health: Mapping[str, Any], stdout: str) -> str:
    if stdout:
        return str(stdout)[:MAX_STDOUT_CHARS]
    for key in ("stdout", "stderr", "output", "log", "logs", "message", "messages", "payload", "raw", "traceback"):
        value = health.get(key)
        if isinstance(value, str) and value:
            return value[:MAX_STDOUT_CHARS]
    return ""


def _extract_directive_kinds(stdout: str) -> list[str]:
    kinds: list[str] = []
    if _SESSIONS_SPAWN_RE.search(stdout or ""):
        kinds.append("sessions_spawn")
    return kinds


@dataclass(frozen=True)
class EvolverSignalDecision:
    status: str
    reason_code: str
    running: bool | None = None
    actionable: bool = False
    directive_count: int = 0
    directive_kinds: tuple[str, ...] = ()
    safe_summary: str = ""
    source_ref: str = ""
    public_metadata: Mapping[str, Any] = field(default_factory=dict)
    raw_output_present: bool = False
    malformed: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema": EVOLVER_SIGNAL_SCHEMA,
            "source": "evomap_evolver",
            "status": self.status,
            "reason_code": self.reason_code,
            "running": self.running,
            "actionable": self.actionable,
            "directive_count": self.directive_count,
            "directive_kinds": list(self.directive_kinds),
            "directive_execution": "inert_data_only",
            "safe_summary": self.safe_summary,
            "source_ref": self.source_ref,
            "public_metadata": dict(self.public_metadata),
            "raw_output_present": self.raw_output_present,
            "malformed": self.malformed,
        }


def classify_evolver_signal(
    health: Mapping[str, Any] | None = None,
    *,
    stdout: str = "",
    source_ref: str = "",
    malformed: bool = False,
    malformed_reason: str = "",
) -> EvolverSignalDecision:
    """Classify an Evolver health/output signal without executing it."""

    health = dict(health or {})
    stdout_text = _raw_output_text(health, stdout)
    directive_kinds = tuple(_extract_directive_kinds(stdout_text))
    running_value = health.get("running")
    running = running_value if isinstance(running_value, bool) else None
    public = _public_metadata(health)
    if stdout_text:
        public["stdout_redacted"] = True
        public["stdout_hash"] = _hash_text(stdout_text)
    if malformed:
        reason = _safe_str(malformed_reason, max_len=120) or "Evolver signal could not be parsed."
        return EvolverSignalDecision(
            status="malformed",
            reason_code="EVOLVER_SIGNAL_MALFORMED",
            running=None,
            actionable=True,
            directive_count=0,
            safe_summary="Evolver signal is malformed and needs inspection.",
            source_ref=source_ref,
            public_metadata={"malformed_reason": reason},
            raw_output_present=bool(stdout_text),
            malformed=True,
        )
    if directive_kinds:
        return EvolverSignalDecision(
            status="actionable",
            reason_code="EVOLVER_DIRECTIVE_OBSERVED",
            running=running,
            actionable=True,
            directive_count=len(directive_kinds),
            directive_kinds=directive_kinds,
            safe_summary="Evolver emitted host-runtime directive text; Hermes must decide whether to interpret it.",
            source_ref=source_ref,
            public_metadata=public,
            raw_output_present=True,
        )
    if running is False:
        return EvolverSignalDecision(
            status="stopped",
            reason_code="EVOLVER_NOT_RUNNING",
            running=False,
            actionable=True,
            safe_summary="Evolver health reports stopped or unavailable state.",
            source_ref=source_ref,
            public_metadata=public,
            raw_output_present=bool(stdout_text),
        )
    if running is True:
        return EvolverSignalDecision(
            status="healthy",
            reason_code="EVOLVER_HEALTHY",
            running=True,
            safe_summary="Evolver health reports running state with no actionable directive.",
            source_ref=source_ref,
            public_metadata=public,
            raw_output_present=bool(stdout_text),
        )
    if health:
        return EvolverSignalDecision(
            status="observed",
            reason_code="EVOLVER_SIGNAL_OBSERVED",
            running=None,
            safe_summary="Evolver signal was observed without an actionable directive.",
            source_ref=source_ref,
            public_metadata=public,
            raw_output_present=bool(stdout_text),
        )
    return EvolverSignalDecision(
        status="missing",
        reason_code="EVOLVER_SIGNAL_MISSING",
        running=None,
        safe_summary="No Evolver signal was provided.",
        source_ref=source_ref,
        public_metadata={},
        raw_output_present=False,
    )


def load_evolver_signal_file(path: Path | None) -> EvolverSignalDecision:
    """Load and classify an Evolver signal file public-safely."""

    if path is None:
        return classify_evolver_signal(None)
    if not path.exists():
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason="signal_file_missing",
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason=f"{type(exc).__name__}",
        )
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            return classify_evolver_signal(
                None,
                source_ref=str(path),
                malformed=True,
                malformed_reason="signal_file_not_regular",
            )
        if file_stat.st_size > MAX_SIGNAL_BYTES:
            return classify_evolver_signal(
                None,
                source_ref=str(path),
                malformed=True,
                malformed_reason="signal_file_too_large",
            )
        raw = os.read(fd, MAX_SIGNAL_BYTES + 1)
    except OSError as exc:
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason=f"{type(exc).__name__}",
        )
    finally:
        os.close(fd)
    if len(raw) > MAX_SIGNAL_BYTES:
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason="signal_file_too_large",
        )
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - malformed external signal must be visible.
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason=f"{type(exc).__name__}",
        )
    if not isinstance(loaded, Mapping):
        return classify_evolver_signal(
            None,
            source_ref=str(path),
            malformed=True,
            malformed_reason="signal_file_not_object",
        )
    return classify_evolver_signal(loaded, source_ref=str(path))


__all__ = [
    "EVOLVER_SIGNAL_FILE_SCHEMA",
    "EVOLVER_SIGNAL_SCHEMA",
    "EvolverSignalDecision",
    "classify_evolver_signal",
    "load_evolver_signal_file",
]
