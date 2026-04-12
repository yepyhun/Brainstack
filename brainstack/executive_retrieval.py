from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List

from .db import BrainstackStore
from .transcript import has_meaningful_transcript_evidence
from .usefulness import graph_priority_adjustment, profile_priority_adjustment

RRF_K = 60


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


def _round_robin(*groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    max_len = max((len(group) for group in groups), default=0)
    for index in range(max_len):
        for group in groups:
            if index < len(group):
                output.append(group[index])
    return output


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
) -> Dict[str, Any]:
    profile_limit = max(int(policy.get("profile_limit", 0)), 0)
    continuity_match_limit = max(int(policy.get("continuity_match_limit", 0)), 0)
    continuity_recent_limit = max(int(policy.get("continuity_recent_limit", 0)), 0)
    transcript_limit = max(int(policy.get("transcript_limit", 0)), 0)
    graph_limit = max(int(policy.get("graph_limit", 0)), 0)
    corpus_limit = max(int(policy.get("corpus_limit", 0)), 0)

    keyword_profile_rows = (
        _profile_keyword_rows(
            store.search_profile(query=query, limit=max(profile_limit * 4, 8)),
            limit=max(profile_limit * 2, 6),
        )
        if profile_limit > 0
        else []
    )
    keyword_continuity_rows = (
        store.search_continuity(query=query, session_id=session_id, limit=max(continuity_match_limit * 4, 8))
        if continuity_match_limit > 0
        else []
    )
    keyword_transcript_rows = (
        store.search_transcript(query=query, session_id=session_id, limit=max(transcript_limit * 4, 6))
        if transcript_limit > 0
        else []
    )
    keyword_corpus_rows = (
        store.search_corpus(query=query, limit=max(corpus_limit * 4, 8))
        if corpus_limit > 0
        else []
    )
    semantic_conversation_rows = (
        store.search_conversation_semantic(query=query, session_id=session_id, limit=max(transcript_limit * 4, 8))
        if transcript_limit > 0
        else []
    )
    semantic_corpus_rows = (
        store.search_corpus_semantic(query=query, limit=max(corpus_limit * 4, 8))
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
            store.search_graph(query=query, limit=max(graph_limit * 4, 12)),
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
            store.search_graph(query=query, limit=max(graph_limit * 6, 12)),
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
            candidate.rrf_score,
            len(candidate.channel_ranks),
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
                "channel_ranks": dict(candidate.channel_ranks),
            }
            for candidate in fused
        ],
    }
