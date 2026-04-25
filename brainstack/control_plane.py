from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Mapping

from .db import BrainstackStore
from .executive_retrieval import retrieve_executive_context
from .local_typed_understanding import analyze_local_query
from .profile_contract import resolve_direct_identity_profile_slots
from .retrieval import render_working_memory_block
from .temporal import record_is_effective_at, record_temporal_status


def _has_current_and_prior_graph_states(graph_rows: list[dict[str, Any]]) -> bool:
    has_current = any(
        str(row.get("row_type") or "") == "state"
        and bool(row.get("is_current"))
        and record_temporal_status(row) == "current"
        and record_is_effective_at(row)
        for row in graph_rows
    )
    has_prior = any(
        str(row.get("row_type") or "") == "state"
        and not (
            bool(row.get("is_current"))
            and record_temporal_status(row) == "current"
            and record_is_effective_at(row)
        )
        for row in graph_rows
    )
    return has_current and has_prior


@dataclass
class QueryAnalysis:
    operating_like: bool
    task_like: bool
    profile_slot_targets: tuple[str, ...]
    task_lookup: Dict[str, Any] | None
    operating_lookup: Dict[str, Any] | None
    route_payload: Dict[str, Any] | None


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
    style_contract_char_budget: int
    evidence_item_budget: int
    operating_limit: int
    graph_limit: int
    corpus_limit: int
    corpus_char_budget: int
    continuation_emphasis: bool
    show_authoritative_contract: bool
    suppress_contract_if_in_system_substrate: bool
    render_ordinary_contract: bool


def analyze_query(
    store: BrainstackStore,
    query: str,
    *,
    principal_scope_key: str = "",
    timezone_name: str = "UTC",
) -> QueryAnalysis:
    profile_slot_targets = resolve_direct_identity_profile_slots(query)
    understanding = analyze_local_query(
        store,
        query=query,
        principal_scope_key=principal_scope_key,
        timezone_name=timezone_name,
    )
    task_lookup = understanding.get("task_lookup")
    operating_lookup = understanding.get("operating_lookup")
    route_payload = understanding.get("route_payload")
    return QueryAnalysis(
        operating_like=isinstance(operating_lookup, dict),
        task_like=isinstance(task_lookup, dict),
        profile_slot_targets=profile_slot_targets,
        task_lookup=dict(task_lookup) if isinstance(task_lookup, Mapping) else None,
        operating_lookup=dict(operating_lookup) if isinstance(operating_lookup, Mapping) else None,
        route_payload=dict(route_payload) if isinstance(route_payload, Mapping) else None,
    )


def _initial_policy(
    *,
    analysis: QueryAnalysis,
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    evidence_item_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    operating_match_limit: int = 3,
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
        style_contract_char_budget=0,
        evidence_item_budget=max(1, min(evidence_item_budget, 6)),
        operating_limit=min(operating_match_limit, 2),
        graph_limit=min(graph_limit, 2),
        corpus_limit=min(corpus_limit, 2),
        corpus_char_budget=min(corpus_char_budget, 360),
        continuation_emphasis=False,
        show_authoritative_contract=False,
        suppress_contract_if_in_system_substrate=True,
        render_ordinary_contract=False,
    )

    if analysis.profile_slot_targets:
        policy.mode = "balanced"
        policy.collapse_mode = "balanced"
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 2))
        policy.continuity_recent_limit = max(1, min(continuity_recent_limit, 1))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 560))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 5))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 2))
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 1))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 1))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 260))
        policy.show_authoritative_contract = False

    if analysis.operating_like:
        policy.mode = "balanced"
        policy.collapse_mode = "balanced"
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 2))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 640))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 7))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 4))
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 2))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 2))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 360))

    if analysis.task_like:
        policy.mode = "compact"
        policy.collapse_mode = "aggressive"
        policy.profile_limit = min(policy.profile_limit, 1)
        policy.continuity_match_limit = max(1, min(continuity_match_limit, 2))
        policy.continuity_recent_limit = max(1, min(continuity_recent_limit, 1))
        policy.transcript_limit = max(1, min(transcript_match_limit, 1))
        policy.transcript_char_budget = min(max(policy.transcript_char_budget, 220), 320)
        policy.evidence_item_budget = max(1, min(evidence_item_budget, 3))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 2))
        policy.graph_limit = 0
        policy.corpus_limit = 0
        policy.corpus_char_budget = 0
        policy.show_graph_history = False

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
    evidence_item_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    operating_match_limit: int = 3,
    route_resolver: Callable[[str], Dict[str, Any] | str] | None = None,
    timezone_name: str = "UTC",
    system_substrate: Dict[str, Any] | None = None,
    render_ordinary_contract: bool = False,
    record_retrievals: bool = True,
) -> Dict[str, Any]:
    analysis = analyze_query(
        store,
        query,
        principal_scope_key=principal_scope_key,
        timezone_name=timezone_name,
    )
    behavior_policy_snapshot = store.get_behavior_policy_snapshot(principal_scope_key=principal_scope_key)
    compiled_behavior_policy = store.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
    policy = _initial_policy(
        analysis=analysis,
        profile_match_limit=profile_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        evidence_item_budget=evidence_item_budget,
        operating_match_limit=operating_match_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
    )
    policy.render_ordinary_contract = bool(render_ordinary_contract)

    retrieval = retrieve_executive_context(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        timezone_name=timezone_name,
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
    task_rows = retrieval.get("task_rows") or []
    operating_rows = retrieval.get("operating_rows") or []
    channels = retrieval["channels"]
    routing = retrieval.get("routing", {"requested_mode": "fact", "applied_mode": "fact"})

    if routing.get("applied_mode") == "temporal":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 720)
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 2))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 8))
    elif routing.get("applied_mode") == "aggregate":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 960)
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 3))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 3))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 650))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 3))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 9))
    elif routing.get("applied_mode") == "style_contract":
        policy.style_contract_char_budget = max(policy.style_contract_char_budget, 2400)
        policy.show_authoritative_contract = True

    support_channels = sum(
        1
        for channel in channels
        if channel.get("status") == "active" and int(channel.get("candidate_count") or 0) > 0
    )
    conflict_present = any(row["row_type"] == "conflict" for row in graph_rows)
    profile_support_present = bool(
        profile_items
        and (
            analysis.profile_slot_targets
            or routing.get("applied_mode") == "style_contract"
            or any(str(row.get("category") or "").strip() == "preference" for row in profile_items)
        )
    )
    thin_support_without_contract = not any(
        (
            profile_items,
            matched,
            recent,
            transcript_rows,
            task_rows,
            operating_rows,
            graph_rows,
            corpus_rows,
        )
    )

    if profile_support_present:
        policy.mode = "balanced"
        policy.collapse_mode = "balanced"
        policy.profile_limit = max(policy.profile_limit, min(profile_match_limit, 4))
        policy.continuity_match_limit = max(1, min(continuity_match_limit, 2))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.transcript_char_budget = max(policy.transcript_char_budget, min(transcript_char_budget, 560))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 2))
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 2))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 2))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 320))
        if routing.get("applied_mode") != "style_contract":
            policy.show_authoritative_contract = False
            policy.suppress_contract_if_in_system_substrate = False

    if (
        compiled_behavior_policy is not None
        and thin_support_without_contract
        and routing.get("applied_mode") != "style_contract"
    ):
        policy.suppress_contract_if_in_system_substrate = False

    if conflict_present:
        policy.mode = "deep"
        policy.collapse_mode = "minimal"
        policy.provenance_mode = "expanded"
        policy.show_graph_history = True
        policy.conflict_escalation = True
        policy.show_policy = True
    elif _has_current_and_prior_graph_states(graph_rows) and routing.get("applied_mode") == "temporal":
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))

    if analysis.operating_like and operating_rows and not conflict_present:
        policy.confidence_band = "high"
    elif profile_support_present and not conflict_present:
        policy.confidence_band = "high"
    elif routing.get("applied_mode") == "style_contract" and profile_items and not conflict_present:
        policy.confidence_band = "high"
    elif analysis.profile_slot_targets and profile_items and not conflict_present:
        policy.confidence_band = "high"
    elif routing.get("applied_mode") == "temporal" and graph_rows and not conflict_present:
        policy.confidence_band = "high" if support_channels >= 2 else "medium"
    elif transcript_rows and not conflict_present:
        policy.confidence_band = "medium"
    elif support_channels >= 3 and not conflict_present:
        policy.confidence_band = "high"
    elif support_channels >= 1 and not conflict_present:
        policy.confidence_band = "medium"
    else:
        policy.confidence_band = "low"

    if policy.confidence_band == "low":
        policy.provenance_mode = "expanded"
        policy.show_policy = True

    if conflict_present:
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "open graph conflict requires verification before relying on memory only"
    elif policy.confidence_band == "low":
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "memory support is too thin for a memory-only response"
    else:
        policy.tool_avoidance_allowed = True
        policy.tool_avoidance_reason = "memory support is sufficient for a first response"

    policy_payload = asdict(policy)
    if isinstance(behavior_policy_snapshot, dict):
        policy_payload["behavior_policy_snapshot"] = behavior_policy_snapshot
    if compiled_behavior_policy is not None:
        compiled_policy_payload = (
            dict(compiled_behavior_policy.get("policy") or {})
            if isinstance(compiled_behavior_policy, dict)
            else {}
        )
        if compiled_policy_payload:
            policy_payload["compiled_behavior_policy"] = compiled_policy_payload
    lookup_semantics = retrieval.get("lookup_semantics")
    if isinstance(lookup_semantics, dict):
        policy_payload["lookup_semantics"] = lookup_semantics

    block = render_working_memory_block(
        policy=policy_payload,
        route_mode=str(routing.get("applied_mode") or "fact"),
        profile_items=profile_items,
        task_rows=task_rows,
        operating_rows=operating_rows,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
        system_substrate=system_substrate,
    )

    if record_retrievals and profile_items:
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
    if record_retrievals and graph_rows:
        store.record_graph_retrievals(rows=graph_rows)
    if record_retrievals and corpus_rows:
        store.record_corpus_retrievals(rows=corpus_rows)
    return {
        "analysis": asdict(analysis),
        "policy": policy_payload,
        "channels": channels,
        "profile_items": profile_items,
        "task_rows": task_rows,
        "operating_rows": operating_rows,
        "matched": matched,
        "recent": recent,
        "transcript_rows": transcript_rows,
        "graph_rows": graph_rows,
        "corpus_rows": corpus_rows,
        "fused_candidates": retrieval["fused_candidates"],
        "decomposition": retrieval.get("decomposition", {"used": False, "queries": [query]}),
        "entity_resolution": retrieval.get("entity_resolution", {}),
        "associative_expansion": retrieval.get("associative_expansion", {}),
        "routing": routing,
        "system_substrate": dict(system_substrate or {}),
        "block": block,
    }
