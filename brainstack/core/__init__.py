"""IO-free Brainstack core contracts.

This package must stay independent from provider, storage, retrieval, diagnostics,
backend, and installer code.
"""

from __future__ import annotations

from .answerability import (
    AnswerType,
    AnswerabilityState,
    MaxClaimStrength,
    MemoryAnswerability,
)
from .authority import AuthorityClass, SourceRole
from .candidates import CandidateContract
from .errors import (
    AuthorityBoundaryViolation,
    BackendDegraded,
    BrainstackError,
    CapabilityUnavailable,
    MigrationBlocked,
    PublicSurfaceRegression,
    StoreInvariantViolation,
)
from .evidence import EvidenceRef, EvidenceRole
from .ids import EvidenceId, ReceiptId, ScopeKey, StableKey, TraceId, require_non_empty
from .reason_codes import ReasonCode
from .receipts import ProjectionReceipt, ReceiptStatus, WriteReceipt
from .scope import MemoryScope, ScopeKind
from .trace import PacketTrace

__all__ = [
    "AnswerType",
    "AnswerabilityState",
    "AuthorityBoundaryViolation",
    "AuthorityClass",
    "BackendDegraded",
    "BrainstackError",
    "CandidateContract",
    "CapabilityUnavailable",
    "EvidenceId",
    "EvidenceRef",
    "EvidenceRole",
    "MaxClaimStrength",
    "MemoryAnswerability",
    "MemoryScope",
    "MigrationBlocked",
    "PacketTrace",
    "ProjectionReceipt",
    "PublicSurfaceRegression",
    "ReasonCode",
    "ReceiptId",
    "ReceiptStatus",
    "ScopeKey",
    "ScopeKind",
    "SourceRole",
    "StableKey",
    "StoreInvariantViolation",
    "TraceId",
    "WriteReceipt",
    "require_non_empty",
]
