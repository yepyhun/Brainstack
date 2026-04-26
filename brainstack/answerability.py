from __future__ import annotations

from typing import Any, Mapping, Sequence

from .authority_policy import (
    CLAIM_MEMORY_TRUTH,
    CLAIM_NONE,
    REASON_CONFLICTING_TRUTH,
    REASON_HOST_MIRROR_DIVERGED,
    REASON_NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE,
    REASON_NO_CANDIDATES,
    REASON_ONLY_SUPPORTING_CONTEXT,
    REASON_PACKET_SUPPRESSED,
    REASON_PENDING_WRITE_BARRIER,
    classify_evidence_authority,
    infer_query_intent,
)


ANSWERABILITY_SCHEMA = "brainstack.memory_answerability.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _item_packet_text(item: Mapping[str, Any]) -> str:
    for key in ("excerpt", "content", "object_value", "value_text", "subject", "stable_key", "evidence_key"):
        value = _text(item.get(key))
        if value:
            return value
    return ""


def _visible_in_packet(item: Mapping[str, Any], packet_text: str) -> bool:
    if not packet_text:
        return False
    normalized_packet = packet_text.casefold()
    for value in (_item_packet_text(item), _text(item.get("stable_key")), _text(item.get("evidence_key"))):
        if len(value) >= 12 and value.casefold()[:80] in normalized_packet:
            return True
    return False


def _flatten_selected(selected_by_shelf: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for shelf, raw_rows in selected_by_shelf.items():
        for row in raw_rows or []:
            if isinstance(row, Mapping):
                rows.append({**dict(row), "shelf": _text(row.get("shelf")) or str(shelf)})
    return rows


def _evidence_ids(items: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("evidence_key")) for item in items if str(item.get("evidence_key") or "")]


def _must_not_claim(items: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(claim)
            for item in items
            for claim in item.get("must_not_claim", [])
            if str(claim)
        }
    )


def _classified_groups(classified: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    return {
        "conflicts": [item for item in classified if item.get("reason_code") == REASON_CONFLICTING_TRUTH],
        "degraded": [
            item
            for item in classified
            if item.get("reason_code") in {REASON_PENDING_WRITE_BARRIER, REASON_HOST_MIRROR_DIVERGED}
        ],
        "answer": [item for item in classified if item.get("answer_authority")],
        "supporting": [item for item in classified if item.get("supporting_only") and item.get("evidence_key")],
        "excluded": [
            item
            for item in classified
            if not item.get("answer_authority") and not item.get("supporting_only") and item.get("evidence_key")
        ],
    }


def _base_answerability(
    *,
    state: str,
    can_answer: bool,
    max_claim_strength: str,
    answer_type: str,
    authority: str,
    reason: str,
    reason_code: str,
    answer_evidence_ids: Sequence[str] = (),
    supporting_context_ids: Sequence[str] = (),
    excluded_evidence_ids: Sequence[str] = (),
    must_not_claim: Sequence[str] = (),
    can_claim_current_assignment: bool = False,
) -> dict[str, Any]:
    return {
        "schema": ANSWERABILITY_SCHEMA,
        "state": state,
        "can_answer": can_answer,
        "max_claim_strength": max_claim_strength,
        "answer_type": answer_type,
        "authority": authority,
        "can_claim_memory_truth": max_claim_strength == CLAIM_MEMORY_TRUTH,
        "can_claim_current_assignment": can_claim_current_assignment,
        "reason": reason,
        "reason_code": reason_code,
        "answer_evidence_ids": list(answer_evidence_ids),
        "supporting_context_ids": list(supporting_context_ids),
        "excluded_evidence_ids": list(excluded_evidence_ids),
        "must_not_claim": list(must_not_claim),
    }


def _packet_suppressed_answerability(
    *, supporting: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return _base_answerability(
        state="unanswerable",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="none",
        authority="none",
        reason="authoritative evidence missing from final packet",
        reason_code=REASON_PACKET_SUPPRESSED,
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids(excluded),
        must_not_claim=["memory_truth", "current_assignment"],
    )


def _degraded_answerability(
    *,
    degraded: Sequence[Mapping[str, Any]],
    supporting: Sequence[Mapping[str, Any]],
    excluded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    strongest = degraded[0]
    reason_code = str(strongest.get("reason_code") or REASON_HOST_MIRROR_DIVERGED)
    return _base_answerability(
        state="degraded" if reason_code == REASON_PENDING_WRITE_BARRIER else "conflicted",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="none",
        authority="none",
        reason="explicit truth projection is pending or diverged",
        reason_code=reason_code,
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids([*degraded, *excluded]),
        must_not_claim=["single_current_truth", "memory_truth"],
    )


def _conflicted_answerability(
    *,
    conflicts: Sequence[Mapping[str, Any]],
    supporting: Sequence[Mapping[str, Any]],
    excluded: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return _base_answerability(
        state="conflicted",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="none",
        authority="none",
        reason="conflicting memory evidence selected",
        reason_code=REASON_CONFLICTING_TRUTH,
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids([*conflicts, *excluded]),
        must_not_claim=["single_current_truth", "memory_truth"],
    )


def _answerable_contract(
    *, answer: Sequence[Mapping[str, Any]], supporting: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    strongest = answer[0]
    max_claim = str(strongest.get("max_claim_strength") or CLAIM_NONE)
    return _base_answerability(
        state="answerable",
        can_answer=True,
        max_claim_strength=max_claim,
        answer_type=str(strongest.get("answer_type") or "none"),
        authority=str(strongest.get("authority") or "none"),
        reason="selected memory evidence supports a bounded answer",
        reason_code=str(strongest.get("reason_code") or "SELECTED_MEMORY_EVIDENCE"),
        answer_evidence_ids=_evidence_ids(answer),
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids(excluded),
        must_not_claim=_must_not_claim(answer),
        can_claim_current_assignment=any(bool(item.get("current_assignment_authority")) for item in answer),
    )


def _current_assignment_absence_answerability(
    *, supporting: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return _base_answerability(
        state="unanswerable",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="current_assignment_absence",
        authority="none",
        reason="no typed current-assignment evidence was selected",
        reason_code=REASON_NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE,
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids(excluded),
        must_not_claim=["memory_truth", "current_assignment", "lifetime_certainty"],
    )


def _supporting_only_answerability(
    *, supporting: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    return _base_answerability(
        state="unanswerable",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="none",
        authority="none",
        reason="only supporting context was selected",
        reason_code=REASON_ONLY_SUPPORTING_CONTEXT,
        supporting_context_ids=_evidence_ids(supporting),
        excluded_evidence_ids=_evidence_ids(excluded),
        must_not_claim=["memory_truth", "current_assignment"],
    )


def _no_candidates_answerability(*, excluded: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return _base_answerability(
        state="unanswerable",
        can_answer=False,
        max_claim_strength=CLAIM_NONE,
        answer_type="none",
        authority="none",
        reason="no supported memory truth selected",
        reason_code=REASON_NO_CANDIDATES,
        excluded_evidence_ids=_evidence_ids(excluded),
        must_not_claim=["memory_truth", "current_assignment"],
    )


def _packet_visible_answers(
    *,
    answer: Sequence[Mapping[str, Any]],
    by_key: Mapping[str, Mapping[str, Any]],
    packet_text: str | None,
) -> list[Mapping[str, Any]] | None:
    if packet_text is None or not answer:
        return None
    return [
        item
        for item in answer
        if _visible_in_packet(by_key.get(str(item.get("evidence_key") or ""), {}), packet_text)
    ]


def build_memory_answerability(
    *,
    query: str,
    analysis: Mapping[str, Any] | None,
    selected_by_shelf: Mapping[str, Sequence[Mapping[str, Any]]],
    packet_text: str | None = None,
) -> dict[str, Any]:
    query_intent = infer_query_intent(query=query, analysis=analysis)
    rows = _flatten_selected(selected_by_shelf)
    classified = [classify_evidence_authority(row, query_intent=query_intent) for row in rows]
    by_key = {
        str(item.get("evidence_key") or ""): item
        for item in rows
        if str(item.get("evidence_key") or "")
    }
    groups = _classified_groups(classified)
    conflicts = groups["conflicts"]
    degraded = groups["degraded"]
    answer = groups["answer"]
    supporting = groups["supporting"]
    excluded = groups["excluded"]

    visible_answer = _packet_visible_answers(answer=answer, by_key=by_key, packet_text=packet_text)
    if visible_answer is not None:
        if not visible_answer:
            return _packet_suppressed_answerability(supporting=supporting, excluded=excluded)
        answer = visible_answer

    if degraded:
        return _degraded_answerability(degraded=degraded, supporting=supporting, excluded=excluded)
    if conflicts:
        return _conflicted_answerability(conflicts=conflicts, supporting=supporting, excluded=excluded)
    if answer:
        return _answerable_contract(answer=answer, supporting=supporting, excluded=excluded)
    if query_intent == "current_assignment":
        return _current_assignment_absence_answerability(supporting=supporting, excluded=excluded)
    if supporting:
        return _supporting_only_answerability(supporting=supporting, excluded=excluded)
    return _no_candidates_answerability(excluded=excluded)
