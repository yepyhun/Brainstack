from __future__ import annotations

from typing import Any, Mapping

from ..canonical_memory_event import canonical_event_from_admission_decision
from ..core.admission import AdmissionDecision, TruthShelf, TruthWritePermit
from .durable_truth_port import DurableTruthPort
from .store_runtime import utc_now_iso


def merge_admission_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    decision: AdmissionDecision,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.update(decision.metadata_payload())
    payload["truth_eligible"] = bool(decision.truth_eligible)
    payload["support_visibility"] = decision.support_visibility.value
    payload["admission_decision"] = decision.decision.value
    payload["admission_reason_code"] = decision.reason_code
    return payload


class ProjectionWriter:
    """Single durable projection path for derived Tier-2/consolidation writes."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.port = DurableTruthPort(store)

    def _record_receipt_and_event(
        self,
        *,
        decision: AdmissionDecision,
        metadata: Mapping[str, Any] | None = None,
        durable_row_id: int = 0,
    ) -> int:
        payload = dict(metadata or {})
        receipt_id = int(
            self.store.record_admission_receipt(
                decision=decision,
                durable_row_id=int(durable_row_id or 0),
                metadata=payload,
            )
        )
        if hasattr(self.store, "record_canonical_memory_event"):
            proposal = decision.proposal
            # Canonical events require real source-span provenance. Legacy direct writes
            # remain receipt-only until their caller supplies a source event/span.
            if proposal.source_event_id and proposal.source_span_id:
                event = canonical_event_from_admission_decision(
                    decision=decision,
                    receipt_id=receipt_id,
                    durable_row_id=int(durable_row_id or 0),
                    metadata=payload,
                    observed_at=utc_now_iso(),
                )
                self.store.record_canonical_memory_event(event)
        return receipt_id

    def record_decision(
        self,
        *,
        decision: AdmissionDecision,
        metadata: Mapping[str, Any] | None = None,
        durable_row_id: int = 0,
    ) -> int:
        return self._record_receipt_and_event(
            decision=decision,
            durable_row_id=int(durable_row_id or 0),
            metadata=dict(metadata or {}),
        )

    def write_profile(
        self,
        *,
        decision: AdmissionDecision,
        category: str,
        content: str,
        source: str,
        confidence: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        permit = TruthWritePermit.from_admission(
            decision,
            shelf=TruthShelf.PROFILE,
            slot=decision.target_slot or decision.storage_key,
        )
        row_id = int(
            self.port.write_profile(
                stable_key=decision.stable_key,
                category=category,
                content=content,
                source=source,
                confidence=confidence,
                permit=permit,
                metadata=merge_admission_metadata(metadata, decision=decision),
            )
        )
        self._record_receipt_and_event(decision=decision, durable_row_id=row_id, metadata=dict(metadata or {}))
        return row_id

    def write_graph_state(
        self,
        *,
        decision: AdmissionDecision,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        permit = TruthWritePermit.from_admission(
            decision,
            shelf=TruthShelf.GRAPH,
            slot=decision.target_slot or attribute,
        )
        outcome = self.port.write_graph_state(
            subject_name=subject_name,
            attribute=attribute,
            value_text=value_text,
            source=source,
            permit=permit,
            supersede=decision.supersede,
            metadata=merge_admission_metadata(metadata, decision=decision),
        )
        self._record_receipt_and_event(
            decision=decision,
            durable_row_id=int(outcome.get("state_id") or 0),
            metadata=dict(metadata or {}),
        )
        return dict(outcome)

    def write_graph_relation(
        self,
        *,
        decision: AdmissionDecision,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        metadata: Mapping[str, Any] | None = None,
        inferred: bool = False,
    ) -> dict[str, Any]:
        permit = TruthWritePermit.from_admission(
            decision,
            shelf=TruthShelf.GRAPH,
            slot=predicate,
        )
        outcome = self.port.write_graph_relation(
            subject_name=subject_name,
            predicate=predicate,
            object_name=object_name,
            source=source,
            permit=permit,
            metadata=merge_admission_metadata(metadata, decision=decision),
            inferred=inferred,
        )
        self._record_receipt_and_event(
            decision=decision,
            durable_row_id=int(outcome.get("relation_id") or 0),
            metadata=dict(metadata or {}),
        )
        return dict(outcome)
