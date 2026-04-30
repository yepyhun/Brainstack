from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

from .admission_policy import canonical_graph_slot, canonical_profile_slot
from .profile_contract import normalize_profile_slot
from .style_contract import STYLE_CONTRACT_SLOT


TIER2_CONSOLIDATION_PLAN_SCHEMA = "brainstack.tier2_consolidation_plan.v1"
TIER2_CONSOLIDATION_BUDGET_SCHEMA = "brainstack.tier2_candidate_budget.v1"

TIER2_KIND_CAPS: dict[str, int] = {
    "profile_items": 8,
    "states": 8,
    "relations": 4,
    "inferred_relations": 2,
    "typed_entities": 4,
    "temporal_events": 8,
    "decisions": 6,
}

TIER2_TOTAL_CANDIDATE_CAP = 32
TIER2_CONTINUITY_SUMMARY_MAX_CHARS = 480
TIER2_DECISION_MAX_CHARS = 240


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _hash(value: Any, *, length: int = 24) -> str:
    text = _text(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length] if text else ""


def _json_hash(value: Any, *, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _profile_stable_key(candidate: Mapping[str, Any]) -> str:
    category = _text(candidate.get("category")).lower()
    slot = normalize_profile_slot(candidate.get("slot"))
    if slot:
        if slot.split(":", 1)[0] in {"identity", "preference", "shared_work", "reference"}:
            return slot
        return f"{category}:{slot}"
    content_hash = _hash(candidate.get("content"), length=16)
    return f"{category or 'profile'}:{content_hash}"


def _candidate_hash(candidate: Mapping[str, Any]) -> str:
    return _json_hash(
        {
            "category": candidate.get("category"),
            "slot": candidate.get("slot"),
            "subject": candidate.get("subject"),
            "attribute": candidate.get("attribute"),
            "predicate": candidate.get("predicate"),
            "object": candidate.get("object"),
            "value": candidate.get("value"),
            "content": candidate.get("content"),
            "name": candidate.get("name"),
            "entity_type": candidate.get("entity_type"),
            "turn_number": candidate.get("turn_number"),
        }
    )


def bound_tier2_extracted_payload(
    extracted: Mapping[str, Any],
    *,
    total_cap: int = TIER2_TOTAL_CANDIDATE_CAP,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply Hindsight-style bounded background consolidation limits.

    This does not decide truth. It prevents unbounded custom extractors from
    turning one background pass into memory bloat before admission runs.
    """

    bounded = dict(extracted)
    accepted_total = 0
    omitted_by_kind: dict[str, int] = {}
    accepted_by_kind: dict[str, int] = {}

    for kind, cap in TIER2_KIND_CAPS.items():
        raw_items = _list(extracted.get(kind))
        accepted_items: list[Any] = []
        for item in raw_items:
            if len(accepted_items) >= cap or accepted_total >= total_cap:
                omitted_by_kind[kind] = omitted_by_kind.get(kind, 0) + 1
                continue
            if kind == "decisions" and len(_text(item)) > TIER2_DECISION_MAX_CHARS:
                omitted_by_kind[kind] = omitted_by_kind.get(kind, 0) + 1
                continue
            accepted_items.append(item)
            accepted_total += 1
        bounded[kind] = accepted_items
        accepted_by_kind[kind] = len(accepted_items)
        if len(raw_items) > len(accepted_items):
            omitted_by_kind[kind] = omitted_by_kind.get(kind, 0) + (len(raw_items) - len(accepted_items) - omitted_by_kind.get(kind, 0))

    summary = _text(extracted.get("continuity_summary"))
    if summary and len(summary) > TIER2_CONTINUITY_SUMMARY_MAX_CHARS:
        bounded["continuity_summary"] = ""
        omitted_by_kind["continuity_summary"] = 1

    omitted_total = sum(omitted_by_kind.values())
    budget = {
        "schema": TIER2_CONSOLIDATION_BUDGET_SCHEMA,
        "status": "trimmed" if omitted_total else "within_budget",
        "total_cap": int(total_cap),
        "accepted_total": int(accepted_total),
        "omitted_total": int(omitted_total),
        "accepted_by_kind": accepted_by_kind,
        "omitted_by_kind": omitted_by_kind,
        "bloat_guard_active": True,
    }
    return bounded, budget


def _existing_profile_status(store: Any, *, stable_key: str, content: str, principal_scope_key: str) -> dict[str, Any]:
    existing = store.get_profile_item(stable_key=stable_key, principal_scope_key=principal_scope_key)
    if not existing:
        return {"existing_state": "missing", "proposed_action": "ADD"}
    existing_hash = _hash(existing.get("content"))
    if _text(existing.get("content")) == _text(content):
        return {"existing_state": "same", "proposed_action": "NONE", "existing_hash": existing_hash}
    return {"existing_state": "different", "proposed_action": "UPDATE", "existing_hash": existing_hash}


def _existing_graph_state_status(store: Any, *, subject: str, predicate: str, value: str) -> dict[str, Any]:
    try:
        rows = store.list_current_graph_states(limit=200)
    except Exception:
        return {"existing_state": "unknown", "proposed_action": "DEFER"}
    for row in rows:
        if _text(row.get("subject")).casefold() == _text(subject).casefold() and _text(row.get("predicate")).casefold() == _text(predicate).casefold():
            existing_value = row.get("object_value") or row.get("object") or row.get("value") or row.get("value_text")
            existing_hash = _hash(existing_value)
            if _text(existing_value) == _text(value):
                return {"existing_state": "same", "proposed_action": "NONE", "existing_hash": existing_hash}
            return {"existing_state": "different", "proposed_action": "DEFER_CONFLICT_REVIEW", "existing_hash": existing_hash}
    return {"existing_state": "missing", "proposed_action": "ADD"}


def _source_ids(consolidation_source: Mapping[str, Any]) -> list[str]:
    return [str(item) for item in list(consolidation_source.get("source_ids") or []) if _text(item)]


def _proposal_base(
    *,
    plan_id: str,
    source_ids: list[str],
    source_fingerprint: str,
    candidate_path: str,
    kind: str,
    target_shelf: str,
    target_slot: str,
    storage_key: str,
    candidate: Mapping[str, Any],
    existing: Mapping[str, Any],
) -> dict[str, Any]:
    proposal_id = "t2p_" + _json_hash(
        {
            "plan_id": plan_id,
            "candidate_path": candidate_path,
            "kind": kind,
            "target_shelf": target_shelf,
            "target_slot": target_slot,
            "storage_key": storage_key,
            "candidate_hash": _candidate_hash(candidate),
        },
        length=20,
    )
    return {
        "proposal_id": proposal_id,
        "candidate_path": candidate_path,
        "kind": kind,
        "target_shelf": target_shelf,
        "target_slot": target_slot,
        "storage_key": storage_key,
        "candidate_hash": _candidate_hash(candidate),
        "source_ids": source_ids,
        "source_fingerprint": source_fingerprint,
        **dict(existing),
    }


def build_tier2_consolidation_plan(
    *,
    store: Any,
    extracted: Mapping[str, Any],
    session_id: str,
    turn_number: int,
    source: str,
    metadata: Mapping[str, Any],
    consolidation_source: Mapping[str, Any],
) -> dict[str, Any]:
    source_fingerprint = _text(consolidation_source.get("source_fingerprint"))
    source_id_list = _source_ids(consolidation_source)
    plan_seed = {
        "session_id": session_id,
        "turn_number": int(turn_number or 0),
        "source": source,
        "source_fingerprint": source_fingerprint,
    }
    plan_id = "t2cp_" + _json_hash(plan_seed, length=20)
    principal_scope_key = _text(metadata.get("principal_scope_key"))
    proposals: list[dict[str, Any]] = []

    style_contract = extracted.get("style_contract")
    if isinstance(style_contract, Mapping):
        content = _text(style_contract.get("content"))
        existing = _existing_profile_status(
            store,
            stable_key=STYLE_CONTRACT_SLOT,
            content=content,
            principal_scope_key=principal_scope_key,
        )
        proposals.append(
            _proposal_base(
                plan_id=plan_id,
                source_ids=source_id_list,
                source_fingerprint=source_fingerprint,
                candidate_path="style_contract",
                kind="style_contract",
                target_shelf="profile",
                target_slot="preference.style_contract",
                storage_key=STYLE_CONTRACT_SLOT,
                candidate=style_contract,
                existing=existing,
            )
        )

    for index, candidate in enumerate(_list(extracted.get("profile_items"))):
        if not isinstance(candidate, Mapping):
            continue
        stable_key = _profile_stable_key(candidate)
        target_slot = canonical_profile_slot(stable_key, category=_text(candidate.get("category")).lower())
        existing = _existing_profile_status(
            store,
            stable_key=stable_key,
            content=_text(candidate.get("content")),
            principal_scope_key=principal_scope_key,
        )
        proposals.append(
            _proposal_base(
                plan_id=plan_id,
                source_ids=source_id_list,
                source_fingerprint=source_fingerprint,
                candidate_path=f"profile_items[{index}]",
                kind="profile",
                target_shelf="profile",
                target_slot=target_slot,
                storage_key=stable_key,
                candidate=candidate,
                existing=existing,
            )
        )

    for field, kind, subject_key, predicate_key, value_key in (
        ("states", "state", "subject", "attribute", "value"),
        ("relations", "relation", "subject", "predicate", "object"),
        ("inferred_relations", "inferred_relation", "subject", "predicate", "object"),
    ):
        for index, candidate in enumerate(_list(extracted.get(field))):
            if not isinstance(candidate, Mapping):
                continue
            predicate = _text(candidate.get(predicate_key)).lower()
            value = _text(candidate.get(value_key))
            target_slot = canonical_graph_slot(attribute=predicate if kind == "state" else "", predicate=predicate)
            existing = _existing_graph_state_status(
                store,
                subject=_text(candidate.get(subject_key)),
                predicate=predicate,
                value=value,
            )
            proposals.append(
                _proposal_base(
                    plan_id=plan_id,
                    source_ids=source_id_list,
                    source_fingerprint=source_fingerprint,
                    candidate_path=f"{field}[{index}]",
                    kind=kind,
                    target_shelf="graph",
                    target_slot=target_slot,
                    storage_key=target_slot,
                    candidate=candidate,
                    existing=existing,
                )
            )

    for field, kind in (("typed_entities", "typed_entity"), ("temporal_events", "temporal_event")):
        for index, candidate in enumerate(_list(extracted.get(field))):
            if not isinstance(candidate, Mapping):
                continue
            proposals.append(
                _proposal_base(
                    plan_id=plan_id,
                    source_ids=source_id_list,
                    source_fingerprint=source_fingerprint,
                    candidate_path=f"{field}[{index}]",
                    kind=kind,
                    target_shelf="continuity" if kind == "temporal_event" else "graph",
                    target_slot=kind,
                    storage_key=f"{kind}:{candidate.get('turn_number') or index}",
                    candidate=candidate,
                    existing={"existing_state": "unchecked", "proposed_action": "ADMISSION_REQUIRED"},
                )
            )

    if _text(extracted.get("continuity_summary")):
        proposals.append(
            _proposal_base(
                plan_id=plan_id,
                source_ids=source_id_list,
                source_fingerprint=source_fingerprint,
                candidate_path="continuity_summary",
                kind="continuity_summary",
                target_shelf="continuity",
                target_slot="tier2_summary",
                storage_key=f"tier2_summary:{session_id}",
                candidate={"content": extracted.get("continuity_summary")},
                existing={"existing_state": "unchecked", "proposed_action": "ADMISSION_REQUIRED"},
            )
        )

    for index, decision in enumerate(_list(extracted.get("decisions"))):
        proposals.append(
            _proposal_base(
                plan_id=plan_id,
                source_ids=source_id_list,
                source_fingerprint=source_fingerprint,
                candidate_path=f"decisions[{index}]",
                kind="decision",
                target_shelf="continuity",
                target_slot="decision",
                storage_key=f"decision:{_hash(decision, length=16)}",
                candidate={"content": decision},
                existing={"existing_state": "unchecked", "proposed_action": "ADMISSION_REQUIRED"},
            )
        )

    counts: dict[str, int] = {}
    for proposal in proposals:
        counts[proposal["kind"]] = counts.get(proposal["kind"], 0) + 1
    return {
        "schema": TIER2_CONSOLIDATION_PLAN_SCHEMA,
        "plan_id": plan_id,
        "session_id": session_id,
        "turn_number": int(turn_number or 0),
        "source": source,
        "source_ids": source_id_list,
        "source_fingerprint": source_fingerprint,
        "proposal_count": len(proposals),
        "proposal_counts": counts,
        "proposals": proposals,
        "status": "has_proposals" if proposals else "empty",
    }


def attach_consolidation_plan_metadata(extracted: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    payload = deepcopy(dict(extracted))
    proposals = {str(item.get("candidate_path")): dict(item) for item in list(plan.get("proposals") or []) if isinstance(item, Mapping)}

    def attach(candidate: Any, candidate_path: str) -> Any:
        if not isinstance(candidate, Mapping):
            return candidate
        proposal = proposals.get(candidate_path)
        if not proposal:
            return dict(candidate)
        item = dict(candidate)
        metadata = dict(item.get("metadata") or {})
        metadata.setdefault("source_event_id", str(plan.get("plan_id") or ""))
        metadata.setdefault("source_span_id", str(proposal.get("proposal_id") or ""))
        metadata.setdefault("trace_id", str(proposal.get("proposal_id") or ""))
        metadata["consolidation"] = {
            "schema": TIER2_CONSOLIDATION_PLAN_SCHEMA,
            "plan_id": str(plan.get("plan_id") or ""),
            "proposal_id": str(proposal.get("proposal_id") or ""),
            "candidate_path": candidate_path,
            "source_ids": list(proposal.get("source_ids") or []),
            "source_fingerprint": str(proposal.get("source_fingerprint") or ""),
            "existing_state": str(proposal.get("existing_state") or ""),
            "proposed_action": str(proposal.get("proposed_action") or ""),
        }
        item["metadata"] = metadata
        return item

    if isinstance(payload.get("style_contract"), Mapping):
        payload["style_contract"] = attach(payload["style_contract"], "style_contract")
    for field in TIER2_KIND_CAPS:
        payload[field] = [attach(item, f"{field}[{index}]") for index, item in enumerate(_list(payload.get(field)))]
    return payload
