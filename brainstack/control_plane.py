from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from .db import BrainstackStore
from .retrieval import render_working_memory_block
from .transcript import has_meaningful_transcript_evidence

HIGH_STAKES_TERMS = (
    "safe",
    "safety",
    "dose",
    "dosage",
    "diagnosis",
    "diagnose",
    "treatment",
    "treat",
    "patient",
    "symptom",
    "legal",
    "law",
    "contract",
    "prescription",
    "medicine",
    "drug",
)

EXPLANATION_TERMS = (
    "why",
    "how",
    "explain",
    "connection",
    "connect",
    "related",
    "relationship",
    "compare",
    "összefügg",
    "miért",
    "hogyan",
    "kapcsol",
)

TEMPORAL_TERMS = (
    "now",
    "current",
    "currently",
    "before",
    "after",
    "previous",
    "changed",
    "when",
    "date",
    "days",
    "months",
    "years",
    "most recent",
    "latest",
    "most current",
    "előző",
    "most",
    "jelenlegi",
)

PREFERENCE_TERMS = (
    "prefer",
    "preference",
    "like",
    "dislike",
    "want",
    "style",
    "usually",
    "mindig",
    "inkább",
    "szeretem",
)


def _contains_any(query: str, terms: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return any(term in lowered for term in terms)


@dataclass
class QueryAnalysis:
    high_stakes: bool
    explanatory: bool
    temporal: bool
    preference: bool


@dataclass
class WorkingMemoryPolicy:
    mode: str
    collapse_mode: str
    provenance_mode: str
    confidence_band: str
    show_graph_history: bool
    conflict_escalation: bool
    tool_avoidance_allowed: bool
    tool_avoidance_reason: str
    show_policy: bool
    profile_limit: int
    continuity_match_limit: int
    continuity_recent_limit: int
    transcript_limit: int
    transcript_char_budget: int
    graph_limit: int
    corpus_limit: int
    corpus_char_budget: int


def analyze_query(query: str) -> QueryAnalysis:
    return QueryAnalysis(
        high_stakes=_contains_any(query, HIGH_STAKES_TERMS),
        explanatory=_contains_any(query, EXPLANATION_TERMS),
        temporal=_contains_any(query, TEMPORAL_TERMS),
        preference=_contains_any(query, PREFERENCE_TERMS),
    )


def _initial_policy(
    *,
    analysis: QueryAnalysis,
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
) -> WorkingMemoryPolicy:
    policy = WorkingMemoryPolicy(
        mode="balanced",
        collapse_mode="balanced",
        provenance_mode="compact",
        confidence_band="medium",
        show_graph_history=False,
        conflict_escalation=False,
        tool_avoidance_allowed=False,
        tool_avoidance_reason="policy not finalized",
        show_policy=False,
        profile_limit=min(profile_match_limit, 3),
        continuity_match_limit=min(continuity_match_limit, 2),
        continuity_recent_limit=min(continuity_recent_limit, 1),
        transcript_limit=min(transcript_match_limit, 1),
        transcript_char_budget=min(transcript_char_budget, 260),
        graph_limit=min(graph_limit, 2),
        corpus_limit=min(corpus_limit, 2),
        corpus_char_budget=min(corpus_char_budget, 360),
    )

    if analysis.preference and not analysis.high_stakes:
        policy.mode = "compact"
        policy.collapse_mode = "aggressive"
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = min(continuity_match_limit, 1)
        policy.continuity_recent_limit = min(continuity_recent_limit, 1)
        policy.transcript_limit = 0
        policy.transcript_char_budget = 0
        policy.graph_limit = 1
        policy.corpus_limit = 0
        policy.corpus_char_budget = 0

    if analysis.explanatory:
        policy.mode = "balanced"
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 3))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 3))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 650))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 1))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 300))

    if analysis.temporal:
        policy.mode = "balanced"
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))

    if analysis.high_stakes:
        policy.mode = "deep"
        policy.collapse_mode = "minimal"
        policy.provenance_mode = "expanded"
        policy.show_graph_history = True
        policy.show_policy = True
        policy.transcript_limit = 0
        policy.transcript_char_budget = 0
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 5))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 4))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 900))

    return policy


def build_working_memory_packet(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
) -> Dict[str, Any]:
    analysis = analyze_query(query)
    policy = _initial_policy(
        analysis=analysis,
        profile_match_limit=profile_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
    )

    profile_items = store.search_profile(query=query, limit=policy.profile_limit) if policy.profile_limit > 0 else []
    matched = (
        store.search_continuity(query=query, session_id=session_id, limit=policy.continuity_match_limit)
        if policy.continuity_match_limit > 0
        else []
    )
    matched_ids = {item["id"] for item in matched}
    recent = []
    if policy.continuity_recent_limit > 0:
        recent = store.recent_continuity(session_id=session_id, limit=max(policy.continuity_recent_limit * 2, 2))
        recent = [item for item in recent if item["id"] not in matched_ids][: policy.continuity_recent_limit]

    graph_rows = store.search_graph(query=query, limit=policy.graph_limit) if policy.graph_limit > 0 else []
    corpus_rows = (
        store.search_corpus(query=query, limit=max(policy.corpus_limit * 3, policy.corpus_limit))
        if policy.corpus_limit > 0
        else []
    )
    transcript_rows: List[Dict[str, Any]] = []

    if policy.transcript_limit > 0:
        transcript_candidates = store.search_transcript(
            query=query,
            session_id=session_id,
            limit=max(policy.transcript_limit * 3, policy.transcript_limit),
        )
        continuity_is_compact = (not matched) or all(len(str(item.get("content", ""))) <= 220 for item in matched)
        transcript_allowed = (
            continuity_is_compact
            and not profile_items
            and not graph_rows
            and not corpus_rows
            and has_meaningful_transcript_evidence(query, transcript_candidates)
        )
        if transcript_allowed:
            transcript_rows = transcript_candidates[: policy.transcript_limit]

    support_shelves = sum(
        1
        for rows in (profile_items, matched or recent, transcript_rows, graph_rows, corpus_rows)
        if rows
    )
    conflict_present = any(row["row_type"] == "conflict" for row in graph_rows)

    if conflict_present:
        policy.mode = "deep"
        policy.collapse_mode = "minimal"
        policy.provenance_mode = "expanded"
        policy.show_graph_history = True
        policy.conflict_escalation = True
        policy.show_policy = True

    if analysis.preference and profile_items and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif analysis.temporal and graph_rows and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high" if support_shelves >= 2 else "medium"
    elif transcript_rows and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "medium"
    elif support_shelves >= 3 and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif support_shelves >= 1 and not conflict_present:
        policy.confidence_band = "medium"
    else:
        policy.confidence_band = "low"

    if policy.confidence_band == "low":
        policy.provenance_mode = "expanded"
        policy.show_policy = True

    if analysis.high_stakes:
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "high-stakes query requires explicit verification or tools"
    elif conflict_present:
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "open graph conflict requires verification before relying on memory only"
    elif policy.confidence_band == "low":
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "memory support is too thin for a memory-only response"
    else:
        policy.tool_avoidance_allowed = True
        policy.tool_avoidance_reason = "memory support is sufficient for a first response"

    block = render_working_memory_block(
        policy=asdict(policy),
        profile_items=profile_items,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )
    return {
        "analysis": asdict(analysis),
        "policy": asdict(policy),
        "block": block,
    }
