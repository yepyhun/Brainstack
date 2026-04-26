"""Trace contracts linking ingest, write, recall, packet, and answerability."""

from __future__ import annotations

from dataclasses import dataclass, field

from .ids import EvidenceId, ReceiptId, TraceId


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
