"""Trace-based memory packet budget pilot.

This module is deliberately small and deterministic. It does not retrieve,
rank semantically, call a model, or interpret user language. It only decides
which already-built evidence candidates survive a token budget.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .reason_codes import ReasonCode
from .trace import (
    AUTHORITY_CITED_CORPUS,
    AUTHORITY_DURABLE_TRUTH,
    AUTHORITY_INSPECT_ONLY,
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_SUPPORT_ONLY,
    DECISION_DEMOTED,
    DECISION_DROPPED,
    DECISION_SELECTED,
    build_evidence_trace,
)

BUDGET_STATUS_NOT_APPLICABLE = "not_applicable"
BUDGET_STATUS_WITHIN_LIMIT = "within_limit"
BUDGET_STATUS_APPLIED = "applied"
BUDGET_STATUS_INSUFFICIENT_AUTHORITY = "insufficient_for_authority_minimum"
DEFAULT_PACKET_BUDGET_MODE = "active"
DEFAULT_PACKET_BUDGET_MAX_CANDIDATE_TOKENS = 120

_DROPPED_DECISIONS = {DECISION_DROPPED, DECISION_DEMOTED}
_PROTECTED_AUTHORITIES = {
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_DURABLE_TRUTH,
    AUTHORITY_CITED_CORPUS,
}
ALLOWED_PACKET_BUDGET_REASON_CODES = {
    ReasonCode.BUDGET_INSUFFICIENT_FOR_AUTHORITY_MINIMUM.value,
    ReasonCode.DROPPED_BUDGET_DUPLICATE_LOWER_AUTHORITY.value,
    ReasonCode.DROPPED_BUDGET_LOW_AUTHORITY.value,
    ReasonCode.DROPPED_BUDGET_OVERFLOW.value,
    ReasonCode.DROPPED_BUDGET_STALE_TRANSCRIPT.value,
    ReasonCode.DROPPED_BUDGET_SUPPORT_ONLY.value,
    ReasonCode.SELECTED_BUDGET_PROTECTED_AUTHORITY.value,
    ReasonCode.SELECTED_BUDGET_WITHIN_LIMIT.value,
}
PACKET_BUDGET_TRACE_DECISION_FIELDS = {
    "candidate_id",
    "decision",
    "reason_code",
    "token_estimate",
}


def resolve_packet_budget_mode(mode: str | None = None) -> str:
    """Resolve packet-budget mode from explicit value, env, then safe default."""

    configured = mode
    if configured is None:
        configured = os.environ.get("BRAINSTACK_PACKET_BUDGET_MODE")
    resolved = " ".join(str(configured or DEFAULT_PACKET_BUDGET_MODE).strip().split()).casefold()
    if resolved not in {"off", "shadow", "active"}:
        return "off"
    return resolved


def resolve_packet_budget_max_candidate_tokens(value: int | None = None) -> int | None:
    """Resolve packet-budget cap from explicit value, env, then default."""

    if value is not None:
        return value
    configured = os.environ.get("BRAINSTACK_PACKET_BUDGET_MAX_CANDIDATE_TOKENS")
    if configured:
        try:
            parsed = int(configured)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return DEFAULT_PACKET_BUDGET_MAX_CANDIDATE_TOKENS


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _token_estimate(candidate: Mapping[str, Any]) -> int:
    return max(0, int(candidate.get("token_estimate") or 0))


def _decision(candidate: Mapping[str, Any]) -> str:
    return _text(candidate.get("decision"))


def _answer_allowed(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("answer_evidence_allowed")) or bool(candidate.get("answer_evidence"))


def is_authority_critical(candidate: Mapping[str, Any]) -> bool:
    """Return true when a candidate must never be dropped for budget reasons."""

    if bool(candidate.get("protected")) or bool(candidate.get("required_for_answer")):
        return True
    if _text(candidate.get("receipt_id")) and _answer_allowed(candidate):
        return True
    authority = _text(candidate.get("authority"))
    if authority in _PROTECTED_AUTHORITIES and _answer_allowed(candidate):
        return True
    if bool(candidate.get("truth_eligible")) and _answer_allowed(candidate):
        return True
    return False


def _fingerprint_key(candidate: Mapping[str, Any]) -> str:
    target_slot = _text(candidate.get("target_slot"))
    fingerprint = _text(candidate.get("value_fingerprint"))
    if target_slot and fingerprint:
        return f"{target_slot}:{fingerprint}"
    stable_key = _text(candidate.get("stable_key"))
    if stable_key:
        return stable_key
    return ""


def _authority_weight(candidate: Mapping[str, Any]) -> int:
    authority = _text(candidate.get("authority"))
    if authority == AUTHORITY_RECEIPT_BACKED:
        return 0
    if authority == AUTHORITY_DURABLE_TRUTH:
        return 1
    if authority == AUTHORITY_CITED_CORPUS:
        return 2
    if bool(candidate.get("answer_evidence_allowed")):
        return 3
    if authority == AUTHORITY_SUPPORT_ONLY:
        return 20
    if authority == AUTHORITY_INSPECT_ONLY:
        return 30
    return 10


def _is_stale_transcript(candidate: Mapping[str, Any]) -> bool:
    return bool(candidate.get("stale"))


def _drop_reason(
    candidate: Mapping[str, Any],
    *,
    duplicate_lower_authority: bool = False,
    insufficient_authority: bool = False,
) -> str:
    if insufficient_authority:
        return ReasonCode.BUDGET_INSUFFICIENT_FOR_AUTHORITY_MINIMUM.value
    if duplicate_lower_authority:
        return ReasonCode.DROPPED_BUDGET_DUPLICATE_LOWER_AUTHORITY.value
    if _is_stale_transcript(candidate):
        return ReasonCode.DROPPED_BUDGET_STALE_TRANSCRIPT.value
    if _text(candidate.get("authority")) == AUTHORITY_SUPPORT_ONLY:
        return ReasonCode.DROPPED_BUDGET_SUPPORT_ONLY.value
    return ReasonCode.DROPPED_BUDGET_LOW_AUTHORITY.value


def _select_reason(candidate: Mapping[str, Any]) -> str:
    if is_authority_critical(candidate):
        return ReasonCode.SELECTED_BUDGET_PROTECTED_AUTHORITY.value
    return ReasonCode.SELECTED_BUDGET_WITHIN_LIMIT.value


@dataclass(frozen=True)
class PacketBudgetPolicy:
    """Hard cap for candidate-token estimates."""

    max_candidate_tokens: int | None


@dataclass(frozen=True)
class PacketBudgetResult:
    """Inspectable output of a packet budget pass."""

    candidates: list[dict[str, Any]]
    status: str
    max_candidate_tokens: int | None
    estimated_tokens_before: int
    selected_candidate_tokens: int
    dropped_candidate_tokens: int
    authority_minimum_tokens: int
    truncated: bool
    fail_closed: bool

    def to_trace_packet_budget(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "max_tokens": self.max_candidate_tokens,
            "estimated_tokens_before": self.estimated_tokens_before,
            "selected_candidate_tokens": self.selected_candidate_tokens,
            "dropped_candidate_tokens": self.dropped_candidate_tokens,
            "authority_minimum_tokens": self.authority_minimum_tokens,
            "truncated": self.truncated,
            "fail_closed": self.fail_closed,
            "truncation_reason": ReasonCode.DROPPED_BUDGET_OVERFLOW.value
            if self.truncated
            else None,
            "truncation_policy": "drop_low_authority_supporting_context_first"
            if self.truncated
            else None,
            "answer_evidence_preserved": True,
            "receipt_coverage_preserved": True,
            "authority_fields_preserved": True,
            "scope_fields_preserved": True,
            "correction_fields_preserved": True,
            "budget_decisions": [
                {
                    "candidate_id": _text(item.get("candidate_id")),
                    "decision": _text(item.get("decision")),
                    "reason_code": _text(item.get("reason_code")),
                    "token_estimate": _token_estimate(item),
                }
                for item in self.candidates
            ],
            "budget_reason_code_registry_pass": all(
                _text(item.get("reason_code")) in ALLOWED_PACKET_BUDGET_REASON_CODES
                for item in self.candidates
            ),
            "raw_text_in_budget_trace": False,
        }


def _copy_with_decision(
    candidate: Mapping[str, Any],
    *,
    decision: str,
    reason_code: str,
) -> dict[str, Any]:
    updated = dict(candidate)
    updated["decision"] = decision
    updated["reason_code"] = reason_code
    if decision == DECISION_DROPPED:
        updated["model_facing_allowed"] = False
        updated["model_facing_default"] = False
        updated["answer_evidence_allowed"] = False
        updated["answer_evidence"] = False
        updated["truth_eligible"] = False
    return updated


def _duplicate_lower_authority_ids(candidates: Sequence[Mapping[str, Any]]) -> set[str]:
    by_key: dict[str, list[Mapping[str, Any]]] = {}
    for candidate in candidates:
        key = _fingerprint_key(candidate)
        if not key:
            continue
        by_key.setdefault(key, []).append(candidate)

    duplicate_ids: set[str] = set()
    for group in by_key.values():
        if len(group) < 2:
            continue
        winner = sorted(
            group,
            key=lambda item: (
                _authority_weight(item),
                _token_estimate(item),
                _text(item.get("candidate_id")),
            ),
        )[0]
        winner_id = _text(winner.get("candidate_id"))
        for candidate in group:
            candidate_id = _text(candidate.get("candidate_id"))
            if candidate_id and candidate_id != winner_id:
                duplicate_ids.add(candidate_id)
    return duplicate_ids


def apply_packet_budget(
    candidates: Sequence[Mapping[str, Any]],
    policy: PacketBudgetPolicy,
) -> PacketBudgetResult:
    """Apply a deterministic budget to already-built evidence candidates."""

    max_tokens = policy.max_candidate_tokens
    copied = [dict(item) for item in candidates]
    estimated_before = sum(_token_estimate(item) for item in copied)
    if max_tokens is None:
        selected_tokens = sum(
            _token_estimate(item)
            for item in copied
            if _decision(item) == DECISION_SELECTED
        )
        dropped_tokens = sum(
            _token_estimate(item)
            for item in copied
            if _decision(item) in _DROPPED_DECISIONS
        )
        return PacketBudgetResult(
            candidates=copied,
            status=BUDGET_STATUS_NOT_APPLICABLE,
            max_candidate_tokens=None,
            estimated_tokens_before=estimated_before,
            selected_candidate_tokens=selected_tokens,
            dropped_candidate_tokens=dropped_tokens,
            authority_minimum_tokens=0,
            truncated=False,
            fail_closed=False,
        )

    pre_dropped = [item for item in copied if _decision(item) in _DROPPED_DECISIONS]
    active = [item for item in copied if _decision(item) not in _DROPPED_DECISIONS]
    duplicate_ids = _duplicate_lower_authority_ids(active)
    protected = [
        item
        for item in active
        if is_authority_critical(item) and _text(item.get("candidate_id")) not in duplicate_ids
    ]
    authority_minimum_tokens = sum(_token_estimate(item) for item in protected)

    selected: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = list(pre_dropped)

    if authority_minimum_tokens > max_tokens:
        selected.extend(
            _copy_with_decision(
                item,
                decision=DECISION_SELECTED,
                reason_code=ReasonCode.SELECTED_BUDGET_PROTECTED_AUTHORITY.value,
            )
            for item in protected
        )
        protected_ids = {_text(item.get("candidate_id")) for item in protected}
        for item in active:
            candidate_id = _text(item.get("candidate_id"))
            if candidate_id in protected_ids:
                continue
            if candidate_id in duplicate_ids:
                dropped.append(
                    _copy_with_decision(
                        item,
                        decision=DECISION_DROPPED,
                        reason_code=_drop_reason(item, duplicate_lower_authority=True),
                    )
                )
                continue
            dropped.append(
                _copy_with_decision(
                    item,
                    decision=DECISION_DROPPED,
                    reason_code=_drop_reason(item, insufficient_authority=True),
                )
            )
        return _result(
            selected=selected,
            dropped=dropped,
            status=BUDGET_STATUS_INSUFFICIENT_AUTHORITY,
            max_tokens=max_tokens,
            estimated_before=estimated_before,
            authority_minimum_tokens=authority_minimum_tokens,
            fail_closed=True,
        )

    remaining = max_tokens
    protected_ids: set[str] = set()
    for item in sorted(protected, key=lambda item: (_authority_weight(item), _text(item.get("candidate_id")))):
        selected.append(
            _copy_with_decision(
                item,
                decision=DECISION_SELECTED,
                reason_code=ReasonCode.SELECTED_BUDGET_PROTECTED_AUTHORITY.value,
            )
        )
        protected_ids.add(_text(item.get("candidate_id")))
        remaining -= _token_estimate(item)

    optional = [
        item
        for item in active
        if _text(item.get("candidate_id")) not in protected_ids
    ]
    for item in sorted(
        optional,
        key=lambda item: (
            _authority_weight(item),
            _token_estimate(item),
            _text(item.get("candidate_id")),
        ),
    ):
        candidate_id = _text(item.get("candidate_id"))
        if candidate_id in duplicate_ids:
            dropped.append(
                _copy_with_decision(
                    item,
                    decision=DECISION_DROPPED,
                    reason_code=_drop_reason(item, duplicate_lower_authority=True),
                )
            )
            continue
        if not _answer_allowed(item):
            if _token_estimate(item) <= remaining:
                selected.append(
                    _copy_with_decision(
                        item,
                        decision=DECISION_SELECTED,
                        reason_code=ReasonCode.SELECTED_BUDGET_WITHIN_LIMIT.value,
                    )
                )
                remaining -= _token_estimate(item)
                continue
            dropped.append(
                _copy_with_decision(
                    item,
                    decision=DECISION_DROPPED,
                    reason_code=_drop_reason(item),
                )
            )
            continue
        if _token_estimate(item) <= remaining:
            selected.append(
                _copy_with_decision(
                    item,
                    decision=DECISION_SELECTED,
                    reason_code=_select_reason(item),
                )
            )
            remaining -= _token_estimate(item)
            continue
        dropped.append(
            _copy_with_decision(
                item,
                decision=DECISION_DROPPED,
                reason_code=_drop_reason(item),
            )
        )

    selected_tokens = sum(_token_estimate(item) for item in selected)
    status = (
        BUDGET_STATUS_WITHIN_LIMIT
        if selected_tokens == estimated_before and not dropped
        else BUDGET_STATUS_APPLIED
    )
    return _result(
        selected=selected,
        dropped=dropped,
        status=status,
        max_tokens=max_tokens,
        estimated_before=estimated_before,
        authority_minimum_tokens=authority_minimum_tokens,
        fail_closed=False,
    )


def _result(
    *,
    selected: Sequence[Mapping[str, Any]],
    dropped: Sequence[Mapping[str, Any]],
    status: str,
    max_tokens: int,
    estimated_before: int,
    authority_minimum_tokens: int,
    fail_closed: bool,
) -> PacketBudgetResult:
    candidates = [dict(item) for item in [*selected, *dropped]]
    selected_tokens = sum(
        _token_estimate(item)
        for item in candidates
        if _decision(item) == DECISION_SELECTED
    )
    dropped_tokens = sum(
        _token_estimate(item)
        for item in candidates
        if _decision(item) in _DROPPED_DECISIONS
    )
    return PacketBudgetResult(
        candidates=candidates,
        status=status,
        max_candidate_tokens=max_tokens,
        estimated_tokens_before=estimated_before,
        selected_candidate_tokens=selected_tokens,
        dropped_candidate_tokens=dropped_tokens,
        authority_minimum_tokens=authority_minimum_tokens,
        truncated=dropped_tokens > 0 or fail_closed,
        fail_closed=fail_closed,
    )


def build_budgeted_evidence_trace(
    *,
    trace: Mapping[str, Any],
    max_candidate_tokens: int,
) -> dict[str, Any]:
    """Return a new evidence trace with budget decisions applied."""

    policy = PacketBudgetPolicy(max_candidate_tokens=max_candidate_tokens)
    result = apply_packet_budget(
        [item for item in trace.get("candidates") or [] if isinstance(item, Mapping)],
        policy,
    )
    scope = trace.get("scope") if isinstance(trace.get("scope"), Mapping) else {}
    budgeted = build_evidence_trace(
        trace_id=_text(trace.get("trace_id")),
        turn_id=_text(trace.get("turn_id")),
        query_summary=_text(trace.get("query_summary")),
        principal_scope_key=_text(scope.get("principal_scope_key")),
        workspace_scope_key=_text(scope.get("workspace_scope_key")),
        candidates=result.candidates,
        receipt_coverage=trace.get("receipt_coverage")
        if isinstance(trace.get("receipt_coverage"), Mapping)
        else None,
        max_tokens=max_candidate_tokens,
        truncated=result.truncated,
    )
    budgeted["packet_budget"].update(result.to_trace_packet_budget())
    return budgeted


def validate_packet_budget_trace(trace: Mapping[str, Any]) -> list[str]:
    """Validate budget-specific invariants that generic trace validation cannot see."""

    errors: list[str] = []
    candidates = [item for item in trace.get("candidates") or [] if isinstance(item, Mapping)]
    for candidate in candidates:
        if _decision(candidate) == DECISION_DROPPED and is_authority_critical(candidate):
            errors.append("budget_dropped_authority_critical_evidence")
    packet_budget = trace.get("packet_budget")
    if isinstance(packet_budget, Mapping):
        decisions = packet_budget.get("budget_decisions")
        if isinstance(decisions, list):
            for decision in decisions:
                if not isinstance(decision, Mapping):
                    errors.append("budget_decision_not_mapping")
                    continue
                extra_fields = set(decision) - PACKET_BUDGET_TRACE_DECISION_FIELDS
                if extra_fields:
                    errors.append("budget_decision_contains_unregistered_fields")
                reason_code = _text(decision.get("reason_code"))
                if reason_code not in ALLOWED_PACKET_BUDGET_REASON_CODES:
                    errors.append("budget_reason_code_not_registered")
        if packet_budget.get("budget_reason_code_registry_pass") is False:
            errors.append("budget_reason_code_registry_failed")
        if packet_budget.get("raw_text_in_budget_trace") is True:
            errors.append("budget_trace_contains_raw_text")
        for key in (
            "answer_evidence_preserved",
            "receipt_coverage_preserved",
            "authority_fields_preserved",
            "scope_fields_preserved",
            "correction_fields_preserved",
        ):
            if packet_budget.get(key) is False:
                errors.append(f"budget_{key}_false")
    return errors
