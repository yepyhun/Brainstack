from __future__ import annotations

from typing import Any, Iterable, Mapping


ENTITY_RESOLUTION_SCHEMA = "brainstack.entity_resolution.v1"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _candidate_key(candidate: Mapping[str, Any]) -> tuple[int, str, str]:
    return (
        int(candidate.get("canonical_id") or 0),
        str(candidate.get("canonical_name") or ""),
        str(candidate.get("source_channel") or ""),
    )


def _dedupe_candidates(candidates: Iterable[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            float(item.get("confidence") or 0.0),
            1 if str(item.get("source_channel") or "") == "explicit_alias" else 0,
            str(item.get("canonical_name") or ""),
        ),
        reverse=True,
    ):
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
        if len(output) >= limit:
            break
    return output


def resolve_entity_candidates(
    store: Any,
    *,
    query: str,
    principal_scope_key: str = "",
    limit: int = 4,
) -> dict[str, Any]:
    """Return traceable entity candidates without mutating durable identity truth."""
    normalized_query = _normalize_text(query)
    if not normalized_query:
        return {
            "schema": ENTITY_RESOLUTION_SCHEMA,
            "status": "idle",
            "query": "",
            "candidates": [],
            "no_merge_reasons": ["empty_query"],
        }

    candidates: list[dict[str, Any]] = []
    exact_rows = store.conn.execute(
        """
        SELECT id, canonical_name, normalized_name, '' AS matched_alias
        FROM graph_entities
        WHERE normalized_name = ?
           OR instr(?, normalized_name) > 0
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_query, normalized_query, max(limit * 2, 8)),
    ).fetchall()
    for row in exact_rows:
        candidates.append(
            {
                "canonical_id": int(row["id"]),
                "canonical_name": str(row["canonical_name"] or ""),
                "matched_alias": "",
                "source_channel": "canonical_lexical",
                "confidence": 0.74,
                "merge_eligible": False,
                "reason": "canonical_entity_name_matched_query",
            }
        )

    alias_rows = store.conn.execute(
        """
        SELECT ge.id, ge.canonical_name, ga.alias_name
        FROM graph_entity_aliases ga
        JOIN graph_entities ge ON ge.id = ga.target_entity_id
        WHERE ga.normalized_alias = ?
           OR instr(?, ga.normalized_alias) > 0
        ORDER BY ga.updated_at DESC, ga.id DESC
        LIMIT ?
        """,
        (normalized_query, normalized_query, max(limit * 2, 8)),
    ).fetchall()
    for row in alias_rows:
        candidates.append(
            {
                "canonical_id": int(row["id"]),
                "canonical_name": str(row["canonical_name"] or ""),
                "matched_alias": str(row["alias_name"] or ""),
                "source_channel": "explicit_alias",
                "confidence": 0.96,
                "merge_eligible": False,
                "reason": "explicit_alias_points_to_canonical_entity",
            }
        )

    if not candidates:
        for row in store.search_semantic_evidence(
            query=query,
            principal_scope_key=principal_scope_key,
            shelves=("graph",),
            limit=max(limit * 2, 8),
        ):
            canonical_name = str(row.get("subject") or "").strip()
            if not canonical_name:
                continue
            candidates.append(
                {
                    "canonical_id": 0,
                    "canonical_name": canonical_name,
                    "matched_alias": "",
                    "source_channel": "semantic_evidence",
                    "confidence": float(row.get("semantic_score") or 0.0),
                    "merge_eligible": False,
                    "reason": "semantic_graph_evidence_candidate_read_only",
                    "evidence_key": str(row.get("semantic_evidence_key") or ""),
                    "row_type": str(row.get("row_type") or ""),
                    "row_id": int(row.get("row_id") or 0),
                }
            )

    selected = _dedupe_candidates(candidates, limit=max(int(limit or 0), 1))
    no_merge_reasons = ["resolver_candidates_are_read_only"]
    if not selected:
        no_merge_reasons.append("no_exact_alias_or_semantic_candidate")
    return {
        "schema": ENTITY_RESOLUTION_SCHEMA,
        "status": "active" if selected else "no_match",
        "query": str(query or ""),
        "principal_scope_key": str(principal_scope_key or ""),
        "candidates": selected,
        "no_merge_reasons": no_merge_reasons,
    }


def annotate_graph_rows_with_entity_resolution(
    rows: Iterable[dict[str, Any]],
    entity_resolution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates = [
        dict(candidate)
        for candidate in entity_resolution.get("candidates", [])
        if isinstance(candidate, Mapping)
    ]
    by_name: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        canonical_name = str(candidate.get("canonical_name") or "")
        if canonical_name and canonical_name not in by_name:
            by_name[canonical_name] = candidate
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        candidate_match = by_name.get(str(item.get("subject") or ""))
        if candidate_match:
            item["entity_resolution_source"] = str(candidate_match.get("source_channel") or "")
            item["entity_resolution_reason"] = str(candidate_match.get("reason") or "")
            item["entity_resolution_confidence"] = float(candidate_match.get("confidence") or 0.0)
            item["entity_resolution_merge_eligible"] = bool(candidate_match.get("merge_eligible"))
        output.append(item)
    return output


def filter_graph_rows_to_entity_resolution_candidates(
    rows: Iterable[dict[str, Any]],
    entity_resolution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates = [
        dict(candidate)
        for candidate in entity_resolution.get("candidates", [])
        if isinstance(candidate, Mapping)
    ]
    candidate_names = {
        str(candidate.get("canonical_name") or "")
        for candidate in candidates
        if str(candidate.get("canonical_name") or "").strip()
    }
    if not candidate_names:
        return [dict(row) for row in rows]
    return [dict(row) for row in rows if str(row.get("subject") or "") in candidate_names]
