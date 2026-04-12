from __future__ import annotations

import re
from typing import Any, Dict, List

from .db import BrainstackStore


STATUS_WORDS = {"active", "paused", "archived", "completed", "retired", "pending"}
SUPERSEDE_MARKERS = (" now", " currently", " changed to", " no longer", " from ")


def _clean_value(value: str) -> str:
    return " ".join(value.strip().strip(" .").split())


def _should_supersede(sentence: str) -> bool:
    lowered = f" {sentence.lower()} "
    return any(marker in lowered for marker in SUPERSEDE_MARKERS)


def _extract_graph_candidates(text: str) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not text:
        return candidates

    sentences = [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]
    for sentence in sentences:
        cleaned = " ".join(sentence.split())

        relation_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+works on\s+(?P<object>[A-Z][A-Za-z0-9_ /-]{1,80})",
            cleaned,
        )
        if relation_match:
            candidates.append(
                {
                    "kind": "relation",
                    "subject": _clean_value(relation_match.group("subject")),
                    "predicate": "works_on",
                    "object": _clean_value(relation_match.group("object")),
                }
            )

        location_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+is\s+(?:in|at)\s+(?P<value>[A-Z][A-Za-z0-9_ /-]{1,80})",
            cleaned,
        )
        if location_match:
            candidates.append(
                {
                    "kind": "state",
                    "subject": _clean_value(location_match.group("subject")),
                    "attribute": "location",
                    "value": _clean_value(location_match.group("value")),
                    "supersede": _should_supersede(cleaned),
                }
            )

        status_match = re.search(
            r"(?P<subject>[A-Z][A-Za-z0-9_ /-]{1,60}?)\s+is\s+(?P<value>active|paused|archived|completed|retired|pending)(?:\s+now|\s+currently)?",
            cleaned,
            re.IGNORECASE,
        )
        if status_match:
            candidates.append(
                {
                    "kind": "state",
                    "subject": _clean_value(status_match.group("subject")),
                    "attribute": "status",
                    "value": status_match.group("value").lower(),
                    "supersede": _should_supersede(cleaned),
                }
            )

    return candidates


def ingest_graph_candidates(
    store: BrainstackStore,
    *,
    text: str,
    source: str,
    metadata: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for candidate in _extract_graph_candidates(text):
        if candidate["kind"] == "relation":
            relation_id = store.add_graph_relation(
                subject_name=candidate["subject"],
                predicate=candidate["predicate"],
                object_name=candidate["object"],
                source=source,
                metadata=metadata,
            )
            results.append({"status": "relation", "relation_id": relation_id, **candidate})
            continue

        outcome = store.upsert_graph_state(
            subject_name=candidate["subject"],
            attribute=candidate["attribute"],
            value_text=candidate["value"],
            source=source,
            supersede=bool(candidate.get("supersede")),
            metadata=metadata,
        )
        results.append({**candidate, **outcome})
    return results
