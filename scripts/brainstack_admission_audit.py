#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def _decode(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _violation(kind: str, severity: str, row: sqlite3.Row, reason: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "severity": severity,
        "row_id": int(row["id"]),
        "reason": reason,
        "candidate_repair": "operator_review_demote_or_quarantine",
    }


def audit(db_path: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        violations: list[dict[str, Any]] = []
        for row in conn.execute(
            """
            SELECT id, stable_key, category, content, source, metadata_json
            FROM profile_items
            WHERE active = 1
            ORDER BY id ASC
            """
        ):
            stable_key = str(row["stable_key"] or "")
            source = str(row["source"] or "")
            metadata = _decode(row["metadata_json"])
            admission = metadata.get("admission") if isinstance(metadata.get("admission"), dict) else {}
            if stable_key.split("::", 1)[0] == "identity:name" and source.startswith("tier2:"):
                item = _violation("profile", "P0", row, "derived_generic_identity_name_active")
                item.update({"stable_key": stable_key, "content": row["content"]})
                violations.append(item)
            if admission and admission.get("truth_eligible") is False:
                item = _violation("profile", "P0", row, "non_truth_eligible_profile_row_active")
                item.update({"stable_key": stable_key, "decision": admission.get("decision")})
                violations.append(item)

        for row in conn.execute(
            """
            SELECT gs.id, e.canonical_name AS subject, gs.attribute, gs.value_text, gs.source, gs.metadata_json
            FROM graph_states gs
            JOIN graph_entities e ON e.id = gs.entity_id
            WHERE gs.is_current = 1
            ORDER BY gs.id ASC
            """
        ):
            attribute = str(row["attribute"] or "").casefold()
            value = str(row["value_text"] or "").casefold()
            metadata = _decode(row["metadata_json"])
            admission = metadata.get("admission") if isinstance(metadata.get("admission"), dict) else {}
            if any(token in f"{attribute} {value}" for token in ("shell_access", "terminal", "tool_access", "capability")):
                item = _violation("graph_state", "P0", row, "runtime_capability_active_graph_truth")
                item.update({"subject": row["subject"], "attribute": row["attribute"], "value": row["value_text"]})
                violations.append(item)
            if admission and admission.get("truth_eligible") is False:
                item = _violation("graph_state", "P0", row, "non_truth_eligible_graph_state_active")
                item.update({"subject": row["subject"], "attribute": row["attribute"], "decision": admission.get("decision")})
                violations.append(item)

        for row in conn.execute(
            """
            SELECT r.id, s.canonical_name AS subject, r.predicate, r.object_text, r.source, r.metadata_json
            FROM graph_relations r
            JOIN graph_entities s ON s.id = r.subject_entity_id
            WHERE r.active = 1
            ORDER BY r.id ASC
            """
        ):
            predicate = str(row["predicate"] or "").casefold()
            obj = str(row["object_text"] or "").casefold()
            metadata = _decode(row["metadata_json"])
            admission = metadata.get("admission") if isinstance(metadata.get("admission"), dict) else {}
            if any(token in f"{predicate} {obj}" for token in ("shell_access", "terminal", "tool_access", "capability")):
                item = _violation("graph_relation", "P0", row, "runtime_capability_active_graph_relation")
                item.update({"subject": row["subject"], "predicate": row["predicate"], "object": row["object_text"]})
                violations.append(item)
            if admission and admission.get("truth_eligible") is False:
                item = _violation("graph_relation", "P0", row, "non_truth_eligible_graph_relation_active")
                item.update({"subject": row["subject"], "predicate": row["predicate"], "decision": admission.get("decision")})
                violations.append(item)

        return {
            "schema": "brainstack.admission_audit.v1",
            "db_path": str(Path(db_path)),
            "mutation_performed": False,
            "violation_count": len(violations),
            "p0_count": sum(1 for item in violations if item.get("severity") == "P0"),
            "violations": violations,
        }
    finally:
        conn.close()


def _now(conn: sqlite3.Connection) -> str:
    return str(conn.execute("SELECT strftime('%Y-%m-%dT%H:%M:%fZ','now')").fetchone()[0])


def _ensure_admission_receipts_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS admission_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admission_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            policy_version TEXT NOT NULL,
            slot_registry_version TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            source_event_id TEXT NOT NULL DEFAULT '',
            source_turn_id TEXT NOT NULL DEFAULT '',
            source_span_id TEXT NOT NULL DEFAULT '',
            turn_role TEXT NOT NULL DEFAULT '',
            assertion_speaker TEXT NOT NULL DEFAULT '',
            span_kind TEXT NOT NULL DEFAULT '',
            target_shelf TEXT NOT NULL DEFAULT '',
            target_slot TEXT NOT NULL DEFAULT '',
            stable_key TEXT NOT NULL DEFAULT '',
            truth_eligible INTEGER NOT NULL DEFAULT 0,
            support_visibility TEXT NOT NULL DEFAULT 'inspect_only',
            durable_row_id INTEGER NOT NULL DEFAULT 0,
            candidate_excerpt TEXT NOT NULL DEFAULT '',
            candidate_hash TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admission_receipts_decision
        ON admission_receipts(decision, target_shelf, target_slot, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_admission_receipts_trace
        ON admission_receipts(trace_id, created_at DESC);
        """
    )


def _receipt(
    conn: sqlite3.Connection,
    *,
    violation: dict[str, Any],
    target_shelf: str,
    target_slot: str,
    stable_key: str,
    durable_row_id: int,
    candidate_excerpt: str,
    reason: str,
) -> None:
    now = _now(conn)
    candidate_hash = hashlib.sha256(str(candidate_excerpt or "").encode("utf-8")).hexdigest()
    metadata = {
        "repair": {
            "schema": "brainstack.admission_repair.v1",
            "violation": violation,
            "repair_action": "operator_approved_demote_or_quarantine",
            "raw_transcript_deleted": False,
        }
    }
    conn.execute(
        """
        INSERT INTO admission_receipts (
            admission_id, candidate_id, trace_id, policy_version, slot_registry_version,
            decision, reason_code, source_event_id, source_turn_id, source_span_id,
            turn_role, assertion_speaker, span_kind, target_shelf, target_slot,
            stable_key, truth_eligible, support_visibility, durable_row_id,
            candidate_excerpt, candidate_hash, metadata_json, created_at
        ) VALUES (?, ?, '', 'brainstack.admission.repair.v1', 'brainstack.slot_registry.v1',
                  'QUARANTINE_PROPOSAL', ?, '', '', '',
                  '', 'unknown', 'unknown', ?, ?, ?, 0, 'inspect_only', ?,
                  ?, ?, ?, ?)
        """,
        (
            f"repair:{target_shelf}:{durable_row_id}:{candidate_hash[:12]}",
            f"repair:{target_shelf}:{durable_row_id}:{candidate_hash[:12]}",
            reason,
            target_shelf,
            target_slot,
            stable_key,
            int(durable_row_id),
            str(candidate_excerpt or "")[:240],
            candidate_hash,
            json.dumps(metadata, ensure_ascii=True, sort_keys=True),
            now,
        ),
    )


def repair(db_path: str) -> dict[str, Any]:
    before = audit(db_path)
    db_file = Path(db_path)
    backup_path = db_file.with_name(f"{db_file.name}.pre-admission-repair.bak")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        backup_conn = sqlite3.connect(backup_path)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()
        _ensure_admission_receipts_schema(conn)
        now = _now(conn)
        repaired: list[dict[str, Any]] = []
        for violation in before.get("violations", []):
            kind = str(violation.get("kind") or "")
            row_id = int(violation.get("row_id") or 0)
            if row_id <= 0:
                continue
            if kind == "profile":
                row = conn.execute(
                    "SELECT id, stable_key, content FROM profile_items WHERE id = ?",
                    (row_id,),
                ).fetchone()
                if not row:
                    continue
                conn.execute("UPDATE profile_items SET active = 0, updated_at = ? WHERE id = ?", (now, row_id))
                conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (row_id,))
                _receipt(
                    conn,
                    violation=violation,
                    target_shelf="profile",
                    target_slot="identity.name",
                    stable_key=str(row["stable_key"] or ""),
                    durable_row_id=row_id,
                    candidate_excerpt=str(row["content"] or ""),
                    reason=str(violation.get("reason") or "legacy_admission_repair"),
                )
                repaired.append({"kind": kind, "row_id": row_id, "action": "deactivate_profile_row"})
            elif kind == "graph_state":
                row = conn.execute(
                    "SELECT id, attribute, value_text FROM graph_states WHERE id = ?",
                    (row_id,),
                ).fetchone()
                if not row:
                    continue
                conn.execute("UPDATE graph_states SET is_current = 0, valid_to = ? WHERE id = ?", (now, row_id))
                _receipt(
                    conn,
                    violation=violation,
                    target_shelf="graph",
                    target_slot=str(row["attribute"] or ""),
                    stable_key=str(row["attribute"] or ""),
                    durable_row_id=row_id,
                    candidate_excerpt=str(row["value_text"] or ""),
                    reason=str(violation.get("reason") or "legacy_admission_repair"),
                )
                repaired.append({"kind": kind, "row_id": row_id, "action": "demote_graph_state"})
            elif kind == "graph_relation":
                row = conn.execute(
                    "SELECT id, predicate, object_text FROM graph_relations WHERE id = ?",
                    (row_id,),
                ).fetchone()
                if not row:
                    continue
                conn.execute("UPDATE graph_relations SET active = 0 WHERE id = ?", (row_id,))
                _receipt(
                    conn,
                    violation=violation,
                    target_shelf="graph",
                    target_slot=str(row["predicate"] or ""),
                    stable_key=str(row["predicate"] or ""),
                    durable_row_id=row_id,
                    candidate_excerpt=str(row["object_text"] or ""),
                    reason=str(violation.get("reason") or "legacy_admission_repair"),
                )
                repaired.append({"kind": kind, "row_id": row_id, "action": "deactivate_graph_relation"})
        conn.commit()
    finally:
        conn.close()
    after = audit(db_path)
    return {
        "schema": "brainstack.admission_repair.v1",
        "db_path": str(db_file),
        "backup_path": str(backup_path),
        "raw_transcript_deleted": False,
        "before_p0_count": int(before.get("p0_count") or 0),
        "after_p0_count": int(after.get("p0_count") or 0),
        "repaired": repaired,
        "after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only admission-policy audit for active durable Brainstack rows.")
    parser.add_argument("db_path")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--repair", action="store_true", help="Demote/quarantine detected active violations and write repair receipts.")
    args = parser.parse_args()
    report = repair(args.db_path) if args.repair else audit(args.db_path)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    p0_count = int(report.get("p0_count") if "p0_count" in report else report.get("after_p0_count") or 0)
    return 1 if p0_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
