"""Skill progressive-disclosure audit helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = "brainstack.skill_runtime_audit.v1"
DEFAULT_OVERSIZED_SKILL_CHARS = 8_000


@dataclass(frozen=True)
class SkillAuditEntry:
    path: str
    chars: int
    content_hash: str
    has_references_dir: bool
    verdict: str
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reason_codes"] = list(self.reason_codes)
        return data


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _iter_skill_files(roots: Sequence[Path]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        if root.name == "SKILL.md" and root.is_file():
            yield root
            continue
        yield from root.rglob("SKILL.md")


def audit_skill_files(
    roots: Sequence[Path],
    *,
    oversized_chars: int = DEFAULT_OVERSIZED_SKILL_CHARS,
) -> dict[str, Any]:
    entries: list[SkillAuditEntry] = []
    for path in sorted(set(_iter_skill_files(roots))):
        text = path.read_text(encoding="utf-8", errors="replace")
        reasons: list[str] = []
        if len(text) > oversized_chars:
            reasons.append("OVERSIZED_ENTRYPOINT")
        has_refs = (path.parent / "references").is_dir()
        if len(text) > oversized_chars and not has_refs:
            reasons.append("NO_REFERENCES_DIR")
        verdict = "degraded" if reasons else "healthy"
        entries.append(
            SkillAuditEntry(
                path=str(path),
                chars=len(text),
                content_hash=_hash_text(text),
                has_references_dir=has_refs,
                verdict=verdict,
                reason_codes=tuple(reasons),
            )
        )
    degraded = [entry for entry in entries if entry.verdict != "healthy"]
    return {
        "schema": SCHEMA_VERSION,
        "verdict": "degraded" if degraded else "healthy",
        "oversized_threshold_chars": oversized_chars,
        "skill_count": len(entries),
        "degraded_count": len(degraded),
        "entries": [entry.to_dict() for entry in entries],
        "policy": {
            "auto_rewrite_unknown_skills": False,
            "recommended_pattern": "short_SKILL_md_entrypoint_plus_focused_references",
        },
    }


def validate_skill_view_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate that a skill_view result exposes progressive-disclosure metadata."""

    content_mode = payload.get("content_mode")
    has_hash = isinstance(payload.get("content_hash"), str) and bool(payload.get("content_hash"))
    already_loaded = "already_loaded_in_session" in payload
    full_available = payload.get("full_content_available") is True or content_mode == "full"
    missing = []
    if content_mode not in {"summary", "auto", "full"}:
        missing.append("content_mode")
    if not has_hash:
        missing.append("content_hash")
    if not already_loaded:
        missing.append("already_loaded_in_session")
    return {
        "schema": "brainstack.skill_view_payload_validation.v1",
        "verdict": "healthy" if not missing else "degraded",
        "missing": missing,
        "full_content_available": full_available,
    }

