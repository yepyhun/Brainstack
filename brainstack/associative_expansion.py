from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from time import perf_counter
import re
from typing import Any


ASSOCIATIVE_EXPANSION_SCHEMA_VERSION = "brainstack.associative_expansion.v1"
ASSOCIATIVE_EXPANSION_MODE = "bounded_graph_activation.v1"
TOKEN_RE = re.compile(r"[^\W_]+(?:[-_][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True)
class AssociativeExpansionBounds:
    max_seed_count: int = 4
    max_depth: int = 1
    max_candidate_count: int = 8
    max_search_count: int = 16
    allowed_shelves: tuple[str, ...] = ("graph",)


def graph_evidence_key(row: Mapping[str, Any]) -> str:
    return f"graph:{row.get('row_type')}:{int(row.get('row_id') or 0)}"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _token_set(value: Any) -> set[str]:
    return {
        token
        for token in TOKEN_RE.findall(str(value or "").casefold())
        if len(token) >= 2
    }


def _metadata_text(metadata: Mapping[str, Any] | None) -> str:
    if not isinstance(metadata, Mapping):
        return ""
    parts: list[str] = []
    raw_terms = metadata.get("semantic_terms")
    if isinstance(raw_terms, str):
        parts.append(raw_terms)
    elif isinstance(raw_terms, (list, tuple, set)):
        parts.extend(str(value or "") for value in raw_terms if isinstance(value, (str, int, float)))
    for key in ("context_id", "source_id", "authority_class", "provenance_class"):
        if metadata.get(key):
            parts.append(str(metadata.get(key)))
    return " ".join(part for part in parts if part)


def _graph_text(row: Mapping[str, Any]) -> str:
    parts = [
        row.get("subject"),
        row.get("predicate"),
        row.get("object_value"),
        row.get("conflict_value"),
        _metadata_text(row.get("metadata") if isinstance(row.get("metadata"), Mapping) else None),
    ]
    return " ".join(_normalize_text(part) for part in parts if _normalize_text(part))


def _anchor_values(row: Mapping[str, Any], *, limit: int = 4) -> list[str]:
    anchors: list[str] = []
    for key in ("subject", "object_value"):
        value = _normalize_text(row.get(key))
        if len(value) < 2 or value in anchors:
            continue
        anchors.append(value)
        if len(anchors) >= limit:
            break
    return anchors


def _candidate_score(
    row: Mapping[str, Any],
    *,
    query_terms: set[str],
    depth: int,
) -> tuple[bool, float, str, int]:
    candidate_terms = _token_set(_graph_text(row))
    overlap = len(query_terms & candidate_terms)
    if overlap < 1:
        return False, 0.0, "insufficient_query_relevance", overlap
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    authority_bonus = 0.18 if str((metadata or {}).get("authority_class") or "").strip() == "graph" else 0.0
    current_bonus = 0.22 if bool(row.get("is_current")) else 0.0
    depth_penalty = max(int(depth) - 1, 0) * 0.2
    score = float(overlap) + authority_bonus + current_bonus - depth_penalty
    return True, round(score, 6), "query_overlap", overlap


def _candidate_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_key": graph_evidence_key(row),
        "row_type": str(row.get("row_type") or ""),
        "subject": str(row.get("subject") or ""),
        "predicate": str(row.get("predicate") or ""),
        "object_value": str(row.get("object_value") or ""),
        "source": str(row.get("source") or ""),
    }


def build_associative_expansion(
    store: Any,
    *,
    query: str,
    principal_scope_key: str,
    seed_rows: Iterable[Mapping[str, Any]],
    bounds: AssociativeExpansionBounds | None = None,
) -> dict[str, Any]:
    active_bounds = bounds or AssociativeExpansionBounds()
    started = perf_counter()
    query_terms = _token_set(query)
    seeds = [dict(row) for row in seed_rows if str(row.get("row_type") or "").strip()]
    seeds = seeds[: max(int(active_bounds.max_seed_count), 0)]
    seed_keys = {graph_evidence_key(row) for row in seeds}
    seen_keys = set(seed_keys)
    included: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    hops: list[dict[str, Any]] = []
    search_count = 0

    if "graph" not in active_bounds.allowed_shelves:
        return {
            "schema": ASSOCIATIVE_EXPANSION_SCHEMA_VERSION,
            "mode": ASSOCIATIVE_EXPANSION_MODE,
            "status": "disabled",
            "reason": "graph shelf is not allowed for this expansion run",
            "bounds": asdict(active_bounds),
            "seeds": [],
            "hops": [],
            "included_candidates": [],
            "suppressed_candidates": [],
            "cost": {"elapsed_ms": 0, "search_count": 0},
        }
    if not query_terms:
        return {
            "schema": ASSOCIATIVE_EXPANSION_SCHEMA_VERSION,
            "mode": ASSOCIATIVE_EXPANSION_MODE,
            "status": "idle",
            "reason": "query has no searchable terms",
            "bounds": asdict(active_bounds),
            "seeds": [],
            "hops": [],
            "included_candidates": [],
            "suppressed_candidates": [],
            "cost": {"elapsed_ms": 0, "search_count": 0},
        }
    if not seeds:
        return {
            "schema": ASSOCIATIVE_EXPANSION_SCHEMA_VERSION,
            "mode": ASSOCIATIVE_EXPANSION_MODE,
            "status": "idle",
            "reason": "no graph seed rows available",
            "bounds": asdict(active_bounds),
            "seeds": [],
            "hops": [],
            "included_candidates": [],
            "suppressed_candidates": [],
            "cost": {"elapsed_ms": 0, "search_count": 0},
        }

    frontier = list(seeds)
    max_depth = max(int(active_bounds.max_depth), 0)
    max_candidates = max(int(active_bounds.max_candidate_count), 0)
    max_searches = max(int(active_bounds.max_search_count), 0)
    for depth in range(1, max_depth + 1):
        next_frontier: list[dict[str, Any]] = []
        for seed in frontier:
            if search_count >= max_searches or len(included) >= max_candidates:
                break
            seed_key = graph_evidence_key(seed)
            for anchor in _anchor_values(seed):
                if search_count >= max_searches or len(included) >= max_candidates:
                    break
                search_count += 1
                rows = [
                    dict(row)
                    for row in store.search_graph(
                        query=anchor,
                        principal_scope_key=principal_scope_key,
                        limit=max(max_candidates * 2, 8),
                    )
                ]
                hop = {
                    "depth": depth,
                    "seed_key": seed_key,
                    "anchor": anchor,
                    "candidate_count": len(rows),
                }
                hops.append(hop)
                for candidate in rows:
                    candidate_key = graph_evidence_key(candidate)
                    if candidate_key in seen_keys:
                        suppressed.append(
                            {
                                **_candidate_summary(candidate),
                                "seed_key": seed_key,
                                "anchor": anchor,
                                "depth": depth,
                                "reason": "duplicate_seed_or_candidate",
                            }
                        )
                        continue
                    accepted, score, reason, overlap = _candidate_score(
                        candidate,
                        query_terms=query_terms,
                        depth=depth,
                    )
                    if not accepted:
                        suppressed.append(
                            {
                                **_candidate_summary(candidate),
                                "seed_key": seed_key,
                                "anchor": anchor,
                                "depth": depth,
                                "reason": reason,
                                "query_token_overlap": overlap,
                            }
                        )
                        seen_keys.add(candidate_key)
                        continue
                    payload = dict(candidate)
                    payload["retrieval_source"] = "graph.associative_expansion"
                    payload["match_mode"] = "associative"
                    payload["associative_score"] = score
                    payload["associative_seed_key"] = seed_key
                    payload["associative_anchor"] = anchor
                    payload["associative_depth"] = depth
                    payload["associative_reason"] = reason
                    payload["keyword_score"] = max(float(payload.get("keyword_score") or 0.0), score)
                    included.append(payload)
                    next_frontier.append(payload)
                    seen_keys.add(candidate_key)
                    if len(included) >= max_candidates:
                        break
        frontier = next_frontier
        if not frontier or search_count >= max_searches or len(included) >= max_candidates:
            break

    included.sort(
        key=lambda row: (
            float(row.get("associative_score") or 0.0),
            str(row.get("happened_at") or ""),
            str(row.get("subject") or ""),
        ),
        reverse=True,
    )
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    status = "active" if included else "idle"
    reason = "bounded associative graph candidates found" if included else "no candidates passed bounded relevance controls"
    return {
        "schema": ASSOCIATIVE_EXPANSION_SCHEMA_VERSION,
        "mode": ASSOCIATIVE_EXPANSION_MODE,
        "status": status,
        "reason": reason,
        "bounds": asdict(active_bounds),
        "seeds": [
            {
                **_candidate_summary(row),
                "anchors": _anchor_values(row),
            }
            for row in seeds
        ],
        "hops": hops,
        "included_candidates": [
            {
                **_candidate_summary(row),
                "seed_key": str(row.get("associative_seed_key") or ""),
                "anchor": str(row.get("associative_anchor") or ""),
                "depth": int(row.get("associative_depth") or 0),
                "score": float(row.get("associative_score") or 0.0),
                "reason": str(row.get("associative_reason") or ""),
            }
            for row in included
        ],
        "suppressed_candidates": suppressed[: max(max_candidates * 2, 8)],
        "cost": {
            "elapsed_ms": elapsed_ms,
            "search_count": search_count,
            "seed_count": len(seeds),
            "included_count": len(included),
            "suppressed_count": len(suppressed),
        },
        "candidate_rows": included[:max_candidates],
    }
