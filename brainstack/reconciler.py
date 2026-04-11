from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping

from .db import BrainstackStore
from .tier1_extractor import build_profile_stable_key


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _profile_stable_key(candidate: Mapping[str, Any]) -> str:
    category = _normalize_text(candidate.get("category")).lower()
    slot = _normalize_text(candidate.get("slot")).lower()
    if slot:
        return f"{category}:{slot}"
    return build_profile_stable_key(category, _normalize_text(candidate.get("content")))


def _reconcile_profile_items(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    session_id: str,
    turn_number: int,
    source: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
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
            metadata={
                "session_id": session_id,
                "turn_number": turn_number,
                "tier": "tier2",
            },
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
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        outcome = store.upsert_graph_state(
            subject_name=_normalize_text(candidate.get("subject")),
            attribute=_normalize_text(candidate.get("attribute")).lower(),
            value_text=_normalize_text(candidate.get("value")),
            source=source,
            supersede=bool(candidate.get("supersede", False)),
            metadata={**metadata, "confidence": float(candidate.get("confidence", 0.82))},
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
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    for candidate in candidates:
        outcome = store.upsert_graph_relation(
            subject_name=_normalize_text(candidate.get("subject")),
            predicate=_normalize_text(candidate.get("predicate")).lower(),
            object_name=_normalize_text(candidate.get("object")),
            source=source,
            metadata={**metadata, "confidence": float(candidate.get("confidence", 0.8))},
        )
        action = "NONE" if outcome["status"] == "unchanged" else "ADD"
        actions.append({"kind": "relation", "action": action, **candidate, **outcome})
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
    actions.extend(
        _reconcile_states(
            store,
            candidates=extracted.get("states", []),
            metadata=payload,
            source=source,
        )
    )
    actions.extend(
        _reconcile_relations(
            store,
            candidates=extracted.get("relations", []),
            metadata=payload,
            source=source,
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
