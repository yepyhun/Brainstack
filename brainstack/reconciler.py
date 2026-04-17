from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .db import BrainstackStore
from .provenance import merge_provenance
from .style_contract import build_style_contract_document
from .tier1_extractor import build_profile_stable_key


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _extract_identity_name(value: Any) -> str:
    text = _normalize_text(value)
    lowered = text.lower()
    if lowered.startswith("user identity:"):
        return _normalize_text(text.split(":", 1)[1]).rstrip(".,;:!?")
    if lowered.startswith("user's name is "):
        candidate = _normalize_text(text[len("User's name is ") :])
        if " (" in candidate:
            candidate = _normalize_text(candidate.split(" (", 1)[0])
        return candidate.rstrip(".,;:!?")
    return text.rstrip(".,;:!?")


def _current_user_name(store: BrainstackStore, *, principal_scope_key: str = "") -> str:
    for stable_key in ("identity:name", "identity:user_name", "identity:user_identity"):
        item = store.get_profile_item(stable_key=stable_key, principal_scope_key=principal_scope_key)
        if not item:
            continue
        extracted = _extract_identity_name(item.get("content"))
        if extracted:
            return extracted
    return ""


def _canonicalize_person_subject(name: Any, *, user_name: str) -> str:
    normalized = _normalize_text(name)
    if not normalized:
        return ""
    if user_name and normalized.lower() in {"user", "the user"}:
        return user_name
    return normalized


def _profile_stable_key(candidate: Mapping[str, Any]) -> str:
    category = _normalize_text(candidate.get("category")).lower()
    slot = _normalize_text(candidate.get("slot")).lower()
    if slot:
        if slot.split(":", 1)[0] in {"identity", "preference", "shared_work"}:
            return slot
        return f"{category}:{slot}"
    return build_profile_stable_key(category, _normalize_text(candidate.get("content")))


def _candidate_metadata(
    candidate: Mapping[str, Any],
    *,
    base_metadata: Mapping[str, Any],
    confidence: float,
) -> Dict[str, Any]:
    payload = dict(base_metadata)
    payload["confidence"] = float(confidence)
    raw_metadata = candidate.get("metadata")
    if isinstance(raw_metadata, Mapping):
        payload.update(raw_metadata)
    raw_temporal = candidate.get("temporal")
    if isinstance(raw_temporal, Mapping):
        payload["temporal"] = {**payload.get("temporal", {}), **raw_temporal}
    candidate_provenance = candidate.get("provenance") if isinstance(candidate.get("provenance"), Mapping) else None
    payload["provenance"] = merge_provenance(payload.get("provenance"), candidate_provenance)
    return payload


def _reconcile_profile_items(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    source: str,
    metadata: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        category = _normalize_text(candidate.get("category")).lower()
        content = _normalize_text(candidate.get("content"))
        if not category or not content:
            continue
        stable_key = _profile_stable_key(candidate)
        principal_scope_key = str(metadata.get("principal_scope_key") or "").strip()
        existing = store.get_profile_item(stable_key=stable_key, principal_scope_key=principal_scope_key)
        if existing and _normalize_text(existing.get("content")) == content:
            actions.append({"kind": "profile", "action": "NONE", "stable_key": stable_key, "category": category})
            continue
        action = "UPDATE" if existing else "ADD"
        row_id = store.upsert_profile_item(
            stable_key=stable_key,
            category=category,
            content=content,
            source=source,
            confidence=float(candidate.get("confidence", 0.75)),
            metadata=_candidate_metadata(
                candidate,
                base_metadata=metadata,
                confidence=float(candidate.get("confidence", 0.75)),
            ),
        )
        actions.append(
            {
                "kind": "profile",
                "action": action,
                "stable_key": stable_key,
                "category": category,
                "row_id": row_id,
            }
        )
    return actions


def _reconcile_states(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    metadata: Dict[str, Any],
    source: str,
    user_name: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        outcome = store.upsert_graph_state(
            subject_name=subject_name,
            attribute=_normalize_text(candidate.get("attribute")).lower(),
            value_text=_normalize_text(candidate.get("value")),
            source=source,
            supersede=bool(candidate.get("supersede", False)),
            metadata=_candidate_metadata(
                candidate,
                base_metadata=metadata,
                confidence=float(candidate.get("confidence", 0.82)),
            ),
        )
        status = str(outcome.get("status", "")).lower()
        if status == "unchanged":
            action = "NONE"
        elif status == "superseded":
            action = "UPDATE"
        elif status == "conflict":
            action = "CONFLICT"
        else:
            action = "ADD"
        actions.append({"kind": "state", "action": action, **candidate, **outcome})
    return actions


def _reconcile_relations(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    metadata: Dict[str, Any],
    source: str,
    user_name: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        object_name = _canonicalize_person_subject(candidate.get("object"), user_name=user_name)
        outcome = store.upsert_graph_relation(
            subject_name=subject_name,
            predicate=_normalize_text(candidate.get("predicate")).lower(),
            object_name=object_name,
            source=source,
            metadata=_candidate_metadata(
                candidate,
                base_metadata=metadata,
                confidence=float(candidate.get("confidence", 0.8)),
            ),
        )
        action = "NONE" if outcome["status"] == "unchanged" else "ADD"
        actions.append({"kind": "relation", "action": action, **candidate, **outcome})
    return actions


def _reconcile_inferred_relations(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    metadata: Dict[str, Any],
    source: str,
    user_name: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        object_name = _canonicalize_person_subject(candidate.get("object"), user_name=user_name)
        outcome = store.upsert_graph_inferred_relation(
            subject_name=subject_name,
            predicate=_normalize_text(candidate.get("predicate")).lower(),
            object_name=object_name,
            source=source,
            metadata=_candidate_metadata(
                candidate,
                base_metadata=metadata,
                confidence=float(candidate.get("confidence", 0.62)),
            ),
        )
        status = str(outcome.get("status", "")).lower()
        if status in {"unchanged", "shadowed"}:
            action = "NONE"
        else:
            action = "ADD"
        actions.append({"kind": "inferred_relation", "action": action, **candidate, **outcome})
    return actions


def _typed_entity_name(candidate: Mapping[str, Any]) -> str:
    name = _normalize_text(candidate.get("name"))
    if name:
        return name
    entity_type = _normalize_text(candidate.get("entity_type")).lower() or "event"
    turn_number = int(candidate.get("turn_number") or 0)
    return f"{entity_type} turn {turn_number}".strip()


def _reconcile_typed_entities(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    metadata: Dict[str, Any],
    source: str,
    user_name: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        entity_name = _typed_entity_name(candidate)
        entity_type = _normalize_text(candidate.get("entity_type")).lower()
        if not entity_name or not entity_type:
            continue
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name) or user_name or "User"
        entity_metadata = _candidate_metadata(
            candidate,
            base_metadata=metadata,
            confidence=float(candidate.get("confidence", 0.78)),
        )
        raw_attributes_value = candidate.get("attributes")
        raw_attributes: Mapping[Any, Any] = raw_attributes_value if isinstance(raw_attributes_value, Mapping) else {}
        actions.extend(
            store.upsert_typed_entity(
                entity_name=entity_name,
                entity_type=entity_type,
                subject_name=subject_name,
                attributes=raw_attributes,
                source=source,
                metadata=entity_metadata,
                confidence=float(candidate.get("confidence", 0.78)),
            )
        )
    return actions


def _reconcile_style_contract_artifact(
    store: BrainstackStore,
    *,
    artifact: Mapping[str, Any] | None,
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(artifact, Mapping):
        return []
    principal_scope_key = str(metadata.get("principal_scope_key") or "").strip()
    if not principal_scope_key:
        return []
    raw_content = str(artifact.get("content") or "").strip()
    if not raw_content:
        return []

    document = build_style_contract_document(
        principal_scope_key=principal_scope_key,
        principal_scope=metadata.get("principal_scope") if isinstance(metadata.get("principal_scope"), Mapping) else None,
        content=raw_content,
        source=str(artifact.get("source") or "tier2_llm"),
    )
    existing = store.get_corpus_document(stable_key=str(document["stable_key"]))
    existing_content = ""
    if existing:
        existing_content = "\n\n".join(
            str(section.get("content") or "").strip()
            for section in list(existing.get("sections") or [])
            if str(section.get("content") or "").strip()
        )
    if _normalize_text(existing_content) == _normalize_text(raw_content):
        return [{"kind": "corpus", "action": "NONE", "doc_kind": str(document["doc_kind"]), "stable_key": str(document["stable_key"])}]

    ingest_result = store.ingest_corpus_document(
        stable_key=str(document["stable_key"]),
        title=str(document["title"]),
        doc_kind=str(document["doc_kind"]),
        source=str(document["source"]),
        sections=list(document["sections"]),
        metadata=dict(document["metadata"]),
    )
    return [
        {
            "kind": "corpus",
            "action": "UPDATE" if existing else "ADD",
            "doc_kind": str(document["doc_kind"]),
            "stable_key": str(document["stable_key"]),
            "document_id": int(ingest_result.get("document_id") or 0),
            "section_count": int(ingest_result.get("section_count") or 0),
        }
    ]


def _reconcile_continuity(
    store: BrainstackStore,
    *,
    session_id: str,
    turn_number: int,
    temporal_events: Iterable[Mapping[str, Any]],
    continuity_summary: str,
    decisions: Iterable[str],
    source: str,
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for event in temporal_events:
        content = _normalize_text(event.get("content"))
        if not content:
            continue
        event_turn_number = int(event.get("turn_number") or turn_number or 0)
        event_metadata = _candidate_metadata(
            event,
            base_metadata=metadata,
            confidence=float(event.get("confidence", 0.76)),
        )
        if store.find_continuity_event(session_id=session_id, kind="temporal_event", content=content) is not None:
            actions.append({"kind": "continuity", "action": "NONE", "type": "temporal_event", "content": content})
            continue
        row_id = store.add_continuity_event(
            session_id=session_id,
            turn_number=event_turn_number,
            kind="temporal_event",
            content=content,
            source=source,
            metadata=event_metadata,
        )
        actions.append(
            {
                "kind": "continuity",
                "action": "ADD",
                "type": "temporal_event",
                "row_id": row_id,
                "content": content,
            }
        )

    if continuity_summary:
        if store.find_continuity_event(session_id=session_id, kind="tier2_summary", content=continuity_summary) is None:
            row_id = store.add_continuity_event(
                session_id=session_id,
                turn_number=turn_number,
                kind="tier2_summary",
                content=continuity_summary,
                source=source,
                metadata=metadata,
            )
            actions.append({"kind": "continuity", "action": "ADD", "row_id": row_id, "type": "summary"})
        else:
            actions.append({"kind": "continuity", "action": "NONE", "type": "summary"})

    for decision in decisions:
        if store.find_continuity_event(session_id=session_id, kind="decision", content=decision) is not None:
            actions.append({"kind": "continuity", "action": "NONE", "type": "decision", "content": decision})
            continue
        row_id = store.add_continuity_event(
            session_id=session_id,
            turn_number=turn_number,
            kind="decision",
            content=decision,
            source=source,
            metadata=metadata,
        )
        actions.append({"kind": "continuity", "action": "ADD", "type": "decision", "row_id": row_id, "content": decision})
    return actions


def reconcile_tier2_candidates(
    store: BrainstackStore,
    *,
    session_id: str,
    turn_number: int,
    source: str,
    extracted: Mapping[str, Any],
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = dict(metadata or {})
    payload.update({"session_id": session_id, "turn_number": turn_number, "tier": "tier2"})
    actions: List[Dict[str, Any]] = []
    actions.extend(
        _reconcile_profile_items(
            store,
            candidates=extracted.get("profile_items", []),
            source=source,
            metadata=payload,
        )
    )
    user_name = _current_user_name(store, principal_scope_key=str(payload.get("principal_scope_key") or ""))
    if user_name:
        merge_action = store.merge_entity_alias(alias_name="User", target_name=user_name)
        if merge_action.get("status") == "merged":
            actions.append({"kind": "graph_entity", "action": "MERGE_ALIAS", **merge_action, "target_name": user_name})
    actions.extend(
        _reconcile_states(
            store,
            candidates=extracted.get("states", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_relations(
            store,
            candidates=extracted.get("relations", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_inferred_relations(
            store,
            candidates=extracted.get("inferred_relations", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_typed_entities(
            store,
            candidates=extracted.get("typed_entities", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_style_contract_artifact(
            store,
            artifact=extracted.get("style_contract_artifact"),
            metadata=payload,
        )
    )
    actions.extend(
        _reconcile_continuity(
            store,
            session_id=session_id,
            turn_number=turn_number,
            temporal_events=extracted.get("temporal_events", []),
            continuity_summary=_normalize_text(extracted.get("continuity_summary")),
            decisions=extracted.get("decisions", []),
            source=source,
            metadata=payload,
        )
    )
    return {"actions": actions}
