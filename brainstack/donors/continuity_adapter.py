from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from ..transcript import (
    build_transcript_snapshot,
    build_turn_summary,
    format_turn_content,
    trim_text_boundary,
)


def write_turn_records(
    store,
    *,
    session_id: str,
    turn_number: int,
    user_content: str,
    assistant_content: str,
    created_at: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> None:
    store.add_continuity_event(
        session_id=session_id,
        turn_number=turn_number,
        kind="turn",
        content=build_turn_summary(user_content, assistant_content),
        source="sync_turn",
        created_at=created_at,
        metadata=metadata,
    )
    store.add_transcript_entry(
        session_id=session_id,
        turn_number=turn_number,
        kind="turn",
        content=format_turn_content(user_content, assistant_content),
        source="sync_turn",
        created_at=created_at,
        metadata=metadata,
    )


def build_snapshot_source_window(
    messages: List[Dict[str, Any]],
    *,
    max_items: int,
    preview_chars: int = 96,
) -> Dict[str, Any]:
    bounded_messages = list(messages[-max(0, int(max_items)):]) if max_items else []
    start_index = max(0, len(messages) - len(bounded_messages))
    previews: List[Dict[str, Any]] = []
    digest_parts: List[str] = []
    for offset, message in enumerate(bounded_messages):
        role = str(message.get("role", "unknown")).strip() or "unknown"
        preview = trim_text_boundary(message.get("content", ""), max_len=preview_chars)
        if not preview:
            continue
        previews.append(
            {
                "index": start_index + offset,
                "role": role,
                "preview": preview,
            }
        )
        digest_parts.append(f"{role}:{preview}")

    digest = ""
    if digest_parts:
        digest = hashlib.sha1("||".join(digest_parts).encode("utf-8")).hexdigest()[:16]

    return {
        "input_message_count": len(messages),
        "captured_message_count": len(previews),
        "source_window_start": start_index if previews else 0,
        "window_digest": digest,
        "source_window": previews,
    }


def write_snapshot_records(
    store,
    *,
    session_id: str,
    turn_number: int,
    messages: List[Dict[str, Any]],
    label: str,
    kind: str,
    source: str,
    max_items: int,
    created_at: str | None = None,
    metadata: Dict[str, Any] | None = None,
) -> str:
    summary = build_transcript_snapshot(messages, label=label, max_items=max_items)
    if not summary:
        return ""
    enriched_metadata = dict(metadata or {})
    enriched_metadata.setdefault("session_id", session_id)
    enriched_metadata.setdefault("turn_number", turn_number)
    enriched_metadata.setdefault("origin", source)
    provenance = build_snapshot_source_window(messages, max_items=max_items)
    existing_provenance = enriched_metadata.get("provenance")
    merged_provenance = dict(existing_provenance) if isinstance(existing_provenance, dict) else {}
    merged_provenance.update(provenance)
    enriched_metadata["provenance"] = merged_provenance
    store.add_continuity_event(
        session_id=session_id,
        turn_number=turn_number,
        kind=kind,
        content=summary,
        source=source,
        created_at=created_at,
        metadata=enriched_metadata,
    )
    store.add_transcript_entry(
        session_id=session_id,
        turn_number=turn_number,
        kind=kind,
        content=summary,
        source=source,
        created_at=created_at,
        metadata=enriched_metadata,
    )
    return summary
