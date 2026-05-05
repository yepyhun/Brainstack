from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from .canonical_memory_event import CANONICAL_MEMORY_EVENT_CORE_GROUPS, validate_canonical_memory_event
from .projection_semantics import apply_read_model_supersession, classify_projection_semantics

GRAPHITI_PROJECTION_SCHEMA_VERSION = "brainstack.graphiti_projection.v1"
GRAPH_MEMORY_KINDS = {"graph_relation", "graph_state", "temporal_event"}
ANSWERABLE_EVENT_TYPES = {"durable_fact_committed", "proposal_accepted"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _hash(value: Any, *, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _canonical_event(row_or_event: Mapping[str, Any]) -> Mapping[str, Any]:
    if all(isinstance(row_or_event.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return row_or_event
    nested = _mapping(row_or_event.get("event"))
    if all(isinstance(nested.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return nested
    return {}


def _event_sort_key(event: Mapping[str, Any]) -> tuple[str, str]:
    event_group = _mapping(event.get("event"))
    temporal = _mapping(event.get("temporal"))
    return (_text(temporal.get("transaction_time")), _text(event_group.get("event_id")))


def _episode_from_event(event: Mapping[str, Any]) -> dict[str, Any]:
    source = _mapping(event.get("source"))
    return {
        "episode_id": _text(source.get("source_event_id")),
        "source_event_id": _text(source.get("source_event_id")),
        "source_span_id": _text(source.get("source_span_id")),
        "source_quote_hash": _text(source.get("source_quote_hash")),
        "speaker": _text(source.get("speaker")),
        "assertion_speaker": _text(source.get("assertion_speaker")),
        "source_modality": _text(source.get("source_modality")),
        "observed_at": _text(source.get("observed_at")),
    }


def _entity(ref: str, *, source_event_id: str, source_span_id: str) -> dict[str, Any]:
    return {
        "entity_ref": ref,
        "canonical_label_hash": ref,
        "source_event_ids": [source_event_id] if source_event_id else [],
        "source_span_ids": [source_span_id] if source_span_id else [],
    }


def _merge_entity(existing: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    for key in ("source_event_ids", "source_span_ids"):
        merged = sorted(set(_list(existing.get(key))) | set(_list(incoming.get(key))))
        existing[key] = merged


def project_canonical_events_to_graphiti(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build Graphiti-compatible read projection from canonical events.

    This is a projection/read model. It never writes durable truth and never
    reinterprets authority, scope, truth eligibility, or support visibility.
    """

    normalized_events = [_canonical_event(event) for event in events]
    normalized_events = [event for event in normalized_events if event]
    normalized_events = apply_read_model_supersession(normalized_events)

    episodes: dict[str, dict[str, Any]] = {}
    entities: dict[str, dict[str, Any]] = {}
    current_edges: list[dict[str, Any]] = []
    prior_edges: list[dict[str, Any]] = []
    inspect_only_edges: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    counters = {
        "invalid_canonical_event": 0,
        "missing_source_projection": 0,
        "non_graph_memory_kind_projected": 0,
        "truth_ineligible_answerable_edge": 0,
        "support_only_answerable_edge": 0,
        "expired_answerable_edge": 0,
        "unresolved_conflict_answerable_edge": 0,
        "projection_rebuild_mismatch": 0,
    }

    for event in sorted(normalized_events, key=_event_sort_key):
        event_group = _mapping(event.get("event"))
        source = _mapping(event.get("source"))
        claim = _mapping(event.get("claim"))
        authority = _mapping(event.get("authority"))
        temporal = _mapping(event.get("temporal"))
        projection = _mapping(event.get("projection"))
        hints = _mapping(projection.get("projection_hints"))
        event_id = _text(event_group.get("event_id"))
        validation_issues = validate_canonical_memory_event(event)
        if validation_issues:
            counters["invalid_canonical_event"] += 1
            issues.append({"event_id": event_id, "issues": validation_issues})
            continue

        source_event_id = _text(source.get("source_event_id"))
        source_span_id = _text(source.get("source_span_id"))
        episode = _episode_from_event(event)
        episodes[episode["episode_id"]] = episode

        memory_kind = _text(claim.get("memory_kind"))
        graph_ready = bool(hints.get("graph_ready"))
        if memory_kind not in GRAPH_MEMORY_KINDS or not graph_ready:
            skipped.append(
                {
                    "event_id": event_id,
                    "memory_kind": memory_kind,
                    "reason": "NON_GRAPH_MEMORY_KIND",
                }
            )
            continue

        if not source_event_id or not source_span_id:
            counters["missing_source_projection"] += 1
            issues.append({"event_id": event_id, "issues": ["missing_source_projection"]})
            continue

        subject_ref = _text(claim.get("subject_ref")) or _hash(["subject", claim.get("stable_fact_id")])
        object_ref = _text(claim.get("object_ref")) or _text(claim.get("normalized_value_hash"))
        predicate = _text(claim.get("predicate")) or _text(claim.get("target_slot"))
        if not predicate or not object_ref:
            counters["missing_source_projection"] += 1
            issues.append({"event_id": event_id, "issues": ["missing_graph_claim_parts"]})
            continue

        for ref in (subject_ref, object_ref):
            incoming = _entity(ref, source_event_id=source_event_id, source_span_id=source_span_id)
            if ref in entities:
                _merge_entity(entities[ref], incoming)
            else:
                entities[ref] = incoming

        semantics = classify_projection_semantics(event)
        truth_eligible = bool(authority.get("truth_eligible"))
        support_visibility = _text(authority.get("support_visibility"))
        valid_to = _text(temporal.get("valid_to"))
        supersedes = [_text(item) for item in _list(temporal.get("supersedes")) if _text(item)]
        superseded_by = _text(temporal.get("superseded_by"))
        answerable = semantics.is_answer_safe
        current = semantics.is_current
        conflicted = semantics.is_conflicted
        edge = {
            "edge_id": _hash([event_id, subject_ref, predicate, object_ref]),
            "event_id": event_id,
            "stable_fact_id": _text(claim.get("stable_fact_id")),
            "subject_ref": subject_ref,
            "predicate": predicate,
            "object_ref": object_ref,
            "source_event_id": source_event_id,
            "source_span_id": source_span_id,
            "source_quote_hash": _text(source.get("source_quote_hash")),
            "scope": dict(_mapping(event.get("scope"))),
            "valid_from": _text(temporal.get("valid_from")),
            "valid_to": valid_to,
            "supersedes": supersedes,
            "superseded_by": superseded_by,
            "transaction_time": _text(temporal.get("transaction_time")),
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "answerable": answerable,
            "current": current,
            "conflicted": conflicted,
            "projection_reason_codes": [reason.value for reason in semantics.reason_codes],
            "projection_semantics": semantics.to_public_dict(),
        }
        if edge["answerable"] and not truth_eligible:
            counters["truth_ineligible_answerable_edge"] += 1
        if edge["answerable"] and support_visibility != "answer_evidence":
            counters["support_only_answerable_edge"] += 1
        if edge["answerable"] and valid_to:
            counters["expired_answerable_edge"] += 1
        if edge["answerable"] and conflicted:
            counters["unresolved_conflict_answerable_edge"] += 1

        if answerable:
            current_edges.append(edge)
        elif semantics.is_prior:
            prior_edges.append(edge)
        else:
            inspect_only_edges.append(edge)

    for edge_list in (current_edges, prior_edges, inspect_only_edges):
        edge_list.sort(key=lambda item: (item["scope"].get("principal_scope_key", ""), item["edge_id"]))
    entity_list = [entities[key] for key in sorted(entities)]
    episode_list = [episodes[key] for key in sorted(episodes)]
    critical_failures = sum(counters.values())
    return {
        "schema": GRAPHITI_PROJECTION_SCHEMA_VERSION,
        "status": "pass" if critical_failures == 0 else "fail",
        "graphiti_contract": {
            "episode_provenance": True,
            "temporal_validity": True,
            "entity_refs_are_stable": True,
            "edge_invalidation": True,
            "conflict_visibility": True,
            "rebuildable_from_canonical_events": True,
            "second_write_authority": False,
        },
        "critical_counters": counters,
        "episodes": episode_list,
        "entities": entity_list,
        "current_edges": current_edges,
        "prior_edges": prior_edges,
        "inspect_only_edges": inspect_only_edges,
        "skipped": skipped,
        "issues": issues,
    }
