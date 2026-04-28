"""Trace contracts linking ingest, write, recall, packet, and answerability."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .ids import EvidenceId, ReceiptId, TraceId
from .reason_codes import ReasonCode, is_reason_code

EVIDENCE_TRACE_SCHEMA = "brainstack.evidence_trace.v1"

AUTHORITY_DURABLE_TRUTH = "durable_truth"
AUTHORITY_RECEIPT_BACKED = "receipt_backed"
AUTHORITY_CITED_CORPUS = "cited_corpus"
AUTHORITY_SUPPORT_ONLY = "support_only"
AUTHORITY_INSPECT_ONLY = "inspect_only"
AUTHORITY_CORRECTED_FALSE = "corrected_false"

DECISION_SELECTED = "selected"
DECISION_DROPPED = "dropped"
DECISION_DEMOTED = "demoted"

PRIVATE_AUTHORITY_CLASSES = {
    AUTHORITY_SUPPORT_ONLY,
    AUTHORITY_INSPECT_ONLY,
    AUTHORITY_CORRECTED_FALSE,
}


def value_fingerprint(value: object) -> str:
    text = str(value or "")
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _text(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def make_evidence_candidate(
    *,
    candidate_id: str,
    shelf: str,
    source_role: str,
    authority: str,
    decision: str,
    reason_code: str,
    target_slot: str = "",
    source_event_id: str = "",
    source_span_id: str = "",
    capture_plan_id: str | None = None,
    proposal_id: str | None = None,
    admission_id: str | None = None,
    receipt_id: str | None = None,
    truth_eligible: bool = False,
    model_facing_allowed: bool = False,
    answer_evidence_allowed: bool = False,
    raw_value: object = "",
    redacted_excerpt: str | None = None,
    token_estimate: int = 0,
    final_rank: int | None = None,
    supersedes: Sequence[str] = (),
    corrected_by: str | None = None,
) -> dict[str, Any]:
    """Create a redaction-safe evidence trace candidate.

    Raw values are never copied into the trace. Only fingerprints and optional
    redacted excerpts are carried.
    """

    return {
        "candidate_id": _text(candidate_id),
        "source_event_id": _text(source_event_id),
        "source_span_id": _text(source_span_id),
        "capture_plan_id": capture_plan_id,
        "proposal_id": proposal_id,
        "admission_id": admission_id,
        "receipt_id": receipt_id,
        "shelf": _text(shelf),
        "target_slot": _text(target_slot),
        "source_role": _text(source_role),
        "authority": _text(authority),
        "truth_eligible": bool(truth_eligible),
        "model_facing_allowed": bool(model_facing_allowed),
        "answer_evidence_allowed": bool(answer_evidence_allowed),
        "score": {
            "raw_similarity": None,
            "salience": None,
            "recency": None,
            "authority_weight": None,
            "final_rank": final_rank,
        },
        "decision": _text(decision),
        "reason_code": _text(reason_code),
        "token_estimate": int(token_estimate),
        "supersedes": list(supersedes),
        "corrected_by": corrected_by,
        "raw_text_included": False,
        "redacted_excerpt": redacted_excerpt,
        "value_fingerprint": value_fingerprint(raw_value),
    }


def proof_chain_from_candidate(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    source_span_id = _text(candidate.get("source_span_id"))
    if source_span_id:
        chain.append(
            {
                "stage": "source_span",
                "id": source_span_id,
                "source_role": _text(candidate.get("source_role")),
                "text_hash": _text(candidate.get("value_fingerprint")),
            }
        )
    proposal_id = _text(candidate.get("proposal_id"))
    if proposal_id:
        chain.append(
            {
                "stage": "capture_proposal",
                "id": proposal_id,
                "target_slot": _text(candidate.get("target_slot")),
                "normalized_value_hash": _text(candidate.get("value_fingerprint")),
            }
        )
    admission_id = _text(candidate.get("admission_id"))
    if admission_id:
        chain.append({"stage": "admission_decision", "id": admission_id, "decision": "accepted"})
    receipt_id = _text(candidate.get("receipt_id"))
    if receipt_id:
        chain.append({"stage": "write_receipt", "id": receipt_id, "status": "committed"})
    if _text(candidate.get("candidate_id")):
        chain.append(
            {
                "stage": "retrieval_candidate",
                "id": _text(candidate.get("candidate_id")),
                "truth_eligible": bool(candidate.get("truth_eligible")),
            }
        )
    if _text(candidate.get("decision")) == DECISION_SELECTED:
        chain.append({"stage": "packet_selection", "decision": "selected_answer_evidence"})
    return chain


def _candidate_errors(candidate: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    reason_code = _text(candidate.get("reason_code"))
    if not is_reason_code(reason_code):
        errors.append(f"unknown_reason_code:{reason_code or '<missing>'}")
    decision = _text(candidate.get("decision"))
    if decision in {DECISION_DROPPED, DECISION_DEMOTED} and not reason_code:
        errors.append("dropped_or_demoted_candidate_missing_reason_code")
    if candidate.get("raw_text_included") is True:
        errors.append("raw_text_included")
    source_role = _text(candidate.get("source_role")).casefold()
    if source_role == "assistant" and (
        candidate.get("truth_eligible") or candidate.get("answer_evidence_allowed")
    ):
        errors.append("assistant_claim_cannot_be_answer_truth")
    authority = _text(candidate.get("authority"))
    if authority in PRIVATE_AUTHORITY_CLASSES and candidate.get("answer_evidence_allowed"):
        errors.append(f"{authority}_cannot_be_answer_evidence")
    if decision == DECISION_SELECTED and not candidate.get("answer_evidence_allowed"):
        errors.append("selected_candidate_not_answer_evidence_allowed")
    if decision == DECISION_SELECTED:
        for key in ("source_event_id", "source_span_id", "authority"):
            if not _text(candidate.get(key)):
                errors.append(f"selected_candidate_missing_{key}")
    return errors


def build_trace_completeness(trace: Mapping[str, Any]) -> dict[str, bool]:
    candidates = trace.get("candidates") if isinstance(trace.get("candidates"), list) else []
    selected = [item for item in candidates if isinstance(item, Mapping) and item.get("decision") == DECISION_SELECTED]
    dropped = [
        item
        for item in candidates
        if isinstance(item, Mapping) and item.get("decision") in {DECISION_DROPPED, DECISION_DEMOTED}
    ]
    receipt_coverage = trace.get("receipt_coverage")
    has_receipt_coverage = isinstance(receipt_coverage, Mapping) and bool(
        receipt_coverage.get("coverage_status")
    )
    completeness = {
        "has_source_provenance": all(_text(item.get("source_span_id")) for item in selected),
        "has_authority": all(_text(item.get("authority")) for item in selected),
        "has_truth_eligibility": all("truth_eligible" in item for item in selected),
        "has_reason_codes": all(is_reason_code(item.get("reason_code")) for item in candidates if isinstance(item, Mapping)),
        "has_receipt_coverage_when_applicable": has_receipt_coverage,
        "has_drop_reasons_for_all_dropped_candidates": all(
            is_reason_code(item.get("reason_code")) for item in dropped
        ),
        "raw_private_text_excluded": all(
            not bool(item.get("raw_text_included")) for item in candidates if isinstance(item, Mapping)
        ),
    }
    completeness["complete_for_audit"] = all(completeness.values())
    return completeness


def build_evidence_trace(
    *,
    trace_id: str,
    turn_id: str,
    query_summary: str,
    principal_scope_key: str,
    workspace_scope_key: str,
    candidates: Sequence[Mapping[str, Any]],
    receipt_coverage: Mapping[str, Any] | None = None,
    max_tokens: int | None = None,
    truncated: bool = False,
) -> dict[str, Any]:
    selected = [
        _text(item.get("candidate_id"))
        for item in candidates
        if _text(item.get("decision")) == DECISION_SELECTED
    ]
    dropped: dict[str, int] = {}
    for item in candidates:
        if _text(item.get("decision")) in {DECISION_DROPPED, DECISION_DEMOTED}:
            code = _text(item.get("reason_code")) or ReasonCode.UNCLASSIFIED.value
            dropped[code] = dropped.get(code, 0) + 1
    proof_chain: list[dict[str, Any]] = []
    for item in candidates:
        if _text(item.get("decision")) == DECISION_SELECTED:
            proof_chain.extend(proof_chain_from_candidate(item))
    estimated_tokens = sum(int(item.get("token_estimate") or 0) for item in candidates)
    trace: dict[str, Any] = {
        "schema": EVIDENCE_TRACE_SCHEMA,
        "trace_id": _text(trace_id),
        "turn_id": _text(turn_id),
        "query_summary": _text(query_summary),
        "scope": {
            "principal_scope_key": _text(principal_scope_key),
            "workspace_scope_key": _text(workspace_scope_key),
        },
        "candidate_counts": {
            "input": len(candidates),
            "dropped": sum(dropped.values()),
            "selected": len(selected),
        },
        "candidates": [dict(item) for item in candidates],
        "proof_chain": proof_chain,
        "selected_answer_evidence": selected,
        "dropped_summary": [
            {"reason_code": reason_code, "count": count}
            for reason_code, count in sorted(dropped.items())
        ],
        "packet_budget": {
            "max_tokens": max_tokens,
            "estimated_tokens": estimated_tokens,
            "truncated": bool(truncated),
            "truncation_reason": ReasonCode.DROPPED_BUDGET_OVERFLOW.value if truncated else None,
            "truncation_policy": "drop_low_authority_supporting_context_first" if truncated else None,
            "answer_evidence_preserved": True,
            "receipt_coverage_preserved": True,
            "authority_fields_preserved": True,
            "scope_fields_preserved": True,
            "correction_fields_preserved": True,
        },
        "receipt_coverage": dict(receipt_coverage or {"coverage_status": "not_applicable"}),
    }
    trace["trace_completeness"] = build_trace_completeness(trace)
    return trace


def validate_evidence_trace(trace: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if trace.get("schema") != EVIDENCE_TRACE_SCHEMA:
        errors.append("invalid_trace_schema")
    candidates = trace.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates_not_list")
        candidates = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            errors.append("candidate_not_mapping")
            continue
        errors.extend(_candidate_errors(candidate))
    completeness = trace.get("trace_completeness")
    if not isinstance(completeness, Mapping):
        errors.append("missing_trace_completeness")
    elif completeness.get("complete_for_audit"):
        expected = build_trace_completeness(trace)
        for key, value in expected.items():
            if completeness.get(key) != value:
                errors.append(f"trace_completeness_mismatch:{key}")
    packet_budget = trace.get("packet_budget")
    if isinstance(packet_budget, Mapping) and packet_budget.get("truncated"):
        for key in (
            "answer_evidence_preserved",
            "receipt_coverage_preserved",
            "authority_fields_preserved",
            "scope_fields_preserved",
            "correction_fields_preserved",
        ):
            if packet_budget.get(key) is not True:
                errors.append(f"truncation_dropped_{key}")
    return errors


def assert_evidence_trace_complete(trace: Mapping[str, Any]) -> None:
    errors = validate_evidence_trace(trace)
    completeness = trace.get("trace_completeness")
    if isinstance(completeness, Mapping) and completeness.get("complete_for_audit") is not True:
        errors.append("trace_not_complete_for_audit")
    if errors:
        raise ValueError(";".join(errors))


@dataclass(frozen=True, slots=True)
class PacketTrace:
    turn_trace_id: TraceId
    packet_id: str
    write_receipt_ids: tuple[ReceiptId, ...] = field(default_factory=tuple)
    selected_evidence_ids: tuple[EvidenceId, ...] = field(default_factory=tuple)
    suppressed_evidence_ids: tuple[EvidenceId, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "turn_trace_id": str(self.turn_trace_id),
            "packet_id": self.packet_id,
            "write_receipt_ids": [str(item) for item in self.write_receipt_ids],
            "selected_evidence_ids": [str(item) for item in self.selected_evidence_ids],
            "suppressed_evidence_ids": [str(item) for item in self.suppressed_evidence_ids],
        }
