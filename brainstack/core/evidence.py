"""Evidence references and roles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .authority import AuthorityClass, SourceRole
from .ids import EvidenceId, StableKey
from .reason_codes import ReasonCode


class EvidenceRole(StrEnum):
    ANSWER = "answer"
    SUPPORTING = "supporting"
    EXCLUDED = "excluded"


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    evidence_id: EvidenceId
    shelf: str
    stable_key: StableKey | None
    role: EvidenceRole
    authority: AuthorityClass
    source_role: SourceRole
    reason_code: ReasonCode = ReasonCode.UNCLASSIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "evidence_id": str(self.evidence_id),
            "shelf": self.shelf,
            "stable_key": None if self.stable_key is None else str(self.stable_key),
            "role": self.role.value,
            "authority": self.authority.value,
            "source_role": self.source_role.value,
            "reason_code": self.reason_code.value,
        }
