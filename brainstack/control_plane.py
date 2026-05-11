from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Callable, Dict, Mapping

from .core.packet_budget import (
    PacketBudgetPolicy,
    apply_packet_budget,
    resolve_packet_budget_max_candidate_tokens,
    resolve_packet_budget_mode,
)
from .adaptive_route_plan import build_adaptive_route_plan, route_plan_limit_overrides, route_plan_resolver_payload
from .current_truth_view import rebuild_current_truth_view
from .db import BrainstackStore
from .executive_retrieval import retrieve_executive_context
from .local_typed_understanding import analyze_local_query
from .profile_contract import resolve_direct_identity_profile_slots
from .retrieval import render_working_memory_block
from .retrieval_control_plan import retrieval_control_plan_from_adaptive_plan
from .retrieval_context_envelope import build_retrieval_context_envelope
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


_EXPLICIT_EVIDENCE_CLASS_TERMS = {
    "profile": "profile",
    "continuity": "continuity",
    "transcript": "transcript",
    "operating": "operating",
    "graph": "graph",
    "corpus": "corpus",
    "citation": "corpus",
    "citations": "corpus",
    "task": "task",
    "tasks": "task",
}


def _explicit_evidence_classes_from_query(query: str) -> list[str]:
    lowered = str(query or "").casefold()
    tokens = set(re.findall(r"[^\W_]+(?:[-_][^\W_]+)*", lowered, re.UNICODE))
    classes = [
        evidence_class
        for token, evidence_class in _EXPLICIT_EVIDENCE_CLASS_TERMS.items()
        if token in tokens
    ]
    if "current truth" in lowered or "current-truth" in lowered or "current_truth" in lowered:
        classes.append("current_truth")
    if "memory" in tokens and "proof" in tokens:
        classes.append("deep_mixed")
    return list(dict.fromkeys(classes))


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
    semantic_evidence_enabled: bool
    semantic_evidence_reason: str
    retrieval_control_plan: Dict[str, Any] = field(default_factory=dict)


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
        semantic_evidence_enabled=True,
        semantic_evidence_reason="default_enabled_before_route_plan",
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


def _apply_route_policy(
    policy: WorkingMemoryPolicy,
    routing: Mapping[str, Any],
    *,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    evidence_item_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    operating_match_limit: int,
) -> None:
    applied_mode = routing.get("applied_mode")
    if applied_mode == "temporal":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 720)
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 4))
        policy.continuity_match_limit = max(policy.continuity_match_limit, min(continuity_match_limit, 3))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 2))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 8))
    elif applied_mode == "aggregate":
        policy.transcript_char_budget = max(policy.transcript_char_budget, 960)
        policy.show_graph_history = True
        policy.graph_limit = max(policy.graph_limit, min(graph_limit, 3))
        policy.corpus_limit = max(policy.corpus_limit, min(corpus_limit, 3))
        policy.corpus_char_budget = max(policy.corpus_char_budget, min(corpus_char_budget, 650))
        policy.continuity_recent_limit = max(policy.continuity_recent_limit, min(continuity_recent_limit, 2))
        policy.transcript_limit = max(policy.transcript_limit, min(transcript_match_limit, 2))
        policy.operating_limit = max(policy.operating_limit, min(operating_match_limit, 3))
        policy.evidence_item_budget = max(policy.evidence_item_budget, min(evidence_item_budget, 9))
    elif applied_mode == "style_contract":
        policy.style_contract_char_budget = max(policy.style_contract_char_budget, 2400)
        policy.show_authoritative_contract = True


def _profile_support_present(
    *,
    analysis: QueryAnalysis,
    routing: Mapping[str, Any],
    profile_items: list[dict[str, Any]],
) -> bool:
    return bool(
        profile_items
        and (
            analysis.profile_slot_targets
            or routing.get("applied_mode") == "style_contract"
            or any(str(row.get("category") or "").strip() == "preference" for row in profile_items)
        )
    )


def _thin_support_without_contract(
    *,
    profile_items: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    transcript_rows: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    operating_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> bool:
    return not any(
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


def _apply_support_policy(
    policy: WorkingMemoryPolicy,
    *,
    analysis: QueryAnalysis,
    routing: Mapping[str, Any],
    compiled_behavior_policy: Any,
    profile_support_present: bool,
    thin_support_without_contract: bool,
    conflict_present: bool,
    graph_rows: list[dict[str, Any]],
    profile_match_limit: int,
    continuity_recent_limit: int,
    continuity_match_limit: int,
    transcript_match_limit: int,
    transcript_char_budget: int,
    graph_limit: int,
    corpus_limit: int,
    corpus_char_budget: int,
    operating_match_limit: int,
) -> None:
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

    if compiled_behavior_policy is not None and thin_support_without_contract and routing.get("applied_mode") != "style_contract":
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


def _support_channel_count(channels: list[dict[str, Any]]) -> int:
    return sum(
        1
        for channel in channels
        if channel.get("status") == "active" and int(channel.get("candidate_count") or 0) > 0
    )


def _apply_confidence_policy(
    policy: WorkingMemoryPolicy,
    *,
    analysis: QueryAnalysis,
    routing: Mapping[str, Any],
    support_channels: int,
    conflict_present: bool,
    profile_support_present: bool,
    profile_items: list[dict[str, Any]],
    transcript_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    operating_rows: list[dict[str, Any]],
) -> None:
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


def _apply_tool_avoidance_policy(policy: WorkingMemoryPolicy, *, conflict_present: bool) -> None:
    if conflict_present:
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "open graph conflict requires verification before relying on memory only"
    elif policy.confidence_band == "low":
        policy.tool_avoidance_allowed = False
        policy.tool_avoidance_reason = "memory support is too thin for a memory-only response"
    else:
        policy.tool_avoidance_allowed = True
        policy.tool_avoidance_reason = "memory support is sufficient for a first response"


def _policy_payload(
    *,
    policy: WorkingMemoryPolicy,
    behavior_policy_snapshot: Any,
    compiled_behavior_policy: Any,
    retrieval: Mapping[str, Any],
) -> dict[str, Any]:
    policy_payload = asdict(policy)
    if isinstance(behavior_policy_snapshot, dict):
        policy_payload["behavior_policy_snapshot"] = behavior_policy_snapshot
    if compiled_behavior_policy is not None:
        compiled_policy_payload = (
            dict(compiled_behavior_policy.get("policy") or {}) if isinstance(compiled_behavior_policy, dict) else {}
        )
        if compiled_policy_payload:
            policy_payload["compiled_behavior_policy"] = compiled_policy_payload
    lookup_semantics = retrieval.get("lookup_semantics")
    if isinstance(lookup_semantics, dict):
        policy_payload["lookup_semantics"] = lookup_semantics
    return policy_payload


def _record_working_memory_retrievals(
    store: BrainstackStore,
    *,
    record_retrievals: bool,
    retrieval: Mapping[str, Any],
    profile_items: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> None:
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


def _packet_budget_token_estimate(row: Mapping[str, Any]) -> int:
    payload = {
        "stable_key": row.get("stable_key") or row.get("storage_key") or "",
        "content": row.get("content") or row.get("object_value") or row.get("summary") or "",
        "source": row.get("source") or "",
    }
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return max(1, (len(text) + 3) // 4)


def _packet_budget_target_slot(channel: str, row: Mapping[str, Any]) -> str:
    return str(
        row.get("target_slot")
        or row.get("category")
        or row.get("record_type")
        or row.get("row_type")
        or channel
        or ""
    ).strip()


def _packet_budget_value_fingerprint(row: Mapping[str, Any]) -> str:
    existing = str(row.get("value_fingerprint") or row.get("content_hash") or row.get("section_hash") or "").strip()
    if existing:
        return existing
    value = str(
        row.get("content")
        or row.get("object_value")
        or row.get("value_text")
        or row.get("summary")
        or row.get("title")
        or row.get("heading")
        or ""
    )
    normalized = " ".join(value.split())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


def _packet_budget_candidate(
    *,
    channel: str,
    index: int,
    row: Mapping[str, Any],
    protected: bool,
    authority: str,
) -> dict[str, Any]:
    candidate_id = f"{channel}:{row.get('id') or row.get('row_id') or row.get('stable_key') or index}"
    target_slot = _packet_budget_target_slot(channel, row)
    value_fingerprint = _packet_budget_value_fingerprint(row)
    return {
        "candidate_id": candidate_id,
        "evidence_id": candidate_id,
        "channel": channel,
        "stable_key": row.get("stable_key") or row.get("storage_key") or "",
        "target_slot": target_slot,
        "value_fingerprint": value_fingerprint,
        "authority": authority,
        "decision": "selected",
        "source_role": row.get("source_role") or row.get("source") or "memory",
        "truth_eligible": protected,
        "answer_evidence_allowed": protected,
        "answer_evidence": protected,
        "protected": protected,
        "token_estimate": _packet_budget_token_estimate(row),
    }


def _working_memory_budget_candidates(
    *,
    profile_items: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    operating_rows: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    transcript_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    groups = [
        ("profile_items", profile_items, True, "durable_truth"),
        ("task_rows", task_rows, True, "durable_truth"),
        ("operating_rows", operating_rows, True, "durable_truth"),
        ("graph_rows", graph_rows, True, "durable_truth"),
        ("corpus_rows", corpus_rows, True, "cited_corpus"),
        ("matched", matched, False, "support_only"),
        ("recent", recent, False, "support_only"),
        ("transcript_rows", transcript_rows, False, "support_only"),
    ]
    for channel, rows, protected, authority in groups:
        for index, row in enumerate(rows):
            candidates.append(
                _packet_budget_candidate(
                    channel=channel,
                    index=index,
                    row=row,
                    protected=protected,
                    authority=authority,
                )
            )
    return candidates


def _apply_working_memory_packet_budget(
    *,
    mode: str | None,
    max_candidate_tokens: int | None,
    profile_items: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    operating_rows: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    transcript_rows: list[dict[str, Any]],
    graph_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    requested_mode = "" if mode is None else str(mode)
    normalized_mode = resolve_packet_budget_mode(mode)
    resolved_max_candidate_tokens = resolve_packet_budget_max_candidate_tokens(max_candidate_tokens)
    telemetry: dict[str, Any] = {
        "mode": normalized_mode,
        "enabled": normalized_mode in {"shadow", "active"},
        "applied_to_output": False,
        "max_candidate_tokens": resolved_max_candidate_tokens,
        "requested_mode": requested_mode or None,
    }
    if requested_mode and normalized_mode == "off" and requested_mode.strip().casefold() != "off":
        telemetry["disabled_reason"] = "invalid_packet_budget_mode"
    if normalized_mode == "off" or resolved_max_candidate_tokens is None:
        if normalized_mode in {"shadow", "active"} and resolved_max_candidate_tokens is None:
            telemetry["disabled_reason"] = "missing_packet_budget_max_candidate_tokens"
        return {
            "telemetry": telemetry,
            "profile_items": profile_items,
            "task_rows": task_rows,
            "operating_rows": operating_rows,
            "matched": matched,
            "recent": recent,
            "transcript_rows": transcript_rows,
            "graph_rows": graph_rows,
            "corpus_rows": corpus_rows,
        }
    candidates = _working_memory_budget_candidates(
        profile_items=profile_items,
        task_rows=task_rows,
        operating_rows=operating_rows,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )
    result = apply_packet_budget(
        candidates,
        PacketBudgetPolicy(max_candidate_tokens=resolved_max_candidate_tokens),
    )
    telemetry.update(result.to_trace_packet_budget())
    if normalized_mode == "shadow":
        return {
            "telemetry": telemetry,
            "profile_items": profile_items,
            "task_rows": task_rows,
            "operating_rows": operating_rows,
            "matched": matched,
            "recent": recent,
            "transcript_rows": transcript_rows,
            "graph_rows": graph_rows,
            "corpus_rows": corpus_rows,
        }
    kept_ids = {
        str(item.get("candidate_id") or "")
        for item in result.candidates
        if str(item.get("decision") or "") == "selected"
    }

    def kept(channel: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            candidate = _packet_budget_candidate(
                channel=channel,
                index=index,
                row=row,
                protected=channel in {"profile_items", "task_rows", "operating_rows", "graph_rows", "corpus_rows"},
                authority="support_only",
            )
            if candidate["candidate_id"] in kept_ids:
                output.append(row)
        return output

    telemetry["applied_to_output"] = True
    return {
        "telemetry": telemetry,
        "profile_items": kept("profile_items", profile_items),
        "task_rows": kept("task_rows", task_rows),
        "operating_rows": kept("operating_rows", operating_rows),
        "matched": kept("matched", matched),
        "recent": kept("recent", recent),
        "transcript_rows": kept("transcript_rows", transcript_rows),
        "graph_rows": kept("graph_rows", graph_rows),
        "corpus_rows": kept("corpus_rows", corpus_rows),
    }


def _store_backend_health(store: BrainstackStore) -> dict[str, str]:
    graph_requested = str(getattr(store, "_graph_backend_name", "sqlite") or "sqlite").strip().lower()
    corpus_requested = str(getattr(store, "_corpus_backend_name", "sqlite") or "sqlite").strip().lower()
    graph_backend = getattr(store, "_graph_backend", None)
    corpus_backend = getattr(store, "_corpus_backend", None)
    graph_error = str(getattr(store, "_graph_backend_error", "") or "").strip()
    corpus_error = str(getattr(store, "_corpus_backend_error", "") or "").strip()
    return {
        "graph": "degraded" if graph_requested not in {"", "none", "sqlite"} and (graph_backend is None or graph_error) else "active",
        "corpus": "degraded" if corpus_requested not in {"", "none", "sqlite"} and (corpus_backend is None or corpus_error) else "active",
    }


def _canonical_events_for_current_truth_view(store: BrainstackStore) -> list[dict[str, Any]]:
    if not hasattr(store, "list_canonical_memory_events"):
        return []
    events: list[dict[str, Any]] = []
    for row in store.list_canonical_memory_events(limit=100):
        event = row.get("event") if isinstance(row, Mapping) else None
        if isinstance(event, Mapping):
            events.append(dict(event))
    return events


def _current_truth_targets_from_understanding(understanding: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    target_slots = tuple(
        str(item).strip()
        for item in (understanding.get("current_truth_target_slots") or understanding.get("target_slots") or ())
        if str(item).strip()
    )
    stable_fact_ids = tuple(
        str(item).strip()
        for item in (understanding.get("current_truth_stable_fact_ids") or understanding.get("stable_fact_ids") or ())
        if str(item).strip()
    )
    return tuple(dict.fromkeys(target_slots)), tuple(dict.fromkeys(stable_fact_ids))


def _current_truth_l0_view(
    store: BrainstackStore,
    *,
    principal_scope_key: str,
    target_slots: tuple[str, ...] = (),
    stable_fact_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    if (target_slots or stable_fact_ids) and hasattr(store, "get_current_truth_l0_candidates"):
        return store.get_current_truth_l0_candidates(
            principal_scope_key=principal_scope_key,
            target_slots=target_slots,
            stable_fact_ids=stable_fact_ids,
            limit=96,
        )
    if hasattr(store, "get_current_truth_l0_snapshot"):
        return store.get_current_truth_l0_snapshot(principal_scope_key=principal_scope_key, limit=5000)
    return rebuild_current_truth_view(_canonical_events_for_current_truth_view(store))


def _apply_adaptive_route_overrides(
    policy: WorkingMemoryPolicy,
    plan: Mapping[str, Any],
    *,
    limit_caps: Mapping[str, int],
) -> None:
    overrides = route_plan_limit_overrides(plan)
    for key, value in overrides.items():
        if hasattr(policy, key):
            cap = int(limit_caps.get(key, value) or 0)
            setattr(policy, key, max(min(int(value or 0), cap), 0))
    semantic = plan.get("semantic_retrieval") if isinstance(plan.get("semantic_retrieval"), Mapping) else {}
    policy.semantic_evidence_enabled = bool(semantic.get("enabled"))
    policy.semantic_evidence_reason = str(semantic.get("reason") or "").strip() or "route_gated"


def _adaptive_route_plan_with_effective_limits(
    plan: Mapping[str, Any],
    policy: WorkingMemoryPolicy,
) -> dict[str, Any]:
    """Return a public route plan whose shelf limits match the effective runtime policy."""

    updated = dict(plan)
    shelf_budget = dict(plan.get("shelf_budget") if isinstance(plan.get("shelf_budget"), Mapping) else {})
    shelf_limits = dict(shelf_budget.get("shelf_limits") if isinstance(shelf_budget.get("shelf_limits"), Mapping) else {})
    effective_limits = {
        "profile": int(policy.profile_limit),
        "continuity_match": int(policy.continuity_match_limit),
        "continuity_recent": int(policy.continuity_recent_limit),
        "transcript": int(policy.transcript_limit),
        "operating": int(policy.operating_limit),
        "graph": int(policy.graph_limit),
        "corpus": int(policy.corpus_limit),
    }
    shelf_limits.update(effective_limits)
    if int(shelf_limits.get("semantic_evidence") or 0) > 0:
        shelf_limits["semantic_evidence"] = max(int(policy.evidence_item_budget) * 4, 16)
    backend_call_budget = dict(
        shelf_budget.get("backend_call_budget") if isinstance(shelf_budget.get("backend_call_budget"), Mapping) else {}
    )
    backend_call_budget.update(
        {
            "profile": 1 if effective_limits["profile"] > 0 else 0,
            "continuity": 2 if effective_limits["continuity_match"] > 0 or effective_limits["continuity_recent"] > 0 else 0,
            "transcript": 2 if effective_limits["transcript"] > 0 else 0,
            "operating": 1 if effective_limits["operating"] > 0 else 0,
            "graph": 2 if effective_limits["graph"] > 0 else 0,
            "corpus": 2 if effective_limits["corpus"] > 0 else 0,
            "semantic_evidence": 1 if int(shelf_limits.get("semantic_evidence") or 0) > 0 else 0,
        }
    )
    shelf_budget["shelf_limits"] = shelf_limits
    shelf_budget["backend_call_budget"] = backend_call_budget
    shelf_budget["backend_call_budget_total"] = sum(int(value or 0) for value in backend_call_budget.values())
    updated["shelf_budget"] = shelf_budget
    return updated


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
    record_retrievals: bool = False,
    packet_budget_mode: str | None = None,
    packet_budget_max_candidate_tokens: int | None = None,
    adaptive_route_signals: Mapping[str, Any] | None = None,
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

    adaptive_understanding: dict[str, Any] = {
        "profile_slot_targets": list(analysis.profile_slot_targets),
    }
    explicit_evidence_classes = _explicit_evidence_classes_from_query(query)
    if explicit_evidence_classes:
        adaptive_understanding.setdefault("required_evidence_classes", []).extend(explicit_evidence_classes)
    if analysis.route_payload:
        adaptive_understanding["route_payload"] = dict(analysis.route_payload)
    if analysis.task_like:
        adaptive_understanding.setdefault("required_evidence_classes", []).append("continuity")
    if analysis.operating_like:
        adaptive_understanding.setdefault("required_evidence_classes", []).append("operating")
    if adaptive_route_signals:
        adaptive_understanding.update(dict(adaptive_route_signals))
    current_truth_target_slots, current_truth_stable_fact_ids = _current_truth_targets_from_understanding(adaptive_understanding)
    current_truth_view = _current_truth_l0_view(
        store,
        principal_scope_key=principal_scope_key,
        target_slots=current_truth_target_slots,
        stable_fact_ids=current_truth_stable_fact_ids,
    )
    adaptive_route_plan = build_adaptive_route_plan(
        query,
        query_understanding=adaptive_understanding,
        current_truth_view=current_truth_view,
        backend_health=_store_backend_health(store),
    )
    _apply_adaptive_route_overrides(
        policy,
        adaptive_route_plan,
        limit_caps={
            "profile_limit": profile_match_limit,
            "continuity_recent_limit": continuity_recent_limit,
            "continuity_match_limit": continuity_match_limit,
            "transcript_limit": transcript_match_limit,
            "transcript_char_budget": transcript_char_budget,
            "operating_limit": operating_match_limit,
            "graph_limit": graph_limit,
            "corpus_limit": corpus_limit,
            "corpus_char_budget": corpus_char_budget,
            "evidence_item_budget": evidence_item_budget,
        },
    )
    adaptive_route_plan = _adaptive_route_plan_with_effective_limits(adaptive_route_plan, policy)
    retrieval_control_plan = retrieval_control_plan_from_adaptive_plan(adaptive_route_plan)
    adaptive_route_plan["plan_id"] = retrieval_control_plan.plan_id
    policy.retrieval_control_plan = retrieval_control_plan.to_public_dict()

    effective_route_resolver = route_resolver
    if effective_route_resolver is None:
        route_payload = route_plan_resolver_payload(adaptive_route_plan)

        def effective_route_resolver(_query: str, _payload: dict[str, str] = route_payload) -> dict[str, str]:
            return dict(_payload)

    retrieval = retrieve_executive_context(
        store,
        query=query,
        session_id=session_id,
        principal_scope_key=principal_scope_key,
        timezone_name=timezone_name,
        analysis=asdict(analysis),
        policy=asdict(policy),
        route_resolver=effective_route_resolver,
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

    _apply_route_policy(
        policy,
        routing,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        evidence_item_budget=evidence_item_budget,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
        operating_match_limit=operating_match_limit,
    )
    support_channels = _support_channel_count(channels)
    conflict_present = any(row["row_type"] == "conflict" for row in graph_rows)
    profile_support_present = _profile_support_present(
        analysis=analysis,
        routing=routing,
        profile_items=profile_items,
    )
    thin_support_without_contract = _thin_support_without_contract(
        profile_items=profile_items,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        task_rows=task_rows,
        operating_rows=operating_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )

    _apply_support_policy(
        policy,
        analysis=analysis,
        routing=routing,
        compiled_behavior_policy=compiled_behavior_policy,
        profile_support_present=profile_support_present,
        thin_support_without_contract=thin_support_without_contract,
        conflict_present=conflict_present,
        graph_rows=graph_rows,
        profile_match_limit=profile_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        continuity_match_limit=continuity_match_limit,
        transcript_match_limit=transcript_match_limit,
        transcript_char_budget=transcript_char_budget,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=corpus_char_budget,
        operating_match_limit=operating_match_limit,
    )
    _apply_confidence_policy(
        policy,
        analysis=analysis,
        routing=routing,
        support_channels=support_channels,
        conflict_present=conflict_present,
        profile_support_present=profile_support_present,
        profile_items=profile_items,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        operating_rows=operating_rows,
    )
    _apply_tool_avoidance_policy(policy, conflict_present=conflict_present)
    policy_payload = _policy_payload(
        policy=policy,
        behavior_policy_snapshot=behavior_policy_snapshot,
        compiled_behavior_policy=compiled_behavior_policy,
        retrieval=retrieval,
    )
    policy_payload["adaptive_route_plan"] = {
        "plan_id": retrieval_control_plan.plan_id,
        "schema": adaptive_route_plan.get("schema"),
        "status": adaptive_route_plan.get("status"),
        "route_class": adaptive_route_plan.get("route_class"),
        "requested_route_class": adaptive_route_plan.get("requested_route_class"),
        "retrieval_mode": adaptive_route_plan.get("retrieval_mode"),
        "route_decision": dict(adaptive_route_plan.get("route_decision") or {}),
        "activated_shelves": list(adaptive_route_plan.get("activated_shelves") or []),
        "skipped_shelves": list(adaptive_route_plan.get("skipped_shelves") or []),
        "fallback": dict(adaptive_route_plan.get("fallback") or {}),
        "current_truth_view": dict(adaptive_route_plan.get("current_truth_view") or {}),
        "guardrails": dict(adaptive_route_plan.get("guardrails") or {}),
        "semantic_retrieval": dict(adaptive_route_plan.get("semantic_retrieval") or {}),
        "shelf_budget": dict(adaptive_route_plan.get("shelf_budget") or {}),
    }
    policy_payload["retrieval_control_plan"] = retrieval_control_plan.to_public_dict()
    budgeted = _apply_working_memory_packet_budget(
        mode=packet_budget_mode,
        max_candidate_tokens=packet_budget_max_candidate_tokens,
        profile_items=profile_items,
        task_rows=task_rows,
        operating_rows=operating_rows,
        matched=matched,
        recent=recent,
        transcript_rows=transcript_rows,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )
    profile_items = budgeted["profile_items"]
    task_rows = budgeted["task_rows"]
    operating_rows = budgeted["operating_rows"]
    matched = budgeted["matched"]
    recent = budgeted["recent"]
    transcript_rows = budgeted["transcript_rows"]
    graph_rows = budgeted["graph_rows"]
    corpus_rows = budgeted["corpus_rows"]
    packet_budget = dict(budgeted["telemetry"])
    policy_payload["packet_budget"] = packet_budget
    retrieval_context_envelope = build_retrieval_context_envelope(
        principal_scope_key=principal_scope_key,
        adaptive_route_plan=adaptive_route_plan,
        current_truth_view={
            "rebuild": dict(current_truth_view.get("rebuild") or {}),
            "counters": dict(current_truth_view.get("counters") or {}),
            "current_truth_row_count": len(current_truth_view.get("current_truth_rows") or []),
            "non_answerable_row_count": len(current_truth_view.get("non_answerable_rows") or []),
        },
        policy=policy_payload,
        packet_budget=packet_budget,
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
    policy_payload["retrieval_context_envelope"] = retrieval_context_envelope

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

    _record_working_memory_retrievals(
        store,
        record_retrievals=record_retrievals,
        retrieval=retrieval,
        profile_items=profile_items,
        graph_rows=graph_rows,
        corpus_rows=corpus_rows,
    )
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
        "adaptive_route_plan": adaptive_route_plan,
        "retrieval_control_plan": retrieval_control_plan.to_public_dict(),
        "current_truth_view": {
            "schema": current_truth_view.get("schema"),
            "status": current_truth_view.get("status"),
            "rebuild": dict(current_truth_view.get("rebuild") or {}),
            "source_event_span": dict(current_truth_view.get("source_event_span") or {}),
            "counters": dict(current_truth_view.get("counters") or {}),
            "current_truth_row_count": len(current_truth_view.get("current_truth_rows") or []),
            "non_answerable_row_count": len(current_truth_view.get("non_answerable_rows") or []),
        },
        "system_substrate": dict(system_substrate or {}),
        "packet_budget": packet_budget,
        "retrieval_context_envelope": retrieval_context_envelope,
        "block": block,
    }
