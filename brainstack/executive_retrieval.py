from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping

from .db import BrainstackStore
from .operating_truth import (
    OPERATING_RECORD_TYPES,
    RECENT_WORK_RECAP_RECORD_TYPES,
)
from .profile_contract import is_native_explicit_style_item
from .structured_understanding import infer_query_understanding
from .style_contract import STYLE_CONTRACT_SLOT
from .tier2_extractor import _default_llm_caller, _extract_json_object, _extract_text_content
from .transcript import primary_user_turn_content, split_turn_content
from .usefulness import graph_priority_adjustment, profile_priority_adjustment

RRF_K = 60
ROUTE_FACT = "fact"
ROUTE_TEMPORAL = "temporal"
ROUTE_AGGREGATE = "aggregate"
ROUTE_STYLE_CONTRACT = "style_contract"
TEMPORAL_CONTINUITY_CAP = 3
TEMPORAL_RECENT_CAP = 3
TEMPORAL_TRANSCRIPT_CAP = 3
TEMPORAL_GRAPH_CAP = 3
AGGREGATE_CONTINUITY_CAP = 6
AGGREGATE_TRANSCRIPT_CAP = 6
AGGREGATE_GRAPH_CAP = 2
FUSION_CHANNEL_WEIGHTS = {
    "keyword": 1.0,
    "operating": 1.05,
    "semantic": 1.12,
    "graph": 1.08,
    "temporal": 1.04,
}
FUSION_SHELF_WEIGHTS = {
    "profile": 1.12,
    "operating": 1.08,
    "graph": 1.05,
    "continuity_match": 1.0,
    "continuity_recent": 0.96,
    "transcript": 1.0,
    "corpus": 0.94,
}

logger = logging.getLogger(__name__)


def _is_native_profile_mirror_receipt(row: Dict[str, Any]) -> bool:
    return str(row.get("category") or "").strip() == "native_profile_mirror"

@dataclass
class RetrievalChannelStatus:
    name: str
    status: str
    reason: str = ""
    candidate_count: int = 0


@dataclass
class EvidenceCandidate:
    key: str
    shelf: str
    row: Dict[str, Any]
    rrf_score: float = 0.0
    channel_ranks: Dict[str, int] = field(default_factory=dict)

    def seen_in(self, name: str, rank: int) -> None:
        current = self.channel_ranks.get(name)
        if current is None or rank < current:
            self.channel_ranks[name] = rank


@dataclass
class RetrievalRoute:
    requested_mode: str = ROUTE_FACT
    applied_mode: str = ROUTE_FACT
    source: str = "default"
    reason: str = ""
    fallback_used: bool = False
    resolution_status: str = "not_attempted"
    resolution_error: str = ""
    resolution_error_class: str = ""
    bounds: Dict[str, Any] = field(default_factory=dict)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _classify_route_resolution_error(exc: Exception) -> str:
    text = _normalize_text(exc).casefold()
    status_code = getattr(exc, "status_code", None)
    if status_code == 402 or any(term in text for term in ("payment required", "credits", "can only afford", "billing")):
        return "economic_drift"
    if any(term in text for term in ("auth", "unauthorized", "refresh token", "re-authenticate", "access token")):
        return "auth_drift"
    return "resolver_failure"


def _build_cross_session_search_queries(query: str) -> List[str]:
    normalized = _normalize_text(query)
    return [normalized] if normalized else []


def _build_lookup_semantics(
    *,
    query: str,
    task_lookup: Mapping[str, Any] | None,
    task_rows: List[Dict[str, Any]],
    operating_lookup: Mapping[str, Any] | None,
    operating_rows: List[Dict[str, Any]],
    selected: Mapping[str, Any],
) -> Dict[str, Any] | None:
    recent_work_rows = [
        row
        for row in operating_rows
        if str(row.get("record_type") or "").strip() in RECENT_WORK_RECAP_RECORD_TYPES
    ]
    if isinstance(operating_lookup, Mapping):
        fallback_sources: List[str] = []
        if list(selected.get("matched") or []):
            fallback_sources.append("continuity_match")
        if list(selected.get("recent") or []):
            fallback_sources.append("continuity_recent")
        if list(selected.get("transcript_rows") or []):
            fallback_sources.append("transcript")
        if list(selected.get("graph_rows") or []):
            fallback_sources.append("graph")
        return {
            "active": True,
            "domain": "operating_truth",
            "structured_owner_status": "brainstack.operating_truth",
            "structured_lookup_performed": True,
            "structured_record_count": len(operating_rows),
            "record_types": [
                str(value or "").strip()
                for value in (operating_lookup.get("record_types") or ())
                if str(value or "").strip() in OPERATING_RECORD_TYPES
            ],
            "fallback_sources": fallback_sources,
            "result_status": "committed_records" if operating_rows else "structured_miss",
        }
    if recent_work_rows:
        fallback_sources = []
        if list(selected.get("matched") or []):
            fallback_sources.append("continuity_match")
        if list(selected.get("recent") or []):
            fallback_sources.append("continuity_recent")
        if list(selected.get("transcript_rows") or []):
            fallback_sources.append("transcript")
        return {
            "active": True,
            "domain": "recent_work_recap",
            "structured_owner_status": "brainstack.operating_truth",
            "structured_lookup_performed": True,
            "structured_record_count": len(recent_work_rows),
            "record_types": [
                str(row.get("record_type") or "").strip()
                for row in recent_work_rows
                if str(row.get("record_type") or "").strip()
            ],
            "fallback_sources": fallback_sources,
            "result_status": "committed_records",
        }
    if not isinstance(task_lookup, Mapping):
        return None

    fallback_sources: List[str] = []
    if list(selected.get("matched") or []):
        fallback_sources.append("continuity_match")
    if list(selected.get("recent") or []):
        fallback_sources.append("continuity_recent")
    if list(selected.get("transcript_rows") or []):
        fallback_sources.append("transcript")
    if list(selected.get("graph_rows") or []):
        fallback_sources.append("graph")

    if task_rows:
        result_status = "committed_records"
    elif fallback_sources:
        result_status = "structured_miss_with_fallback"
    else:
        result_status = "structured_miss"

    return {
        "active": True,
        "domain": "task_like",
        "structured_owner_status": "brainstack.task_memory",
        "structured_lookup_performed": True,
        "structured_record_count": len(task_rows),
        "item_type": str(task_lookup.get("item_type") or "").strip(),
        "due_date": str(task_lookup.get("due_date") or "").strip(),
        "date_scope": str(task_lookup.get("date_scope") or "").strip(),
        "followup_only": bool(task_lookup.get("followup_only")),
        "fallback_sources": fallback_sources,
        "result_status": result_status,
    }


def _looks_user_led(text: str) -> bool:
    return bool(_normalize_text(split_turn_content(text).get("user")))


def _has_meaningful_transcript_signal(rows: Iterable[Dict[str, Any]]) -> bool:
    for row in rows:
        if float(row.get("keyword_score") or 0.0) > 0.0:
            return True
        if str(row.get("match_mode") or "").strip() == "semantic" and float(row.get("semantic_score") or 0.0) > 0.0:
            return True
        if (
            str(row.get("match_mode") or "").strip() == "support"
            and str(row.get("retrieval_source") or "").strip() == "transcript.session_support"
            and bool(row.get("same_principal"))
        ):
            return True
    return False


def _candidate_text(candidate: EvidenceCandidate) -> str:
    row = candidate.row
    if candidate.shelf == "graph":
        return _graph_match_text(row)
    if candidate.shelf == "profile":
        return _normalize_text(row.get("content"))
    if candidate.shelf == "transcript":
        return _normalize_text(primary_user_turn_content(row.get("content")))
    return _normalize_text(row.get("content"))


def _candidate_priority_bonus(candidate: EvidenceCandidate) -> float:
    row = candidate.row
    text = _candidate_text(candidate)
    bonus = 0.0
    query_has_digits = bool(row.get("_brainstack_query_has_digits"))

    if candidate.shelf == "transcript":
        bonus += 0.05
        if "keyword" in candidate.channel_ranks:
            bonus += 0.03
        if _looks_user_led(text):
            bonus += 0.04
    elif candidate.shelf == "operating":
        bonus += 0.07
    elif candidate.shelf == "continuity_match":
        bonus += 0.02
    elif candidate.shelf == "continuity_recent":
        bonus += 0.01

    if query_has_digits and any(char.isdigit() for char in text):
        bonus += 0.08
    if '"' in text or "'" in text:
        bonus += 0.02

    keyword_score = float(row.get("keyword_score") or 0.0)
    if keyword_score > 0.0:
        bonus += min(0.06, keyword_score * 0.06)

    semantic_score = float(row.get("semantic_score") or 0.0)
    if semantic_score > 0.0:
        bonus += min(0.08, semantic_score * 0.08)

    query_token_overlap = int(row.get("_brainstack_query_token_overlap") or 0)
    if query_token_overlap > 0:
        bonus += min(0.09, query_token_overlap * 0.03)

    if bool(row.get("same_session")):
        bonus += 0.03

    if candidate.shelf == "graph":
        fact_class = _graph_fact_class(row)
        if fact_class == "explicit_state_current":
            bonus += 0.08
        elif fact_class == "explicit_state_prior":
            bonus -= 0.02
        elif fact_class == "conflict":
            bonus -= 0.04

    return bonus


def _agreement_bonus(candidate: EvidenceCandidate) -> float:
    channel_count = len(candidate.channel_ranks)
    if channel_count <= 1:
        return 0.0
    return min(0.15, 0.05 * (channel_count - 1))


def _fusion_rank_contribution(*, channel_name: str, shelf: str, rank: int) -> float:
    channel_weight = float(FUSION_CHANNEL_WEIGHTS.get(channel_name, 1.0))
    shelf_weight = float(FUSION_SHELF_WEIGHTS.get(shelf, 1.0))
    return (channel_weight * shelf_weight) / (RRF_K + rank)


def _llm_route_resolver(query: str) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You classify Brainstack memory retrieval questions into one of four modes.\n"
                "Return JSON only with the schema {\"mode\": \"fact|temporal|aggregate|style_contract\", \"reason\": \"...\"}.\n"
                "Use temporal when the user needs ordering, before/after comparison, date difference, or change over time.\n"
                "Use aggregate when the user needs totals, counts across multiple events, or exhaustive collection.\n"
                "Use style_contract when the user is explicitly asking about their detailed rule pack, named style pack, rule list, or the full style contract itself.\n"
                "Use fact for ordinary fact lookup or if uncertain."
            ),
        },
        {
            "role": "user",
            "content": query,
        },
    ]
    response = _default_llm_caller(
        task="memory_prefetch_routing_hint",
        messages=messages,
        timeout=6.0,
        max_tokens=120,
    )
    payload = _extract_json_object(_extract_text_content(response))
    return {
        "mode": _normalize_text(payload.get("mode")),
        "reason": _normalize_text(payload.get("reason")),
    }


def _missing_style_contract_row(*, principal_scope_key: str = "") -> Dict[str, Any]:
    scope_key = str(principal_scope_key or "").strip()
    return {
        "id": 0,
        "stable_key": "behavior_contract:missing",
        "storage_key": f"behavior_contract::missing::{scope_key or '_global'}",
        "principal_scope_key": scope_key,
        "category": "system",
        "content": (
            "No committed full behavior contract is stored for this principal scope. "
            "Do not reconstruct a full rule list from derived policy summaries, profile slots, or transcript fragments."
        ),
        "source": "brainstack.behavior_contract",
        "confidence": 1.0,
        "metadata": {
            "memory_class": "behavior_contract_status",
            "status_reason": "no_committed_behavior_contract",
            "principal_scope_key": scope_key,
        },
        "updated_at": "",
        "active": True,
        "keyword_score": 2.0,
        "retrieval_source": "behavior_contract.missing",
        "match_mode": "authority",
        "_direct_slot_match": True,
    }


def _default_route_resolver(query: str) -> Dict[str, Any]:
    return {
        "mode": ROUTE_FACT,
        "reason": "fact route default",
        "source": "fact_default",
    }


def _resolve_route(
    query: str,
    *,
    route_resolver: Callable[[str], Dict[str, Any] | str] | None,
) -> RetrievalRoute:
    normalized = _normalize_text(query)
    route = RetrievalRoute(reason="fact route default")
    if not normalized:
        return route

    deterministic = _default_route_resolver(normalized)
    resolver = route_resolver
    source = "injected"
    if resolver is None:
        route.source = str(deterministic.get("source") or "fact_default")
        route.reason = str(deterministic.get("reason") or route.reason)
        route.resolution_status = "skipped"
        return route

    try:
        payload = resolver(normalized)
    except Exception as exc:
        logger.warning("Brainstack route resolution failed: %s", exc)
        route.source = "route_resolution_failed"
        route.reason = "route resolver failed; staying on fact route"
        route.resolution_status = "failed"
        route.resolution_error = str(exc)
        route.resolution_error_class = _classify_route_resolution_error(exc)
        return route

    if isinstance(payload, str):
        mode = _normalize_text(payload).lower()
        reason = ""
    elif isinstance(payload, dict):
        mode = _normalize_text(payload.get("mode")).lower()
        reason = _normalize_text(payload.get("reason"))
        source = _normalize_text(payload.get("source")) or source
    else:
        route.source = "route_resolution_failed"
        route.reason = "route resolver returned unsupported payload; staying on fact route"
        route.resolution_status = "failed"
        route.resolution_error = f"unsupported payload type: {type(payload).__name__}"
        route.resolution_error_class = "unsupported_payload"
        return route

    if mode not in {ROUTE_FACT, ROUTE_TEMPORAL, ROUTE_AGGREGATE, ROUTE_STYLE_CONTRACT}:
        route.source = "route_resolution_failed"
        route.reason = "route resolver returned unsupported mode; staying on fact route"
        route.resolution_status = "failed"
        route.resolution_error = f"unsupported mode: {mode or '<empty>'}"
        route.resolution_error_class = "unsupported_mode"
        return route
    route.requested_mode = mode
    route.applied_mode = mode
    route.source = source
    route.reason = reason
    route.resolution_status = "resolved"
    return route


def _round_robin(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index < len(group):
                output.append(group[index])
    return output


def _row_unique_key(row: Dict[str, Any]) -> str:
    if "row_type" in row:
        return f"graph:{row.get('row_type')}:{int(row.get('row_id') or 0)}"
    if "document_id" in row:
        return f"corpus:{int(row.get('document_id') or 0)}:{int(row.get('section_index') or 0)}"
    return f"{str(row.get('session_id') or '')}:{int(row.get('id') or 0)}"


def _dedupe_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key = _row_unique_key(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    return output


def _same_principal_session_support_rows(
    store: BrainstackStore,
    anchor_rows: Iterable[Dict[str, Any]],
    *,
    current_session_id: str,
    per_session_limit: int = 2,
) -> List[Dict[str, Any]]:
    support_rows: List[Dict[str, Any]] = []
    seen_support_keys: set[str] = set()
    seen_anchor_sessions: set[str] = set()
    for anchor in _dedupe_rows(anchor_rows):
        if str(anchor.get("kind") or "") != "session_summary":
            continue
        if not bool(anchor.get("same_principal")):
            continue
        session_id = str(anchor.get("session_id") or "").strip()
        if not session_id or session_id == current_session_id or session_id in seen_anchor_sessions:
            continue
        seen_anchor_sessions.add(session_id)
        session_rows = store.recent_transcript(
            session_id=session_id,
            limit=max(per_session_limit * 3, 6),
        )
        ranked_session_rows = sorted(
            [
                dict(row)
                for row in session_rows
                if str(row.get("kind") or "") != "session_summary"
            ],
            key=lambda row: (
                int(row.get("turn_number") or 0),
                int(row.get("id") or 0),
            ),
            reverse=True,
        )
        added = 0
        for row in ranked_session_rows:
            row.setdefault("same_principal", True)
            row.setdefault("same_session", False)
            row.setdefault("keyword_score", 0.0)
            row.setdefault("retrieval_source", "transcript.session_support")
            row.setdefault("match_mode", "support")
            key = _row_unique_key(row)
            if key in seen_support_keys:
                continue
            seen_support_keys.add(key)
            support_rows.append(row)
            added += 1
            if added >= per_session_limit:
                break
    return support_rows


def _row_time_value(row: Dict[str, Any]) -> str:
    metadata = row.get("metadata")
    temporal_payload = metadata.get("temporal") if isinstance(metadata, dict) else None
    temporal = temporal_payload if isinstance(temporal_payload, dict) else {}
    return (
        str(temporal.get("observed_at") or "").strip()
        or str(row.get("created_at") or "").strip()
        or str(row.get("happened_at") or "").strip()
    )


def _parse_time_value(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None

    def _normalize_parsed(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    try:
        return _normalize_parsed(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        pass
    candidate = value.split("T", 1)[0] if "T" in value else value[:10]
    try:
        return _normalize_parsed(datetime.fromisoformat(candidate))
    except ValueError:
        pass
    for fmt in ("%Y/%m/%d (%a) %H:%M", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            return _normalize_parsed(datetime.strptime(value, fmt))
        except ValueError:
            continue
    return None


def _row_time_fields(row: Dict[str, Any]) -> tuple[str, datetime | None]:
    raw = _row_time_value(row)
    return raw, _parse_time_value(raw)


def _temporal_anchor_key(row: Dict[str, Any]) -> str:
    raw, parsed = _row_time_fields(row)
    return parsed.isoformat() if parsed is not None else raw


def _sort_rows_chronologically(rows: Iterable[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    deduped = _chronologically_sorted_rows(rows)
    return deduped[:limit]


def _chronologically_sorted_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    decorated = []
    for row in _dedupe_rows(rows):
        raw_time, parsed_time = _row_time_fields(row)
        decorated.append(
            (
                0 if parsed_time is not None else 1,
                parsed_time or datetime.max,
                raw_time,
                int(row.get("turn_number") or 0),
                int(row.get("id") or row.get("row_id") or 0),
                row,
            )
        )
    decorated.sort()
    return [row for *_, row in decorated]


def _temporal_diversity_key(row: Dict[str, Any]) -> str:
    _, parsed = _row_time_fields(row)
    session_id = str(row.get("session_id") or "").strip()
    if parsed is not None:
        bucket = parsed.date().isoformat()
        return f"{session_id}:{bucket}" if session_id else bucket
    return ""


def _temporal_diverse_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    ranked = _chronologically_sorted_rows(rows)
    if limit <= 0 or not ranked:
        return []

    bucket_representatives: Dict[str, Dict[str, Any]] = {}
    for row in ranked:
        bucket = _temporal_diversity_key(row)
        if bucket:
            # Keep the latest row within the same temporal bucket so a concrete
            # realized event can displace earlier planning/context rows.
            bucket_representatives[bucket] = dict(row)

    selected = _chronologically_sorted_rows(bucket_representatives.values())
    seen = {_row_unique_key(row) for row in selected}
    for row in ranked:
        key = _row_unique_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(row))
    return selected[:limit]


def _select_temporal_priority_rows(
    primary_rows: Iterable[Dict[str, Any]],
    fallback_rows: Iterable[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    selected = _temporal_diverse_rows(primary_rows, limit=limit)
    if len(selected) >= limit:
        return selected
    seen = {_row_unique_key(row) for row in selected}
    for row in _temporal_diverse_rows(fallback_rows, limit=max(limit * 4, limit)):
        key = _row_unique_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(row))
        if len(selected) >= limit:
            break
    return selected


def _aggregate_row_priority(row: Dict[str, Any]) -> tuple[Any, ...]:
    return (
        1 if bool(row.get("same_session")) else 0,
        float(row.get("semantic_score") or 0.0),
        float(row.get("keyword_score") or 0.0),
        _row_time_value(row),
        int(row.get("turn_number") or 0),
        int(row.get("id") or 0),
    )


def _aggregate_diverse_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    limit: int,
) -> List[Dict[str, Any]]:
    ranked = sorted(_dedupe_rows(rows), key=_aggregate_row_priority, reverse=True)
    primary: List[Dict[str, Any]] = []
    secondary: List[Dict[str, Any]] = []
    seen_sessions: set[str] = set()
    for row in ranked:
        session_key = str(row.get("session_id") or "").strip()
        if session_key and session_key not in seen_sessions:
            primary.append(row)
            seen_sessions.add(session_key)
        else:
            secondary.append(row)
    return (primary + secondary)[:limit]


def _native_aggregate_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
) -> List[Dict[str, Any]]:
    _ = (store, query, session_id)
    # Disabled until native aggregate plans come from structured understanding
    # rather than phrase-matched query heuristics.
    return []


def _fact_transcript_row_priority(row: Dict[str, Any]) -> tuple[Any, ...]:
    content = _normalize_text(row.get("content") or row.get("content_excerpt"))
    keyword_score = float(row.get("keyword_score") or 0.0)
    retrieval_source = str(row.get("retrieval_source") or "")
    match_mode = str(row.get("match_mode") or "")
    return (
        1 if keyword_score > 0.0 else 0,
        keyword_score,
        1 if match_mode == "keyword" or "keyword" in retrieval_source else 0,
        1 if _looks_user_led(content) else 0,
        1 if bool(row.get("same_session")) else 0,
        float(row.get("semantic_score") or 0.0),
        -len(content),
        str(row.get("created_at") or ""),
        int(row.get("turn_number") or 0),
        int(row.get("id") or 0),
    )


def _transcript_join_key(row: Dict[str, Any]) -> str:
    session_id = str(row.get("session_id") or "").strip()
    turn_number = int(row.get("turn_number") or 0)
    if session_id and turn_number > 0:
        return f"{session_id}:{turn_number}"
    row_id = int(row.get("id") or row.get("row_id") or 0)
    if session_id and row_id > 0:
        return f"{session_id}:id:{row_id}"
    if row_id > 0:
        return f"id:{row_id}"
    return ""


def _fact_transcript_rows(
    *,
    store: BrainstackStore,
    current_session_id: str,
    fused_transcript_rows: List[Dict[str, Any]],
    keyword_transcript_rows: List[Dict[str, Any]],
    semantic_conversation_rows: List[Dict[str, Any]],
    matched_rows: List[Dict[str, Any]],
    limit: int,
) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    effective_limit = limit
    if fused_transcript_rows:
        effective_limit = max(limit, 3)
    elif keyword_transcript_rows and semantic_conversation_rows:
        effective_limit = max(limit, 2)
    rows = _dedupe_rows(
        list(fused_transcript_rows)
        + _round_robin(keyword_transcript_rows, semantic_conversation_rows)
    )
    support_rows = _same_principal_session_support_rows(
        store,
        matched_rows,
        current_session_id=current_session_id,
    )
    ranked_rows = sorted(rows, key=_fact_transcript_row_priority, reverse=True)
    top_ranked_keys = {
        _transcript_join_key(row)
        for row in ranked_rows[: max(effective_limit * 2, effective_limit + 1)]
        if _transcript_join_key(row)
    }
    matched_keys: List[str] = []
    seen_matched_keys: set[str] = set()
    for row in matched_rows:
        join_key = _transcript_join_key(row)
        if not join_key or join_key not in top_ranked_keys or join_key in seen_matched_keys:
            continue
        seen_matched_keys.add(join_key)
        matched_keys.append(join_key)
    transcript_by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        join_key = _transcript_join_key(row)
        if join_key:
            transcript_by_key.setdefault(join_key, row)
    preferred_rows: List[Dict[str, Any]] = []
    seen_keys: set[str] = set()
    for join_key in matched_keys:
        preferred = transcript_by_key.get(join_key)
        if preferred is None or join_key in seen_keys:
            continue
        seen_keys.add(join_key)
        preferred_rows.append(preferred)

    remaining_rows = [
        row
        for row in ranked_rows
        if _transcript_join_key(row) not in seen_keys
    ]
    support_preferred: List[Dict[str, Any]] = []
    for row in support_rows:
        join_key = _transcript_join_key(row)
        unique_key = _row_unique_key(row)
        if unique_key in seen_keys or (join_key and join_key in seen_keys):
            continue
        if join_key:
            seen_keys.add(join_key)
        seen_keys.add(unique_key)
        support_preferred.append(row)
    return (preferred_rows + support_preferred + remaining_rows)[:effective_limit]


def _fact_sort_key(candidate: EvidenceCandidate) -> tuple[Any, ...]:
    bonus = _candidate_priority_bonus(candidate)
    agreement_bonus = _agreement_bonus(candidate)
    return (
        candidate.rrf_score + bonus + agreement_bonus,
        agreement_bonus,
        bonus,
        len(candidate.channel_ranks),
        1 if candidate.shelf == "operating" else 0,
        1 if candidate.shelf == "transcript" else 0,
        1 if candidate.shelf == "graph" else 0,
        1 if candidate.shelf == "profile" else 0,
    )


def _route_limits(
    *,
    route: RetrievalRoute,
    profile_limit: int,
    continuity_match_limit: int,
    continuity_recent_limit: int,
    transcript_limit: int,
    operating_limit: int,
    graph_limit: int,
    corpus_limit: int,
) -> Dict[str, int]:
    limits = {
        "profile_limit": profile_limit,
        "continuity_match_limit": continuity_match_limit,
        "continuity_recent_limit": continuity_recent_limit,
        "transcript_limit": transcript_limit,
        "operating_limit": operating_limit,
        "graph_limit": graph_limit,
        "corpus_limit": corpus_limit,
    }
    if route.applied_mode == ROUTE_TEMPORAL:
        limits["continuity_match_limit"] = max(limits["continuity_match_limit"], TEMPORAL_CONTINUITY_CAP)
        limits["continuity_recent_limit"] = max(limits["continuity_recent_limit"], TEMPORAL_RECENT_CAP)
        limits["transcript_limit"] = max(limits["transcript_limit"], TEMPORAL_TRANSCRIPT_CAP)
        limits["graph_limit"] = max(limits["graph_limit"], TEMPORAL_GRAPH_CAP)
        route.bounds = {
            "kind": "row_cap",
            "continuity": limits["continuity_match_limit"],
            "recent": limits["continuity_recent_limit"],
            "transcript": limits["transcript_limit"],
            "graph": limits["graph_limit"],
        }
    elif route.applied_mode == ROUTE_AGGREGATE:
        limits["continuity_match_limit"] = max(limits["continuity_match_limit"], AGGREGATE_CONTINUITY_CAP)
        limits["transcript_limit"] = max(limits["transcript_limit"], AGGREGATE_TRANSCRIPT_CAP)
        limits["graph_limit"] = max(limits["graph_limit"], AGGREGATE_GRAPH_CAP)
        route.bounds = {
            "kind": "row_cap",
            "continuity": limits["continuity_match_limit"],
            "transcript": limits["transcript_limit"],
            "graph": limits["graph_limit"],
        }
    elif route.applied_mode == ROUTE_STYLE_CONTRACT:
        limits["profile_limit"] = max(1, min(limits["profile_limit"], 4))
        limits["continuity_match_limit"] = 0
        limits["continuity_recent_limit"] = 0
        limits["transcript_limit"] = 0
        limits["operating_limit"] = 0
        limits["graph_limit"] = 0
        limits["corpus_limit"] = 0
        route.bounds = {"kind": "slot_target", "profile": limits["profile_limit"]}
    return limits


def _route_has_support(route: RetrievalRoute, selected: Dict[str, List[Dict[str, Any]]]) -> bool:
    if route.applied_mode == ROUTE_AGGREGATE:
        if any(str(row.get("kind") or "") == "native_aggregate" for row in selected.get("matched", ())):
            return True
        total = sum(
            len(selected.get(name, ()))
            for name in ("matched", "transcript_rows", "graph_rows", "corpus_rows")
        )
        return total >= 2
    if route.applied_mode == ROUTE_TEMPORAL:
        anchors = {
            _temporal_anchor_key(row)
            for name in ("matched", "recent", "transcript_rows", "graph_rows")
            for row in selected.get(name, ())
            if _temporal_anchor_key(row)
        }
        return len(anchors) >= 2
    if route.applied_mode == ROUTE_STYLE_CONTRACT:
        return any(
            str(row.get("stable_key") or "").strip() == STYLE_CONTRACT_SLOT or is_native_explicit_style_item(row)
            for row in selected.get("profile_items", ())
        )
    return True


def _keep_temporal_transcript_rows_with_anchor_support(selected: Dict[str, List[Dict[str, Any]]]) -> bool:
    transcript_rows = list(selected.get("transcript_rows", ()))
    if not transcript_rows:
        return False
    transcript_anchors = {
        _temporal_anchor_key(row)
        for row in transcript_rows
        if _temporal_anchor_key(row)
    }
    if len(transcript_anchors) >= 2:
        return True
    overall_anchors = {
        _temporal_anchor_key(row)
        for name in ("matched", "recent", "transcript_rows", "graph_rows")
        for row in selected.get(name, ())
        if _temporal_anchor_key(row)
    }
    if len(overall_anchors) < 2:
        return False
    return any(
        str(row.get("match_mode") or "").strip() == "support"
        and str(row.get("retrieval_source") or "").strip() == "transcript.session_support"
        and bool(row.get("same_principal"))
        for row in transcript_rows
    )


def _select_temporal_rows(
    *,
    keyword_continuity_rows: List[Dict[str, Any]],
    recent_rows: List[Dict[str, Any]],
    temporal_continuity_rows: List[Dict[str, Any]],
    temporal_transcript_rows: List[Dict[str, Any]],
    graph_rows: List[Dict[str, Any]],
    limits: Dict[str, int],
) -> Dict[str, List[Dict[str, Any]]]:
    prioritized_recent_rows = _select_temporal_priority_rows(
        temporal_continuity_rows,
        recent_rows,
        limit=limits["continuity_recent_limit"],
    )
    recent_keys = {_row_unique_key(row) for row in prioritized_recent_rows}
    prioritized_matched_rows = _select_temporal_priority_rows(
        [
            row
            for row in temporal_continuity_rows
            if _row_unique_key(row) not in recent_keys
        ],
        _dedupe_rows(_round_robin(keyword_continuity_rows, recent_rows)),
        limit=limits["continuity_match_limit"],
    )
    return {
        "profile_items": [],
        "matched": prioritized_matched_rows,
        "recent": prioritized_recent_rows,
        "transcript_rows": _sort_rows_chronologically(
            temporal_transcript_rows,
            limit=limits["transcript_limit"],
        ),
        "graph_rows": _temporal_graph_rows(graph_rows, limit=limits["graph_limit"]),
        "corpus_rows": [],
    }


def _select_aggregate_rows(
    *,
    native_aggregate_rows: List[Dict[str, Any]],
    keyword_continuity_rows: List[Dict[str, Any]],
    keyword_transcript_rows: List[Dict[str, Any]],
    semantic_conversation_rows: List[Dict[str, Any]],
    keyword_corpus_rows: List[Dict[str, Any]],
    semantic_corpus_rows: List[Dict[str, Any]],
    graph_rows: List[Dict[str, Any]],
    limits: Dict[str, int],
) -> Dict[str, List[Dict[str, Any]]]:
    aggregate_matched = _aggregate_diverse_rows(
        keyword_continuity_rows,
        limit=limits["continuity_match_limit"],
    )
    if native_aggregate_rows:
        aggregate_matched = _dedupe_rows([*native_aggregate_rows, *aggregate_matched])[
            : limits["continuity_match_limit"]
        ]
    return {
        "profile_items": [],
        "matched": aggregate_matched,
        "recent": [],
        "transcript_rows": _aggregate_diverse_rows(
            _round_robin(semantic_conversation_rows, keyword_transcript_rows),
            limit=limits["transcript_limit"],
        ),
        "graph_rows": _graph_channel_rows(graph_rows, limit=limits["graph_limit"]),
        "corpus_rows": _corpus_channel_rows(
            _round_robin(semantic_corpus_rows, keyword_corpus_rows),
            limit=limits["corpus_limit"],
        ),
    }


def _collect_query_rows(
    *,
    shelf: str,
    queries: List[str],
    searcher: Callable[[str], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if not queries:
        return []
    groups: List[List[Dict[str, Any]]] = []
    for query in queries:
        rows = [dict(row) for row in searcher(query)]
        for row in rows:
            row.setdefault("_brainstack_query_variant", query)
        groups.append(rows)

    seen: set[str] = set()
    merged: List[Dict[str, Any]] = []
    for row in _round_robin(*groups):
        key = _candidate_key(shelf, row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def _annotate_query_flags(rows: Iterable[Dict[str, Any]], *, query: str) -> List[Dict[str, Any]]:
    query_has_digits = any(char.isdigit() for char in str(query or ""))
    query_tokens = {
        token
        for token in re.findall(r"[^\W_]+", _normalize_text(query).casefold(), flags=re.UNICODE)
        if len(token) >= 3
    }
    annotated: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["_brainstack_query_has_digits"] = query_has_digits
        content = _normalize_text(payload.get("content") or payload.get("content_excerpt"))
        row_tokens = {
            token
            for token in re.findall(r"[^\W_]+", content.casefold(), flags=re.UNICODE)
            if len(token) >= 3
        }
        payload["_brainstack_query_token_overlap"] = len(query_tokens & row_tokens)
        annotated.append(payload)
    return annotated


def _profile_keyword_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(rows))
    ranked.sort(
        key=lambda item: (
            1 if bool(item[1].get("_direct_slot_match")) else 0,
            float(item[1].get("keyword_score") or 0.0),
            profile_priority_adjustment(item[1]),
            float(item[1].get("confidence") or 0.0),
            str(item[1].get("updated_at") or ""),
            -0.05 * item[0],
        ),
        reverse=True,
    )
    return [row for _, row in ranked[:limit]]


def _operating_channel_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(_dedupe_rows(rows)))
    ranked.sort(
        key=lambda item: (
            float(item[1].get("keyword_score") or 0.0),
            str(item[1].get("updated_at") or ""),
            -0.05 * item[0],
        ),
        reverse=True,
    )
    return [row for _, row in ranked[:limit]]


def _graph_match_text(row: Dict[str, Any]) -> str:
    parts = [
        str(row.get("subject") or "").strip(),
        str(row.get("attribute") or "").strip(),
        str(row.get("value") or "").strip(),
        str(row.get("predicate") or "").strip(),
        str(row.get("object_value") or "").strip(),
        str(row.get("conflict_value") or "").strip(),
    ]
    return " ".join(part for part in parts if part)


def _graph_fact_class(row: Dict[str, Any]) -> str:
    row_type = str(row.get("row_type") or "").strip()
    if row_type == "conflict":
        return "conflict"
    if row_type == "inferred_relation":
        return "inferred_relation"
    if row_type == "relation":
        return "explicit_relation"
    if row_type == "state":
        if row.get("is_current"):
            return "explicit_state_current"
        return "explicit_state_prior"
    return row_type or "graph"


def _graph_channel_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(rows))
    ranked.sort(
        key=lambda item: (
            graph_priority_adjustment(item[1]),
            float(item[1].get("keyword_score") or 0.0),
            str(item[1].get("happened_at") or ""),
            -0.05 * item[0],
        ),
        reverse=True,
    )
    return [row for _, row in ranked[:limit]]


def _corpus_channel_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(_dedupe_rows(rows)))
    ranked.sort(
        key=lambda item: (
            float(item[1].get("semantic_score") or 0.0),
            float(item[1].get("keyword_score") or 0.0),
            1 if "semantic" in str(item[1].get("retrieval_source") or "") else 0,
            1 if bool(item[1].get("same_session")) else 0,
            -0.05 * item[0],
        ),
        reverse=True,
    )
    return [row for _, row in ranked[:limit]]


def _temporal_graph_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(rows))
    ranked.sort(
        key=lambda item: (
            1 if _graph_fact_class(item[1]) == "explicit_state_current" else 0,
            1 if _graph_fact_class(item[1]) == "conflict" else 0,
            1 if _graph_fact_class(item[1]) == "explicit_state_prior" else 0,
            str(item[1].get("happened_at") or ""),
            -0.05 * item[0],
        ),
        reverse=True,
    )
    return [row for _, row in ranked[:limit]]


def _candidate_key(shelf: str, row: Dict[str, Any]) -> str:
    if shelf == "profile":
        stable_key = str(row.get("stable_key") or "").strip()
        return f"profile:{stable_key or row.get('id')}"
    if shelf == "operating":
        stable_key = str(row.get("stable_key") or "").strip()
        return f"operating:{stable_key or row.get('id')}"
    if shelf in {"continuity_match", "continuity_recent"}:
        return f"continuity:{int(row.get('id') or 0)}"
    if shelf == "transcript":
        return f"transcript:{int(row.get('id') or 0)}"
    if shelf == "graph":
        return f"graph:{row.get('row_type')}:{int(row.get('row_id') or 0)}"
    if shelf == "corpus":
        return f"corpus:{int(row.get('document_id') or 0)}:{int(row.get('section_index') or 0)}"
    return f"{shelf}:{row!r}"


def _merge_shelf(existing: str, new: str) -> str:
    priorities = {
        "profile": 5,
        "operating": 4,
        "graph": 3,
        "continuity_match": 2,
        "continuity_recent": 1,
        "transcript": 0,
        "corpus": -1,
    }
    return existing if priorities.get(existing, 0) >= priorities.get(new, 0) else new


def _merge_channel(
    merged: Dict[str, EvidenceCandidate],
    *,
    channel_name: str,
    rows: Iterable[Dict[str, Any]],
    shelf: str,
) -> None:
    for rank, row in enumerate(rows, start=1):
        key = _candidate_key(shelf, row)
        candidate = merged.get(key)
        if candidate is None:
            candidate = EvidenceCandidate(key=key, shelf=shelf, row=row)
            merged[key] = candidate
        else:
            candidate.shelf = _merge_shelf(candidate.shelf, shelf)
        candidate.seen_in(channel_name, rank)
        candidate.rrf_score += _fusion_rank_contribution(
            channel_name=channel_name,
            shelf=shelf,
            rank=rank,
        )


def _channel_status(name: str, rows: List[Dict[str, Any]], *, reason: str = "", status: str = "active") -> Dict[str, Any]:
    return asdict(
        RetrievalChannelStatus(
            name=name,
            status=status,
            reason=reason,
            candidate_count=len(rows),
        )
    )


def _select_rows(
    candidates: List[EvidenceCandidate],
    *,
    profile_limit: int,
    continuity_match_limit: int,
    continuity_recent_limit: int,
    transcript_limit: int,
    operating_limit: int,
    graph_limit: int,
    corpus_limit: int,
    evidence_item_budget: int,
) -> Dict[str, List[Dict[str, Any]]]:
    profile_items: List[Dict[str, Any]] = []
    matched: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    transcript_rows: List[Dict[str, Any]] = []
    operating_rows: List[Dict[str, Any]] = []
    graph_rows: List[Dict[str, Any]] = []
    corpus_rows: List[Dict[str, Any]] = []

    seen_profile_keys: set[str] = set()
    seen_continuity_ids: set[int] = set()
    seen_transcript_ids: set[int] = set()
    seen_operating_keys: set[str] = set()
    seen_graph_keys: set[tuple[str, int]] = set()
    seen_corpus_keys: set[tuple[int, int]] = set()
    evidence_items_used = 0
    shared_budget_enabled = evidence_item_budget > 0

    def materialize(candidate: EvidenceCandidate) -> Dict[str, Any]:
        row = dict(candidate.row)
        row["_brainstack_rrf_score"] = candidate.rrf_score
        row["_brainstack_channels"] = sorted(candidate.channel_ranks)
        row["_brainstack_channel_ranks"] = dict(candidate.channel_ranks)
        return row

    for candidate in candidates:
        row = materialize(candidate)
        if candidate.shelf == "profile" and len(profile_items) < profile_limit:
            stable_key = str(row.get("stable_key") or "").strip()
            if stable_key and stable_key not in seen_profile_keys:
                seen_profile_keys.add(stable_key)
                profile_items.append(row)
            continue

        if shared_budget_enabled and evidence_items_used >= evidence_item_budget:
            continue

        if candidate.shelf == "continuity_match" and len(matched) < continuity_match_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_continuity_ids:
                seen_continuity_ids.add(row_id)
                matched.append(row)
                evidence_items_used += 1
            continue

        if candidate.shelf == "continuity_recent" and len(recent) < continuity_recent_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_continuity_ids:
                seen_continuity_ids.add(row_id)
                recent.append(row)
                evidence_items_used += 1
            continue

        if candidate.shelf == "transcript" and len(transcript_rows) < transcript_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_transcript_ids:
                seen_transcript_ids.add(row_id)
                transcript_rows.append(row)
                evidence_items_used += 1
            continue

        if candidate.shelf == "operating" and len(operating_rows) < operating_limit:
            stable_key = str(row.get("stable_key") or "").strip()
            if stable_key and stable_key not in seen_operating_keys:
                seen_operating_keys.add(stable_key)
                operating_rows.append(row)
                evidence_items_used += 1
            continue

        if candidate.shelf == "graph" and len(graph_rows) < graph_limit:
            row_key = (str(row.get("row_type") or ""), int(row.get("row_id") or 0))
            if row_key[1] > 0 and row_key not in seen_graph_keys:
                seen_graph_keys.add(row_key)
                graph_rows.append(row)
                evidence_items_used += 1
            continue

        if candidate.shelf == "corpus" and len(corpus_rows) < corpus_limit:
            corpus_row_key = (int(row.get("document_id") or 0), int(row.get("section_index") or 0))
            if corpus_row_key[0] > 0 and corpus_row_key not in seen_corpus_keys:
                seen_corpus_keys.add(corpus_row_key)
                corpus_rows.append(row)
                evidence_items_used += 1
            continue

    return {
        "profile_items": profile_items,
        "matched": matched,
        "recent": recent,
        "transcript_rows": transcript_rows,
        "operating_rows": operating_rows,
        "graph_rows": graph_rows,
        "corpus_rows": corpus_rows,
    }


def retrieve_executive_context(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
    principal_scope_key: str = "",
    analysis: Dict[str, Any],
    policy: Dict[str, Any],
    route_resolver: Callable[[str], Dict[str, Any] | str] | None = None,
    timezone_name: str = "UTC",
) -> Dict[str, Any]:
    profile_limit = max(int(policy.get("profile_limit", 0)), 0)
    continuity_match_limit = max(int(policy.get("continuity_match_limit", 0)), 0)
    continuity_recent_limit = max(int(policy.get("continuity_recent_limit", 0)), 0)
    transcript_limit = max(int(policy.get("transcript_limit", 0)), 0)
    evidence_item_budget = max(int(policy.get("evidence_item_budget", 0)), 0)
    operating_limit = max(int(policy.get("operating_limit", 0)), 0)
    graph_limit = max(int(policy.get("graph_limit", 0)), 0)
    corpus_limit = max(int(policy.get("corpus_limit", 0)), 0)
    style_contract_row = store.get_profile_item(
        stable_key=STYLE_CONTRACT_SLOT,
        principal_scope_key=principal_scope_key,
    )
    native_explicit_style_rows = [
        row
        for row in store.list_profile_items(limit=24, principal_scope_key=principal_scope_key)
        if is_native_explicit_style_item(row)
    ]
    analysis_route_payload = analysis.get("route_payload")
    effective_route_resolver = route_resolver
    if effective_route_resolver is None and isinstance(analysis_route_payload, Mapping):
        payload = dict(analysis_route_payload)
        effective_route_resolver = lambda _query, _payload=payload: dict(_payload)
    elif effective_route_resolver is None:
        fallback_payload = infer_query_understanding(query, timezone_name=timezone_name).get("route")
        if isinstance(fallback_payload, Mapping):
            payload = dict(fallback_payload)
            effective_route_resolver = lambda _query, _payload=payload: dict(_payload)
    route = _resolve_route(
        query,
        route_resolver=effective_route_resolver,
    )
    limits = _route_limits(
        route=route,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        operating_limit=operating_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
    )
    search_queries = [_normalize_text(query)]
    continuity_queries = _build_cross_session_search_queries(query)
    task_lookup = analysis.get("task_lookup") if isinstance(analysis.get("task_lookup"), Mapping) else None
    operating_lookup = analysis.get("operating_lookup") if isinstance(analysis.get("operating_lookup"), Mapping) else None
    task_rows = (
        store.list_task_items(
            principal_scope_key=principal_scope_key,
            due_date=str(task_lookup.get("due_date") or "").strip(),
            item_type=str(task_lookup.get("item_type") or "").strip(),
            statuses=("open",),
            limit=24,
        )
        if isinstance(task_lookup, Mapping)
        else []
    )
    operating_target_types = (
        [
            str(value or "").strip()
            for value in (operating_lookup.get("record_types") or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        if isinstance(operating_lookup, Mapping)
        else []
    )
    profile_limit = limits["profile_limit"]
    continuity_match_limit = limits["continuity_match_limit"]
    continuity_recent_limit = limits["continuity_recent_limit"]
    transcript_limit = limits["transcript_limit"]
    operating_limit = limits["operating_limit"]
    graph_limit = limits["graph_limit"]
    corpus_limit = limits["corpus_limit"]

    profile_target_slots = tuple(str(slot) for slot in analysis.get("profile_slot_targets") or ())
    preserve_authoritative_contract = bool(policy.get("show_authoritative_contract"))
    if route.applied_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract:
        profile_target_slots = tuple({*profile_target_slots, STYLE_CONTRACT_SLOT})
    excluded_profile_slots = () if route.applied_mode == ROUTE_STYLE_CONTRACT or preserve_authoritative_contract else (STYLE_CONTRACT_SLOT,)

    keyword_profile_rows = (
        _profile_keyword_rows(
            store.search_profile(
                query=query,
                limit=max(profile_limit * 4, 8),
                principal_scope_key=principal_scope_key,
                target_slots=profile_target_slots,
                excluded_slots=excluded_profile_slots,
            ),
            limit=max(profile_limit * 2, 6),
        )
        if profile_limit > 0
        else []
    )
    keyword_profile_rows = _annotate_query_flags(keyword_profile_rows, query=query)
    keyword_profile_rows = [row for row in keyword_profile_rows if not _is_native_profile_mirror_receipt(row)]
    if route.applied_mode == ROUTE_STYLE_CONTRACT:
        keyword_profile_rows = [
            row
            for row in keyword_profile_rows
            if str(row.get("stable_key") or "").strip() == STYLE_CONTRACT_SLOT or is_native_explicit_style_item(row)
        ]
        if not keyword_profile_rows:
            if native_explicit_style_rows:
                keyword_profile_rows = list(native_explicit_style_rows)
            else:
                keyword_profile_rows = [_missing_style_contract_row(principal_scope_key=principal_scope_key)]
    keyword_continuity_rows = (
        _collect_query_rows(
            shelf="continuity_match",
            queries=continuity_queries,
            searcher=lambda variant: store.search_continuity(
                query=variant,
                session_id=session_id,
                principal_scope_key=principal_scope_key,
                limit=max(continuity_match_limit * 4, 8),
            ),
        )
        if continuity_match_limit > 0
        else []
    )
    keyword_continuity_rows = _annotate_query_flags(keyword_continuity_rows, query=query)
    keyword_transcript_session_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=continuity_queries,
            searcher=lambda variant: store.search_transcript(
                query=variant,
                session_id=session_id,
                limit=max(transcript_limit * 4, 6),
            ),
        )
        if transcript_limit > 0
        else []
    )
    keyword_transcript_session_rows = _annotate_query_flags(keyword_transcript_session_rows, query=query)
    keyword_transcript_global_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=continuity_queries,
            searcher=lambda variant: store.search_transcript_global(
                query=variant,
                session_id=session_id,
                principal_scope_key=principal_scope_key,
                limit=max(transcript_limit * 6, 12),
            ),
        )
        if transcript_limit > 0
        else []
    )
    keyword_transcript_global_rows = _annotate_query_flags(keyword_transcript_global_rows, query=query)
    keyword_transcript_rows = _round_robin(
        keyword_transcript_session_rows,
        keyword_transcript_global_rows,
    )
    keyword_operating_rows = (
        _operating_channel_rows(
            store.search_operating_records(
                query=query,
                principal_scope_key=principal_scope_key,
                record_types=operating_target_types or None,
                limit=max(operating_limit * 4, 8),
            ),
            limit=max(operating_limit * 3, 8),
        )
        if operating_limit > 0
        else []
    )
    keyword_operating_rows = _annotate_query_flags(keyword_operating_rows, query=query)
    recent_work_operating_rows = (
        _operating_channel_rows(
            store.search_operating_records(
                query=query,
                principal_scope_key=principal_scope_key,
                record_types=RECENT_WORK_RECAP_RECORD_TYPES,
                limit=max(operating_limit * 4, 8),
            ),
            limit=max(operating_limit * 3, 8),
        )
        if operating_limit > 0
        else []
    )
    recent_work_operating_rows = _annotate_query_flags(recent_work_operating_rows, query=query)
    current_operating_rows = (
        store.list_operating_records(
            principal_scope_key=principal_scope_key,
            record_types=operating_target_types or None,
            limit=max(operating_limit * 2, 6),
        )
        if operating_limit > 0 and isinstance(operating_lookup, Mapping)
        else []
    )
    current_operating_rows = _annotate_query_flags(current_operating_rows, query=query)
    keyword_corpus_rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus(
                query=variant,
                limit=max(corpus_limit * 4, 8),
            ),
        )
        if corpus_limit > 0
        else []
    )
    keyword_corpus_rows = _annotate_query_flags(keyword_corpus_rows, query=query)
    semantic_conversation_rows = (
        _collect_query_rows(
                shelf="transcript",
                queries=search_queries,
                searcher=lambda variant: store.search_conversation_semantic(
                    query=variant,
                    session_id=session_id,
                    limit=max(transcript_limit * 4, 8),
                    principal_scope_key=principal_scope_key,
                ),
            )
        if transcript_limit > 0
        else []
    )
    semantic_conversation_rows = _annotate_query_flags(semantic_conversation_rows, query=query)
    semantic_corpus_rows = (
        _collect_query_rows(
            shelf="corpus",
            queries=search_queries,
            searcher=lambda variant: store.search_corpus_semantic(
                query=variant,
                limit=max(corpus_limit * 4, 8),
            ),
        )
        if corpus_limit > 0
        else []
    )
    semantic_corpus_rows = _annotate_query_flags(semantic_corpus_rows, query=query)
    task_structured_authority = isinstance(task_lookup, Mapping) and route.applied_mode != ROUTE_TEMPORAL
    if task_structured_authority:
        keyword_continuity_rows = []
        keyword_transcript_session_rows = []
        keyword_transcript_global_rows = []
        keyword_transcript_rows = []
        semantic_conversation_rows = []
    keyword_rows = _round_robin(
        keyword_profile_rows,
        keyword_operating_rows,
        recent_work_operating_rows,
        keyword_continuity_rows,
        keyword_transcript_rows,
        keyword_corpus_rows,
    )

    graph_rows = (
        _graph_channel_rows(
            _collect_query_rows(
                shelf="graph",
                queries=search_queries,
                searcher=lambda variant: store.search_graph(
                    query=variant,
                    limit=max(graph_limit * 4, 12),
                    principal_scope_key=principal_scope_key,
                ),
            ),
            limit=max(graph_limit * 3, 8),
        )
        if graph_limit > 0
        else []
    )
    graph_rows = _annotate_query_flags(graph_rows, query=query)

    recent_rows = (
        store.recent_continuity(session_id=session_id, limit=max(continuity_recent_limit * 4, 6))
        if continuity_recent_limit > 0
        else []
    )
    temporal_continuity_search = getattr(store, "search_temporal_continuity", None)
    temporal_continuity_rows = (
        temporal_continuity_search(
            query=query,
            session_id=session_id,
            principal_scope_key=principal_scope_key,
            limit=max(continuity_recent_limit * 4, TEMPORAL_RECENT_CAP),
        )
        if continuity_recent_limit > 0
        and route.applied_mode == ROUTE_TEMPORAL
        and callable(temporal_continuity_search)
        else []
    )
    temporal_continuity_rows = _annotate_query_flags(temporal_continuity_rows, query=query)
    recent_rows = _annotate_query_flags(recent_rows, query=query)
    if task_structured_authority:
        recent_rows = []
        temporal_continuity_rows = []
    temporal_support_requested = route.applied_mode == ROUTE_TEMPORAL or route.requested_mode == ROUTE_TEMPORAL

    temporal_graph_rows = []
    if graph_limit > 0 and temporal_support_requested:
        temporal_graph_rows = _temporal_graph_rows(
            _collect_query_rows(
                shelf="graph",
                queries=search_queries,
                searcher=lambda variant: store.search_graph(
                    query=variant,
                    limit=max(graph_limit * 6, 12),
                    principal_scope_key=principal_scope_key,
                ),
            ),
            limit=max(graph_limit * 2, 6),
        )

    temporal_transcript_rows = []
    if transcript_limit > 0 and temporal_support_requested:
        temporal_support_rows = _same_principal_session_support_rows(
            store,
            _dedupe_rows(_round_robin(temporal_continuity_rows, recent_rows)),
            current_session_id=session_id,
        )
        temporal_transcript_rows = _sort_rows_chronologically(
            _round_robin(keyword_transcript_rows, semantic_conversation_rows, temporal_support_rows),
            limit=max(TEMPORAL_TRANSCRIPT_CAP * 2, transcript_limit * 2),
        )

    temporal_rows = _round_robin(
        temporal_continuity_rows,
        recent_rows,
        temporal_transcript_rows,
        temporal_graph_rows,
    )
    native_aggregate_rows = (
        _native_aggregate_rows(
            store,
            query=query,
            session_id=session_id,
        )
        if route.applied_mode == ROUTE_AGGREGATE
        else []
    )
    graph_status = store.graph_backend_channel_status()

    merged: Dict[str, EvidenceCandidate] = {}
    _merge_channel(merged, channel_name="keyword", rows=keyword_profile_rows, shelf="profile")
    _merge_channel(merged, channel_name="operating", rows=keyword_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=recent_work_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="operating", rows=current_operating_rows, shelf="operating")
    _merge_channel(merged, channel_name="keyword", rows=keyword_continuity_rows, shelf="continuity_match")
    _merge_channel(merged, channel_name="keyword", rows=keyword_transcript_rows, shelf="transcript")
    _merge_channel(merged, channel_name="keyword", rows=keyword_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_conversation_rows, shelf="transcript")
    _merge_channel(merged, channel_name="semantic", rows=semantic_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="graph", rows=graph_rows, shelf="graph")
    _merge_channel(merged, channel_name="temporal", rows=temporal_continuity_rows, shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=recent_rows, shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=temporal_transcript_rows, shelf="transcript")
    _merge_channel(merged, channel_name="temporal", rows=temporal_graph_rows, shelf="graph")

    fused = sorted(merged.values(), key=_fact_sort_key, reverse=True)

    fact_selected = _select_rows(
        fused,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        operating_limit=operating_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        evidence_item_budget=evidence_item_budget,
    )
    fused_transcript_rows = [candidate.row for candidate in fused if candidate.shelf == "transcript"]
    fact_selected["transcript_rows"] = _fact_transcript_rows(
        store=store,
        current_session_id=session_id,
        fused_transcript_rows=fused_transcript_rows,
        keyword_transcript_rows=keyword_transcript_rows,
        semantic_conversation_rows=semantic_conversation_rows,
        matched_rows=fact_selected["matched"],
        limit=limits["transcript_limit"],
    )
    selected = fact_selected
    if route.applied_mode == ROUTE_TEMPORAL:
        selected = _select_temporal_rows(
            keyword_continuity_rows=keyword_continuity_rows,
            recent_rows=recent_rows,
            temporal_continuity_rows=temporal_continuity_rows,
            temporal_transcript_rows=temporal_transcript_rows,
            graph_rows=temporal_graph_rows,
            limits=limits,
        )
    elif route.applied_mode == ROUTE_AGGREGATE:
        selected = _select_aggregate_rows(
            native_aggregate_rows=native_aggregate_rows,
            keyword_continuity_rows=keyword_continuity_rows,
            keyword_transcript_rows=keyword_transcript_rows,
            semantic_conversation_rows=semantic_conversation_rows,
            keyword_corpus_rows=keyword_corpus_rows,
            semantic_corpus_rows=semantic_corpus_rows,
            graph_rows=graph_rows,
            limits=limits,
        )

    transcript_rows = selected["transcript_rows"]
    if transcript_rows and not _has_meaningful_transcript_signal(transcript_rows):
        if route.applied_mode == ROUTE_TEMPORAL and _keep_temporal_transcript_rows_with_anchor_support(selected):
            pass
        else:
            selected["transcript_rows"] = []
    if route.applied_mode != ROUTE_FACT and not _route_has_support(route, selected):
        route.fallback_used = True
        route.applied_mode = ROUTE_FACT
        selected = fact_selected

    semantic_status = (
        store.corpus_semantic_channel_status()
        if corpus_limit > 0 or keyword_corpus_rows or semantic_corpus_rows
        else {
            "status": "idle",
            "reason": "Corpus semantic retrieval was intentionally skipped for this query shape.",
        }
    )
    channels = [
        _channel_status(
            "task_memory",
            task_rows,
            reason="structured task truth",
            status="active" if task_lookup is not None else "idle",
        ),
        _channel_status(
            "operating_truth",
            keyword_operating_rows + recent_work_operating_rows + current_operating_rows,
            reason="first-class operating truth",
            status="active" if operating_lookup is not None or bool(recent_work_operating_rows) else "idle",
        ),
        _channel_status(
            "semantic",
            semantic_conversation_rows + semantic_corpus_rows,
            reason=str(semantic_status.get("reason") or ""),
            status=str(semantic_status.get("status") or "degraded"),
        ),
        _channel_status("keyword", keyword_rows),
        _channel_status(
            "graph",
            graph_rows,
            reason=str(graph_status.get("reason") or ""),
            status=str(graph_status.get("status") or "degraded"),
        ),
        _channel_status("temporal", temporal_rows),
    ]
    lookup_semantics = _build_lookup_semantics(
        query=query,
        task_lookup=task_lookup,
        task_rows=task_rows,
        operating_lookup=operating_lookup,
        operating_rows=selected.get("operating_rows") or [],
        selected=selected,
    )

    return {
        **selected,
        "task_rows": task_rows,
        "operating_rows": selected.get("operating_rows") or [],
        "channels": channels,
        "fused_candidates": [
            {
                "key": candidate.key,
                "shelf": candidate.shelf,
                "rrf_score": candidate.rrf_score,
                "agreement_bonus": _agreement_bonus(candidate),
                "priority_bonus": _candidate_priority_bonus(candidate),
                "channel_ranks": dict(candidate.channel_ranks),
                "id": int(candidate.row.get("id") or 0),
                "row_id": int(candidate.row.get("row_id") or 0),
                "turn_number": int(candidate.row.get("turn_number") or 0),
                "document_id": int(candidate.row.get("document_id") or 0),
                "section_index": int(candidate.row.get("section_index") or 0),
                "created_at": str(candidate.row.get("created_at") or ""),
                "keyword_score": float(candidate.row.get("keyword_score") or 0.0),
                "semantic_score": float(candidate.row.get("semantic_score") or 0.0),
                "same_session": bool(candidate.row.get("same_session")),
                "content_excerpt": _candidate_text(candidate)[:220],
            }
            for candidate in fused
        ],
        "decomposition": {
            "used": False,
            "queries": list(search_queries),
            "legacy_disabled": True,
        },
        "lookup_semantics": lookup_semantics,
        "routing": asdict(route),
    }
