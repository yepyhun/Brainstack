from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Tier2ReconcileResult:
    action_counts: dict[str, int] = field(default_factory=dict)
    writes_performed: int = 0
    operating_promotions: dict[str, Any] = field(default_factory=dict)
    budget_report: dict[str, Any] = field(default_factory=dict)
    consolidation_plan: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "Tier2ReconcileResult":
        return cls()

    @classmethod
    def from_parts(
        cls,
        *,
        action_counts: Mapping[str, Any] | None = None,
        writes_performed: Any = 0,
        operating_promotions: Mapping[str, Any] | None = None,
        budget_report: Mapping[str, Any] | None = None,
        consolidation_plan: Mapping[str, Any] | None = None,
    ) -> "Tier2ReconcileResult":
        return cls(
            action_counts={str(key): int(value or 0) for key, value in dict(action_counts or {}).items()},
            writes_performed=int(writes_performed or 0),
            operating_promotions=dict(operating_promotions or {}),
            budget_report=dict(budget_report or {}),
            consolidation_plan=dict(consolidation_plan or {}),
        )

    def to_trace(self) -> dict[str, Any]:
        return {
            "action_counts": dict(self.action_counts),
            "writes_performed": int(self.writes_performed),
            "operating_promotions": dict(self.operating_promotions),
            "consolidation_budget": dict(self.budget_report),
            "consolidation_plan": dict(self.consolidation_plan),
        }
