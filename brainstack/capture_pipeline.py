"""Structured explicit-capture proposal pipeline.

The pipeline accepts structured extractor output. It deliberately does not parse
natural language with keyword rules. Extractors may be LLM/donor-backed, but
Brainstack core receives span-anchored target-slot proposals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .admission_policy import admit_claim
from .core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind
from .memory_write_receipts import (
    CapturePlan,
    CaptureProposalRef,
    build_ack_plan,
    build_memory_write_receipt,
    compute_receipt_coverage,
    stable_id,
)

CAPTURE_PIPELINE_SCHEMA = "brainstack.capture_pipeline.v1"

CAPTURE_INTENT_EXPLICIT = "explicit_capture"
CAPTURE_INTENT_CORRECTION = "correction"
CAPTURE_INTENT_PREFERENCE = "preference_update"
CAPTURE_INTENT_REFERENCE = "reference_save"
CAPTURE_INTENT_PROJECT = "project_metadata"
MIN_CAPTURE_PROPOSAL_CONFIDENCE = 0.5


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _source_authority(intent: str) -> SourceAuthority:
    if intent == CAPTURE_INTENT_CORRECTION:
        return SourceAuthority.USER_CORRECTION
    return SourceAuthority.USER_EXPLICIT_ASSERTION


def _span_kind(intent: str) -> SpanKind:
    if intent == CAPTURE_INTENT_CORRECTION:
        return SpanKind.CORRECTION
    return SpanKind.ASSERTION


@dataclass(frozen=True)
class StructuredCaptureItem:
    target_slot: str
    normalized_value: str
    source_span_id: str
    capture_intent: str = CAPTURE_INTENT_EXPLICIT
    stable_key: str = ""
    proposal_id: str = ""
    surface_value: str = ""
    language: str = ""
    confidence: float = 1.0
    required_for_full_ack: bool = True

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> "StructuredCaptureItem":
        target_slot = _text(item.get("target_slot"))
        normalized_value = _text(item.get("normalized_value"))
        source_span_id = _text(item.get("source_span_id"))
        stable_key = _text(item.get("stable_key")) or target_slot
        proposal_id = _text(item.get("proposal_id")) or stable_id(
            "cap",
            item.get("turn_id"),
            target_slot,
            stable_key,
            source_span_id,
            normalized_value,
        )
        try:
            confidence = float(item.get("confidence", 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return cls(
            target_slot=target_slot,
            normalized_value=normalized_value,
            source_span_id=source_span_id,
            capture_intent=_text(item.get("capture_intent")) or CAPTURE_INTENT_EXPLICIT,
            stable_key=stable_key,
            proposal_id=proposal_id,
            surface_value=_text(item.get("surface_value")) or normalized_value,
            language=_text(item.get("language")),
            confidence=confidence,
            required_for_full_ack=bool(item.get("required_for_full_ack", True)),
        )

    def to_ref(self) -> CaptureProposalRef:
        return CaptureProposalRef(
            proposal_id=self.proposal_id,
            target_slot=self.target_slot,
            stable_key=self.stable_key,
            source_span_id=self.source_span_id,
            normalized_value=self.normalized_value,
            required_for_full_ack=self.required_for_full_ack,
        )


def _coerce_structured_items(
    *,
    turn_id: str,
    items: Sequence[Mapping[str, Any] | StructuredCaptureItem],
) -> list[StructuredCaptureItem]:
    return [
        item if isinstance(item, StructuredCaptureItem) else StructuredCaptureItem.from_mapping({**item, "turn_id": turn_id})
        for item in items
    ]


def _is_capture_plan_candidate(item: StructuredCaptureItem) -> bool:
    return bool(
        item.target_slot
        and item.normalized_value
        and item.source_span_id
        and item.confidence >= MIN_CAPTURE_PROPOSAL_CONFIDENCE
    )


def build_capture_plan_from_structured(
    *,
    turn_id: str,
    source_event_id: str,
    source_role: str,
    items: Sequence[Mapping[str, Any] | StructuredCaptureItem],
) -> dict[str, Any]:
    if _text(source_role).casefold() != "user":
        plan = CapturePlan.from_proposals(
            turn_id=turn_id,
            source_event_id=source_event_id,
            proposals=(),
            plan_status="rejected",
        )
        payload = plan.to_dict()
        payload["rejection_reason"] = "non_user_source_role"
        return payload
    structured = _coerce_structured_items(turn_id=turn_id, items=items)
    refs = [
        item.to_ref()
        for item in structured
        if _is_capture_plan_candidate(item)
    ]
    plan = CapturePlan.from_proposals(
        turn_id=turn_id,
        source_event_id=source_event_id,
        proposals=refs,
        plan_status="has_proposals" if refs else "needs_clarification",
    )
    payload = plan.to_dict()
    payload["schema"] = "brainstack.capture_plan.v1"
    if not refs:
        payload["no_capture_reason"] = "missing_target_slot_value_or_source_span"
    return payload


def claim_proposal_from_capture_item(
    item: Mapping[str, Any] | StructuredCaptureItem,
    *,
    turn_id: str,
    source_event_id: str,
    source_role: str = "user",
) -> ClaimProposal:
    structured = item if isinstance(item, StructuredCaptureItem) else StructuredCaptureItem.from_mapping({**item, "turn_id": turn_id})
    authority = _source_authority(structured.capture_intent)
    if _text(source_role).casefold() != "user":
        authority = SourceAuthority.ASSISTANT_CLAIM
    shelf = "graph" if structured.target_slot.startswith("project.") else "profile"
    return ClaimProposal(
        claim_id=structured.proposal_id,
        proposal_type=structured.capture_intent,
        source_event_id=source_event_id,
        source_turn_id=turn_id,
        source_span_id=structured.source_span_id,
        turn_role=source_role,
        assertion_speaker=AssertionSpeaker.USER if source_role == "user" else AssertionSpeaker.ASSISTANT,
        span_kind=_span_kind(structured.capture_intent),
        target_shelf=shelf,
        target_slot=structured.target_slot,
        storage_key=structured.stable_key,
        surface_value=structured.surface_value,
        normalized_value=structured.normalized_value,
        language=structured.language,
        normalization_method="structured_extractor",
        authority_class=authority,
        confidence=structured.confidence,
        trace_id=turn_id,
        metadata={
            "schema": CAPTURE_PIPELINE_SCHEMA,
            "capture_intent": structured.capture_intent,
            "required_for_full_ack": structured.required_for_full_ack,
        },
    )


def admit_structured_capture_items(
    *,
    turn_id: str,
    source_event_id: str,
    source_role: str,
    items: Sequence[Mapping[str, Any] | StructuredCaptureItem],
) -> dict[str, Any]:
    structured = _coerce_structured_items(turn_id=turn_id, items=items)
    plan = build_capture_plan_from_structured(
        turn_id=turn_id,
        source_event_id=source_event_id,
        source_role=source_role,
        items=structured,
    )
    decisions = []
    if plan.get("plan_status") == "has_proposals":
        plan_proposal_ids = {str(proposal.get("proposal_id") or "") for proposal in plan.get("proposals", [])}
        for item in structured:
            if item.proposal_id not in plan_proposal_ids:
                continue
            proposal = claim_proposal_from_capture_item(
                item,
                turn_id=turn_id,
                source_event_id=source_event_id,
                source_role=source_role,
            )
            decision = admit_claim(proposal)
            decisions.append(
                {
                    "proposal_id": proposal.claim_id,
                    "decision": decision.decision.value,
                    "reason_code": decision.reason_code,
                    "accepted": decision.accepted,
                    "target_slot": decision.target_slot,
                    "stable_key": decision.stable_key,
                    "truth_eligible": decision.truth_eligible,
                    "policy_version": decision.policy_version,
                    "slot_registry_version": decision.slot_registry_version,
                }
            )
    return {
        "schema": CAPTURE_PIPELINE_SCHEMA,
        "capture_plan": plan,
        "admission_decisions": decisions,
    }


def simulate_receipt_coverage_for_accepted_capture(
    *,
    turn_id: str,
    source_event_id: str,
    source_role: str,
    items: Sequence[Mapping[str, Any] | StructuredCaptureItem],
    principal_scope_key: str,
    workspace_scope_key: str,
    session_id: str,
) -> dict[str, Any]:
    admitted = admit_structured_capture_items(
        turn_id=turn_id,
        source_event_id=source_event_id,
        source_role=source_role,
        items=items,
    )
    plan_payload = admitted["capture_plan"]
    plan = CapturePlan.from_proposals(
        turn_id=turn_id,
        source_event_id=source_event_id,
        proposals=plan_payload.get("proposals", []),
        capture_plan_id=str(plan_payload.get("capture_plan_id") or ""),
        plan_status=str(plan_payload.get("plan_status") or "has_proposals"),
    )
    accepted = {decision["proposal_id"] for decision in admitted["admission_decisions"] if decision["accepted"]}
    receipts = [
        build_memory_write_receipt(
            capture_plan=plan,
            proposal=proposal,
            principal_scope_key=principal_scope_key,
            workspace_scope_key=workspace_scope_key,
            session_id=session_id,
            shelf="graph" if proposal.target_slot.startswith("project.") else "profile",
        )
        for proposal in plan.proposals
        if proposal.proposal_id in accepted
    ]
    coverage = compute_receipt_coverage(
        plan,
        receipts,
        principal_scope_key=principal_scope_key,
        workspace_scope_key=workspace_scope_key,
        session_id=session_id,
    )
    return {
        **admitted,
        "memory_write_receipts": receipts,
        "receipt_coverage": coverage,
        "ack_plan": build_ack_plan(plan, coverage),
    }
