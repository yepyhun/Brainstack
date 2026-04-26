from __future__ import annotations

from typing import Any, Mapping, Sequence

from .authority_policy import (
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
    conflicts = [item for item in classified if item.get("reason_code") == REASON_CONFLICTING_TRUTH]
    degraded = [
        item
        for item in classified
        if item.get("reason_code") in {REASON_PENDING_WRITE_BARRIER, REASON_HOST_MIRROR_DIVERGED}
    ]
    answer = [item for item in classified if item.get("answer_authority")]
    supporting = [item for item in classified if item.get("supporting_only") and item.get("evidence_key")]
    excluded = [
        item
        for item in classified
        if not item.get("answer_authority") and not item.get("supporting_only") and item.get("evidence_key")
    ]

    if packet_text is not None and answer:
        visible_answer = [
            item
            for item in answer
            if _visible_in_packet(by_key.get(str(item.get("evidence_key") or ""), {}), packet_text)
        ]
        if not visible_answer:
            return {
                "schema": ANSWERABILITY_SCHEMA,
                "state": "unanswerable",
                "can_answer": False,
                "max_claim_strength": CLAIM_NONE,
                "answer_type": "none",
                "authority": "none",
                "can_claim_memory_truth": False,
                "can_claim_current_assignment": False,
                "reason": "authoritative evidence missing from final packet",
                "reason_code": REASON_PACKET_SUPPRESSED,
                "answer_evidence_ids": [],
                "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
                "excluded_evidence_ids": [str(item.get("evidence_key")) for item in excluded],
                "must_not_claim": ["memory_truth", "current_assignment"],
            }
        answer = visible_answer

    if degraded:
        strongest = degraded[0]
        reason_code = str(strongest.get("reason_code") or REASON_HOST_MIRROR_DIVERGED)
        return {
            "schema": ANSWERABILITY_SCHEMA,
            "state": "degraded" if reason_code == REASON_PENDING_WRITE_BARRIER else "conflicted",
            "can_answer": False,
            "max_claim_strength": CLAIM_NONE,
            "answer_type": "none",
            "authority": "none",
            "can_claim_memory_truth": False,
            "can_claim_current_assignment": False,
            "reason": "explicit truth projection is pending or diverged",
            "reason_code": reason_code,
            "answer_evidence_ids": [],
            "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
            "excluded_evidence_ids": [str(item.get("evidence_key")) for item in degraded + excluded],
            "must_not_claim": ["single_current_truth", "memory_truth"],
        }
    if conflicts:
        return {
            "schema": ANSWERABILITY_SCHEMA,
            "state": "conflicted",
            "can_answer": False,
            "max_claim_strength": CLAIM_NONE,
            "answer_type": "none",
            "authority": "none",
            "can_claim_memory_truth": False,
            "can_claim_current_assignment": False,
            "reason": "conflicting memory evidence selected",
            "reason_code": REASON_CONFLICTING_TRUTH,
            "answer_evidence_ids": [],
            "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
            "excluded_evidence_ids": [str(item.get("evidence_key")) for item in conflicts + excluded],
            "must_not_claim": ["single_current_truth", "memory_truth"],
        }
    if answer:
        strongest = answer[0]
        max_claim = str(strongest.get("max_claim_strength") or CLAIM_NONE)
        return {
            "schema": ANSWERABILITY_SCHEMA,
            "state": "answerable",
            "can_answer": True,
            "max_claim_strength": max_claim,
            "answer_type": str(strongest.get("answer_type") or "none"),
            "authority": str(strongest.get("authority") or "none"),
            "can_claim_memory_truth": max_claim == "memory_truth",
            "can_claim_current_assignment": any(bool(item.get("current_assignment_authority")) for item in answer),
            "reason": "selected memory evidence supports a bounded answer",
            "reason_code": str(strongest.get("reason_code") or "SELECTED_MEMORY_EVIDENCE"),
            "answer_evidence_ids": [str(item.get("evidence_key")) for item in answer],
            "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
            "excluded_evidence_ids": [str(item.get("evidence_key")) for item in excluded],
            "must_not_claim": sorted(
                {
                    str(claim)
                    for item in answer
                    for claim in item.get("must_not_claim", [])
                    if str(claim)
                }
            ),
        }
    if query_intent == "current_assignment":
        return {
            "schema": ANSWERABILITY_SCHEMA,
            "state": "unanswerable",
            "can_answer": False,
            "max_claim_strength": CLAIM_NONE,
            "answer_type": "current_assignment_absence",
            "authority": "none",
            "can_claim_memory_truth": False,
            "can_claim_current_assignment": False,
            "reason": "no typed current-assignment evidence was selected",
            "reason_code": REASON_NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE,
            "answer_evidence_ids": [],
            "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
            "excluded_evidence_ids": [str(item.get("evidence_key")) for item in excluded],
            "must_not_claim": ["memory_truth", "current_assignment", "lifetime_certainty"],
        }
    if supporting:
        return {
            "schema": ANSWERABILITY_SCHEMA,
            "state": "unanswerable",
            "can_answer": False,
            "max_claim_strength": CLAIM_NONE,
            "answer_type": "none",
            "authority": "none",
            "can_claim_memory_truth": False,
            "can_claim_current_assignment": False,
            "reason": "only supporting context was selected",
            "reason_code": REASON_ONLY_SUPPORTING_CONTEXT,
            "answer_evidence_ids": [],
            "supporting_context_ids": [str(item.get("evidence_key")) for item in supporting],
            "excluded_evidence_ids": [str(item.get("evidence_key")) for item in excluded],
            "must_not_claim": ["memory_truth", "current_assignment"],
        }
    return {
        "schema": ANSWERABILITY_SCHEMA,
        "state": "unanswerable",
        "can_answer": False,
        "max_claim_strength": CLAIM_NONE,
        "answer_type": "none",
        "authority": "none",
        "can_claim_memory_truth": False,
        "can_claim_current_assignment": False,
        "reason": "no supported memory truth selected",
        "reason_code": REASON_NO_CANDIDATES,
        "answer_evidence_ids": [],
        "supporting_context_ids": [],
        "excluded_evidence_ids": [str(item.get("evidence_key")) for item in excluded],
        "must_not_claim": ["memory_truth", "current_assignment"],
    }
