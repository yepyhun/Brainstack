#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.persistent_bloat import build_persistent_bloat_report  # noqa: E402

PRIVATE_SOAK_SENTINEL = "PRIVATE_PERSISTENT_BLOAT_SOAK_TEXT_MUST_NOT_LEAK"
DEFAULT_SOAK_ITERATIONS = 24


def _hash(value: str, *, length: int = 32) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _timestamp(index: int) -> str:
    return f"2026-02-01T00:{index % 60:02d}:00Z"


def _record_receipt(store: BrainstackStore, suffix: str, *, decision: str = "ACCEPT_DURABLE", stable_key: str = "identity:name") -> None:
    store.conn.execute(
        """
        INSERT INTO admission_receipts (
            admission_id, candidate_id, trace_id, policy_version, slot_registry_version, decision,
            reason_code, source_event_id, source_turn_id, source_span_id, turn_role, assertion_speaker,
            span_kind, target_shelf, target_slot, stable_key, truth_eligible, support_visibility,
            durable_row_id, candidate_excerpt, candidate_hash, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"admission-{suffix}",
            f"candidate-{suffix}",
            f"trace-{suffix}",
            "brainstack.admission.v1",
            "brainstack.slot_registry.v1",
            decision,
            "accepted" if decision == "ACCEPT_DURABLE" else "support_or_rejected",
            f"turn-{suffix}",
            f"turn-number-{suffix}",
            f"span-{suffix}",
            "user",
            "user",
            "explicit",
            "profile",
            stable_key.replace(":", "."),
            stable_key,
            1 if decision == "ACCEPT_DURABLE" else 0,
            "answer_evidence" if decision == "ACCEPT_DURABLE" else "normal",
            1,
            "candidate excerpt hash only",
            _hash(f"candidate-{suffix}"),
            "{}",
            _timestamp(len(suffix)),
        ),
    )


def _canonical_event(
    suffix: str,
    *,
    event_type: str,
    stable_fact_id: str,
    truth_eligible: bool,
    support_visibility: str,
    budget_class: str,
    authority_critical: bool,
    memory_kind: str = "profile",
) -> dict[str, Any]:
    digest = hashlib.sha256(suffix.encode("utf-8")).hexdigest()
    return {
        "event": {
            "event_id": f"cme_{digest[:24]}",
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": "sha256:" + digest[:48],
        },
        "source": {
            "source_event_id": f"turn-{suffix}",
            "source_span_id": f"span-{suffix}",
            "source_quote_hash": _hash(f"quote-{suffix}"),
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": _timestamp(len(suffix)),
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": "principal:soak",
            "workspace_scope_key": f"workspace:{suffix[-1] if suffix else '0'}",
            "session_id": "session:soak",
            "project_id": f"project:{suffix[-1] if suffix else '0'}",
        },
        "claim": {
            "memory_kind": memory_kind,
            "target_slot": stable_fact_id.replace(":", "."),
            "subject_ref": _hash(f"subject-{suffix}", length=24),
            "predicate": "is",
            "object_ref": _hash(f"object-{suffix}", length=24),
            "normalized_value_hash": _hash(f"value-{suffix}"),
            "stable_fact_id": stable_fact_id,
        },
        "authority": {
            "authority_class": "user_asserted",
            "truth_eligible": bool(truth_eligible),
            "support_visibility": support_visibility,
            "confidence": 0.9,
            "admission_decision_id": f"decision-{suffix}",
            "receipt_id": f"receipt-{suffix}" if event_type == "durable_fact_committed" else "",
        },
        "temporal": {
            "valid_from": _timestamp(len(suffix)),
            "valid_to": "",
            "transaction_time": _timestamp(len(suffix)),
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [_hash(f"subject-{suffix}", length=24)],
            "relation_refs": [],
            "budget_class": budget_class,
            "authority_critical": bool(authority_critical),
            "projection_hints": {"graph_ready": memory_kind.startswith("graph"), "budget_ready": True, "multihop_ready": False},
        },
        "trace": {
            "proposal_id": f"proposal-{suffix}",
            "donor_trace": {"donor": "hindsight-compatible"},
            "policy_versions": {"admission": "brainstack.admission.v1", "slot_registry": "brainstack.slot_registry.v1"},
        },
        "extensions": {},
    }


def seed_persistent_bloat_soak(store: BrainstackStore, *, iterations: int = DEFAULT_SOAK_ITERATIONS) -> dict[str, int]:
    """Seed a deterministic long-session bloat fixture without relying on raw text in reports."""

    iterations = max(1, int(iterations or DEFAULT_SOAK_ITERATIONS))
    store.conn.execute(
        "INSERT INTO corpus_documents (stable_key, title, doc_kind, source, metadata_json, created_at, updated_at, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("soak:doc", "Soak doc", "note", "soak", "{}", _timestamp(0), _timestamp(0), 1),
    )
    doc_id = store.conn.execute("SELECT id FROM corpus_documents WHERE stable_key = 'soak:doc'").fetchone()["id"]
    graph_entity_ids: list[int] = []
    for project_index in range(3):
        store.conn.execute(
            "INSERT INTO graph_entities (canonical_name, normalized_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (f"Project {project_index}", f"project-{project_index}", _timestamp(project_index), _timestamp(project_index)),
        )
        graph_entity_ids.append(int(store.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]))

    for index in range(iterations):
        project_id = index % 3
        suffix = f"{index:04d}"
        _record_receipt(store, f"answer-{suffix}", stable_key="identity:preferred_name")
        store.upsert_profile_item(
            stable_key=f"identity:preferred_name:{index}",
            category="identity",
            content=f"Repeated preferred name {project_id} {PRIVATE_SOAK_SENTINEL}",
            source="soak",
            confidence=0.9,
            metadata={"principal_scope_key": "principal:soak", "project_id": f"project:{project_id}"},
        )
        store.record_canonical_memory_event(
            _canonical_event(
                f"answer-{suffix}",
                event_type="durable_fact_committed",
                stable_fact_id="identity:preferred_name",
                truth_eligible=True,
                support_visibility="answer_evidence",
                budget_class="task_relevant",
                authority_critical=True,
            )
        )
        store.record_canonical_memory_event(
            _canonical_event(
                f"support-{suffix}",
                event_type="support_event",
                stable_fact_id=f"support:{suffix}",
                truth_eligible=False,
                support_visibility="normal",
                budget_class="support_only",
                authority_critical=False,
                memory_kind="support_only",
            )
        )
        if index % 2 == 0:
            store.record_canonical_memory_event(
                _canonical_event(
                    f"reject-{suffix}",
                    event_type="proposal_rejected",
                    stable_fact_id="identity:preferred_name",
                    truth_eligible=False,
                    support_visibility="inspect_only",
                    budget_class="archived",
                    authority_critical=False,
                )
            )
        if index % 3 == 0:
            store.record_canonical_memory_event(
                _canonical_event(
                    f"correct-{suffix}",
                    event_type="corrected_false_event",
                    stable_fact_id="identity:preferred_name",
                    truth_eligible=False,
                    support_visibility="contradiction_only",
                    budget_class="archived",
                    authority_critical=False,
                )
            )
        store.conn.execute(
            "INSERT INTO transcript_entries (session_id, turn_number, kind, content, source, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("session:soak", index, "user" if index % 2 else "assistant", f"{PRIVATE_SOAK_SENTINEL} transcript {index}", "soak", "{}", _timestamp(index)),
        )
        store.conn.execute(
            "INSERT INTO continuity_events (session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("session:soak", index, "summary", f"{PRIVATE_SOAK_SENTINEL} continuity {index}", "soak", "{}", _timestamp(index), _timestamp(index)),
        )
        store.conn.execute(
            "INSERT INTO corpus_sections (document_id, section_index, heading, content, token_estimate, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, index, f"Section {index}", f"{PRIVATE_SOAK_SENTINEL} corpus {index}", 25, "{}", _timestamp(index)),
        )
        entity_id = graph_entity_ids[project_id]
        store.conn.execute(
            "INSERT INTO graph_states (entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_id, "status", f"prior-{index}", "soak", "{}", _timestamp(index), _timestamp(index + 1), 0),
        )
        state_id = int(store.conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        if index % 4 == 0:
            store.conn.execute(
                "INSERT INTO graph_conflicts (entity_id, attribute, current_state_id, candidate_value_text, candidate_source, metadata_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entity_id, "status", state_id, f"candidate-{index}", "soak", "{}", "open", _timestamp(index), _timestamp(index)),
            )
        if index % 5 == 0:
            event = store.upsert_proactive_event(
                source="soak",
                kind="evolver_signal",
                principal_scope_key="principal:soak",
                workspace_scope_key=f"workspace:{project_id}",
                title=f"Soak wake {index}",
                summary=f"{PRIVATE_SOAK_SENTINEL} proactive {index}",
                priority="normal",
                state="observed",
                source_ref=f"soak:{index}",
            )
            store.create_proactive_outbox(event_id=event["event_id"], delivery_target="agent")
        store.conn.execute(
            "INSERT INTO operating_records (stable_key, principal_scope_key, record_type, content, owner, source, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (f"recent:{index}", "principal:soak", "recent_work_summary", f"{PRIVATE_SOAK_SENTINEL} work {index}", "agent", "soak", "{}", _timestamp(index), _timestamp(index)),
        )
    store.conn.commit()
    return {
        "iterations": iterations,
        "canonical_events": store.conn.execute("SELECT COUNT(*) AS count FROM canonical_memory_events").fetchone()["count"],
        "transcript_entries": store.conn.execute("SELECT COUNT(*) AS count FROM transcript_entries").fetchone()["count"],
        "continuity_events": store.conn.execute("SELECT COUNT(*) AS count FROM continuity_events").fetchone()["count"],
        "proactive_events": store.conn.execute("SELECT COUNT(*) AS count FROM proactive_events").fetchone()["count"],
    }


def build_persistent_bloat_soak_report(
    *,
    db_path: Path | None = None,
    iterations: int = DEFAULT_SOAK_ITERATIONS,
    thresholds: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else Path(tempfile.mkdtemp()) / "persistent-bloat-soak.sqlite3"
    if path.exists():
        path.unlink()
    store = BrainstackStore(str(path))
    store.open()
    try:
        seed_counts = seed_persistent_bloat_soak(store, iterations=iterations)
        effective_thresholds = {
            "support_only_ratio_warn": 1.0,
            "duplicate_strength_warn": 1.0,
            "write_amplification_warn": 6.0,
            **dict(thresholds or {}),
        }
        report = build_persistent_bloat_report(store, thresholds=effective_thresholds, max_projection_events=max(2000, iterations * 4))
    finally:
        store.close()
    return {
        "schema": "brainstack.persistent_bloat_soak.v1",
        "status": report["status"],
        "public_safe": bool(report.get("public_safe")),
        "db_path": str(path),
        "seed_counts": seed_counts,
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Brainstack persistent memory bloat soak.")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--iterations", type=int, default=DEFAULT_SOAK_ITERATIONS)
    args = parser.parse_args()
    payload = build_persistent_bloat_soak_report(db_path=args.db, iterations=args.iterations)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "status": payload["status"],
                "public_safe": payload["public_safe"],
                "issue_count": payload["report"].get("issue_count"),
                "issues": payload["report"].get("issues"),
                "seed_counts": payload["seed_counts"],
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
