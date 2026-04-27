from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping

from ..core.proactive import (
    PROACTIVE_CONTROL_SCHEMA,
    PROACTIVE_EVENT_SCHEMA,
    PROACTIVE_OUTBOX_SCHEMA,
    ProactiveAuthority,
    ProactiveEventState,
    ProactiveIntendedNextAction,
    ProactiveReasonCode,
)
from .store_protocol import StoreRuntimeBase
from .store_runtime import _decode_json_object, _locked, utc_now_iso


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _decode_json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        loaded = json.loads(str(value))
    except Exception:
        return []
    return loaded if isinstance(loaded, list) else []


def _stable_hash(payload: Mapping[str, Any]) -> str:
    encoded = _json_dumps(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ProactiveStoreMixin(StoreRuntimeBase):
    @_locked
    def _init_proactive_schema_if_needed(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS proactive_events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                kind TEXT NOT NULL,
                principal_scope_key TEXT NOT NULL,
                workspace_scope_key TEXT NOT NULL DEFAULT '',
                workstream_scope_key TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL DEFAULT '',
                priority TEXT NOT NULL DEFAULT 'normal',
                authority TEXT NOT NULL DEFAULT 'proactive_candidate',
                state TEXT NOT NULL DEFAULT 'observed',
                evidence_json TEXT NOT NULL DEFAULT '[]',
                source_ref TEXT NOT NULL DEFAULT '',
                idempotency_key TEXT NOT NULL UNIQUE,
                intended_next_action TEXT NOT NULL DEFAULT 'none',
                reason_code TEXT NOT NULL DEFAULT 'OBSERVED',
                expires_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_proactive_events_scope
                ON proactive_events(principal_scope_key, workspace_scope_key, workstream_scope_key, state);
            CREATE INDEX IF NOT EXISTS idx_proactive_events_kind
                ON proactive_events(kind, priority, updated_at);

            CREATE TABLE IF NOT EXISTS proactive_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason_code TEXT NOT NULL,
                actor TEXT NOT NULL,
                trace_id TEXT NOT NULL DEFAULT '',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_proactive_transitions_event
                ON proactive_transitions(event_id, id);

            CREATE TABLE IF NOT EXISTS proactive_outbox (
                outbox_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                delivery_target TEXT NOT NULL,
                intended_next_action TEXT NOT NULL DEFAULT 'none',
                delivery_state TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_proactive_outbox_state
                ON proactive_outbox(delivery_state, updated_at);

            CREATE TABLE IF NOT EXISTS proactive_attention_ledger (
                principal_scope_key TEXT NOT NULL,
                workspace_scope_key TEXT NOT NULL DEFAULT '',
                workstream_scope_key TEXT NOT NULL DEFAULT '',
                open_proactive_asks INTEGER NOT NULL DEFAULT 0,
                last_notified_keys_json TEXT NOT NULL DEFAULT '[]',
                last_rejected_keys_json TEXT NOT NULL DEFAULT '[]',
                cooldown_until TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (principal_scope_key, workspace_scope_key, workstream_scope_key)
            );
            """
        )
        self.conn.commit()

    def _proactive_row_to_dict(self, row: Any) -> dict[str, Any]:
        return {
            "schema": PROACTIVE_EVENT_SCHEMA,
            "event_id": row["event_id"],
            "source": row["source"],
            "kind": row["kind"],
            "principal_scope_key": row["principal_scope_key"],
            "workspace_scope_key": row["workspace_scope_key"],
            "workstream_scope_key": row["workstream_scope_key"],
            "title": row["title"],
            "summary": row["summary"],
            "priority": row["priority"],
            "authority": row["authority"],
            "state": row["state"],
            "evidence_ids": [str(item) for item in _decode_json_list(row["evidence_json"])],
            "source_ref": row["source_ref"],
            "idempotency_key": row["idempotency_key"],
            "intended_next_action": row["intended_next_action"],
            "reason_code": row["reason_code"],
            "expires_at": row["expires_at"],
            "metadata": _decode_json_object(row["metadata_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _append_proactive_transition(
        self,
        *,
        event_id: str,
        from_state: str | None,
        to_state: str,
        reason_code: str,
        actor: str,
        trace_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO proactive_transitions (
                event_id, from_state, to_state, reason_code, actor, trace_id, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                from_state,
                to_state,
                reason_code,
                actor,
                trace_id,
                _json_dumps(dict(metadata or {})),
                utc_now_iso(),
            ),
        )

    @_locked
    def upsert_proactive_event(
        self,
        *,
        source: str,
        kind: str,
        principal_scope_key: str,
        workspace_scope_key: str = "",
        workstream_scope_key: str = "",
        title: str = "",
        summary: str = "",
        priority: str = "normal",
        authority: str = ProactiveAuthority.PROACTIVE_CANDIDATE.value,
        state: str = ProactiveEventState.OBSERVED.value,
        evidence_ids: Iterable[str] = (),
        source_ref: str = "",
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
        reason_code: str = ProactiveReasonCode.OBSERVED.value,
        expires_at: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        evidence = [str(item) for item in evidence_ids if str(item)]
        fingerprint_payload = {
            "source": str(source),
            "kind": str(kind),
            "principal_scope_key": str(principal_scope_key),
            "workspace_scope_key": str(workspace_scope_key or ""),
            "workstream_scope_key": str(workstream_scope_key or ""),
            "source_ref": str(source_ref or ""),
            "title": str(title or ""),
            "summary": str(summary or ""),
            "evidence": evidence,
        }
        effective_key = str(idempotency_key or _stable_hash(fingerprint_payload))
        event_id = "pe_" + _stable_hash({"idempotency_key": effective_key})[:20]
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT * FROM proactive_events WHERE idempotency_key = ?",
            (effective_key,),
        ).fetchone()
        if existing is None:
            self.conn.execute(
                """
                INSERT INTO proactive_events (
                    event_id, source, kind, principal_scope_key, workspace_scope_key, workstream_scope_key,
                    title, summary, priority, authority, state, evidence_json, source_ref, idempotency_key,
                    intended_next_action, reason_code, expires_at, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    str(source),
                    str(kind),
                    str(principal_scope_key),
                    str(workspace_scope_key or ""),
                    str(workstream_scope_key or ""),
                    str(title or ""),
                    str(summary or ""),
                    str(priority or "normal"),
                    str(authority or ProactiveAuthority.PROACTIVE_CANDIDATE.value),
                    str(state or ProactiveEventState.OBSERVED.value),
                    _json_dumps(evidence),
                    str(source_ref or ""),
                    effective_key,
                    str(intended_next_action or ProactiveIntendedNextAction.NONE.value),
                    str(reason_code or ProactiveReasonCode.OBSERVED.value),
                    expires_at,
                    _json_dumps(dict(metadata or {})),
                    now,
                    now,
                ),
            )
            self._append_proactive_transition(
                event_id=event_id,
                from_state=None,
                to_state=str(state or ProactiveEventState.OBSERVED.value),
                reason_code=str(reason_code or ProactiveReasonCode.OBSERVED.value),
                actor="producer",
                trace_id=trace_id,
                metadata={"created": True},
            )
            material_change = True
        else:
            event_id = str(existing["event_id"])
            old_state = str(existing["state"])
            new_state = str(state or old_state)
            material_change = (
                old_state != new_state
                or str(existing["priority"]) != str(priority or "normal")
                or str(existing["summary"]) != str(summary or "")
                or str(existing["evidence_json"]) != _json_dumps(evidence)
            )
            self.conn.execute(
                """
                UPDATE proactive_events
                SET title = ?, summary = ?, priority = ?, state = ?, evidence_json = ?,
                    intended_next_action = ?, reason_code = ?, expires_at = ?, metadata_json = ?, updated_at = ?
                WHERE event_id = ?
                """,
                (
                    str(title or ""),
                    str(summary or ""),
                    str(priority or "normal"),
                    new_state,
                    _json_dumps(evidence),
                    str(intended_next_action or ProactiveIntendedNextAction.NONE.value),
                    str(reason_code or ProactiveReasonCode.OBSERVED.value),
                    expires_at,
                    _json_dumps(dict(metadata or {})),
                    now,
                    event_id,
                ),
            )
            if old_state != new_state:
                self._append_proactive_transition(
                    event_id=event_id,
                    from_state=old_state,
                    to_state=new_state,
                    reason_code=str(reason_code or ProactiveReasonCode.MATERIAL_CHANGE.value),
                    actor="producer",
                    trace_id=trace_id,
                    metadata={"material_change": material_change},
                )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM proactive_events WHERE event_id = ?", (event_id,)).fetchone()
        payload = self._proactive_row_to_dict(row)
        payload["created"] = existing is None
        payload["material_change"] = material_change
        return payload

    @_locked
    def create_proactive_outbox(
        self,
        *,
        event_id: str,
        delivery_target: str,
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
    ) -> dict[str, Any]:
        event = self.conn.execute("SELECT * FROM proactive_events WHERE event_id = ?", (event_id,)).fetchone()
        if event is None:
            raise KeyError(f"Unknown proactive event: {event_id}")
        effective_key = str(idempotency_key or f"{event_id}:{delivery_target}")
        outbox_id = "po_" + _stable_hash({"idempotency_key": effective_key})[:20]
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO proactive_outbox (
                outbox_id, event_id, idempotency_key, delivery_target, intended_next_action,
                delivery_state, attempt_count, last_error, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'pending', 0, '', ?, ?)
            ON CONFLICT(idempotency_key) DO UPDATE SET updated_at = excluded.updated_at
            """,
            (
                outbox_id,
                event_id,
                effective_key,
                str(delivery_target),
                str(intended_next_action or event["intended_next_action"] or ProactiveIntendedNextAction.NONE.value),
                now,
                now,
            ),
        )
        self._append_proactive_transition(
            event_id=event_id,
            from_state=str(event["state"]),
            to_state=str(event["state"]),
            reason_code=ProactiveReasonCode.OUTBOX_PENDING.value,
            actor="surfacing_policy",
            metadata={"outbox_id": outbox_id, "delivery_target": str(delivery_target)},
        )
        self._update_attention_ledger_for_outbox(event, effective_key)
        self.conn.commit()
        return {"schema": PROACTIVE_OUTBOX_SCHEMA, "outbox_id": outbox_id, "event_id": event_id, "state": "pending"}

    def _update_attention_ledger_for_outbox(self, event: Any, item_key: str) -> None:
        scope = (
            event["principal_scope_key"],
            event["workspace_scope_key"],
            event["workstream_scope_key"],
        )
        existing = self.conn.execute(
            """
            SELECT * FROM proactive_attention_ledger
            WHERE principal_scope_key = ? AND workspace_scope_key = ? AND workstream_scope_key = ?
            """,
            scope,
        ).fetchone()
        now = utc_now_iso()
        notified = []
        open_count = 0
        if existing is not None:
            notified = [str(item) for item in _decode_json_list(existing["last_notified_keys_json"])]
            open_count = int(existing["open_proactive_asks"] or 0)
        if item_key not in notified:
            notified.append(item_key)
        self.conn.execute(
            """
            INSERT INTO proactive_attention_ledger (
                principal_scope_key, workspace_scope_key, workstream_scope_key,
                open_proactive_asks, last_notified_keys_json, last_rejected_keys_json, cooldown_until, updated_at
            ) VALUES (?, ?, ?, ?, ?, '[]', NULL, ?)
            ON CONFLICT(principal_scope_key, workspace_scope_key, workstream_scope_key) DO UPDATE SET
                open_proactive_asks = excluded.open_proactive_asks,
                last_notified_keys_json = excluded.last_notified_keys_json,
                updated_at = excluded.updated_at
            """,
            (*scope, open_count + 1, _json_dumps(notified[-20:]), now),
        )

    @_locked
    def list_proactive_items(
        self,
        *,
        principal_scope_key: str = "",
        state: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if principal_scope_key:
            clauses.append("principal_scope_key = ?")
            params.append(principal_scope_key)
        if state:
            clauses.append("state = ?")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM proactive_events {where} ORDER BY updated_at DESC LIMIT ?",
            (*params, max(1, min(int(limit or 50), 200))),
        ).fetchall()
        return [self._proactive_row_to_dict(row) for row in rows]

    @_locked
    def inspect_proactive_item(self, *, event_id: str) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM proactive_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown proactive event: {event_id}")
        transitions = self.conn.execute(
            "SELECT * FROM proactive_transitions WHERE event_id = ? ORDER BY id ASC",
            (event_id,),
        ).fetchall()
        outbox = self.conn.execute(
            "SELECT * FROM proactive_outbox WHERE event_id = ? ORDER BY created_at ASC",
            (event_id,),
        ).fetchall()
        return {
            "schema": PROACTIVE_CONTROL_SCHEMA,
            "item": self._proactive_row_to_dict(row),
            "transitions": [
                {
                    "id": item["id"],
                    "from_state": item["from_state"],
                    "to_state": item["to_state"],
                    "reason_code": item["reason_code"],
                    "actor": item["actor"],
                    "trace_id": item["trace_id"],
                    "metadata": _decode_json_object(item["metadata_json"]),
                    "created_at": item["created_at"],
                }
                for item in transitions
            ],
            "outbox": [
                {
                    "outbox_id": item["outbox_id"],
                    "delivery_target": item["delivery_target"],
                    "delivery_state": item["delivery_state"],
                    "attempt_count": item["attempt_count"],
                    "last_error": item["last_error"],
                    "created_at": item["created_at"],
                    "updated_at": item["updated_at"],
                }
                for item in outbox
            ],
        }

    @_locked
    def set_proactive_item_state(
        self,
        *,
        event_id: str,
        state: str,
        reason_code: str,
        actor: str = "operator",
        trace_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM proactive_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown proactive event: {event_id}")
        old_state = str(row["state"])
        now = utc_now_iso()
        self.conn.execute(
            "UPDATE proactive_events SET state = ?, reason_code = ?, metadata_json = ?, updated_at = ? WHERE event_id = ?",
            (
                str(state),
                str(reason_code),
                _json_dumps({**_decode_json_object(row["metadata_json"]), **dict(metadata or {})}),
                now,
                event_id,
            ),
        )
        self._append_proactive_transition(
            event_id=event_id,
            from_state=old_state,
            to_state=str(state),
            reason_code=str(reason_code),
            actor=str(actor),
            trace_id=trace_id,
            metadata=dict(metadata or {}),
        )
        if state in {ProactiveEventState.ACCEPTED.value, ProactiveEventState.REJECTED.value}:
            self._close_attention_ask(row, rejected=state == ProactiveEventState.REJECTED.value)
        self.conn.commit()
        return self.inspect_proactive_item(event_id=event_id)

    def _close_attention_ask(self, row: Any, *, rejected: bool) -> None:
        scope = (
            row["principal_scope_key"],
            row["workspace_scope_key"],
            row["workstream_scope_key"],
        )
        existing = self.conn.execute(
            """
            SELECT * FROM proactive_attention_ledger
            WHERE principal_scope_key = ? AND workspace_scope_key = ? AND workstream_scope_key = ?
            """,
            scope,
        ).fetchone()
        if existing is None:
            return
        rejected_keys = [str(item) for item in _decode_json_list(existing["last_rejected_keys_json"])]
        if rejected and row["idempotency_key"] not in rejected_keys:
            rejected_keys.append(str(row["idempotency_key"]))
        self.conn.execute(
            """
            UPDATE proactive_attention_ledger
            SET open_proactive_asks = ?, last_rejected_keys_json = ?, updated_at = ?
            WHERE principal_scope_key = ? AND workspace_scope_key = ? AND workstream_scope_key = ?
            """,
            (
                max(0, int(existing["open_proactive_asks"] or 0) - 1),
                _json_dumps(rejected_keys[-20:]),
                utc_now_iso(),
                *scope,
            ),
        )

    @_locked
    def proactive_recent_cost(self, *, limit: int = 100) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT metadata_json FROM proactive_events ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(int(limit or 100), 500)),),
        ).fetchall()
        provider_calls = 0
        prompt_tokens = 0
        completion_tokens = 0
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            provider_calls += int(metadata.get("provider_calls") or 0)
            prompt_tokens += int(metadata.get("prompt_tokens") or 0)
            completion_tokens += int(metadata.get("completion_tokens") or 0)
        return {
            "schema": PROACTIVE_CONTROL_SCHEMA,
            "provider_calls": provider_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "sample_size": len(rows),
        }

    @_locked
    def list_pending_proactive_outbox(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT o.*, e.title, e.summary, e.kind, e.priority, e.evidence_json
            FROM proactive_outbox o
            JOIN proactive_events e ON e.event_id = o.event_id
            WHERE o.delivery_state = 'pending'
            ORDER BY o.created_at ASC
            LIMIT ?
            """,
            (max(1, min(int(limit or 50), 200)),),
        ).fetchall()
        return [
            {
                "schema": PROACTIVE_OUTBOX_SCHEMA,
                "outbox_id": row["outbox_id"],
                "event_id": row["event_id"],
                "delivery_target": row["delivery_target"],
                "intended_next_action": row["intended_next_action"],
                "delivery_state": row["delivery_state"],
                "attempt_count": row["attempt_count"],
                "last_error": row["last_error"],
                "title": row["title"],
                "summary": row["summary"],
                "kind": row["kind"],
                "priority": row["priority"],
                "evidence_ids": [str(item) for item in _decode_json_list(row["evidence_json"])],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    @_locked
    def mark_proactive_outbox(
        self,
        *,
        outbox_id: str,
        delivery_state: str,
        last_error: str = "",
        actor: str = "surfacing_policy",
    ) -> dict[str, Any]:
        row = self.conn.execute("SELECT * FROM proactive_outbox WHERE outbox_id = ?", (outbox_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown proactive outbox row: {outbox_id}")
        now = utc_now_iso()
        self.conn.execute(
            """
            UPDATE proactive_outbox
            SET delivery_state = ?, last_error = ?, attempt_count = attempt_count + 1, updated_at = ?
            WHERE outbox_id = ?
            """,
            (str(delivery_state), str(last_error or ""), now, outbox_id),
        )
        self._append_proactive_transition(
            event_id=str(row["event_id"]),
            from_state=None,
            to_state=str(delivery_state),
            reason_code=ProactiveReasonCode.NOTIFIED.value if delivery_state == "delivered" else ProactiveReasonCode.BLOCKED.value,
            actor=actor,
            metadata={"outbox_id": outbox_id, "delivery_state": str(delivery_state), "last_error": str(last_error or "")},
        )
        self.conn.commit()
        return {"schema": PROACTIVE_OUTBOX_SCHEMA, "outbox_id": outbox_id, "delivery_state": str(delivery_state)}
