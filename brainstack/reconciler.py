from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .db import BrainstackStore
from .provenance import merge_provenance
from .tier1_extractor import build_profile_stable_key


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _extract_identity_name(value: Any) -> str:
    text = _normalize_text(value)
    lowered = text.lower()
    if lowered.startswith("user identity:"):
        return _normalize_text(text.split(":", 1)[1])
    return text


def _current_user_name(store: BrainstackStore) -> str:
    item = store.get_profile_item(stable_key="identity:identity:name")
    if not item:
        return ""
    return _extract_identity_name(item.get("content"))


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
    session_id: str,
    turn_number: int,
    source: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    base_metadata = {"session_id": session_id, "turn_number": turn_number, "tier": "tier2"}
    for candidate in candidates:
        category = _normalize_text(candidate.get("category")).lower()
        content = _normalize_text(candidate.get("content"))
        if not category or not content:
            continue
        stable_key = _profile_stable_key(candidate)
        existing = store.get_profile_item(stable_key=stable_key)
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
                base_metadata=base_metadata,
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


def _reconcile_continuity(
    store: BrainstackStore,
    *,
    session_id: str,
    turn_number: int,
    continuity_summary: str,
    decisions: Iterable[str],
    source: str,
    metadata: Dict[str, Any],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
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
            session_id=session_id,
            turn_number=turn_number,
            source=source,
        )
    )
    user_name = _current_user_name(store)
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
        _reconcile_continuity(
            store,
            session_id=session_id,
            turn_number=turn_number,
            continuity_summary=_normalize_text(extracted.get("continuity_summary")),
            decisions=extracted.get("decisions", []),
            source=source,
            metadata=payload,
        )
    )
    return {"actions": actions}
