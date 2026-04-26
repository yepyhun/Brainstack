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
    UNCLASSIFIED = "unclassified"
