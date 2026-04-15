from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List

from .db import BrainstackStore
from .tier2_extractor import _default_llm_caller, _extract_json_object, _extract_text_content
from .transcript import has_meaningful_transcript_evidence, tokenize_match_text
from .usefulness import graph_priority_adjustment, profile_priority_adjustment

RRF_K = 60
ROUTE_FACT = "fact"
ROUTE_TEMPORAL = "temporal"
ROUTE_AGGREGATE = "aggregate"
ROUTING_HINT_MIN_TOKENS = 5
ROUTING_HINT_MIN_CHARS = 28
TEMPORAL_CONTINUITY_CAP = 3
TEMPORAL_RECENT_CAP = 3
TEMPORAL_TRANSCRIPT_CAP = 3
TEMPORAL_GRAPH_CAP = 3
AGGREGATE_CONTINUITY_CAP = 6
AGGREGATE_TRANSCRIPT_CAP = 6
AGGREGATE_GRAPH_CAP = 2

logger = logging.getLogger(__name__)

AGGREGATE_ROUTE_CUES = (
    "in total",
    "total",
    "how many",
    "count",
    "altogether",
    "combined",
    "sum",
)
TEMPORAL_STRONG_CUES = (
    "order of",
    "earliest",
    "latest",
    "most recent",
    "first",
    "second",
    "third",
    "what is the order",
    "which came first",
    "which happened first",
    "how many days",
    "how many months",
    "how many years",
    "when did",
)
TEMPORAL_WEAK_CUES = (
    "before",
    "after",
    "previous",
    "changed",
    "between",
)

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
    bounds: Dict[str, Any] = field(default_factory=dict)


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _looks_user_led(text: str) -> bool:
    return _normalize_text(text).lower().startswith("user:")


def _candidate_text(candidate: EvidenceCandidate) -> str:
    row = candidate.row
    if candidate.shelf == "graph":
        return _graph_match_text(row)
    if candidate.shelf == "profile":
        return _normalize_text(row.get("content"))
    return _normalize_text(row.get("content"))


def _candidate_priority_bonus(candidate: EvidenceCandidate) -> float:
    row = candidate.row
    text = _candidate_text(candidate)
    bonus = 0.0
    query_has_digits = bool(row.get("_brainstack_query_has_digits"))

    if candidate.shelf == "transcript":
        bonus += 0.08
        if "keyword" in candidate.channel_ranks:
            bonus += 0.04
        if _looks_user_led(text):
            bonus += 0.06
    elif candidate.shelf == "continuity_match":
        bonus += 0.02
    elif candidate.shelf == "continuity_recent":
        bonus += 0.01

    if query_has_digits and any(char.isdigit() for char in text):
        bonus += 0.08
    if '"' in text or "'" in text:
        bonus += 0.02

    overlap = int(row.get("overlap_count") or 0)
    if overlap > 0:
        bonus += min(0.06, 0.015 * overlap)

    semantic_score = float(row.get("semantic_score") or 0.0)
    if semantic_score > 0.0:
        bonus += min(0.08, semantic_score * 0.08)

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


def _should_attempt_route_hint(query: str) -> bool:
    normalized = _normalize_text(query)
    if len(normalized) < ROUTING_HINT_MIN_CHARS:
        return False
    tokens = tokenize_match_text(normalized)
    if len(tokens) < ROUTING_HINT_MIN_TOKENS:
        return False
    structural_markers = sum(1 for marker in (",", ":", ";", "/", "=") if marker in normalized)
    if structural_markers >= 2:
        return True
    if structural_markers >= 1 and any(char.isdigit() for char in normalized):
        return True
    if len(tokens) >= 8 and len(normalized) >= 45:
        return True
    return normalized.endswith("?") and len(tokens) >= 6 and len(normalized) >= 38


def _llm_route_resolver(query: str) -> Dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": (
                "You classify Brainstack memory retrieval questions into one of three modes.\n"
                "Return JSON only with the schema {\"mode\": \"fact|temporal|aggregate\", \"reason\": \"...\"}.\n"
                "Use temporal when the user needs ordering, before/after comparison, date difference, or change over time.\n"
                "Use aggregate when the user needs totals, counts across multiple events, or exhaustive collection.\n"
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


def _contains_cue(normalized: str, cue: str) -> bool:
    return cue in normalized


def _default_route_resolver(query: str) -> Dict[str, Any]:
    normalized = f" {_normalize_text(query).lower()} "
    temporal_strong_hits = [cue for cue in TEMPORAL_STRONG_CUES if _contains_cue(normalized, cue)]
    if temporal_strong_hits:
        return {
            "mode": ROUTE_TEMPORAL,
            "reason": f"deterministic temporal cues: {', '.join(temporal_strong_hits)}",
            "source": "deterministic_route_hint",
        }

    aggregate_hits = [cue for cue in AGGREGATE_ROUTE_CUES if _contains_cue(normalized, cue)]
    if aggregate_hits:
        return {
            "mode": ROUTE_AGGREGATE,
            "reason": f"deterministic aggregate cues: {', '.join(aggregate_hits)}",
            "source": "deterministic_route_hint",
        }

    temporal_weak_hits = [cue for cue in TEMPORAL_WEAK_CUES if _contains_cue(normalized, cue)]
    if temporal_weak_hits and any(char.isdigit() for char in normalized):
        return {
            "mode": ROUTE_TEMPORAL,
            "reason": f"deterministic temporal cues: {', '.join(temporal_weak_hits)} + digits",
            "source": "deterministic_route_hint",
        }

    return {
        "mode": ROUTE_FACT,
        "reason": "deterministic fact default: no strong structural route cues",
        "source": "deterministic_route_hint",
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

    resolver = route_resolver
    source = "injected"
    if resolver is None and _should_attempt_route_hint(normalized):
        resolver = _default_route_resolver
        source = "deterministic_route_hint"
    if resolver is None:
        return route

    try:
        payload = resolver(normalized)
    except Exception as exc:
        logger.warning("Brainstack route resolution failed: %s", exc)
        route.source = "fallback"
        route.reason = f"route hint failed: {exc}"
        return route

    if isinstance(payload, str):
        mode = _normalize_text(payload).lower()
        reason = ""
    elif isinstance(payload, dict):
        mode = _normalize_text(payload.get("mode")).lower()
        reason = _normalize_text(payload.get("reason"))
        source = _normalize_text(payload.get("source")) or source
    else:
        return route

    if mode not in {ROUTE_FACT, ROUTE_TEMPORAL, ROUTE_AGGREGATE}:
        return route
    route.requested_mode = mode
    route.applied_mode = mode
    route.source = source
    route.reason = reason
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
            row.setdefault("overlap_count", 0)
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


def _temporal_anchor_key(row: Dict[str, Any]) -> str:
    raw = _row_time_value(row)
    parsed = _parse_time_value(raw)
    return parsed.isoformat() if parsed is not None else raw


def _sort_rows_chronologically(rows: Iterable[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    deduped = _chronologically_sorted_rows(rows)
    return deduped[:limit]


def _chronologically_sorted_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped = _dedupe_rows(rows)
    deduped.sort(
        key=lambda row: (
            0 if _parse_time_value(_row_time_value(row)) is not None else 1,
            _parse_time_value(_row_time_value(row)) or datetime.max,
            _row_time_value(row),
            int(row.get("turn_number") or 0),
            int(row.get("id") or row.get("row_id") or 0),
        ),
    )
    return deduped


def _temporal_diversity_key(row: Dict[str, Any]) -> str:
    parsed = _parse_time_value(_row_time_value(row))
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
    unbucketed: List[Dict[str, Any]] = []
    for row in ranked:
        bucket = _temporal_diversity_key(row)
        if bucket:
            # Keep the latest row within the same temporal bucket so a concrete
            # realized event can displace earlier planning/context rows.
            bucket_representatives[bucket] = dict(row)
        else:
            unbucketed.append(dict(row))

    selected = _chronologically_sorted_rows(bucket_representatives.values())
    seen = {_row_unique_key(row) for row in selected}
    for row in ranked:
        key = _row_unique_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(row))
    for row in unbucketed:
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
        int(row.get("overlap_count") or 0),
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


def _query_mentions_any(query: str, phrases: Iterable[str]) -> bool:
    normalized = _normalize_text(query).lower()
    return any(phrase in normalized for phrase in phrases)


def _plan_bounded_native_aggregate_sum(query: str) -> Dict[str, Any] | None:
    normalized = _normalize_text(query).lower()
    if not normalized:
        return None
    has_total = _query_mentions_any(normalized, ("in total", "total", "combined", "sum"))
    has_distance = _query_mentions_any(normalized, ("mile", "miles", "distance"))
    has_road_trip = _query_mentions_any(normalized, ("road trip", "road trips"))
    if has_total and has_distance and has_road_trip:
        return {
            "aggregate_kind": "sum",
            "entity_type": None,
            "entity_type_contains": ("road_trip", "mileage_history"),
            "entity_type_excludes": ("planned_",),
            "metric_attribute": "distance_miles",
            "owner_subject": None,
            "unit": "miles",
        }
    return None


def _native_aggregate_rows(
    store: BrainstackStore,
    *,
    query: str,
    session_id: str,
) -> List[Dict[str, Any]]:
    plan = _plan_bounded_native_aggregate_sum(query)
    if not plan:
        return []
    result = store.query_native_typed_metric_sum(
        owner_subject=(str(plan["owner_subject"]) if plan.get("owner_subject") is not None else None),
        entity_type=(str(plan["entity_type"]) if plan.get("entity_type") is not None else None),
        entity_type_contains=plan.get("entity_type_contains"),
        entity_type_excludes=plan.get("entity_type_excludes"),
        metric_attribute=str(plan["metric_attribute"]),
        limit=16,
    )
    if not result:
        return []
    total = float(result.get("total") or 0.0)
    count = int(result.get("count") or 0)
    matches = list(result.get("matches") or [])
    entity_names = [str(item.get("entity_name") or "").strip() for item in matches if str(item.get("entity_name") or "").strip()]
    unique_names = list(dict.fromkeys(entity_names))[:4]
    if abs(total - round(total)) < 1e-9:
        total_text = f"{int(round(total)):,}"
    else:
        total_text = f"{total:,.2f}".rstrip("0").rstrip(".")
    unit = str(plan.get("unit") or "").strip()
    label = f"{total_text} {unit}".strip()
    support = ", ".join(unique_names)
    if plan.get("entity_type_contains"):
        entity_label = "/".join(str(item) for item in plan["entity_type_contains"])
    else:
        entity_label = str(plan.get("entity_type") or "typed")
    content = f"Native graph sum: {label} across {count} {entity_label} events"
    if support:
        content += f" ({support})"
    return [
        {
            "id": 0,
            "session_id": session_id,
            "turn_number": 0,
            "kind": "native_aggregate",
            "content": content,
            "source": "graph.kuzu:native_sum",
            "same_session": False,
            "overlap_count": 0,
            "semantic_score": 0.0,
            "created_at": "",
            "metadata": {
                "aggregate_kind": plan["aggregate_kind"],
                "entity_type": plan["entity_type"],
                "metric_attribute": plan["metric_attribute"],
                "owner_subject": plan["owner_subject"],
                "count": count,
                "total": total,
                "unit": unit,
                "supporting_entities": unique_names,
            },
        }
    ]


def _fact_transcript_row_priority(row: Dict[str, Any]) -> tuple[Any, ...]:
    content = _normalize_text(row.get("content") or row.get("content_excerpt"))
    token_count = len(tokenize_match_text(content))
    overlap = int(row.get("overlap_count") or 0)
    retrieval_source = str(row.get("retrieval_source") or "")
    match_mode = str(row.get("match_mode") or "")
    density = float(overlap) / float(token_count or 1)
    return (
        1 if overlap > 0 else 0,
        overlap,
        1 if match_mode == "keyword" or "keyword" in retrieval_source else 0,
        density,
        1 if _looks_user_led(content) else 0,
        1 if bool(row.get("same_session")) else 0,
        float(row.get("semantic_score") or 0.0),
        -token_count,
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
    return (
        candidate.rrf_score + bonus,
        bonus,
        len(candidate.channel_ranks),
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
    graph_limit: int,
    corpus_limit: int,
) -> Dict[str, int]:
    limits = {
        "profile_limit": profile_limit,
        "continuity_match_limit": continuity_match_limit,
        "continuity_recent_limit": continuity_recent_limit,
        "transcript_limit": transcript_limit,
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
    return True


def _keep_low_overlap_temporal_transcript_rows(selected: Dict[str, List[Dict[str, Any]]]) -> bool:
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
    annotated: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        payload["_brainstack_query_has_digits"] = query_has_digits
        annotated.append(payload)
    return annotated


def _profile_keyword_rows(rows: List[Dict[str, Any]], *, limit: int) -> List[Dict[str, Any]]:
    ranked = list(enumerate(rows))
    ranked.sort(
        key=lambda item: (
            profile_priority_adjustment(item[1]),
            float(item[1].get("confidence") or 0.0),
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
            item[1].get("overlap_count") or 0,
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
            int(item[1].get("overlap_count") or 0),
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
        "graph": 4,
        "continuity_match": 3,
        "continuity_recent": 2,
        "transcript": 1,
        "corpus": 0,
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
        candidate.rrf_score += 1.0 / (RRF_K + rank)


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
    graph_limit: int,
    corpus_limit: int,
) -> Dict[str, List[Dict[str, Any]]]:
    profile_items: List[Dict[str, Any]] = []
    matched: List[Dict[str, Any]] = []
    recent: List[Dict[str, Any]] = []
    transcript_rows: List[Dict[str, Any]] = []
    graph_rows: List[Dict[str, Any]] = []
    corpus_rows: List[Dict[str, Any]] = []

    seen_profile_keys: set[str] = set()
    seen_continuity_ids: set[int] = set()
    seen_transcript_ids: set[int] = set()
    seen_graph_keys: set[tuple[str, int]] = set()
    seen_corpus_keys: set[tuple[int, int]] = set()

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

        if candidate.shelf == "continuity_match" and len(matched) < continuity_match_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_continuity_ids:
                seen_continuity_ids.add(row_id)
                matched.append(row)
            continue

        if candidate.shelf == "continuity_recent" and len(recent) < continuity_recent_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_continuity_ids:
                seen_continuity_ids.add(row_id)
                recent.append(row)
            continue

        if candidate.shelf == "transcript" and len(transcript_rows) < transcript_limit:
            row_id = int(row.get("id") or 0)
            if row_id > 0 and row_id not in seen_transcript_ids:
                seen_transcript_ids.add(row_id)
                transcript_rows.append(row)
            continue

        if candidate.shelf == "graph" and len(graph_rows) < graph_limit:
            row_key = (str(row.get("row_type") or ""), int(row.get("row_id") or 0))
            if row_key[1] > 0 and row_key not in seen_graph_keys:
                seen_graph_keys.add(row_key)
                graph_rows.append(row)
            continue

        if candidate.shelf == "corpus" and len(corpus_rows) < corpus_limit:
            corpus_row_key = (int(row.get("document_id") or 0), int(row.get("section_index") or 0))
            if corpus_row_key[0] > 0 and corpus_row_key not in seen_corpus_keys:
                seen_corpus_keys.add(corpus_row_key)
                corpus_rows.append(row)
            continue

    return {
        "profile_items": profile_items,
        "matched": matched,
        "recent": recent,
        "transcript_rows": transcript_rows,
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
) -> Dict[str, Any]:
    profile_limit = max(int(policy.get("profile_limit", 0)), 0)
    continuity_match_limit = max(int(policy.get("continuity_match_limit", 0)), 0)
    continuity_recent_limit = max(int(policy.get("continuity_recent_limit", 0)), 0)
    transcript_limit = max(int(policy.get("transcript_limit", 0)), 0)
    graph_limit = max(int(policy.get("graph_limit", 0)), 0)
    corpus_limit = max(int(policy.get("corpus_limit", 0)), 0)
    route = _resolve_route(query, route_resolver=route_resolver)
    limits = _route_limits(
        route=route,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
    )
    search_queries = [_normalize_text(query)]
    profile_limit = limits["profile_limit"]
    continuity_match_limit = limits["continuity_match_limit"]
    continuity_recent_limit = limits["continuity_recent_limit"]
    transcript_limit = limits["transcript_limit"]
    graph_limit = limits["graph_limit"]
    corpus_limit = limits["corpus_limit"]

    keyword_profile_rows = (
        _profile_keyword_rows(
            store.search_profile(
                query=query,
                limit=max(profile_limit * 4, 8),
                principal_scope_key=principal_scope_key,
            ),
            limit=max(profile_limit * 2, 6),
        )
        if profile_limit > 0
        else []
    )
    keyword_profile_rows = _annotate_query_flags(keyword_profile_rows, query=query)
    keyword_continuity_rows = (
        _collect_query_rows(
            shelf="continuity_match",
            queries=search_queries,
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
            queries=search_queries,
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
            queries=search_queries,
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
    keyword_rows = _round_robin(
        keyword_profile_rows,
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
    temporal_graph_rows = []
    if graph_limit > 0 and (
        route.applied_mode == ROUTE_TEMPORAL
        or bool(analysis.get("temporal"))
        or bool(analysis.get("preference"))
    ):
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
    if transcript_limit > 0 and (
        route.applied_mode == ROUTE_TEMPORAL or bool(analysis.get("temporal"))
    ):
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
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
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
    if transcript_rows and not has_meaningful_transcript_evidence(query, transcript_rows):
        if route.applied_mode == ROUTE_TEMPORAL and _keep_low_overlap_temporal_transcript_rows(selected):
            pass
        else:
            selected["transcript_rows"] = []
    if route.applied_mode != ROUTE_FACT and not _route_has_support(route, selected):
        route.fallback_used = True
        route.applied_mode = ROUTE_FACT
        selected = fact_selected

    semantic_status = store.corpus_semantic_channel_status()
    channels = [
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

    return {
        **selected,
        "channels": channels,
        "fused_candidates": [
            {
                "key": candidate.key,
                "shelf": candidate.shelf,
                "rrf_score": candidate.rrf_score,
                "priority_bonus": _candidate_priority_bonus(candidate),
                "channel_ranks": dict(candidate.channel_ranks),
                "id": int(candidate.row.get("id") or 0),
                "row_id": int(candidate.row.get("row_id") or 0),
                "turn_number": int(candidate.row.get("turn_number") or 0),
                "document_id": int(candidate.row.get("document_id") or 0),
                "section_index": int(candidate.row.get("section_index") or 0),
                "created_at": str(candidate.row.get("created_at") or ""),
                "overlap_count": int(candidate.row.get("overlap_count") or 0),
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
        "routing": asdict(route),
    }
