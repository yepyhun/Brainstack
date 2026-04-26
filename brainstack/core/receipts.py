"""Write and projection receipt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .ids import ReceiptId, StableKey, TraceId
from .reason_codes import ReasonCode


class ReceiptStatus(StrEnum):
    PENDING = "pending"
    COMMITTED = "committed"
    FAILED = "failed"
    SKIPPED = "skipped"
    MISSING_AFTER_TIMEOUT = "missing_after_timeout"
    CONFLICT = "conflict"
    UNKNOWN_HOST_RECEIPT = "unknown_host_receipt"


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    receipt_id: ReceiptId
    turn_trace_id: TraceId
    stable_key: StableKey | None
    status: ReceiptStatus
    reason_code: ReasonCode = ReasonCode.UNCLASSIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "receipt_id": str(self.receipt_id),
            "turn_trace_id": str(self.turn_trace_id),
            "stable_key": None if self.stable_key is None else str(self.stable_key),
            "status": self.status.value,
            "reason_code": self.reason_code.value,
        }


@dataclass(frozen=True, slots=True)
class ProjectionReceipt:
    host_receipt_id: ReceiptId | None
    brainstack_receipt_id: ReceiptId | None
    stable_key: StableKey | None
    status: ReceiptStatus
    parity_observable: bool
    reason_code: ReasonCode = ReasonCode.UNCLASSIFIED

    def to_dict(self) -> dict[str, object]:
        return {
            "host_receipt_id": (
                None if self.host_receipt_id is None else str(self.host_receipt_id)
            ),
            "brainstack_receipt_id": (
                None if self.brainstack_receipt_id is None else str(self.brainstack_receipt_id)
            ),
            "stable_key": None if self.stable_key is None else str(self.stable_key),
            "status": self.status.value,
            "parity_observable": self.parity_observable,
            "reason_code": self.reason_code.value,
        }
