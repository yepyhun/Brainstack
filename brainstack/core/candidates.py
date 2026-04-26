"""Retrieval candidate contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .evidence import EvidenceRef


@dataclass(frozen=True, slots=True)
class CandidateContract:
    candidate_id: str
    evidence: EvidenceRef
    score: float | None = None
    selected: bool = False
    suppression_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "evidence": self.evidence.to_dict(),
            "score": self.score,
            "selected": self.selected,
            "suppression_reason": self.suppression_reason,
        }
