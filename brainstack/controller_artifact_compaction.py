"""Compact verbose controller artifacts while keeping replay handles."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "brainstack.controller_artifact_compaction.v1"
DEFAULT_LARGE_FIELD_CHARS = 2_000


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_value(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class CompactedField:
    field: str
    digest: str
    raw_chars: int
    item_count: int | None
    replay_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compact_controller_artifact(
    artifact: Mapping[str, Any],
    *,
    large_field_chars: int = DEFAULT_LARGE_FIELD_CHARS,
    replay_base_ref: str | None = None,
) -> dict[str, Any]:
    compacted = dict(artifact)
    fields: list[CompactedField] = []
    for key, value in list(artifact.items()):
        if key in {"schema", "created_at", "verdict", "status", "task_id", "run_id"}:
            continue
        rendered = _canonical_json(value)
        if len(rendered) <= large_field_chars:
            continue
        digest = _digest_value(value)
        replay_ref = f"{replay_base_ref}#{key}:{digest[:16]}" if replay_base_ref else None
        item_count = len(value) if isinstance(value, (list, tuple, dict)) else None
        compacted[key] = {
            "compacted": True,
            "field": key,
            "digest": digest,
            "raw_chars": len(rendered),
            "item_count": item_count,
            "replay_ref": replay_ref,
        }
        fields.append(
            CompactedField(
                field=key,
                digest=digest,
                raw_chars=len(rendered),
                item_count=item_count,
                replay_ref=replay_ref,
            )
        )
    return {
        "schema": SCHEMA_VERSION,
        "compacted_artifact": compacted,
        "compacted_fields": [field.to_dict() for field in fields],
        "full_replay_required_for_compacted_fields": bool(fields),
    }


def compact_controller_artifact_file(path: Path, *, output_path: Path | None = None) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    result = compact_controller_artifact(artifact, replay_base_ref=str(path))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return result

