from __future__ import annotations

import json
from typing import Any, Mapping

from .store_runtime import _cursor_lastrowid, utc_now_iso
from ..canonical_memory_event import validate_canonical_memory_event


class CanonicalMemoryEventStoreMixin:
    def record_canonical_memory_event(self, event: Mapping[str, Any]) -> int:
        issues = validate_canonical_memory_event(event)
        if issues:
            raise ValueError(f"invalid canonical memory event: {', '.join(issues)}")
        event_group = event["event"]
        source = event["source"]
        scope = event["scope"]
        claim = event["claim"]
        authority = event["authority"]
        now = utc_now_iso()
        payload = json.dumps(event, ensure_ascii=True, sort_keys=True)
        cur = self.conn.execute(
            """
            INSERT OR IGNORE INTO canonical_memory_events (
                event_id, idempotency_key, schema_version, event_type,
                source_event_id, source_span_id, principal_scope_key, workspace_scope_key,
                session_id, stable_fact_id, target_slot, authority_class,
                truth_eligible, support_visibility, receipt_id, event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event_group.get("event_id") or ""),
                str(event_group.get("idempotency_key") or ""),
                str(event_group.get("schema_version") or ""),
                str(event_group.get("event_type") or ""),
                str(source.get("source_event_id") or ""),
                str(source.get("source_span_id") or ""),
                str(scope.get("principal_scope_key") or ""),
                str(scope.get("workspace_scope_key") or ""),
                str(scope.get("session_id") or ""),
                str(claim.get("stable_fact_id") or ""),
                str(claim.get("target_slot") or ""),
                str(authority.get("authority_class") or ""),
                1 if bool(authority.get("truth_eligible")) else 0,
                str(authority.get("support_visibility") or ""),
                str(authority.get("receipt_id") or ""),
                payload,
                now,
            ),
        )
        inserted = cur.rowcount > 0
        row = self.conn.execute(
            "SELECT id FROM canonical_memory_events WHERE idempotency_key = ?",
            (str(event_group.get("idempotency_key") or ""),),
        ).fetchone()
        if row is not None:
            if inserted and hasattr(self, "_upsert_current_truth_l0_from_event"):
                self._upsert_current_truth_l0_from_event(event, projected_at=now)
            self.conn.commit()
            return int(row["id"])
        cur = self.conn.execute(
            """
            INSERT INTO canonical_memory_events (
                event_id, idempotency_key, schema_version, event_type,
                event_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(event_group.get("event_id") or ""),
                str(event_group.get("idempotency_key") or ""),
                str(event_group.get("schema_version") or ""),
                str(event_group.get("event_type") or ""),
                payload,
                now,
            ),
        )
        if hasattr(self, "_upsert_current_truth_l0_from_event"):
            self._upsert_current_truth_l0_from_event(event, projected_at=now)
        self.conn.commit()
        return _cursor_lastrowid(cur)

    def list_canonical_memory_events(
        self,
        *,
        limit: int = 100,
        source_span_id: str = "",
        receipt_id: str = "",
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if source_span_id:
            clauses.append("source_span_id = ?")
            params.append(source_span_id)
        if receipt_id:
            clauses.append("receipt_id = ?")
            params.append(receipt_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT id, event_id, idempotency_key, schema_version, event_type,
                   source_event_id, source_span_id, principal_scope_key, workspace_scope_key,
                   session_id, stable_fact_id, target_slot, authority_class,
                   truth_eligible, support_visibility, receipt_id, event_json, created_at
            FROM canonical_memory_events
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            (*params, max(int(limit or 0), 1)),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["truth_eligible"] = bool(item.get("truth_eligible"))
            try:
                item["event"] = json.loads(str(item.pop("event_json") or "{}"))
            except (TypeError, ValueError):
                item["event"] = {}
            result.append(item)
        return result
