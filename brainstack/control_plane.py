from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict

from .db import BrainstackStore
from .executive_retrieval import retrieve_executive_context
from .profile_contract import resolve_direct_identity_profile_slots
from .retrieval import render_working_memory_block

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
CONTINUATION_TERMS = (
    "continue",
    "pick up where we left off",
    "without repeating",
    "continue that plan",
    "resume",
    "folytasd",
    "folytatni",
    "onnan folytassuk",
    "ismétlés nélkül",
    "ismételném",
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
    continuation: bool
    profile_slot_targets: tuple[str, ...]


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
    continuation_emphasis: bool


def analyze_query(query: str) -> QueryAnalysis:
    profile_slot_targets = resolve_direct_identity_profile_slots(query)
    return QueryAnalysis(
        high_stakes=_contains_any(query, HIGH_STAKES_TERMS),
        explanatory=_contains_any(query, EXPLANATION_TERMS),
        temporal=_contains_any(query, TEMPORAL_TERMS),
        preference=_contains_any(query, PREFERENCE_TERMS),
        continuation=_contains_any(query, CONTINUATION_TERMS),
        profile_slot_targets=profile_slot_targets,
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
        transcript_limit=min(transcript_match_limit, 2),
        transcript_char_budget=min(transcript_char_budget, 520),
        graph_limit=min(graph_limit, 2),
        corpus_limit=min(corpus_limit, 2),
        corpus_char_budget=min(corpus_char_budget, 360),
        continuation_emphasis=False,
    )

    if analysis.preference and not analysis.high_stakes:
        policy.mode = "compact"
        policy.collapse_mode = "aggressive"
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = min(continuity_match_limit, 1)
        policy.continuity_recent_limit = max(1, min(continuity_recent_limit, 2))
        policy.transcript_limit = 0
        policy.transcript_char_budget = 0
        policy.graph_limit = 1
        policy.corpus_limit = 0
        policy.corpus_char_budget = 0

    if analysis.profile_slot_targets and not analysis.high_stakes:
        policy.mode = "compact"
        policy.collapse_mode = "aggressive"
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = min(policy.continuity_match_limit, min(continuity_match_limit, 1))
        policy.continuity_recent_limit = max(1, min(continuity_recent_limit, 1))
        policy.transcript_limit = min(policy.transcript_limit, min(transcript_match_limit, 1))
        policy.transcript_char_budget = min(policy.transcript_char_budget, min(transcript_char_budget, 240))
        policy.graph_limit = 0
        policy.corpus_limit = 0
        policy.corpus_char_budget = 0

    if analysis.explanatory:
        policy.mode = "balanced"
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 3))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 3))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 650))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 640))

    if analysis.continuation and not analysis.high_stakes:
        policy.mode = "balanced"
        policy.continuation_emphasis = True
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 2))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 640))
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 3))

    if analysis.temporal:
        policy.mode = "balanced"
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 640))

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
    principal_scope_key: str = "",
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    route_resolver: Callable[[str], Dict[str, Any] | str] | None = None,
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

    retrieval = retrieve_executive_context(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        analysis=asdict(analysis),
        policy=asdict(policy),
        route_resolver=route_resolver,
    )

    profile_items = retrieval["profile_items"]
    matched = retrieval["matched"]
    recent = retrieval["recent"]
    transcript_rows = retrieval["transcript_rows"]
    graph_rows = retrieval["graph_rows"]
    corpus_rows = retrieval["corpus_rows"]
    channels = retrieval["channels"]
    routing = retrieval.get("routing", {"requested_mode": "fact", "applied_mode": "fact"})

    if routing.get("applied_mode") == "temporal":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 720)
        policy.show_graph_history = True
    elif routing.get("applied_mode") == "aggregate":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 960)

    support_channels = sum(
        1
        for channel in channels
        if channel.get("status") == "active" and int(channel.get("candidate_count") or 0) > 0
    )
    conflict_present = any(row["row_type"] == "conflict" for row in graph_rows)

    if conflict_present:
        policy.mode = "deep"
        policy.collapse_mode = "minimal"
        policy.provenance_mode = "expanded"
        policy.show_graph_history = True
        policy.conflict_escalation = True
        policy.show_policy = True

    if analysis.preference and (profile_items or recent) and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif routing.get("applied_mode") == "style_contract" and profile_items and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif analysis.profile_slot_targets and profile_items and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif analysis.temporal and graph_rows and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high" if support_channels >= 2 else "medium"
    elif transcript_rows and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "medium"
    elif support_channels >= 3 and not analysis.high_stakes and not conflict_present:
        policy.confidence_band = "high"
    elif support_channels >= 1 and not conflict_present:
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
        route_mode=str(routing.get("applied_mode") or "fact"),
        profile_items=profile_items,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )

    if profile_items:
        matched_profile_keys = {
            str(item.get("stable_key") or "").strip()
            for item in retrieval["profile_items"]
            if str(item.get("stable_key") or "").strip()
        }
        store.record_profile_retrievals(
            rows=[
                {
                    "stable_key": row.get("stable_key"),
                    "storage_key": row.get("storage_key"),
                    "category": row.get("category"),
                    "principal_scope_key": row.get("principal_scope_key"),
                    "matched": str(row.get("stable_key") or "").strip() in matched_profile_keys,
                    "fallback": False,
                }
                for row in profile_items
            ]
        )
    if graph_rows:
        store.record_graph_retrievals(rows=graph_rows)
    if corpus_rows:
        store.record_corpus_retrievals(rows=corpus_rows)
    return {
        "analysis": asdict(analysis),
        "policy": asdict(policy),
        "channels": channels,
        "profile_items": profile_items,
        "matched": matched,
        "recent": recent,
        "transcript_rows": transcript_rows,
        "graph_rows": graph_rows,
        "corpus_rows": corpus_rows,
        "fused_candidates": retrieval["fused_candidates"],
        "decomposition": retrieval.get("decomposition", {"used": False, "queries": [query]}),
        "routing": routing,
        "block": block,
    }
