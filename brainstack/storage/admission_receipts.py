from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import Any, Dict, _cursor_lastrowid, json, utc_now_iso
from ..core.admission import AdmissionDecision


class AdmissionReceiptStoreMixin(StoreRuntimeBase):
    def record_admission_receipt(
        self,
        *,
        decision: AdmissionDecision,
        durable_row_id: int = 0,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        proposal = decision.proposal
        now = utc_now_iso()
        payload = dict(metadata or {})
        payload.setdefault("admission", decision.metadata_payload().get("admission", {}))
        cur = self.conn.execute(
            """
            INSERT INTO admission_receipts (
                admission_id, candidate_id, trace_id, policy_version, slot_registry_version,
                decision, reason_code, source_event_id, source_turn_id, source_span_id,
                turn_role, assertion_speaker, span_kind, target_shelf, target_slot,
                stable_key, truth_eligible, support_visibility, durable_row_id,
                candidate_excerpt, candidate_hash, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal.claim_id,
                proposal.claim_id,
                proposal.trace_id,
                decision.policy_version,
                decision.slot_registry_version,
                decision.decision.value,
                decision.reason_code,
                proposal.source_event_id,
                proposal.source_turn_id,
                proposal.source_span_id,
                proposal.turn_role,
                proposal.assertion_speaker.value,
                proposal.span_kind.value,
                proposal.target_shelf,
                decision.target_slot,
                decision.stable_key,
                1 if decision.truth_eligible else 0,
                decision.support_visibility.value,
                int(durable_row_id or 0),
                proposal.candidate_value[:240],
                proposal.source_text_hash,
                json.dumps(payload, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        self.conn.commit()
        return _cursor_lastrowid(cur)

    def list_admission_receipts(self, *, limit: int = 100) -> list[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, admission_id, candidate_id, trace_id, policy_version, slot_registry_version,
                   decision, reason_code, source_event_id, source_turn_id, source_span_id,
                   turn_role, assertion_speaker, span_kind, target_shelf, target_slot,
                   stable_key, truth_eligible, support_visibility, durable_row_id,
                   candidate_excerpt, candidate_hash, metadata_json, created_at
            FROM admission_receipts
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(int(limit or 0), 1),),
        ).fetchall()
        result: list[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_metadata = item.pop("metadata_json", "{}")
            try:
                item["metadata"] = json.loads(raw_metadata or "{}")
            except (TypeError, ValueError):
                item["metadata"] = {}
            item["truth_eligible"] = bool(item.get("truth_eligible"))
            result.append(item)
        return result
