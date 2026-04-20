from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .graph_evidence import GraphEvidenceItem
from .stable_memory_guardrails import StableMemoryAdmissionDecision, should_admit_stable_memory


@dataclass(frozen=True)
class Tier2ScheduleDecision:
    should_queue: bool
    reason: str
    idle_window_seconds: int
    batch_turn_limit: int
    pending_turns: int
    idle_seconds: float | None = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TurnIngestPlan:
    durable_admission: StableMemoryAdmissionDecision
    profile_candidates: List[Dict[str, Any]]
    graph_evidence_items: List[GraphEvidenceItem]
    tier2_schedule: Tier2ScheduleDecision


@dataclass(frozen=True)
class SessionMessageIngestPlan:
    durable_admission: StableMemoryAdmissionDecision
    profile_candidates: List[Dict[str, Any]]
    graph_evidence_items: List[GraphEvidenceItem]


def _default_live_graph_evidence_items() -> List[GraphEvidenceItem]:
    # Phase 40.3 removes regex-based raw text graph guessing from the default
    # ingest path. Live graph writes now require explicit typed evidence from a
    # producer-aligned surface rather than boundary text pattern matching.
    return []


def _plan_tier2_schedule(
    *,
    pending_turns: int,
    idle_seconds: float | None,
    idle_window_seconds: int,
    batch_turn_limit: int,
) -> Tier2ScheduleDecision:
    if idle_seconds is not None and idle_seconds >= idle_window_seconds:
        return Tier2ScheduleDecision(
            should_queue=True,
            reason="idle_window",
            idle_window_seconds=idle_window_seconds,
            batch_turn_limit=batch_turn_limit,
            pending_turns=0,
            idle_seconds=idle_seconds,
        )
    if pending_turns >= batch_turn_limit:
        return Tier2ScheduleDecision(
            should_queue=True,
            reason="turn_batch_limit",
            idle_window_seconds=idle_window_seconds,
            batch_turn_limit=batch_turn_limit,
            pending_turns=0,
            idle_seconds=idle_seconds,
        )
    return Tier2ScheduleDecision(
        should_queue=False,
        reason="waiting_for_batch",
        idle_window_seconds=idle_window_seconds,
        batch_turn_limit=batch_turn_limit,
        pending_turns=pending_turns,
        idle_seconds=idle_seconds,
    )


def build_turn_ingest_plan(
    *,
    user_content: str,
    pending_turns: int,
    idle_seconds: float | None,
    idle_window_seconds: int,
    batch_turn_limit: int,
) -> TurnIngestPlan:
    admission = should_admit_stable_memory(fact_text=user_content)
    schedule = _plan_tier2_schedule(
        pending_turns=pending_turns,
        idle_seconds=idle_seconds,
        idle_window_seconds=idle_window_seconds,
        batch_turn_limit=batch_turn_limit,
    )
    return TurnIngestPlan(
        durable_admission=admission,
        # Phase 17 removes handwritten Tier-1 semantic/profile inference from the
        # live ingest path. Durable profile writes now belong to the Tier-2 path
        # or explicit memory writes, not language-specific slot guessing here.
        profile_candidates=[],
        graph_evidence_items=_default_live_graph_evidence_items(),
        tier2_schedule=schedule,
    )


def build_session_message_ingest_plan(*, role: str, content: str) -> SessionMessageIngestPlan:
    if role != "user":
        return SessionMessageIngestPlan(
            durable_admission=StableMemoryAdmissionDecision(False, "non_user_role"),
            profile_candidates=[],
            graph_evidence_items=[],
        )
    admission = should_admit_stable_memory(fact_text=content)
    return SessionMessageIngestPlan(
        durable_admission=admission,
        profile_candidates=[],
        graph_evidence_items=_default_live_graph_evidence_items(),
    )
