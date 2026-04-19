from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ..graph import ingest_graph_evidence
from ..graph_evidence import GraphEvidenceItem, attach_graph_source_context


def ingest_turn_graph_candidates(
    store,
    *,
    evidence_items: Sequence[GraphEvidenceItem | Mapping[str, Any]],
    session_id: str,
    turn_number: int,
    source: str,
    metadata: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    bound_items = attach_graph_source_context(
        evidence_items,
        session_id=session_id,
        turn_number=turn_number,
    )
    return ingest_graph_evidence(
        store,
        evidence_items=bound_items,
        source=source,
        metadata={**dict(metadata or {}), "session_id": session_id, "turn_number": turn_number},
    )


def ingest_session_graph_candidates(
    store,
    *,
    evidence_items: Sequence[GraphEvidenceItem | Mapping[str, Any]],
    session_id: str,
    source: str,
    metadata: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    bound_items = attach_graph_source_context(
        evidence_items,
        session_id=session_id,
    )
    return ingest_graph_evidence(
        store,
        evidence_items=bound_items,
        source=source,
        metadata={**dict(metadata or {}), "session_id": session_id},
    )
