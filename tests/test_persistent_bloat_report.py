from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brainstack.db import BrainstackStore
from brainstack.persistent_bloat import (
    PERSISTENT_BLOAT_POLICY_SCHEMA,
    PERSISTENT_BLOAT_REPORT_SCHEMA,
    build_persistent_bloat_report,
)

PRIVATE_TEXT = "Laura private raw memory text must never appear"


def _store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    return store


def _canonical_event(
    suffix: str,
    *,
    event_type: str = "durable_fact_committed",
    stable_fact_id: str = "identity:name",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    budget_class: str = "task_relevant",
    authority_critical: bool | None = None,
    receipt_id: str = "receipt-1",
) -> dict[str, Any]:
    if authority_critical is None:
        authority_critical = bool(truth_eligible)
    return {
        "event": {
            "event_id": f"cme_{suffix}",
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{suffix:0<48}"[:55],
        },
        "source": {
            "source_event_id": f"turn-{suffix}",
            "source_span_id": f"span-{suffix}",
            "source_quote_hash": f"sha256:quote-{suffix}",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-01-01T00:00:00Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": "principal:test",
            "workspace_scope_key": "workspace:test",
            "session_id": "session-test",
            "project_id": "project-test",
        },
        "claim": {
            "memory_kind": "profile",
            "target_slot": stable_fact_id.replace(":", "."),
            "subject_ref": "sha256:subject",
            "predicate": "is",
            "object_ref": f"sha256:object-{suffix}",
            "normalized_value_hash": f"sha256:value-{suffix}",
            "stable_fact_id": stable_fact_id,
        },
        "authority": {
            "authority_class": "user_asserted",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.9,
            "admission_decision_id": f"decision-{suffix}",
            "receipt_id": receipt_id if event_type == "durable_fact_committed" else "",
        },
        "temporal": {
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "",
            "transaction_time": "2026-01-01T00:00:00Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": ["sha256:subject"],
            "relation_refs": [],
            "budget_class": budget_class,
            "authority_critical": authority_critical,
            "projection_hints": {"graph_ready": False, "budget_ready": True, "multihop_ready": False},
        },
        "trace": {
            "proposal_id": f"proposal-{suffix}",
            "donor_trace": {"donor": "hindsight-compatible"},
            "policy_versions": {"admission": "brainstack.admission.v1", "slot_registry": "brainstack.slot_registry.v1"},
        },
        "extensions": {},
    }


def _insert_receipt(store: BrainstackStore, suffix: str) -> None:
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
            "ACCEPT_DURABLE",
            "accepted",
            f"turn-{suffix}",
            f"turn-number-{suffix}",
            f"span-{suffix}",
            "user",
            "user",
            "explicit",
            "profile",
            "identity.name",
            "identity:name",
            1,
            "answer_evidence",
            1,
            "candidate excerpt",
            "sha256:candidate",
            "{}",
            "2026-01-01T00:00:00Z",
        ),
    )
    store.conn.commit()


def _seed_noisy_store(store: BrainstackStore) -> None:
    store.upsert_profile_item(
        stable_key="identity:name:1",
        category="identity",
        content=f"Name duplicate {PRIVATE_TEXT}",
        source="test",
        confidence=0.9,
        metadata={},
    )
    store.upsert_profile_item(
        stable_key="identity:name:2",
        category="identity",
        content=f"Name duplicate {PRIVATE_TEXT}",
        source="test",
        confidence=0.9,
        metadata={},
    )
    _insert_receipt(store, "answer1")
    _insert_receipt(store, "answer2")
    store.record_canonical_memory_event(_canonical_event("answer1", stable_fact_id="identity:name"))
    store.record_canonical_memory_event(_canonical_event("answer2", stable_fact_id="identity:name"))
    store.record_canonical_memory_event(
        _canonical_event(
            "support1",
            event_type="support_event",
            stable_fact_id="support:one",
            truth_eligible=False,
            support_visibility="normal",
            budget_class="support_only",
            authority_critical=False,
            receipt_id="",
        )
    )
    store.record_canonical_memory_event(
        _canonical_event(
            "reject1",
            event_type="proposal_rejected",
            stable_fact_id="identity:old",
            truth_eligible=False,
            support_visibility="inspect_only",
            budget_class="archived",
            authority_critical=False,
            receipt_id="",
        )
    )
    for index in range(5):
        store.conn.execute(
            "INSERT INTO transcript_entries (session_id, turn_number, kind, content, source, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("session", index, "user", f"{PRIVATE_TEXT} transcript {index}", "test", "{}", "2026-01-01T00:00:00Z"),
        )
        store.conn.execute(
            "INSERT INTO continuity_events (session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("session", index, "summary", f"{PRIVATE_TEXT} continuity {index}", "test", "{}", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    store.conn.execute(
        "INSERT INTO graph_entities (canonical_name, normalized_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("Example", "example", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    entity_id = store.conn.execute("SELECT id FROM graph_entities LIMIT 1").fetchone()["id"]
    store.conn.execute(
        "INSERT INTO graph_states (entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_id, "name", "old", "test", "{}", "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", 0),
    )
    store.conn.execute(
        "INSERT INTO graph_conflicts (entity_id, attribute, current_state_id, candidate_value_text, candidate_source, metadata_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_id, "name", 1, "candidate", "test", "{}", "open", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    store.conn.execute(
        "INSERT INTO corpus_documents (stable_key, title, doc_kind, source, metadata_json, created_at, updated_at, active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("doc:1", "Doc", "note", "test", "{}", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", 1),
    )
    doc_id = store.conn.execute("SELECT id FROM corpus_documents LIMIT 1").fetchone()["id"]
    store.conn.execute(
        "INSERT INTO corpus_sections (document_id, section_index, heading, content, token_estimate, metadata_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (doc_id, 0, "Heading", f"{PRIVATE_TEXT} corpus", 12, "{}", "2026-01-01T00:00:00Z"),
    )
    event = store.upsert_proactive_event(
        source="test",
        kind="evolver_signal",
        principal_scope_key="principal:test",
        title="Wake",
        summary=PRIVATE_TEXT,
        priority="normal",
        state="observed",
        source_ref="source-ref",
    )
    store.create_proactive_outbox(event_id=event["event_id"], delivery_target="agent")
    store.conn.commit()


def test_empty_store_report_has_all_required_lanes_and_metrics(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        report = build_persistent_bloat_report(store)
    finally:
        store.close()

    assert report["schema"] == PERSISTENT_BLOAT_REPORT_SCHEMA
    assert report["read_only"] is True
    assert report["public_safe"] is True
    assert report["status"] == "pass"
    assert set(report["lanes"]) >= {
        "durable_truth",
        "canonical_events",
        "receipts",
        "transcript",
        "continuity",
        "corpus",
        "semantic_index",
        "graph",
        "proactive",
        "operating_recent_work",
        "behavior_policy",
        "publish_tier2",
    }
    assert set(report["metrics"]) >= {
        "write_amplification",
        "duplicate_strength_inflation",
        "support_only_accumulation",
        "active_packet_growth",
        "stale_prior_retention",
        "projection_rebuild_size",
    }
    assert all(item["schema"] == PERSISTENT_BLOAT_POLICY_SCHEMA for item in report["policy_preview"])


def test_noisy_store_report_is_public_safe_and_exposes_bloat_pressure(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        _seed_noisy_store(store)
        report = build_persistent_bloat_report(store, thresholds={"support_only_ratio_warn": 1, "duplicate_strength_warn": 1})
    finally:
        store.close()

    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    assert PRIVATE_TEXT not in rendered
    assert report["public_safe"] is True
    assert report["metrics"]["duplicate_strength_inflation"]["profile_duplicate_groups"] >= 1
    assert report["metrics"]["duplicate_strength_inflation"]["canonical_duplicate_truth_groups"] >= 1
    assert report["metrics"]["support_only_accumulation"]["transcript_rows"] == 5
    assert report["metrics"]["support_only_accumulation"]["continuity_rows"] == 5
    assert report["metrics"]["stale_prior_retention"]["open_graph_conflicts"] == 1
    assert report["metrics"]["projection_rebuild_size"]["canonical_event_count"] == 4
    assert "DUPLICATE_STRENGTH_INFLATION_WARN" in report["issues"]
    assert "SUPPORT_ONLY_ACCUMULATION_WARN" in report["issues"]
    transcript_policy = next(item for item in report["policy_preview"] if item["lane"] == "transcript_continuity")
    assert transcript_policy["apply_supported"] is False
    assert "source_ref" in transcript_policy["preserves"]
    truth_policy = next(item for item in report["policy_preview"] if item["lane"] == "durable_truth")
    assert truth_policy["action"] == "keep"
    assert truth_policy["apply_supported"] is False


def test_report_is_deterministic_for_same_store(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        _seed_noisy_store(store)
        first = build_persistent_bloat_report(store)
        second = build_persistent_bloat_report(store)
    finally:
        store.close()

    assert first == second
    assert first["critical_counters"]["truth_cleanup_apply_supported"] == 0
    assert first["lanes"]["receipts"]["preserves"] == ["receipt"]
