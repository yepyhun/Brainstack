from __future__ import annotations

from typing import List, Dict, Any

from ..transcript import build_transcript_snapshot, build_turn_summary, format_turn_content


def write_turn_records(
    store,
    *,
    session_id: str,
    turn_number: int,
    user_content: str,
    assistant_content: str,
) -> None:
    store.add_continuity_event(
        session_id=session_id,
        turn_number=turn_number,
        kind="turn",
        content=build_turn_summary(user_content, assistant_content),
        source="sync_turn",
    )
    store.add_transcript_entry(
        session_id=session_id,
        turn_number=turn_number,
        kind="turn",
        content=format_turn_content(user_content, assistant_content),
        source="sync_turn",
    )


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
) -> str:
    summary = build_transcript_snapshot(messages, label=label, max_items=max_items)
    if not summary:
        return ""
    store.add_continuity_event(
        session_id=session_id,
        turn_number=turn_number,
        kind=kind,
        content=summary,
        source=source,
    )
    store.add_transcript_entry(
        session_id=session_id,
        turn_number=turn_number,
        kind=kind,
        content=summary,
        source=source,
    )
    return summary
