"""Model-facing memory answerability contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .authority import AuthorityClass
from .ids import EvidenceId
from .reason_codes import ReasonCode


class AnswerabilityState(StrEnum):
    ANSWERABLE = "answerable"
    UNANSWERABLE = "unanswerable"
    CONFLICTED = "conflicted"
    DEGRADED = "degraded"


class MaxClaimStrength(StrEnum):
    MEMORY_TRUTH = "memory_truth"
    BOUNDED_EVENT = "bounded_event"
    SOURCE_SAYS = "source_says"
    SUPPORTING_CONTEXT = "supporting_context"
    NONE = "none"


class AnswerType(StrEnum):
    EXPLICIT_USER_FACT = "explicit_user_fact"
    CURRENT_ASSIGNMENT = "current_assignment"
    CORPUS_CITATION = "corpus_citation"
    GRAPH_TRUTH = "graph_truth"
    CONVERSATION_EVENT = "conversation_event"
    CONFLICT_REPORT = "conflict_report"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class MemoryAnswerability:
    state: AnswerabilityState
    max_claim_strength: MaxClaimStrength
    answer_type: AnswerType
    authority: AuthorityClass
    reason_code: ReasonCode
    answer_evidence_ids: tuple[EvidenceId, ...] = field(default_factory=tuple)
    supporting_context_ids: tuple[EvidenceId, ...] = field(default_factory=tuple)
    excluded_evidence_ids: tuple[EvidenceId, ...] = field(default_factory=tuple)
    can_claim_memory_truth: bool = False
    can_claim_current_assignment: bool = False
    must_not_claim: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "max_claim_strength": self.max_claim_strength.value,
            "answer_type": self.answer_type.value,
            "authority": self.authority.value,
            "reason_code": self.reason_code.value,
            "answer_evidence_ids": [str(item) for item in self.answer_evidence_ids],
            "supporting_context_ids": [str(item) for item in self.supporting_context_ids],
            "excluded_evidence_ids": [str(item) for item in self.excluded_evidence_ids],
            "can_claim_memory_truth": self.can_claim_memory_truth,
            "can_claim_current_assignment": self.can_claim_current_assignment,
            "must_not_claim": list(self.must_not_claim),
        }
