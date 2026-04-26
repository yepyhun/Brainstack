"""Stable identifiers shared by Brainstack contract modules."""

from __future__ import annotations

from typing import NewType

EvidenceId = NewType("EvidenceId", str)
StableKey = NewType("StableKey", str)
ReceiptId = NewType("ReceiptId", str)
TraceId = NewType("TraceId", str)
ScopeKey = NewType("ScopeKey", str)


def require_non_empty(value: str, *, field: str) -> str:
    """Reject empty public contract identifiers at object construction time."""
    if not value:
        raise ValueError(f"{field} must be non-empty")
    return value
