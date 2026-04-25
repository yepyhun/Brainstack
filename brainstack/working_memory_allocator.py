from __future__ import annotations

from typing import Any, Mapping, Sequence


ALLOCATOR_SCHEMA = "brainstack.global_allocator_shadow.v1"

DEFAULT_MAX_OPERATION_COUNT = 160
MIN_CANDIDATE_BUDGET = 1

REASON_KEEP_AUTHORITY_FLOOR = "keep_authority_floor"
REASON_KEEP_SELECTED_BUDGET_SLOT = "keep_selected_budget_slot"
REASON_CUT_GLOBAL_CANDIDATE_BUDGET = "cut_global_candidate_budget"
REASON_CUT_LOWER_PRIORITY_SUPPRESSED = "cut_lower_priority_suppressed"
REASON_DISABLED = "allocator_disabled"

SHELF_PRIORITY: dict[str, int] = {
    "profile": 90,
    "operating": 85,
    "task": 82,
    "graph": 80,
    "continuity_match": 70,
    "continuity_recent": 65,
    "transcript": 55,
    "corpus": 50,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _selection(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("selection")
    return raw if isinstance(raw, Mapping) else {}


def _authority(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("authority")
    return raw if isinstance(raw, Mapping) else {}


def _score(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("score")
    return raw if isinstance(raw, Mapping) else {}


def _cost(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = candidate.get("cost")
    return raw if isinstance(raw, Mapping) else {}


def _is_authority_floor(candidate: Mapping[str, Any]) -> bool:
    authority = _authority(candidate)
    if bool(authority.get("floor_applied")):
        return True
    return _text(authority.get("level")) == "canonical"


def _priority_tuple(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    selection = _selection(candidate)
    score = _score(candidate)
    shelf = _text(candidate.get("shelf"))
    selected_rank = 1 if _text(selection.get("status")) == "selected" else 0
    return (
        1 if _is_authority_floor(candidate) else 0,
        selected_rank,
        SHELF_PRIORITY.get(shelf, 0),
        _number(score.get("rrf")),
        _number(score.get("semantic")),
        _number(score.get("keyword")),
        _integer(score.get("query_token_overlap")),
        _text(candidate.get("candidate_id")),
    )


def _candidate_summary(candidate: Mapping[str, Any], *, reason_code: str) -> dict[str, Any]:
    score = _score(candidate)
    cost = _cost(candidate)
    return {
        "candidate_id": _text(candidate.get("candidate_id")),
        "evidence_key": _text(candidate.get("evidence_key")),
        "shelf": _text(candidate.get("shelf")),
        "selection_status": _text(_selection(candidate).get("status")),
        "reason_code": reason_code,
        "authority_floor": _integer(_authority(candidate).get("floor")),
        "authority_floor_applied": _is_authority_floor(candidate),
        "rrf_score": _number(score.get("rrf")),
        "preview_token_estimate": _integer(cost.get("preview_token_estimate")),
    }


def _normalize_candidates(candidate_trace: Mapping[str, Any], *, max_operation_count: int) -> list[Mapping[str, Any]]:
    raw_selected = candidate_trace.get("selected")
    raw_suppressed = candidate_trace.get("suppressed")
    selected = list(raw_selected) if isinstance(raw_selected, Sequence) and not isinstance(raw_selected, (str, bytes)) else []
    suppressed = (
        list(raw_suppressed)
        if isinstance(raw_suppressed, Sequence) and not isinstance(raw_suppressed, (str, bytes))
        else []
    )
    candidates = [
        candidate
        for candidate in [*selected, *suppressed]
        if isinstance(candidate, Mapping) and _text(candidate.get("candidate_id"))
    ]
    return candidates[: max(0, int(max_operation_count))]


def build_global_allocator_shadow(
    candidate_trace: Mapping[str, Any],
    *,
    candidate_budget: int,
    enabled: bool = True,
    max_operation_count: int = DEFAULT_MAX_OPERATION_COUNT,
) -> dict[str, Any]:
    """Return deterministic allocation proposal without changing final packet assembly."""
    budget = max(MIN_CANDIDATE_BUDGET, int(candidate_budget or 0))
    if not enabled:
        return {
            "schema": ALLOCATOR_SCHEMA,
            "mode": "disabled",
            "candidate_budget": budget,
            "selected": [],
            "cut": [],
            "reason_codes": [REASON_DISABLED],
            "authority_floor_verdict": "not_evaluated",
        }

    candidates = _normalize_candidates(candidate_trace, max_operation_count=max_operation_count)
    selected_old = [candidate for candidate in candidates if _text(_selection(candidate).get("status")) == "selected"]
    authority_floor = [candidate for candidate in candidates if _is_authority_floor(candidate)]
    ordered = sorted(candidates, key=_priority_tuple, reverse=True)

    kept_ids: set[str] = set()
    kept: list[dict[str, Any]] = []
    cut: list[dict[str, Any]] = []

    for candidate in authority_floor:
        candidate_id = _text(candidate.get("candidate_id"))
        if candidate_id in kept_ids:
            continue
        kept_ids.add(candidate_id)
        kept.append(_candidate_summary(candidate, reason_code=REASON_KEEP_AUTHORITY_FLOOR))

    for candidate in ordered:
        candidate_id = _text(candidate.get("candidate_id"))
        if candidate_id in kept_ids:
            continue
        selected_status = _text(_selection(candidate).get("status")) == "selected"
        if len(kept) < budget and selected_status:
            kept_ids.add(candidate_id)
            kept.append(_candidate_summary(candidate, reason_code=REASON_KEEP_SELECTED_BUDGET_SLOT))
            continue
        reason = REASON_CUT_GLOBAL_CANDIDATE_BUDGET if selected_status else REASON_CUT_LOWER_PRIORITY_SUPPRESSED
        cut.append(_candidate_summary(candidate, reason_code=reason))

    old_token_estimate = sum(_integer(_cost(candidate).get("preview_token_estimate")) for candidate in selected_old)
    new_token_estimate = sum(row["preview_token_estimate"] for row in kept)
    authority_verdict = "pass"
    if len(authority_floor) > budget:
        authority_verdict = "over_budget_due_to_authority_floor"
    elif any(_text(candidate.get("candidate_id")) not in kept_ids for candidate in authority_floor):
        authority_verdict = "fail_authority_floor_cut"

    return {
        "schema": ALLOCATOR_SCHEMA,
        "mode": "shadow_read_only",
        "candidate_budget": budget,
        "max_operation_count": max(0, int(max_operation_count)),
        "operation_count": len(candidates),
        "old_selected_count": len(selected_old),
        "proposed_selected_count": len(kept),
        "cut_count": len(cut),
        "old_preview_token_estimate": old_token_estimate,
        "proposed_preview_token_estimate": new_token_estimate,
        "preview_token_delta": new_token_estimate - old_token_estimate,
        "authority_floor_verdict": authority_verdict,
        "reason_codes": [
            REASON_KEEP_AUTHORITY_FLOOR,
            REASON_KEEP_SELECTED_BUDGET_SLOT,
            REASON_CUT_GLOBAL_CANDIDATE_BUDGET,
            REASON_CUT_LOWER_PRIORITY_SUPPRESSED,
        ],
        "selected": kept,
        "cut": cut,
    }
