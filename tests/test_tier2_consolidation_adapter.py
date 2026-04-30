from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.reconciler import reconcile_tier2_candidates
from brainstack.tier2_consolidation import TIER2_CONSOLIDATION_PLAN_SCHEMA


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
        "tier2-consolidation-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="tier2-consolidation-session",
        turn_number=1,
        kind="turn",
        content="User: My preferred name is Alex.",
        source="test",
        metadata=provider._scoped_metadata(),
    )
    return provider


def test_tier2_batch_emits_hindsight_style_plan_before_quarantine_receipt(tmp_path: Path) -> None:
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
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["status"] == "ok"
        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert result["consolidation_budget"]["status"] == "within_budget"

        plan = result["consolidation_plan"]
        assert plan["schema"] == TIER2_CONSOLIDATION_PLAN_SCHEMA
        assert plan["status"] == "has_proposals"
        assert plan["proposal_count"] == 1
        proposal = plan["proposals"][0]
        assert proposal["kind"] == "profile"
        assert proposal["target_slot"] == "identity.preferred_address_name"
        assert proposal["proposed_action"] == "ADD"
        assert "Alex" not in json.dumps(plan, ensure_ascii=True)

        assert provider._store is not None
        receipts = provider._store.list_admission_receipts(limit=10)
        assert receipts[0]["source_span_id"] == proposal["proposal_id"]
        assert receipts[0]["trace_id"] == proposal["proposal_id"]
        assert receipts[0]["truth_eligible"] is False
        assert receipts[0]["metadata"]["admission"]["authority_class"] == "tier2_summary"
        assert provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()


def test_tier2_verified_user_span_can_write_durable_memory(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "source_quote": "My preferred name is Alex.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "user", "verified_user_span_proof": {"status": "forged"}},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["status"] == "ok"
        assert result["writes_performed"] == 1
        assert result["action_counts"]["ADD"] == 1
        plan = result["consolidation_plan"]
        proposal = plan["proposals"][0]
        assert proposal["user_span_verification"]["status"] == "verified"
        assert "Alex" not in json.dumps(plan, ensure_ascii=True)

        assert provider._store is not None
        item = provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        )
        assert item is not None
        assert item["content"] == "Alex"

        receipts = provider._store.list_admission_receipts(limit=10)
        assert receipts[0]["trace_id"] == proposal["proposal_id"]
        assert receipts[0]["source_span_id"].startswith("usrspan_")
        assert receipts[0]["truth_eligible"] is True
        assert receipts[0]["metadata"]["admission"]["authority_class"] == "user_explicit_assertion"
        proof = receipts[0]["metadata"]["verified_user_span_proof"]
        assert proof["status"] == "verified"
        assert proof["source_span_id"] == receipts[0]["source_span_id"]
        assert proof["source_role"] == "user"
    finally:
        provider.shutdown()


def test_tier2_inexact_user_span_stays_support_only(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "source_quote": "My preferred name is Alexander.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert "user_span_verification" not in result["consolidation_plan"]["proposals"][0]
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()


def test_tier2_assistant_span_cannot_be_verified_as_user_span(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "BotGuess",
                    "source_quote": "Assistant guessed the user is BotGuess.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        assert provider._store is not None
        provider._store.add_transcript_entry(
            session_id="tier2-consolidation-session",
            turn_number=2,
            kind="assistant",
            content="Assistant guessed the user is BotGuess.",
            source="test",
            metadata=provider._scoped_metadata(),
        )
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=2,
            trigger_reason="idle_window",
        )

        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert "user_span_verification" not in result["consolidation_plan"]["proposals"][0]
    finally:
        provider.shutdown()


def test_tier2_assistant_marker_overrides_matching_user_quote(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "source_quote": "My preferred name is Alex.",
                    "confidence": 0.97,
                    "metadata": {"source_role": "assistant"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["writes_performed"] == 0
        assert result["action_counts"]["REJECT_ASSISTANT_AUTHORED"] == 1
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()


def test_tier2_duplicate_background_run_cannot_become_durable_memory_bloat(tmp_path: Path) -> None:
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
        first = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )
        second = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=2,
            trigger_reason="followup_pending_work",
        )

        assert first["writes_performed"] == 0
        assert second["writes_performed"] == 0
        assert first["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert second["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()


def test_tier2_missing_user_authority_does_not_write_even_with_plan_metadata(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "Alex",
                    "confidence": 0.97,
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()


def test_tier2_candidate_budget_blocks_high_volume_bloat(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:name",
                    "content": f"Noisy Name {index}",
                    "confidence": 0.8,
                    "metadata": {"source_role": "user"},
                }
                for index in range(40)
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-consolidation-session",
            turn_number=1,
            trigger_reason="idle_window",
        )

        assert result["consolidation_budget"]["status"] == "trimmed"
        assert result["consolidation_budget"]["accepted_by_kind"]["profile_items"] == 8
        assert result["consolidation_budget"]["omitted_total"] == 32
        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 8
    finally:
        provider.shutdown()


def test_direct_reconciler_omits_overlong_continuity_summary(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        result = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=1,
            source="tier2:test",
            extracted={"continuity_summary": "x" * 900},
        )

        assert result["consolidation_budget"]["status"] == "trimmed"
        assert result["consolidation_budget"]["omitted_by_kind"]["continuity_summary"] == 1
        assert result["actions"] == []
        assert store.find_continuity_event(session_id="s1", kind="tier2_summary", content="x" * 900) is None
    finally:
        store.close()
