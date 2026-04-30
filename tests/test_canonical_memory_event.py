from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.canonical_memory_event import validate_canonical_memory_event
from brainstack.diagnostics import build_memory_kernel_doctor


def _provider(tmp_path: Path, extractor) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 8,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "canonical-event-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="canonical-event-session",
        turn_number=1,
        kind="turn",
        content="User: My preferred name is Alex.",
        source="test",
        metadata=provider._scoped_metadata(),
    )
    return provider


def test_tier2_durable_write_records_canonical_event_receipt_chain(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "source_quote": "My preferred name is Alex.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="canonical-event-session",
            turn_number=1,
            trigger_reason="idle_window",
        )
        assert result["status"] == "ok"
        assert result["writes_performed"] == 1
        assert provider._store is not None

        receipts = provider._store.list_admission_receipts(limit=10)
        events = provider._store.list_canonical_memory_events(limit=10)
        assert len(receipts) == 1
        assert len(events) == 1
        event = events[0]["event"]
        assert validate_canonical_memory_event(event) == []
        assert event["event"]["event_type"] == "durable_fact_committed"
        assert event["authority"]["truth_eligible"] is True
        assert event["authority"]["receipt_id"] == str(receipts[0]["id"])
        assert event["source"]["source_span_id"] == receipts[0]["source_span_id"]
        assert event["trace"]["policy_versions"]["admission"] == receipts[0]["policy_version"]
        assert "Alex" not in json.dumps(event, ensure_ascii=True)
        doctor = build_memory_kernel_doctor(provider._store, tier2_state={"enabled": True})
        assert doctor["row_counts"]["canonical_memory_events"] == 1
        assert doctor["last_writes"]["canonical_memory_events"]
    finally:
        provider.shutdown()


def test_tier2_rejected_candidate_records_inspect_only_canonical_event(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "confidence": 0.97,
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="canonical-event-session",
            turn_number=1,
            trigger_reason="idle_window",
        )
        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert provider._store is not None

        events = provider._store.list_canonical_memory_events(limit=10)
        assert len(events) == 1
        event = events[0]["event"]
        assert validate_canonical_memory_event(event) == []
        assert event["event"]["event_type"] == "proposal_rejected"
        assert event["authority"]["truth_eligible"] is False
        assert event["authority"]["support_visibility"] == "inspect_only"
    finally:
        provider.shutdown()


def test_canonical_event_rejects_projection_extension_redefining_authority() -> None:
    event = {
        "event": {
            "event_id": "cme_test",
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": "support_event",
            "idempotency_key": "sha256:test",
        },
        "source": {
            "source_event_id": "event_1",
            "source_span_id": "span_1",
            "source_quote_hash": "sha256:quote",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-04-30T00:00:00+00:00",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": "scope-a",
            "workspace_scope_key": "workspace-a",
            "session_id": "session-a",
            "project_id": "",
        },
        "claim": {
            "memory_kind": "support_only",
            "target_slot": "tier2_summary",
            "subject_ref": "",
            "predicate": "",
            "object_ref": "",
            "normalized_value_hash": "sha256:value",
            "stable_fact_id": "fact-a",
        },
        "authority": {
            "authority_class": "tier2_summary",
            "truth_eligible": False,
            "support_visibility": "inspect_only",
            "confidence": 0.1,
            "admission_decision_id": "decision-a",
            "receipt_id": "1",
        },
        "temporal": {
            "valid_from": "2026-04-30T00:00:00+00:00",
            "valid_to": "",
            "transaction_time": "2026-04-30T00:00:00+00:00",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [],
            "relation_refs": [],
            "budget_class": "archived",
            "authority_critical": False,
            "projection_hints": {"graph_ready": False, "budget_ready": True, "multihop_ready": False},
        },
        "trace": {
            "proposal_id": "proposal-a",
            "donor_trace": {"donor": "hindsight", "donor_version": "test", "adapter_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {"graphiti.v1": {"truth_eligible": True}},
    }

    assert "extension_redefines_core_semantics:graphiti.v1:truth_eligible" in validate_canonical_memory_event(event)
