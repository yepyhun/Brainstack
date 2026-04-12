from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List

from .db import BrainstackStore
from .tier2_extractor import _default_llm_caller, _extract_json_object, _extract_text_content
from .transcript import has_meaningful_transcript_evidence, tokenize_match_text
from .usefulness import graph_priority_adjustment, profile_priority_adjustment

RRF_K = 60
MAX_DECOMPOSED_SUBQUERIES = 3
DECOMPOSITION_MIN_TOKENS = 6
DECOMPOSITION_MIN_CHARS = 32

logger = logging.getLogger(__name__)


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

    if candidate.shelf == "transcript":
        bonus += 0.08
        if _looks_user_led(text):
            bonus += 0.06
    elif candidate.shelf == "continuity_match":
        bonus += 0.02
    elif candidate.shelf == "continuity_recent":
        bonus += 0.01

    if any(char.isdigit() for char in text):
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


def _should_attempt_query_decomposition(query: str) -> bool:
    normalized = _normalize_text(query)
    if len(normalized) < DECOMPOSITION_MIN_CHARS:
        return False
    tokens = tokenize_match_text(normalized)
    if len(tokens) < DECOMPOSITION_MIN_TOKENS:
        return False
    structural_markers = sum(1 for marker in ("?", ",", ":", ";", "\"") if marker in normalized)
    return structural_markers > 0


def _default_query_decomposer(query: str) -> List[str]:
    messages = [
        {
            "role": "system",
            "content": (
                "You help Brainstack decompose a user query into at most three short, searchable sub-queries.\n"
                "Return JSON only with the schema {\"sub_queries\": [\"...\", \"...\"]}.\n"
                "If decomposition would not materially improve retrieval, return {\"sub_queries\": []}.\n"
                "Keep wording close to the user's language and concrete named events or entities."
            ),
        },
        {
            "role": "user",
            "content": query,
        },
    ]
    response = _default_llm_caller(
        task="memory_prefetch_decomposition",
        messages=messages,
        timeout=6.0,
        max_tokens=180,
    )
    payload = _extract_json_object(_extract_text_content(response))
    items = payload.get("sub_queries")
    if not isinstance(items, list):
        return []
    return [_normalize_text(item) for item in items if _normalize_text(item)]


def _resolve_search_queries(
    query: str,
    *,
    query_decomposer: Callable[[str], List[str]] | None,
) -> List[str]:
    normalized = _normalize_text(query)
    if not normalized or not _should_attempt_query_decomposition(normalized):
        return [normalized]

    decomposer = query_decomposer or _default_query_decomposer
    try:
        proposed = decomposer(normalized)
    except Exception as exc:
        logger.warning("Brainstack query decomposition failed: %s", exc)
        return [normalized]

    output: List[str] = []
    seen: set[str] = set()
    for item in proposed[:MAX_DECOMPOSED_SUBQUERIES]:
        text = _normalize_text(item)
        if not text:
            continue
        lowered = text.lower()
        if lowered == normalized.lower() or lowered in seen:
            continue
        seen.add(lowered)
        output.append(text)
    return output if len(output) >= 2 else [normalized]


def _round_robin(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index < len(group):
                output.append(group[index])
    return output


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
            row_key = (int(row.get("document_id") or 0), int(row.get("section_index") or 0))
            if row_key[0] > 0 and row_key not in seen_corpus_keys:
                seen_corpus_keys.add(row_key)
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
    analysis: Dict[str, Any],
    policy: Dict[str, Any],
    query_decomposer: Callable[[str], List[str]] | None = None,
) -> Dict[str, Any]:
    profile_limit = max(int(policy.get("profile_limit", 0)), 0)
    continuity_match_limit = max(int(policy.get("continuity_match_limit", 0)), 0)
    continuity_recent_limit = max(int(policy.get("continuity_recent_limit", 0)), 0)
    transcript_limit = max(int(policy.get("transcript_limit", 0)), 0)
    graph_limit = max(int(policy.get("graph_limit", 0)), 0)
    corpus_limit = max(int(policy.get("corpus_limit", 0)), 0)
    search_queries = _resolve_search_queries(query, query_decomposer=query_decomposer)
    if len(search_queries) > 1:
        continuity_match_limit = max(continuity_match_limit, min(len(search_queries), MAX_DECOMPOSED_SUBQUERIES))
        transcript_limit = max(transcript_limit, min(len(search_queries), MAX_DECOMPOSED_SUBQUERIES))

    keyword_profile_rows = (
        _profile_keyword_rows(
            store.search_profile(query=query, limit=max(profile_limit * 4, 8)),
            limit=max(profile_limit * 2, 6),
        )
        if profile_limit > 0
        else []
    )
    keyword_continuity_rows = (
        _collect_query_rows(
            shelf="continuity_match",
            queries=search_queries,
            searcher=lambda variant: store.search_continuity(
                query=variant,
                session_id=session_id,
                limit=max(continuity_match_limit * 4, 8),
            ),
        )
        if continuity_match_limit > 0
        else []
    )
    keyword_transcript_rows = (
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
    semantic_conversation_rows = (
        _collect_query_rows(
            shelf="transcript",
            queries=search_queries,
            searcher=lambda variant: store.search_conversation_semantic(
                query=variant,
                session_id=session_id,
                limit=max(transcript_limit * 4, 8),
            ),
        )
        if transcript_limit > 0
        else []
    )
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
                ),
            ),
            limit=max(graph_limit * 3, 8),
        )
        if graph_limit > 0
        else []
    )

    recent_rows = (
        store.recent_continuity(session_id=session_id, limit=max(continuity_recent_limit * 4, 6))
        if continuity_recent_limit > 0
        else []
    )
    temporal_graph_rows = []
    if graph_limit > 0 and (bool(analysis.get("temporal")) or bool(analysis.get("preference"))):
        temporal_graph_rows = _temporal_graph_rows(
            _collect_query_rows(
                shelf="graph",
                queries=search_queries,
                searcher=lambda variant: store.search_graph(
                    query=variant,
                    limit=max(graph_limit * 6, 12),
                ),
            ),
            limit=max(graph_limit * 2, 6),
        )

    temporal_rows = _round_robin(recent_rows, temporal_graph_rows)
    graph_status = store.graph_backend_channel_status()

    merged: Dict[str, EvidenceCandidate] = {}
    _merge_channel(merged, channel_name="keyword", rows=keyword_profile_rows, shelf="profile")
    _merge_channel(merged, channel_name="keyword", rows=keyword_continuity_rows, shelf="continuity_match")
    _merge_channel(merged, channel_name="keyword", rows=keyword_transcript_rows, shelf="transcript")
    _merge_channel(merged, channel_name="keyword", rows=keyword_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="semantic", rows=semantic_conversation_rows, shelf="transcript")
    _merge_channel(merged, channel_name="semantic", rows=semantic_corpus_rows, shelf="corpus")
    _merge_channel(merged, channel_name="graph", rows=graph_rows, shelf="graph")
    _merge_channel(merged, channel_name="temporal", rows=recent_rows, shelf="continuity_recent")
    _merge_channel(merged, channel_name="temporal", rows=temporal_graph_rows, shelf="graph")

    fused = sorted(
        merged.values(),
        key=lambda candidate: (
            candidate.rrf_score + _candidate_priority_bonus(candidate),
            _candidate_priority_bonus(candidate),
            len(candidate.channel_ranks),
            1 if candidate.shelf == "transcript" else 0,
            1 if candidate.shelf == "graph" else 0,
            1 if candidate.shelf == "profile" else 0,
        ),
        reverse=True,
    )

    selected = _select_rows(
        fused,
        profile_limit=profile_limit,
        continuity_match_limit=continuity_match_limit,
        continuity_recent_limit=continuity_recent_limit,
        transcript_limit=transcript_limit,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
    )

    transcript_rows = selected["transcript_rows"]
    if transcript_rows and not has_meaningful_transcript_evidence(query, transcript_rows):
        selected["transcript_rows"] = []

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
            }
            for candidate in fused
        ],
        "decomposition": {
            "used": len(search_queries) > 1,
            "queries": list(search_queries),
        },
    }
