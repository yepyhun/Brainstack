"""Derived truth admission contracts.

Raw transcript/episode append is intentionally outside this contract. This
module only describes whether a derived claim may become durable truth.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


ADMISSION_POLICY_VERSION = "brainstack.admission.v1"
SLOT_REGISTRY_VERSION = "brainstack.slot_registry.v1"


class AdmissionDecisionType(StrEnum):
    ACCEPT_DURABLE = "ACCEPT_DURABLE"
    ACCEPT_WITH_SUPERSESSION = "ACCEPT_WITH_SUPERSESSION"
    ACCEPT_SUPPORTING_EVENT = "ACCEPT_SUPPORTING_EVENT"
    MARK_CORRECTED_FALSE_EVENT = "MARK_CORRECTED_FALSE_EVENT"
    QUARANTINE_PROPOSAL = "QUARANTINE_PROPOSAL"
    REJECT_CANDIDATE = "REJECT_CANDIDATE"


class SupportVisibility(StrEnum):
    ANSWER_EVIDENCE = "answer_evidence"
    NORMAL = "normal"
    HISTORY_ONLY = "history_only"
    CONTRADICTION_ONLY = "contradiction_only"
    INSPECT_ONLY = "inspect_only"


class AssertionSpeaker(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    RUNTIME = "runtime"
    TRUSTED_HOST = "trusted_host"
    TRUSTED_IMPORT = "trusted_import"
    QUOTED_USER = "quoted_user"
    QUOTED_ASSISTANT = "quoted_assistant"
    UNKNOWN = "unknown"


class SpanKind(StrEnum):
    ASSERTION = "assertion"
    CORRECTION = "correction"
    QUOTE = "quote"
    QUESTION = "question"
    TOOL_RESULT = "tool_result"
    RUNTIME_DIAGNOSTIC = "runtime_diagnostic"
    ASSISTANT_ANSWER = "assistant_answer"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


class SourceAuthority(StrEnum):
    USER_EXPLICIT_ASSERTION = "user_explicit_assertion"
    USER_EXPLICIT_ASSIGNMENT = "user_explicit_assignment"
    USER_CORRECTION = "user_correction"
    TRUSTED_HOST = "trusted_host"
    TRUSTED_HOST_ASSIGNMENT = "trusted_host_assignment"
    TRUSTED_IMPORT = "trusted_import"
    TRUSTED_RUNTIME = "trusted_runtime"
    OPERATOR_REPAIR = "operator_repair"
    MIGRATION_BACKFILL = "migration_backfill"
    CANARY_SEED = "canary_seed"
    ASSISTANT_CLAIM = "assistant_claim"
    ASSISTANT_SELF_CLAIM = "assistant_self_claim"
    TIER2_SUMMARY = "tier2_summary"
    PULSE_BACKGROUND = "pulse_background"
    SESSION_RECAP = "session_recap"
    GRAPH_INFERENCE = "graph_inference"
    TRANSCRIPT_EVENT = "transcript_event"
    RUNTIME_DIAGNOSTIC = "runtime_diagnostic"
    UNKNOWN = "unknown"


class TruthShelf(StrEnum):
    PROFILE = "profile"
    GRAPH = "graph"
    OPERATING = "operating"
    TASK = "task"


class WritePathClass(StrEnum):
    DERIVED_ADMISSION_GATE = "DERIVED_ADMISSION_GATE"
    TRUSTED_EXPLICIT_CAPTURE = "TRUSTED_EXPLICIT_CAPTURE"
    TRUSTED_HOST_RUNTIME_WRITE = "TRUSTED_HOST_RUNTIME_WRITE"
    MIGRATION_OR_BACKFILL = "MIGRATION_OR_BACKFILL"
    REPAIR_OR_OPERATOR_APPROVED = "REPAIR_OR_OPERATOR_APPROVED"
    TEST_OR_CANARY_SEED = "TEST_OR_CANARY_SEED"
    STORAGE_INTERNAL_ONLY = "STORAGE_INTERNAL_ONLY"


CURRENT_ASSIGNMENT_AUTHORITIES = frozenset(
    {
        SourceAuthority.USER_EXPLICIT_ASSIGNMENT,
        SourceAuthority.TRUSTED_HOST_ASSIGNMENT,
        SourceAuthority.OPERATOR_REPAIR,
    }
)


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str
    shelf: str
    storage_key: str
    value_type: str = "text"
    exclusive_current: bool = False
    allowed_authorities: frozenset[SourceAuthority] = field(default_factory=frozenset)
    supporting_authorities: frozenset[SourceAuthority] = field(default_factory=frozenset)
    forbidden_authorities: frozenset[SourceAuthority] = field(default_factory=frozenset)
    default_support_visibility: SupportVisibility = SupportVisibility.ANSWER_EVIDENCE


@dataclass(frozen=True)
class ClaimProposal:
    claim_id: str
    proposal_type: str = ""
    source_event_id: str = ""
    source_turn_id: str = ""
    source_span_id: str = ""
    turn_role: str = ""
    assertion_speaker: AssertionSpeaker = AssertionSpeaker.UNKNOWN
    span_kind: SpanKind = SpanKind.UNKNOWN
    target_shelf: str = ""
    target_slot: str = ""
    target_scope: str = ""
    storage_key: str = ""
    subject: str = ""
    predicate: str = ""
    surface_value: str = ""
    normalized_value: str = ""
    candidate_value: str = ""
    language: str = ""
    normalization_method: str = ""
    authority_class: SourceAuthority = SourceAuthority.UNKNOWN
    confidence: float = 0.0
    source_text_hash: str = ""
    trace_id: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def admitted_value(self) -> str:
        return self.normalized_value or self.candidate_value or self.surface_value


@dataclass(frozen=True)
class AdmissionDecision:
    decision: AdmissionDecisionType
    reason_code: str
    proposal: ClaimProposal
    target_slot: str = ""
    storage_key: str = ""
    stable_key: str = ""
    truth_eligible: bool = False
    support_visibility: SupportVisibility = SupportVisibility.INSPECT_ONLY
    supersede: bool = False
    policy_version: str = ADMISSION_POLICY_VERSION
    slot_registry_version: str = SLOT_REGISTRY_VERSION
    notes: str = ""

    @property
    def accepted(self) -> bool:
        return self.decision in {
            AdmissionDecisionType.ACCEPT_DURABLE,
            AdmissionDecisionType.ACCEPT_WITH_SUPERSESSION,
        }

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "admission": {
                "policy_version": self.policy_version,
                "slot_registry_version": self.slot_registry_version,
                "decision": self.decision.value,
                "reason_code": self.reason_code,
                "target_slot": self.target_slot,
                "stable_key": self.stable_key,
                "truth_eligible": self.truth_eligible,
                "support_visibility": self.support_visibility.value,
                "claim_id": self.proposal.claim_id,
                "proposal_type": self.proposal.proposal_type,
                "source_event_id": self.proposal.source_event_id,
                "source_turn_id": self.proposal.source_turn_id,
                "source_span_id": self.proposal.source_span_id,
                "turn_role": self.proposal.turn_role,
                "assertion_speaker": self.proposal.assertion_speaker.value,
                "span_kind": self.proposal.span_kind.value,
                "authority_class": self.proposal.authority_class.value,
                "target_scope": self.proposal.target_scope,
                "surface_value": self.proposal.surface_value,
                "normalized_value": self.proposal.normalized_value,
                "language": self.proposal.language,
                "normalization_method": self.proposal.normalization_method,
            }
        }


@dataclass(frozen=True)
class DurableWriteContext:
    write_path_class: WritePathClass
    source_authority: SourceAuthority
    provenance: Mapping[str, Any] = field(default_factory=dict)
    permit_id: str = ""
    admission_id: str = ""
    trusted_context_id: str = ""
    operator_action_id: str = ""
    migration_id: str = ""
    canary_run_id: str = ""
    policy_version: str = ADMISSION_POLICY_VERSION
    slot_registry_version: str = SLOT_REGISTRY_VERSION

    def metadata_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "write_path_class": self.write_path_class.value,
            "source_authority": self.source_authority.value,
            "permit_id": self.permit_id,
            "policy_version": self.policy_version,
            "slot_registry_version": self.slot_registry_version,
        }
        if self.provenance:
            payload["provenance"] = dict(self.provenance)
        for key in ("admission_id", "trusted_context_id", "operator_action_id", "migration_id", "canary_run_id"):
            value = getattr(self, key)
            if value:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class TruthWritePermit:
    permit_id: str
    write_path_class: WritePathClass
    source_authority: SourceAuthority
    issued_by: str
    trace_id: str = ""
    policy_version: str = ADMISSION_POLICY_VERSION
    allowed_shelves: frozenset[TruthShelf] = field(default_factory=frozenset)
    allowed_slots: frozenset[str] = field(default_factory=frozenset)
    admission_id: str = ""
    trusted_context_id: str = ""
    operator_action_id: str = ""
    migration_id: str = ""
    canary_run_id: str = ""

    @classmethod
    def from_admission(
        cls,
        decision: AdmissionDecision,
        *,
        shelf: TruthShelf,
        slot: str = "",
    ) -> "TruthWritePermit":
        proposal = decision.proposal
        seed = f"{decision.stable_key}|{proposal.claim_id}|{decision.reason_code}|{shelf.value}"
        permit_id = f"permit:admission:{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:24]}"
        return cls(
            permit_id=permit_id,
            write_path_class=WritePathClass.DERIVED_ADMISSION_GATE,
            source_authority=proposal.authority_class,
            issued_by="AdmissionDecision",
            trace_id=proposal.trace_id,
            allowed_shelves=frozenset({shelf}),
            allowed_slots=frozenset(
                item
                for item in {
                    slot,
                    decision.target_slot,
                    decision.storage_key,
                    decision.stable_key,
                }
                if item
            ),
            admission_id=proposal.claim_id,
        )

    @classmethod
    def trusted_explicit(
        cls,
        *,
        permit_id: str,
        source_authority: SourceAuthority = SourceAuthority.USER_EXPLICIT_ASSERTION,
        shelf: TruthShelf,
        slot: str = "",
        trace_id: str = "",
        trusted_context_id: str = "",
    ) -> "TruthWritePermit":
        return cls(
            permit_id=permit_id,
            write_path_class=WritePathClass.TRUSTED_EXPLICIT_CAPTURE,
            source_authority=source_authority,
            issued_by="TrustedExplicitCapture",
            trace_id=trace_id,
            allowed_shelves=frozenset({shelf}),
            allowed_slots=frozenset({slot} if slot else ()),
            trusted_context_id=trusted_context_id or permit_id,
        )

    @classmethod
    def migration(
        cls,
        *,
        migration_id: str,
        shelf: TruthShelf,
        slot: str = "",
        trace_id: str = "",
    ) -> "TruthWritePermit":
        return cls(
            permit_id=f"permit:migration:{migration_id}",
            write_path_class=WritePathClass.MIGRATION_OR_BACKFILL,
            source_authority=SourceAuthority.MIGRATION_BACKFILL,
            issued_by="MigrationContext",
            trace_id=trace_id,
            allowed_shelves=frozenset({shelf}),
            allowed_slots=frozenset({slot} if slot else ()),
            migration_id=migration_id,
        )

    @classmethod
    def operator_repair(
        cls,
        *,
        operator_action_id: str,
        shelf: TruthShelf,
        slot: str = "",
        trace_id: str = "",
    ) -> "TruthWritePermit":
        return cls(
            permit_id=f"permit:repair:{operator_action_id}",
            write_path_class=WritePathClass.REPAIR_OR_OPERATOR_APPROVED,
            source_authority=SourceAuthority.OPERATOR_REPAIR,
            issued_by="OperatorRepairContext",
            trace_id=trace_id,
            allowed_shelves=frozenset({shelf}),
            allowed_slots=frozenset({slot} if slot else ()),
            operator_action_id=operator_action_id,
        )

    @classmethod
    def canary_seed(
        cls,
        *,
        canary_run_id: str,
        shelf: TruthShelf,
        slot: str = "",
        trace_id: str = "",
    ) -> "TruthWritePermit":
        return cls(
            permit_id=f"permit:canary:{canary_run_id}",
            write_path_class=WritePathClass.TEST_OR_CANARY_SEED,
            source_authority=SourceAuthority.CANARY_SEED,
            issued_by="CanarySeedContext",
            trace_id=trace_id,
            allowed_shelves=frozenset({shelf}),
            allowed_slots=frozenset({slot} if slot else ()),
            canary_run_id=canary_run_id,
        )

    def context(self) -> DurableWriteContext:
        provenance: dict[str, Any] = {}
        if self.trace_id:
            provenance["trace_id"] = self.trace_id
        return DurableWriteContext(
            write_path_class=self.write_path_class,
            source_authority=self.source_authority,
            provenance=provenance,
            permit_id=self.permit_id,
            admission_id=self.admission_id,
            trusted_context_id=self.trusted_context_id,
            operator_action_id=self.operator_action_id,
            migration_id=self.migration_id,
            canary_run_id=self.canary_run_id,
            policy_version=self.policy_version,
            slot_registry_version=SLOT_REGISTRY_VERSION,
        )

    def metadata_payload(self) -> dict[str, Any]:
        return {
            "truth_write_permit": {
                "permit_id": self.permit_id,
                "write_path_class": self.write_path_class.value,
                "source_authority": self.source_authority.value,
                "issued_by": self.issued_by,
                "trace_id": self.trace_id,
                "policy_version": self.policy_version,
                "allowed_shelves": [shelf.value for shelf in sorted(self.allowed_shelves, key=lambda item: item.value)],
                "allowed_slots": sorted(self.allowed_slots),
                "admission_id": self.admission_id,
                "trusted_context_id": self.trusted_context_id,
                "operator_action_id": self.operator_action_id,
                "migration_id": self.migration_id,
                "canary_run_id": self.canary_run_id,
            },
            "durable_write_context": self.context().metadata_payload(),
        }


@dataclass(frozen=True)
class TruthWriteCommand:
    shelf: TruthShelf
    stable_key: str = ""
    category: str = ""
    content: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)
