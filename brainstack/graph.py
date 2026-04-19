from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from .db import BrainstackStore
from .graph_evidence import (
    GRAPH_EVIDENCE_BOUNDARY_VERSION,
    GraphEvidenceItem,
    coerce_graph_evidence_item,
    extract_graph_evidence_from_text,
)
from .provenance import merge_provenance


def ingest_graph_evidence(
    store: BrainstackStore,
    *,
    evidence_items: Sequence[GraphEvidenceItem | Mapping[str, Any]],
    source: str,
    metadata: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    base_metadata = dict(metadata or {})
    for raw_item in evidence_items:
        item = coerce_graph_evidence_item(raw_item)
        item_metadata = dict(base_metadata)
        item_metadata["graph_evidence_boundary"] = GRAPH_EVIDENCE_BOUNDARY_VERSION
        item_metadata["graph_evidence"] = item.to_dict()
        item_metadata["provenance"] = merge_provenance(
            item_metadata.get("provenance") if isinstance(item_metadata.get("provenance"), Mapping) else None,
            {
                "origin": item.provenance_class,
                "source_ids": [source],
                "status_reason": "typed_graph_evidence",
            },
        )

        if item.kind == "relation":
            relation_id = store.add_graph_relation(
                subject_name=item.subject,
                predicate=item.predicate,
                object_name=item.object_value,
                source=source,
                metadata=item_metadata,
            )
            results.append({"status": "relation", "relation_id": relation_id, **item.to_dict()})
            continue

        outcome = store.upsert_graph_state(
            subject_name=item.subject,
            attribute=item.attribute,
            value_text=item.value_text,
            source=source,
            supersede=bool(item.supersede),
            metadata=item_metadata,
        )
        results.append({**item.to_dict(), **outcome})
    return results


__all__ = [
    "GraphEvidenceItem",
    "extract_graph_evidence_from_text",
    "ingest_graph_evidence",
]
