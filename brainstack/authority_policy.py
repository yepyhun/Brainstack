from __future__ import annotations

from typing import Any, Mapping

from .explicit_truth_parity import PROJECTION_PENDING, parity_degrades_answerability
from .literal_index import SUPPORT_ONLY_LITERAL_CLASSES
from .operating_truth import is_current_assignment_authority_metadata


AUTHORITY_POLICY_SCHEMA = "brainstack.authority_policy.v1"

REASON_NO_CANDIDATES = "NO_CANDIDATES"
REASON_ONLY_SUPPORTING_CONTEXT = "ONLY_SUPPORTING_CONTEXT"
REASON_AUTHORITY_MISMATCH = "AUTHORITY_MISMATCH"
REASON_SCOPE_MISMATCH = "SCOPE_MISMATCH"
REASON_BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
REASON_CONFLICTING_TRUTH = "CONFLICTING_TRUTH"
REASON_PACKET_SUPPRESSED = "PACKET_SUPPRESSED"
REASON_PENDING_WRITE_BARRIER = "PENDING_WRITE_BARRIER"
REASON_HOST_MIRROR_DIVERGED = "HOST_MIRROR_DIVERGED"
REASON_HOST_PARITY_UNOBSERVABLE = "HOST_PARITY_UNOBSERVABLE"
REASON_EXACT_LITERAL_AMBIGUOUS = "EXACT_LITERAL_AMBIGUOUS"
REASON_SELECTED_MEMORY_EVIDENCE = "SELECTED_MEMORY_EVIDENCE"
REASON_NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE = "NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE"

CLAIM_MEMORY_TRUTH = "memory_truth"
CLAIM_BOUNDED_EVENT = "bounded_event"
CLAIM_SOURCE_SAYS = "source_says"
CLAIM_SUPPORTING_CONTEXT = "supporting_context"
CLAIM_NONE = "none"


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_selected_enough(row: Mapping[str, Any]) -> bool:
    """Reject accidental one-token overlap while keeping typed authority paths deterministic."""

    overlap = _integer(row.get("query_token_overlap"))
    token_count = _integer(row.get("query_token_count"))
    match_mode = _text(row.get("match_mode")).casefold()
    retrieval_source = _text(row.get("retrieval_source")).casefold()
    if match_mode == "authority" or retrieval_source.startswith("live_system_state"):
        return True
    if token_count <= 1:
        return overlap >= 1
    return overlap >= 2


def _literal_support_only(item: Mapping[str, Any]) -> bool:
    tokens = item.get("literal_tokens")
    if not isinstance(tokens, list) or not tokens:
        return False
    classes = {str(token.get("class") or "") for token in tokens if isinstance(token, Mapping)}
    return bool(classes) and classes.issubset(SUPPORT_ONLY_LITERAL_CLASSES)


def _profile_preference_requires_direct_match(item: Mapping[str, Any]) -> bool:
    if _text(item.get("shelf")) != "profile":
        return False
    stable_key = _text(item.get("stable_key")).casefold()
    category = _text(item.get("category")).casefold()
    if not stable_key.startswith("preference:") and category != "preference_policy":
        return False
    retrieval_source = _text(item.get("retrieval_source")).casefold()
    match_mode = _text(item.get("match_mode")).casefold()
    literal_slot_match = item.get("literal_slot_match")
    if retrieval_source == "profile.slot_target" or match_mode == "slot":
        return False
    if isinstance(literal_slot_match, Mapping) and bool(literal_slot_match.get("matched")):
        return False
    return True


def is_current_assignment_authority(item: Mapping[str, Any]) -> bool:
    shelf = _text(item.get("shelf"))
    if bool(item.get("runtime_state_only")):
        return False
    if shelf == "task":
        return not bool(item.get("supporting_evidence_only"))
    if shelf == "operating":
        return is_current_assignment_authority_metadata(
            {
                "current_assignment_authority": bool(item.get("current_assignment_authority")),
                "current_assignment_authority_schema": _text(item.get("current_assignment_authority_schema")),
            }
        )
    return False


def infer_query_intent(*, query: str, analysis: Mapping[str, Any] | None = None) -> str:
    payload = analysis if isinstance(analysis, Mapping) else {}
    operating_lookup = payload.get("operating_lookup")
    lookup_payload: Mapping[str, Any] = operating_lookup if isinstance(operating_lookup, Mapping) else {}
    record_types = {
        _text(value)
        for value in lookup_payload.get("record_types", [])
        if _text(value)
    }
    normalized = _text(query).casefold()
    asks_assignment = (
        "assignment" in normalized
        or "assigned" in normalized
        or "current work" in normalized
        or "workstream" in normalized
        or "aktuális feladat" in normalized
    )
    # Current-assignment authority is a positive typed record gate. Do not let
    # route analysis fall back to generic memory/event answerability when the
    # user is explicitly asking what the agent is currently assigned to do.
    if asks_assignment or (bool(payload.get("operating_like")) and "active_work" in record_types):
        return "current_assignment"
    return "memory"


def classify_evidence_authority(
    item: Mapping[str, Any],
    *,
    query_intent: str = "memory",
) -> dict[str, Any]:
    shelf = _text(item.get("shelf"))
    evidence_key = _text(item.get("evidence_key"))
    supporting_only = bool(item.get("supporting_evidence_only")) or bool(item.get("runtime_state_only"))
    current_assignment = is_current_assignment_authority(item)
    row_type = _text(item.get("row_type") or item.get("record_type")).casefold()
    graph_status = _text(item.get("graph_authority_status")).casefold()
    conflict = row_type == "conflict" or "conflict" in graph_status
    literal_support_only = _literal_support_only(item)
    event_type = _text(item.get("event_type")).casefold()
    explicit_truth_parity = item.get("explicit_truth_parity")
    parity_degraded = parity_degrades_answerability(
        explicit_truth_parity if isinstance(explicit_truth_parity, Mapping) else None
    )
    enough = _is_selected_enough(item)

    result = {
        "schema": AUTHORITY_POLICY_SCHEMA,
        "evidence_key": evidence_key,
        "shelf": shelf,
        "answer_authority": False,
        "supporting_only": True,
        "current_assignment_authority": current_assignment,
        "max_claim_strength": CLAIM_SUPPORTING_CONTEXT if evidence_key else CLAIM_NONE,
        "answer_type": "none",
        "authority": "none",
        "reason_code": REASON_ONLY_SUPPORTING_CONTEXT if evidence_key else REASON_NO_CANDIDATES,
        "must_not_claim": [],
    }
    if not evidence_key:
        return result
    if conflict:
        result.update(
            {
                "max_claim_strength": CLAIM_NONE,
                "reason_code": REASON_CONFLICTING_TRUTH,
                "must_not_claim": ["single_current_truth", "memory_truth"],
            }
        )
        return result
    if parity_degraded:
        projection_status = (
            _text(explicit_truth_parity.get("projection_status"))
            if isinstance(explicit_truth_parity, Mapping)
            else ""
        )
        result.update(
            {
                "max_claim_strength": CLAIM_NONE,
                "reason_code": REASON_PENDING_WRITE_BARRIER
                if projection_status == PROJECTION_PENDING
                else REASON_HOST_MIRROR_DIVERGED,
                "must_not_claim": ["memory_truth", "single_current_truth"],
            }
        )
        return result
    if query_intent == "current_assignment":
        if current_assignment:
            result.update(
                {
                    "answer_authority": True,
                    "supporting_only": False,
                    "max_claim_strength": CLAIM_MEMORY_TRUTH,
                    "answer_type": "current_assignment",
                    "authority": "typed_current_assignment",
                    "reason_code": REASON_SELECTED_MEMORY_EVIDENCE,
                }
            )
            return result
        result["must_not_claim"] = ["current_assignment", "memory_truth"]
        result["reason_code"] = REASON_AUTHORITY_MISMATCH
        return result
    if _profile_preference_requires_direct_match(item):
        result["must_not_claim"] = ["memory_truth"]
        return result
    if supporting_only or literal_support_only or event_type == "assistant_response":
        result["must_not_claim"] = ["memory_truth"]
        return result
    if not enough:
        result["must_not_claim"] = ["memory_truth"]
        result["reason_code"] = REASON_AUTHORITY_MISMATCH
        return result

    if shelf == "corpus":
        result.update(
            {
                "answer_authority": True,
                "supporting_only": False,
                "max_claim_strength": CLAIM_SOURCE_SAYS,
                "answer_type": "corpus_citation",
                "authority": "cited_source_support",
                "reason_code": REASON_SELECTED_MEMORY_EVIDENCE,
            }
        )
    elif shelf in {"continuity_match", "continuity_recent", "transcript"}:
        result.update(
            {
                "answer_authority": True,
                "supporting_only": False,
                "max_claim_strength": CLAIM_BOUNDED_EVENT,
                "answer_type": "conversation_event",
                "authority": "supporting_event",
                "reason_code": REASON_SELECTED_MEMORY_EVIDENCE,
                "must_not_claim": ["durable_user_fact", "lifetime_certainty"],
            }
        )
    elif shelf == "graph":
        result.update(
            {
                "answer_authority": True,
                "supporting_only": False,
                "max_claim_strength": CLAIM_MEMORY_TRUTH,
                "answer_type": "graph_truth",
                "authority": "explicit_current_fact",
                "reason_code": REASON_SELECTED_MEMORY_EVIDENCE,
            }
        )
    else:
        result.update(
            {
                "answer_authority": True,
                "supporting_only": False,
                "max_claim_strength": CLAIM_MEMORY_TRUTH,
                "answer_type": "explicit_user_fact",
                "authority": "explicit_current_fact",
                "reason_code": REASON_SELECTED_MEMORY_EVIDENCE,
            }
        )
    return result
