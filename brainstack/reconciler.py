from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Iterable, List, Mapping

from .admission_policy import admit_claim, graph_claim_proposal, profile_claim_proposal
from .core.admission import AdmissionDecision
from .db import BrainstackStore
from .provenance import merge_provenance
from .storage.projection_writer import ProjectionWriter
from .style_contract import STYLE_CONTRACT_SLOT, normalize_style_contract_payload
from .tier2_consolidation import (
    TRUSTED_TIER2_USER_SPAN_PROOFS_KEY,
    VERIFIED_USER_SPAN_PROOF_KEY,
    bound_tier2_extracted_payload,
)
from .tier2_decision_runtime_gate import evaluate_tier2_decision_core_gate
from .tier1_extractor import build_profile_stable_key


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _json_fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    for stable_key in (
        "identity:preferred_address_name",
        "preference:addressing",
        "identity:name",
        "identity:user_name",
        "identity:user_identity",
    ):
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
    source: str = "",
) -> Dict[str, Any]:
    payload = dict(base_metadata)
    trusted_proofs = payload.pop(TRUSTED_TIER2_USER_SPAN_PROOFS_KEY, {})
    payload["confidence"] = float(confidence)
    raw_metadata = candidate.get("metadata")
    if isinstance(raw_metadata, Mapping):
        payload.update(raw_metadata)
    if str(source or "").strip().lower().startswith(("tier2:", "consolidation:")):
        payload.pop(TRUSTED_TIER2_USER_SPAN_PROOFS_KEY, None)
        payload.pop(VERIFIED_USER_SPAN_PROOF_KEY, None)
        payload.pop("tier2_verified_user_span_proof", None)
        hard_non_user_marker = False
        for key in ("assertion_speaker", "speaker", "source_role", "role", "author_role"):
            value = str(payload.get(key) or "").strip().lower()
            if value in {"assistant", "quoted_assistant", "runtime"}:
                hard_non_user_marker = True
            if value not in {"assistant", "quoted_assistant", "runtime"}:
                payload.pop(key, None)
        for key in ("authority", "authority_class", "source_authority"):
            value = str(payload.get(key) or "").strip().lower()
            if value in {"assistant_claim", "assistant_self_claim", "runtime_diagnostic"}:
                hard_non_user_marker = True
            if value not in {"assistant_claim", "assistant_self_claim", "runtime_diagnostic"}:
                payload.pop(key, None)
        for key in ("span_kind", "kind"):
            value = str(payload.get(key) or "").strip().lower()
            if value in {"assistant_answer", "runtime_diagnostic"}:
                hard_non_user_marker = True
            if value not in {"assistant_answer", "runtime_diagnostic"}:
                payload.pop(key, None)
        if str(payload.get("source_authority") or "").strip().lower() not in {
            "assistant_claim",
            "assistant_self_claim",
            "runtime_diagnostic",
        }:
            payload["source_authority"] = "tier2_summary"
        payload["authority_boundary"] = "tier2_candidate_metadata_cannot_upgrade_authority"
        consolidation = payload.get("consolidation") if isinstance(payload.get("consolidation"), Mapping) else {}
        candidate_path = str(consolidation.get("candidate_path") or "").strip()
        proof = trusted_proofs.get(candidate_path) if isinstance(trusted_proofs, Mapping) else None
        if not hard_non_user_marker and isinstance(proof, Mapping) and str(proof.get("status") or "") == "verified":
            payload[VERIFIED_USER_SPAN_PROOF_KEY] = dict(proof)
            payload["source_event_id"] = str(proof.get("source_event_id") or "")
            payload["source_turn_id"] = str(proof.get("source_turn_id") or proof.get("turn_number") or "")
            payload["source_span_id"] = str(proof.get("source_span_id") or "")
            payload["turn_role"] = "user"
            payload["assertion_speaker"] = "user"
            payload["source_role"] = "user"
            payload["span_kind"] = "assertion"
            payload["source_authority"] = "user_explicit_assertion"
            payload["normalization_method"] = "tier2_verified_user_span_exact_quote"
            payload["authority_boundary"] = "tier2_verified_user_span_proof_required"
        payload["_candidate_metadata_sanitized"] = True
    raw_temporal = candidate.get("temporal")
    if isinstance(raw_temporal, Mapping):
        payload["temporal"] = {**payload.get("temporal", {}), **raw_temporal}
    candidate_provenance = candidate.get("provenance") if isinstance(candidate.get("provenance"), Mapping) else None
    payload["provenance"] = merge_provenance(payload.get("provenance"), candidate_provenance)
    return payload


def _continuity_candidate_with_source_refs(
    candidate: Mapping[str, Any] | str,
    *,
    base_metadata: Mapping[str, Any],
    kind: str,
    content: str,
) -> Mapping[str, Any]:
    payload: Dict[str, Any] = dict(candidate) if isinstance(candidate, Mapping) else {"content": content}
    raw_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), Mapping) else {}
    item_metadata = dict(raw_metadata)
    consolidation_source = (
        base_metadata.get("consolidation_source")
        if isinstance(base_metadata.get("consolidation_source"), Mapping)
        else {}
    )
    source_ids = [str(item) for item in list(consolidation_source.get("source_ids") or []) if str(item or "").strip()]
    source_fingerprint = _normalize_text(consolidation_source.get("source_fingerprint"))
    if source_ids and source_fingerprint:
        content_hash = _json_fingerprint({"kind": kind, "content": content}).removeprefix("sha256:")[:20]
        item_metadata.setdefault("source_event_id", f"consolidation:{source_fingerprint}")
        item_metadata.setdefault("source_span_id", f"consolidation:{kind}:{content_hash}")
        item_metadata.setdefault("trace_id", f"continuity:{kind}:{content_hash}")
        item_metadata.setdefault(
            "consolidation",
            {
                "schema": "brainstack.tier2_continuity_source_ref.v1",
                "candidate_path": kind,
                "source_ids": source_ids,
                "source_fingerprint": source_fingerprint,
                "proposed_action": "ADD",
            },
        )
    payload["metadata"] = item_metadata
    return payload


def _continuity_core_block(
    *,
    kind: str,
    content: str,
    candidate_metadata: Dict[str, Any],
    base_metadata: Mapping[str, Any],
    source: str,
    stable_key: str,
) -> Dict[str, Any] | None:
    return evaluate_tier2_decision_core_gate(
        kind="continuity",
        candidate_metadata=candidate_metadata,
        base_metadata=base_metadata,
        source=source,
        target_kind="support_context",
        target_slot=f"continuity.{kind}",
        stable_key=stable_key,
        normalized_value=content,
    )


def _is_assistant_authored_candidate(candidate: Mapping[str, Any] | None) -> bool:
    if not isinstance(candidate, Mapping):
        return False
    containers = [candidate]
    for key in ("metadata", "provenance"):
        nested = candidate.get(key)
        if isinstance(nested, Mapping):
            containers.append(nested)
    for payload in containers:
        for key in ("role", "source_role", "author_role", "speaker"):
            if str(payload.get(key) or "").strip().lower() == "assistant":
                return True
        if str(payload.get("source") or "").strip().lower().startswith("assistant"):
            return True
    return False


def _admission_action(kind: str, decision: AdmissionDecision, *, row_id: int = 0) -> Dict[str, Any]:
    return {
        "kind": kind,
        "action": decision.decision.value,
        "reason_code": decision.reason_code,
        "stable_key": decision.stable_key,
        "target_slot": decision.target_slot,
        "truth_eligible": decision.truth_eligible,
        "support_visibility": decision.support_visibility.value,
        "row_id": int(row_id or 0),
    }


def _reconcile_profile_items(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    source: str,
    metadata: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    writer = ProjectionWriter(store)
    for candidate in candidates:
        category = _normalize_text(candidate.get("category")).lower()
        content = _normalize_text(candidate.get("content"))
        if not category or not content:
            continue
        stable_key = _profile_stable_key(candidate)
        candidate_metadata = _candidate_metadata(
            candidate,
            base_metadata=metadata,
            confidence=float(candidate.get("confidence", 0.75)),
            source=source,
        )
        proposal = profile_claim_proposal(
            candidate,
            source=source,
            base_metadata=candidate_metadata,
            stable_key=stable_key,
            category=category,
            content=content,
        )
        decision = admit_claim(proposal)
        existing = store.get_profile_item(
            stable_key=decision.stable_key or stable_key,
            principal_scope_key=str(metadata.get("principal_scope_key") or "").strip(),
        )
        existing_ref = None
        if existing:
            existing_ref = {
                "memory_ref": f"profile:{existing.get('id')}",
                "stable_key": decision.stable_key or stable_key,
                "value_fingerprint": _json_fingerprint(existing.get("content")),
            }
        core_block = evaluate_tier2_decision_core_gate(
            kind="profile",
            candidate_metadata=candidate_metadata,
            base_metadata=metadata,
            source=source,
            target_kind="style_rule" if category == "preference" else "profile_fact",
            target_slot=decision.target_slot or stable_key,
            stable_key=decision.stable_key or stable_key,
            normalized_value=content,
            existing_ref=existing_ref,
        )
        if not decision.accepted:
            writer.record_decision(decision=decision, metadata=candidate_metadata)
            actions.append(_admission_action("profile", decision))
            continue
        if core_block:
            actions.append(core_block)
            continue
        category = decision.target_slot.split(".", 1)[0] if "." in decision.target_slot else category
        if existing and _normalize_text(existing.get("content")) == content:
            writer.record_decision(decision=decision, metadata=candidate_metadata, durable_row_id=int(existing.get("id") or 0))
            actions.append({"kind": "profile", "action": "NONE", "stable_key": decision.stable_key, "category": category})
            continue
        action = "UPDATE" if existing else "ADD"
        row_id = writer.write_profile(
            decision=decision,
            category=category,
            content=content,
            source=source,
            confidence=float(candidate.get("confidence", 0.75)),
            metadata=candidate_metadata,
        )
        actions.append(
            {
                "kind": "profile",
                "action": action,
                "stable_key": decision.stable_key,
                "target_slot": decision.target_slot,
                "category": category,
                "row_id": row_id,
            }
        )
    return actions


def _reconcile_style_contract(
    store: BrainstackStore,
    *,
    candidate: Mapping[str, Any] | None,
    source: str,
    metadata: Mapping[str, Any],
) -> List[Dict[str, Any]]:
    normalized = normalize_style_contract_payload(candidate)
    if not normalized:
        return []
    writer = ProjectionWriter(store)
    principal_scope_key = str(metadata.get("principal_scope_key") or "").strip()
    candidate_metadata = _candidate_metadata(
        normalized,
        base_metadata=metadata,
        confidence=float(normalized.get("confidence") or 0.9),
        source=source,
    )
    proposal = profile_claim_proposal(
        normalized,
        source=source,
        base_metadata=candidate_metadata,
        stable_key=STYLE_CONTRACT_SLOT,
        category=str(normalized.get("category") or "preference"),
        content=str(normalized.get("content") or "").strip(),
    )
    decision = admit_claim(proposal)
    existing = store.get_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        principal_scope_key=principal_scope_key,
    )
    existing_ref = None
    if existing:
        existing_ref = {
            "memory_ref": f"profile:{existing.get('id')}",
            "stable_key": decision.stable_key or STYLE_CONTRACT_SLOT,
            "value_fingerprint": _json_fingerprint(existing.get("content")),
        }
    core_block = evaluate_tier2_decision_core_gate(
        kind="style_contract",
        candidate_metadata=candidate_metadata,
        base_metadata=metadata,
        source=source,
        target_kind="style_rule",
        target_slot=decision.target_slot or STYLE_CONTRACT_SLOT,
        stable_key=decision.stable_key or STYLE_CONTRACT_SLOT,
        normalized_value=str(normalized.get("content") or "").strip(),
        existing_ref=existing_ref,
    )
    if not decision.accepted:
        writer.record_decision(decision=decision, metadata=candidate_metadata)
        return [_admission_action("style_contract", decision)]
    if core_block:
        return [core_block]
    content = str(normalized.get("content") or "").strip()
    if existing and str(existing.get("content") or "").strip() == content:
        writer.record_decision(decision=decision, metadata=candidate_metadata, durable_row_id=int(existing.get("id") or 0))
        return [{"kind": "style_contract", "action": "NONE", "stable_key": STYLE_CONTRACT_SLOT}]
    row_id = writer.write_profile(
        decision=decision,
        category=str(normalized.get("category") or "preference"),
        content=content,
        source=str(normalized.get("source") or source),
        confidence=float(normalized.get("confidence") or 0.9),
        metadata=candidate_metadata,
    )
    return [
        {
            "kind": "style_contract",
            "action": "UPDATE" if existing else "ADD",
            "stable_key": STYLE_CONTRACT_SLOT,
            "row_id": row_id,
        }
    ]


def _reconcile_states(
    store: BrainstackStore,
    *,
    candidates: Iterable[Mapping[str, Any]],
    metadata: Dict[str, Any],
    source: str,
    user_name: str,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    writer = ProjectionWriter(store)
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        attribute = _normalize_text(candidate.get("attribute")).lower()
        value_text = _normalize_text(candidate.get("value"))
        candidate_metadata = _candidate_metadata(
            candidate,
            base_metadata=metadata,
            confidence=float(candidate.get("confidence", 0.82)),
            source=source,
        )
        proposal = graph_claim_proposal(
            candidate,
            source=source,
            base_metadata=candidate_metadata,
            target_kind="state",
            subject=subject_name,
            predicate=attribute,
            value=value_text,
        )
        decision = admit_claim(proposal)
        core_block = evaluate_tier2_decision_core_gate(
            kind="state",
            candidate_metadata=candidate_metadata,
            base_metadata=metadata,
            source=source,
            target_kind="relation",
            target_slot=attribute,
            stable_key=f"{subject_name}:{attribute}",
            normalized_value=value_text,
            relation_shape={
                "subject_ref": subject_name,
                "predicate": attribute,
                "object_ref": value_text,
                "direction": "forward",
            },
        )
        if not decision.accepted:
            writer.record_decision(decision=decision, metadata=candidate_metadata)
            actions.append(_admission_action("state", decision))
            continue
        if core_block:
            actions.append(core_block)
            continue
        outcome = writer.write_graph_state(
            decision=decision,
            subject_name=subject_name,
            attribute=attribute,
            value_text=value_text,
            source=source,
            metadata=candidate_metadata,
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
    writer = ProjectionWriter(store)
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        object_name = _canonicalize_person_subject(candidate.get("object"), user_name=user_name)
        predicate = _normalize_text(candidate.get("predicate")).lower()
        candidate_metadata = _candidate_metadata(
            candidate,
            base_metadata=metadata,
            confidence=float(candidate.get("confidence", 0.8)),
            source=source,
        )
        proposal = graph_claim_proposal(
            candidate,
            source=source,
            base_metadata=candidate_metadata,
            target_kind="relation",
            subject=subject_name,
            predicate=predicate,
            value=object_name,
        )
        decision = admit_claim(proposal)
        core_block = evaluate_tier2_decision_core_gate(
            kind="relation",
            candidate_metadata=candidate_metadata,
            base_metadata=metadata,
            source=source,
            target_kind="relation",
            target_slot=predicate,
            stable_key=f"{subject_name}:{predicate}:{object_name}",
            normalized_value=object_name,
            relation_shape={
                "subject_ref": subject_name,
                "predicate": predicate,
                "object_ref": object_name,
                "direction": "forward",
            },
        )
        if not decision.accepted:
            writer.record_decision(decision=decision, metadata=candidate_metadata)
            actions.append(_admission_action("relation", decision))
            continue
        if core_block:
            actions.append(core_block)
            continue
        outcome = writer.write_graph_relation(
            decision=decision,
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            metadata=candidate_metadata,
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
    writer = ProjectionWriter(store)
    for candidate in candidates:
        subject_name = _canonicalize_person_subject(candidate.get("subject"), user_name=user_name)
        object_name = _canonicalize_person_subject(candidate.get("object"), user_name=user_name)
        predicate = _normalize_text(candidate.get("predicate")).lower()
        candidate_metadata = _candidate_metadata(
            candidate,
            base_metadata=metadata,
            confidence=float(candidate.get("confidence", 0.62)),
            source=source,
        )
        proposal = graph_claim_proposal(
            candidate,
            source=source,
            base_metadata=candidate_metadata,
            target_kind="inferred_relation",
            subject=subject_name,
            predicate=predicate,
            value=object_name,
        )
        decision = admit_claim(proposal)
        if not decision.accepted:
            writer.record_decision(decision=decision, metadata=candidate_metadata)
            actions.append(_admission_action("inferred_relation", decision))
            continue
        core_block = evaluate_tier2_decision_core_gate(
            kind="relation",
            candidate_metadata=candidate_metadata,
            base_metadata=metadata,
            source=source,
            target_kind="relation",
            target_slot=decision.target_slot or predicate,
            stable_key=decision.stable_key or decision.target_slot or predicate,
            normalized_value={"subject": subject_name, "predicate": predicate, "object": object_name},
            relation_shape={
                "subject_ref": subject_name,
                "predicate": predicate,
                "object_ref": object_name,
                "direction": "forward",
            },
        )
        if core_block:
            core_block["kind"] = "inferred_relation"
            actions.append(core_block)
            continue
        outcome = writer.write_graph_relation(
            decision=decision,
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            metadata=candidate_metadata,
            inferred=True,
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
    writer = ProjectionWriter(store)
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
            source=source,
        )
        raw_attributes_value = candidate.get("attributes")
        raw_attributes: Mapping[Any, Any] = raw_attributes_value if isinstance(raw_attributes_value, Mapping) else {}
        for attribute, value in {"entity_type": entity_type, "owner_subject": subject_name, **dict(raw_attributes)}.items():
            normalized_attribute = _normalize_text(attribute).lower()
            normalized_value = _normalize_text(value)
            if not normalized_attribute or not normalized_value:
                continue
            proposal = graph_claim_proposal(
                candidate,
                source=source,
                base_metadata=entity_metadata,
                target_kind="typed_entity",
                subject=entity_name,
                predicate=normalized_attribute,
                value=normalized_value,
            )
            decision = admit_claim(proposal)
            if not decision.accepted:
                writer.record_decision(decision=decision, metadata=entity_metadata)
                actions.append(_admission_action("typed_entity", decision))
                continue
            core_block = evaluate_tier2_decision_core_gate(
                kind="state",
                candidate_metadata=entity_metadata,
                base_metadata=metadata,
                source=source,
                target_kind="relation",
                target_slot=decision.target_slot or normalized_attribute,
                stable_key=decision.stable_key or decision.target_slot or normalized_attribute,
                normalized_value={
                    "subject": entity_name,
                    "attribute": normalized_attribute,
                    "value": normalized_value,
                },
                relation_shape={
                    "subject_ref": entity_name,
                    "predicate": normalized_attribute,
                    "object_ref": normalized_value,
                    "direction": "forward",
                },
            )
            if core_block:
                core_block["kind"] = "typed_entity"
                actions.append(core_block)
                continue
            outcome = writer.write_graph_state(
                decision=decision,
                subject_name=entity_name,
                attribute=normalized_attribute,
                value_text=normalized_value,
                source=source,
                metadata=entity_metadata,
            )
            actions.append(
                {
                    "kind": "typed_entity",
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "attribute": normalized_attribute,
                    "action": "NONE" if str(outcome.get("status", "")).lower() in {"unchanged", "shadowed"} else "ADD",
                    **outcome,
                }
            )
    return actions


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
        if _is_assistant_authored_candidate(event):
            actions.append({"kind": "continuity", "action": "REJECT_ASSISTANT_AUTHORED", "type": "temporal_event"})
            continue
        content = _normalize_text(event.get("content"))
        if not content:
            continue
        event_turn_number = int(event.get("turn_number") or turn_number or 0)
        event_metadata = _candidate_metadata(
            event,
            base_metadata=metadata,
            confidence=float(event.get("confidence", 0.76)),
            source=source,
        )
        if store.find_continuity_event(session_id=session_id, kind="temporal_event", content=content) is not None:
            actions.append({"kind": "continuity", "action": "NONE", "type": "temporal_event", "content": content})
            continue
        core_block = _continuity_core_block(
            kind="temporal_event",
            content=content,
            candidate_metadata=event_metadata,
            base_metadata=metadata,
            source=source,
            stable_key=f"continuity:{session_id}:temporal_event:{_json_fingerprint(content)}",
        )
        if core_block:
            core_block["type"] = "temporal_event"
            actions.append(core_block)
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
            summary_candidate = _continuity_candidate_with_source_refs(
                {"content": continuity_summary},
                base_metadata=metadata,
                kind="tier2_summary",
                content=continuity_summary,
            )
            summary_metadata = _candidate_metadata(
                summary_candidate,
                base_metadata=metadata,
                confidence=0.68,
                source=source,
            )
            core_block = _continuity_core_block(
                kind="tier2_summary",
                content=continuity_summary,
                candidate_metadata=summary_metadata,
                base_metadata=metadata,
                source=source,
                stable_key=f"continuity:{session_id}:tier2_summary:{_json_fingerprint(continuity_summary)}",
            )
            if core_block:
                core_block["type"] = "summary"
                actions.append(core_block)
            else:
                row_id = store.add_continuity_event(
                    session_id=session_id,
                    turn_number=turn_number,
                    kind="tier2_summary",
                    content=continuity_summary,
                    source=source,
                    metadata=summary_metadata,
                )
                actions.append({"kind": "continuity", "action": "ADD", "row_id": row_id, "type": "summary"})
        else:
            actions.append({"kind": "continuity", "action": "NONE", "type": "summary"})

    for decision in decisions:
        if isinstance(decision, Mapping) and _is_assistant_authored_candidate(decision):
            actions.append({"kind": "continuity", "action": "REJECT_ASSISTANT_AUTHORED", "type": "decision"})
            continue
        decision_candidate = decision if isinstance(decision, Mapping) else {"content": decision}
        decision_content = _normalize_text(decision_candidate.get("content"))
        if not decision_content:
            continue
        if store.find_continuity_event(session_id=session_id, kind="decision", content=decision_content) is not None:
            actions.append({"kind": "continuity", "action": "NONE", "type": "decision", "content": decision_content})
            continue
        decision_candidate = _continuity_candidate_with_source_refs(
            decision_candidate,
            base_metadata=metadata,
            kind="decision",
            content=decision_content,
        )
        decision_metadata = _candidate_metadata(
            decision_candidate,
            base_metadata=metadata,
            confidence=float(decision_candidate.get("confidence", 0.66)) if isinstance(decision_candidate, Mapping) else 0.66,
            source=source,
        )
        core_block = _continuity_core_block(
            kind="decision",
            content=decision_content,
            candidate_metadata=decision_metadata,
            base_metadata=metadata,
            source=source,
            stable_key=f"continuity:{session_id}:decision:{_json_fingerprint(decision_content)}",
        )
        if core_block:
            core_block["type"] = "decision"
            actions.append(core_block)
            continue
        row_id = store.add_continuity_event(
            session_id=session_id,
            turn_number=turn_number,
            kind="decision",
            content=decision_content,
            source=source,
            metadata=decision_metadata,
        )
        actions.append(
            {
                "kind": "continuity",
                "action": "ADD",
                "type": "decision",
                "row_id": row_id,
                "content": decision_content,
            }
        )
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
    bounded_extracted, budget_report = bound_tier2_extracted_payload(extracted)
    payload = dict(metadata or {})
    payload.update({"session_id": session_id, "turn_number": turn_number, "tier": "tier2"})
    actions: List[Dict[str, Any]] = []
    actions.extend(
        _reconcile_style_contract(
            store,
            candidate=bounded_extracted.get("style_contract"),
            source=source,
            metadata=payload,
        )
    )
    actions.extend(
        _reconcile_profile_items(
            store,
            candidates=bounded_extracted.get("profile_items", []),
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
            candidates=bounded_extracted.get("states", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_relations(
            store,
            candidates=bounded_extracted.get("relations", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_inferred_relations(
            store,
            candidates=bounded_extracted.get("inferred_relations", []),
            metadata=payload,
            source=source,
            user_name=user_name,
        )
    )
    actions.extend(
        _reconcile_typed_entities(
            store,
            candidates=bounded_extracted.get("typed_entities", []),
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
            temporal_events=bounded_extracted.get("temporal_events", []),
            continuity_summary=_normalize_text(bounded_extracted.get("continuity_summary")),
            decisions=bounded_extracted.get("decisions", []),
            source=source,
            metadata=payload,
        )
    )
    return {"actions": actions, "consolidation_budget": budget_report}
