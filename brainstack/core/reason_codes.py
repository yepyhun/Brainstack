"""Public reason codes for inspectable Brainstack decisions."""

from __future__ import annotations

from enum import StrEnum


class ReasonCode(StrEnum):
    """Stable public reason code registry.

    Values are snake_case because they appear in JSON diagnostics and phase proofs.
    """

    AUTHORITATIVE_MEMORY_EVIDENCE = "authoritative_memory_evidence"
    NO_SUPPORTED_MEMORY_TRUTH = "no_supported_memory_truth"
    ONLY_SUPPORTING_CONTEXT = "only_supporting_context"
    AUTHORITY_MISMATCH = "authority_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    CONFLICTING_TRUTH = "conflicting_truth"
    PACKET_SUPPRESSED = "packet_suppressed"
    PENDING_WRITE_BARRIER = "pending_write_barrier"
    HOST_MIRROR_DIVERGED = "host_mirror_diverged"
    HOST_PARITY_UNOBSERVABLE = "host_parity_unobservable"
    EXACT_LITERAL_AMBIGUOUS = "exact_literal_ambiguous"
    PUBLIC_SURFACE_PROTECTED = "public_surface_protected"
    SELECTED_AUTHORITY_MATCH = "selected_authority_match"
    SELECTED_RECEIPT_BACKED_FACT = "selected_receipt_backed_fact"
    SELECTED_CITED_CORPUS = "selected_cited_corpus"
    DROPPED_ASSISTANT_CLAIM_NOT_TRUTH_AUTHORITY = (
        "dropped_assistant_claim_not_truth_authority"
    )
    DROPPED_CORRECTED_FALSE = "dropped_corrected_false"
    DROPPED_INSPECT_ONLY = "dropped_inspect_only"
    DROPPED_SUPPORT_ONLY_FOR_ANSWER_TRUTH = "dropped_support_only_for_answer_truth"
    DROPPED_SCOPE_MISMATCH = "dropped_scope_mismatch"
    DROPPED_BUDGET_OVERFLOW = "dropped_budget_overflow"
    DROPPED_BUDGET_LOW_AUTHORITY = "dropped_budget_low_authority"
    DROPPED_BUDGET_SUPPORT_ONLY = "dropped_budget_support_only"
    DROPPED_BUDGET_DUPLICATE_LOWER_AUTHORITY = (
        "dropped_budget_duplicate_lower_authority"
    )
    DROPPED_BUDGET_STALE_TRANSCRIPT = "dropped_budget_stale_transcript"
    SELECTED_BUDGET_PROTECTED_AUTHORITY = "selected_budget_protected_authority"
    SELECTED_BUDGET_WITHIN_LIMIT = "selected_budget_within_limit"
    BUDGET_INSUFFICIENT_FOR_AUTHORITY_MINIMUM = (
        "budget_insufficient_for_authority_minimum"
    )
    PROJECTION_ANSWER_SAFE_CURRENT_SOURCE_BACKED = (
        "projection_answer_safe_current_source_backed"
    )
    PROJECTION_MISSING_SOURCE_REF = "projection_missing_source_ref"
    PROJECTION_MISSING_RECEIPT_REF = "projection_missing_receipt_ref"
    PROJECTION_PRIOR_EXPIRED = "projection_prior_expired"
    PROJECTION_PRIOR_SUPERSEDED = "projection_prior_superseded"
    PROJECTION_CONFLICTED = "projection_conflicted"
    PROJECTION_CONTRADICTION_ONLY = "projection_contradiction_only"
    PROJECTION_SUPPORT_ONLY = "projection_support_only"
    PROJECTION_RETRIEVAL_ONLY = "projection_retrieval_only"
    PROJECTION_HIDDEN_BY_POLICY = "projection_hidden_by_policy"
    PROJECTION_AUTHORITY_CRITICAL_KEEP = "projection_authority_critical_keep"
    PROJECTION_AUTHORITY_CRITICAL_CANNOT_DROP = (
        "projection_authority_critical_cannot_drop"
    )
    PROJECTION_NOT_ANSWERABLE_MISSING_SOURCE = (
        "projection_not_answerable_missing_source"
    )
    PROJECTION_NOT_ANSWERABLE_MISSING_RECEIPT = (
        "projection_not_answerable_missing_receipt"
    )
    PROJECTION_NOT_ANSWERABLE_CONFLICTED = "projection_not_answerable_conflicted"
    PROJECTION_NOT_ANSWERABLE_SUPPORT_ONLY = "projection_not_answerable_support_only"
    PROJECTION_NOT_ANSWERABLE_PRIOR = "projection_not_answerable_prior"
    PROJECTION_NOT_ANSWERABLE_HIDDEN = "projection_not_answerable_hidden"
    DEMOTED_LOW_AUTHORITY = "demoted_low_authority"
    DEFERRED_EXTERNAL_RUNTIME_OWNER = "deferred_external_runtime_owner"
    NO_CANDIDATE_FOR_RESOLVED_MEMORY_TARGET = "no_candidate_for_resolved_memory_target"
    TRACE_INCOMPLETE = "trace_incomplete"
    RAW_PRIVATE_TEXT_EXCLUDED = "raw_private_text_excluded"
    FULL_ACK_REQUIRES_COMPLETE_RECEIPT_COVERAGE = (
        "full_ack_requires_complete_receipt_coverage"
    )
    UNCLASSIFIED = "unclassified"


def reason_code_values() -> set[str]:
    return {item.value for item in ReasonCode}


def is_reason_code(value: object) -> bool:
    return str(value or "") in reason_code_values()
