"""Shared read-only projection semantics for Canonical Memory Events.

This module classifies already-admitted/read-model memory events for projection
surfaces. It does not write storage, call providers, rebuild graph state, enforce
budget placement, or assemble model-facing packets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .core.admission import SupportVisibility
from .core.reason_codes import ReasonCode

ANSWERABLE_EVENT_TYPES = frozenset({"durable_fact_committed", "proposal_accepted"})
CURRENT_EVENT_TYPES = ANSWERABLE_EVENT_TYPES | frozenset({"support_event"})
CONFLICT_EVENT_TYPES = frozenset({"conflict_opened", "corrected_false_event"})
SUPPORT_ONLY_VISIBILITIES = frozenset(
    {
        SupportVisibility.NORMAL.value,
        SupportVisibility.HISTORY_ONLY.value,
        SupportVisibility.INSPECT_ONLY.value,
    }
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "hidden"}
    return bool(value)


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _event_id(event: Mapping[str, Any]) -> str:
    return _text(_mapping(event.get("event")).get("event_id"))


def _event_sort_key(event: Mapping[str, Any]) -> tuple[str, str]:
    event_group = _mapping(event.get("event"))
    temporal = _mapping(event.get("temporal"))
    return (_text(temporal.get("transaction_time")), _text(event_group.get("event_id")))


def apply_read_model_supersession(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Annotate read-model events superseded by newer canonical events.

    This is projection-only. It does not write storage and does not decide truth.
    It only preserves the donor temporal invariant when a newer canonical event
    already names older event ids in `temporal.supersedes`.
    """

    event_list = list(events)
    superseded_by_by_event_id: dict[str, str] = {}
    for event in sorted(event_list, key=_event_sort_key):
        event_id = _event_id(event)
        if not event_id:
            continue
        for prior_event_id in _list(_mapping(event.get("temporal")).get("supersedes")):
            prior_id = _text(prior_event_id)
            if prior_id:
                superseded_by_by_event_id[prior_id] = event_id

    projected_events: list[Mapping[str, Any]] = []
    for event in event_list:
        superseded_by = superseded_by_by_event_id.get(_event_id(event), "")
        if not superseded_by:
            projected_events.append(event)
            continue
        temporal = dict(_mapping(event.get("temporal")))
        if _text(temporal.get("superseded_by")):
            projected_events.append(event)
            continue
        projected = dict(event)
        temporal["superseded_by"] = superseded_by
        projected["temporal"] = temporal
        projected_events.append(projected)
    return projected_events


@dataclass(frozen=True)
class ProjectionSemanticsDecision:
    """Immutable public-safe classification of one memory projection item."""

    event_id: str
    stable_fact_id: str
    source_event_id: str
    source_span_id: str
    source_quote_hash: str
    receipt_id: str
    is_current: bool
    is_prior: bool
    is_conflicted: bool
    is_support_only: bool
    is_answer_safe: bool
    is_retrieval_only: bool
    is_hidden: bool
    is_authority_critical: bool
    reason_codes: tuple[ReasonCode, ...]

    def to_public_dict(self) -> dict[str, Any]:
        """Return inspect-safe handles and reasons without raw memory text."""

        return {
            "event_id": self.event_id,
            "stable_fact_id": self.stable_fact_id,
            "source_event_id": self.source_event_id,
            "source_span_id": self.source_span_id,
            "source_quote_hash": self.source_quote_hash,
            "receipt_id": self.receipt_id,
            "is_current": self.is_current,
            "is_prior": self.is_prior,
            "is_conflicted": self.is_conflicted,
            "is_support_only": self.is_support_only,
            "is_answer_safe": self.is_answer_safe,
            "is_retrieval_only": self.is_retrieval_only,
            "is_hidden": self.is_hidden,
            "is_authority_critical": self.is_authority_critical,
            "reason_codes": [reason.value for reason in self.reason_codes],
        }


def classify_projection_semantics(event: Mapping[str, Any]) -> ProjectionSemanticsDecision:
    """Classify a Canonical Memory Event for read/projection consumers.

    The classifier is deliberately conservative: source, receipt, temporal,
    conflict, support-only, and hidden blockers prevent answer safety. Authority
    criticality is orthogonal; it protects evidence from silent dropping but never
    upgrades unsafe evidence into answer truth.
    """

    event_group = _mapping(event.get("event"))
    source = _mapping(event.get("source"))
    claim = _mapping(event.get("claim"))
    authority = _mapping(event.get("authority"))
    temporal = _mapping(event.get("temporal"))
    projection = _mapping(event.get("projection"))

    event_id = _text(event_group.get("event_id"))
    event_type = _text(event_group.get("event_type"))
    stable_fact_id = _text(claim.get("stable_fact_id"))
    source_event_id = _text(source.get("source_event_id"))
    source_span_id = _text(source.get("source_span_id"))
    source_quote_hash = _text(source.get("source_quote_hash"))
    receipt_id = _text(authority.get("receipt_id"))
    support_visibility = _text(authority.get("support_visibility"))
    truth_eligible = bool(authority.get("truth_eligible"))
    valid_to = _text(temporal.get("valid_to"))
    superseded_by = _text(temporal.get("superseded_by"))
    budget_class = _text(projection.get("budget_class"))

    missing_source = not (source_event_id and source_span_id and source_quote_hash)
    missing_receipt = truth_eligible and support_visibility == SupportVisibility.ANSWER_EVIDENCE.value and not receipt_id
    is_prior = bool(valid_to or superseded_by)
    is_conflicted = event_type in CONFLICT_EVENT_TYPES or support_visibility == SupportVisibility.CONTRADICTION_ONLY.value
    is_support_only = support_visibility in SUPPORT_ONLY_VISIBILITIES or (
        not truth_eligible and support_visibility != SupportVisibility.CONTRADICTION_ONLY.value
    )
    is_retrieval_only = budget_class == "retrieval_only"
    is_hidden = (
        _flag(projection.get("hidden"))
        or _text(projection.get("visibility")).casefold() == "hidden"
        or _flag(authority.get("hidden"))
    )
    is_authority_critical = bool(projection.get("authority_critical"))
    is_current = event_type in CURRENT_EVENT_TYPES and not is_prior

    blockers = {
        "hidden": is_hidden,
        "missing_source": missing_source,
        "missing_receipt": missing_receipt,
        "prior": is_prior,
        "conflicted": is_conflicted,
        "support_only": is_support_only,
        "not_answer_evidence": support_visibility != SupportVisibility.ANSWER_EVIDENCE.value,
        "not_truth_eligible": not truth_eligible,
        "not_answerable_event_type": event_type not in ANSWERABLE_EVENT_TYPES,
    }
    is_answer_safe = not any(blockers.values())

    reasons: list[ReasonCode] = []
    if is_answer_safe:
        reasons.append(ReasonCode.PROJECTION_ANSWER_SAFE_CURRENT_SOURCE_BACKED)
    if missing_source:
        reasons.extend(
            [
                ReasonCode.PROJECTION_MISSING_SOURCE_REF,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_MISSING_SOURCE,
            ]
        )
    if missing_receipt:
        reasons.extend(
            [
                ReasonCode.PROJECTION_MISSING_RECEIPT_REF,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_MISSING_RECEIPT,
            ]
        )
    if valid_to:
        reasons.extend(
            [
                ReasonCode.PROJECTION_PRIOR_EXPIRED,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_PRIOR,
            ]
        )
    elif superseded_by:
        reasons.extend(
            [
                ReasonCode.PROJECTION_PRIOR_SUPERSEDED,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_PRIOR,
            ]
        )
    if event_type in CONFLICT_EVENT_TYPES:
        reasons.extend(
            [
                ReasonCode.PROJECTION_CONFLICTED,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_CONFLICTED,
            ]
        )
    if support_visibility == SupportVisibility.CONTRADICTION_ONLY.value:
        reasons.extend(
            [
                ReasonCode.PROJECTION_CONTRADICTION_ONLY,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_CONFLICTED,
            ]
        )
    if is_support_only:
        reasons.extend(
            [
                ReasonCode.PROJECTION_SUPPORT_ONLY,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_SUPPORT_ONLY,
            ]
        )
    if is_retrieval_only:
        reasons.append(ReasonCode.PROJECTION_RETRIEVAL_ONLY)
    if is_hidden:
        reasons.extend(
            [
                ReasonCode.PROJECTION_HIDDEN_BY_POLICY,
                ReasonCode.PROJECTION_NOT_ANSWERABLE_HIDDEN,
            ]
        )
    if is_authority_critical:
        reasons.extend(
            [
                ReasonCode.PROJECTION_AUTHORITY_CRITICAL_KEEP,
                ReasonCode.PROJECTION_AUTHORITY_CRITICAL_CANNOT_DROP,
            ]
        )

    return ProjectionSemanticsDecision(
        event_id=event_id,
        stable_fact_id=stable_fact_id,
        source_event_id=source_event_id,
        source_span_id=source_span_id,
        source_quote_hash=source_quote_hash,
        receipt_id=receipt_id,
        is_current=is_current,
        is_prior=is_prior,
        is_conflicted=is_conflicted,
        is_support_only=is_support_only,
        is_answer_safe=is_answer_safe,
        is_retrieval_only=is_retrieval_only,
        is_hidden=is_hidden,
        is_authority_critical=is_authority_critical,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )
