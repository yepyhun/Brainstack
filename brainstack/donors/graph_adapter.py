from __future__ import annotations

from typing import Any, Dict, List

from ..graph import ingest_graph_candidates


def ingest_turn_graph_candidates(
    store,
    *,
    text: str,
    session_id: str,
    turn_number: int,
    source: str,
) -> List[Dict[str, Any]]:
    return ingest_graph_candidates(
        store,
        text=text,
        source=source,
        metadata={"session_id": session_id, "turn_number": turn_number},
    )


def ingest_session_graph_candidates(
    store,
    *,
    text: str,
    session_id: str,
    source: str,
) -> List[Dict[str, Any]]:
    return ingest_graph_candidates(
        store,
        text=text,
        source=source,
        metadata={"session_id": session_id},
    )
