from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from .canonical_memory_event import CANONICAL_MEMORY_EVENT_CORE_GROUPS, validate_canonical_memory_event

MEMPALACE_BUDGET_PROJECTION_SCHEMA_VERSION = "brainstack.mempalace_budget_projection.v1"
ACTIVE_BUDGET_CLASSES = {"always_active", "active_if_task_relevant"}
SUPPORTED_BUDGET_CLASSES = {
    "always_active",
    "active_if_task_relevant",
    "retrieval_only",
    "support_only",
    "archived",
}
MEMORY_KIND_TOKEN_WEIGHTS = {
    "preference": 10,
    "profile": 12,
    "project": 14,
    "reference": 12,
    "graph_relation": 14,
    "graph_state": 14,
    "temporal_event": 12,
    "support_only": 18,
    "runtime_diagnostic": 12,
    "operator_note": 12,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _hash(value: Any, *, length: int = 24) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def _canonical_event(row_or_event: Mapping[str, Any]) -> Mapping[str, Any]:
    if all(isinstance(row_or_event.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return row_or_event
    nested = _mapping(row_or_event.get("event"))
    if all(isinstance(nested.get(group), Mapping) for group in CANONICAL_MEMORY_EVENT_CORE_GROUPS):
        return nested
    return {}


def _normalize_budget_class(event: Mapping[str, Any]) -> str:
    claim = _mapping(event.get("claim"))
    authority = _mapping(event.get("authority"))
    projection = _mapping(event.get("projection"))
    memory_kind = _text(claim.get("memory_kind"))
    budget_class = _text(projection.get("budget_class"))
    truth_eligible = bool(authority.get("truth_eligible"))
    support_visibility = _text(authority.get("support_visibility"))
    authority_critical = bool(projection.get("authority_critical"))

    if budget_class in SUPPORTED_BUDGET_CLASSES:
        if budget_class == "archived" and authority_critical and truth_eligible:
            return "active_if_task_relevant"
        return budget_class
    if authority_critical and truth_eligible and support_visibility == "answer_evidence":
        if memory_kind in {"profile", "preference"}:
            return "always_active"
        return "active_if_task_relevant"
    if support_visibility in {"normal", "support_context"}:
        return "support_only"
    if truth_eligible:
        return "retrieval_only"
    return "archived"


def _estimated_tokens(event: Mapping[str, Any]) -> int:
    claim = _mapping(event.get("claim"))
    authority = _mapping(event.get("authority"))
    memory_kind = _text(claim.get("memory_kind")) or "support_only"
    base = MEMORY_KIND_TOKEN_WEIGHTS.get(memory_kind, 14)
    if bool(authority.get("truth_eligible")):
        base += 2
    if _text(authority.get("support_visibility")) == "answer_evidence":
        base += 2
    return base


def _card(event: Mapping[str, Any], *, budget_class: str) -> dict[str, Any]:
    event_group = _mapping(event.get("event"))
    source = _mapping(event.get("source"))
    scope = _mapping(event.get("scope"))
    claim = _mapping(event.get("claim"))
    authority = _mapping(event.get("authority"))
    projection = _mapping(event.get("projection"))
    temporal = _mapping(event.get("temporal"))
    return {
        "card_id": _hash([event_group.get("event_id"), claim.get("stable_fact_id"), budget_class]),
        "event_id": _text(event_group.get("event_id")),
        "stable_fact_id": _text(claim.get("stable_fact_id")),
        "memory_kind": _text(claim.get("memory_kind")),
        "target_slot": _text(claim.get("target_slot")),
        "value_fingerprint": _text(claim.get("normalized_value_hash")),
        "source_event_id": _text(source.get("source_event_id")),
        "source_span_id": _text(source.get("source_span_id")),
        "scope": dict(scope),
        "authority_class": _text(authority.get("authority_class")),
        "truth_eligible": bool(authority.get("truth_eligible")),
        "support_visibility": _text(authority.get("support_visibility")),
        "authority_critical": bool(projection.get("authority_critical")),
        "budget_class": budget_class,
        "estimated_tokens": _estimated_tokens(event),
        "valid_from": _text(temporal.get("valid_from")),
        "valid_to": _text(temporal.get("valid_to")),
    }


def _sort_key(card: Mapping[str, Any]) -> tuple[int, str, str]:
    priority = {
        "always_active": 0,
        "active_if_task_relevant": 1,
        "retrieval_only": 2,
        "support_only": 3,
        "archived": 4,
    }.get(_text(card.get("budget_class")), 5)
    return (priority, _text(card.get("memory_kind")), _text(card.get("card_id")))


def _contains_forbidden_raw_text(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return any(key in payload for key in ('"raw_text"', '"raw_private_text"', '"packet_text"', '"model_output"'))


def project_canonical_events_to_mempalace_budget(
    events: Iterable[Mapping[str, Any]],
    *,
    max_active_tokens: int = 120,
) -> dict[str, Any]:
    normalized_events = [_canonical_event(event) for event in events]
    normalized_events = [event for event in normalized_events if event]
    counters = {
        "invalid_canonical_event": 0,
        "authority_critical_dropped": 0,
        "support_only_answer_evidence": 0,
        "memory_kind_lost": 0,
        "budget_overflow_untraced": 0,
        "raw_text_in_budget_projection": 0,
    }
    issues: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    for event in normalized_events:
        event_group = _mapping(event.get("event"))
        event_id = _text(event_group.get("event_id"))
        validation_issues = validate_canonical_memory_event(event)
        if validation_issues:
            counters["invalid_canonical_event"] += 1
            issues.append({"event_id": event_id, "issues": validation_issues})
            continue
        budget_class = _normalize_budget_class(event)
        card = _card(event, budget_class=budget_class)
        cards.append(card)

    cards.sort(key=_sort_key)
    authority_cards = [card for card in cards if card["authority_critical"]]
    authority_tokens = sum(int(card["estimated_tokens"]) for card in authority_cards)
    active_cards: list[dict[str, Any]] = []
    retrieval_only: list[dict[str, Any]] = []
    support_only: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    selected_tokens = 0
    fail_closed = authority_tokens > max_active_tokens

    for card in cards:
        decision = {
            "card_id": card["card_id"],
            "event_id": card["event_id"],
            "memory_kind": card["memory_kind"],
            "budget_class": card["budget_class"],
            "authority_critical": card["authority_critical"],
            "estimated_tokens": card["estimated_tokens"],
            "decision": "drop",
            "reason_code": "ARCHIVED_NO_PROMPT",
        }
        if card["authority_critical"]:
            active_cards.append(card)
            selected_tokens += int(card["estimated_tokens"])
            decision["decision"] = "keep"
            decision["reason_code"] = "KEEP_AUTHORITY_CRITICAL"
        elif card["budget_class"] == "always_active":
            if not fail_closed and selected_tokens + int(card["estimated_tokens"]) <= max_active_tokens:
                active_cards.append(card)
                selected_tokens += int(card["estimated_tokens"])
                decision["decision"] = "keep"
                decision["reason_code"] = "KEEP_ALWAYS_ACTIVE"
            else:
                retrieval_only.append(card)
                decision["reason_code"] = "DROP_BUDGET_OVERFLOW_TO_RETRIEVAL"
        elif card["budget_class"] == "active_if_task_relevant":
            if not fail_closed and selected_tokens + int(card["estimated_tokens"]) <= max_active_tokens:
                active_cards.append(card)
                selected_tokens += int(card["estimated_tokens"])
                decision["decision"] = "keep"
                decision["reason_code"] = "KEEP_TASK_RELEVANT"
            else:
                retrieval_only.append(card)
                decision["reason_code"] = "DROP_BUDGET_OVERFLOW_TO_RETRIEVAL"
        elif card["budget_class"] == "retrieval_only":
            retrieval_only.append(card)
            decision["reason_code"] = "DROP_RETRIEVAL_ONLY"
        elif card["budget_class"] == "support_only":
            support_only.append(card)
            decision["reason_code"] = "DROP_SUPPORT_ONLY"
        else:
            archived.append(card)
            decision["reason_code"] = "ARCHIVED_NO_PROMPT"
        decisions.append(decision)

    active_ids = {card["card_id"] for card in active_cards}
    for card in cards:
        if card["authority_critical"] and card["card_id"] not in active_ids:
            counters["authority_critical_dropped"] += 1
        if card["budget_class"] == "support_only" and card["support_visibility"] == "answer_evidence":
            counters["support_only_answer_evidence"] += 1
    for decision in decisions:
        if not decision["memory_kind"]:
            counters["memory_kind_lost"] += 1
        if decision["decision"] == "drop" and not decision["reason_code"]:
            counters["budget_overflow_untraced"] += 1

    result = {
        "schema": MEMPALACE_BUDGET_PROJECTION_SCHEMA_VERSION,
        "status": "pass",
        "max_active_tokens": int(max_active_tokens),
        "selected_active_tokens": selected_tokens,
        "baseline_tokens": sum(int(card["estimated_tokens"]) for card in cards),
        "estimated_delta_tokens": max(sum(int(card["estimated_tokens"]) for card in cards) - selected_tokens, 0),
        "fail_closed": fail_closed,
        "active_cards": active_cards,
        "retrieval_only": retrieval_only,
        "support_only": support_only,
        "archived": archived,
        "budget_decisions": decisions,
        "critical_counters": counters,
        "issues": issues,
    }
    if _contains_forbidden_raw_text(result):
        counters["raw_text_in_budget_projection"] += 1
    if sum(counters.values()) > 0:
        result["status"] = "fail"
    return result
