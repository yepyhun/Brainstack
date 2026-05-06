from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.memory_write_receipts import (
    ACK_FULL,
    ACK_NONE,
    ACK_PARTIAL,
    CAPTURE_PLAN_SCHEMA,
    COVERAGE_COMPLETE,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    MEMORY_WRITE_RECEIPT_SCHEMA,
    RECEIPT_COVERAGE_SCHEMA,
    build_ack_plan,
    build_memory_write_receipt,
    build_single_proposal_capture_plan,
    commitment_guard_trace,
    compute_receipt_coverage,
    is_committed_memory_write_receipt,
)


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _two_proposal_plan():
    return build_single_proposal_capture_plan(
        turn_id="turn-1",
        source_event_id="user-msg-1",
        target_slot="identity.preferred_address_name",
        stable_key="identity.preferred_address_name",
        source_span_id="span-name",
        normalized_value="Alex",
    )


def test_memory_write_receipt_schema_is_emitted_for_admitted_write(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference:engineering_style",
                    "category": "preference",
                    "content": "Root-cause engineering, no bandaid fixes.",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.98,
                    "metadata": {
                        "source_event_id": "user-msg-1",
                        "source_span_id": "span-style",
                        "target_slot": "preference.communication.engineering_style",
                    },
                },
            )
        )

        assert receipt["status"] == "committed"
        assert receipt["capture_plan"]["schema"] == CAPTURE_PLAN_SCHEMA
        assert receipt["memory_write_receipt"]["schema"] == MEMORY_WRITE_RECEIPT_SCHEMA
        assert receipt["memory_write_receipt"]["receipt_status"] == "committed"
        assert receipt["receipt_coverage"]["schema"] == RECEIPT_COVERAGE_SCHEMA
        assert receipt["receipt_coverage"]["coverage_status"] == COVERAGE_COMPLETE
        assert receipt["ack_plan"]["ack_mode"] == ACK_FULL
        assert receipt["memory_commitment_guard"]["final_answer_allowed"] is True
    finally:
        provider.shutdown()


def test_memory_commitment_without_receipt_is_blocked() -> None:
    plan = _two_proposal_plan()
    coverage = compute_receipt_coverage(plan, [])
    trace = commitment_guard_trace(
        capture_plan=plan,
        coverage=coverage,
        commitment_claim_present=True,
    )

    assert coverage["coverage_status"] == COVERAGE_NONE
    assert trace["memory_commitment_guard"]["final_answer_allowed"] is False
    assert trace["memory_commitment_guard"]["reason_code"] == "MEMORY_COMMITMENT_WITHOUT_WRITE_RECEIPT"
    assert build_ack_plan(plan, coverage)["ack_mode"] == ACK_NONE


def test_full_ack_requires_complete_receipt_coverage() -> None:
    plan = build_single_proposal_capture_plan(
        turn_id="turn-1",
        source_event_id="user-msg-1",
        target_slot="identity.preferred_address_name",
        stable_key="identity.preferred_address_name",
        normalized_value="Alex",
    )
    second = build_single_proposal_capture_plan(
        turn_id="turn-1",
        source_event_id="user-msg-1",
        target_slot="identity.age",
        stable_key="identity.age",
        normalized_value="19",
    ).proposals[0]
    plan = plan.__class__.from_proposals(
        turn_id=plan.turn_id,
        source_event_id=plan.source_event_id,
        proposals=(*plan.proposals, second),
        capture_plan_id=plan.capture_plan_id,
    )
    receipt = build_memory_write_receipt(
        capture_plan=plan,
        proposal=plan.proposals[0],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )
    coverage = compute_receipt_coverage(
        plan,
        [receipt],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )
    ack = build_ack_plan(plan, coverage)

    assert coverage["receipt_count"] == 1
    assert coverage["coverage_status"] == COVERAGE_PARTIAL
    assert coverage["full_ack_allowed"] is False
    assert ack["ack_mode"] == ACK_PARTIAL
    assert ack["must_not_claim_full_commit"] is True
    assert "identity.age" in ack["missing_slots"]


def test_receipt_scope_must_match_turn_scope() -> None:
    plan = _two_proposal_plan()
    receipt = build_memory_write_receipt(
        capture_plan=plan,
        proposal=plan.proposals[0],
        principal_scope_key="other-user",
        workspace_scope_key="workspace",
        session_id="session",
    )
    coverage = compute_receipt_coverage(
        plan,
        [receipt],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )

    assert coverage["coverage_status"] == COVERAGE_NONE
    assert coverage["failed_proposals"][0]["reason_code"] == "RECEIPT_SCOPE_MISMATCH"


def test_receipt_idempotency_prevents_duplicate_retry_writes() -> None:
    plan = _two_proposal_plan()
    kwargs = {
        "capture_plan": plan,
        "proposal": plan.proposals[0],
        "principal_scope_key": "user",
        "workspace_scope_key": "workspace",
        "session_id": "session",
    }
    first = build_memory_write_receipt(**kwargs)
    second = build_memory_write_receipt(**kwargs)

    assert first["idempotency_key"] == second["idempotency_key"]
    assert first["transaction_id"] == second["transaction_id"]


def test_assistant_commitment_text_is_not_write_receipt() -> None:
    assistant_claim = {
        "schema": "brainstack.assistant_claim.v1",
        "source_role": "assistant",
        "text": "Megjegyeztem.",
    }

    assert not is_committed_memory_write_receipt(assistant_claim)


def test_committed_receipt_requires_valid_model_facing_durable_ref() -> None:
    plan = _two_proposal_plan()
    receipt = build_memory_write_receipt(
        capture_plan=plan,
        proposal=plan.proposals[0],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )
    receipt["durable_refs"] = "not-a-durable-ref-list"

    coverage = compute_receipt_coverage(
        plan,
        [receipt],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )

    assert not is_committed_memory_write_receipt(receipt)
    assert coverage["coverage_status"] == COVERAGE_NONE
    assert coverage["full_ack_allowed"] is False


def test_committed_receipt_rejects_non_ackable_durable_ref() -> None:
    plan = _two_proposal_plan()
    receipt = build_memory_write_receipt(
        capture_plan=plan,
        proposal=plan.proposals[0],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )
    receipt["durable_refs"][0]["model_facing_ack_allowed"] = False

    coverage = compute_receipt_coverage(
        plan,
        [receipt],
        principal_scope_key="user",
        workspace_scope_key="workspace",
        session_id="session",
    )

    assert not is_committed_memory_write_receipt(receipt)
    assert coverage["coverage_status"] == COVERAGE_NONE
    assert coverage["full_ack_allowed"] is False


def test_final_output_validation_commits_receipt_backed_profile_captures(tmp_path: Path) -> None:
    def extractor(transcript_rows, *_args, **_kwargs):
        assert transcript_rows
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "content": "Canary Alex",
                    "slot": "identity:preferred_address_name",
                    "confidence": 0.96,
                },
                {
                    "category": "identity",
                    "content": "19",
                    "slot": "identity:age",
                    "confidence": 0.96,
                },
                {
                    "category": "reference",
                    "content": "https://example.com/example-lib",
                    "slot": "reference:repository_url",
                    "confidence": 0.96,
                },
            ],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
            "explicit_capture_validation_enabled": True,
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        result = provider.validate_assistant_output(
            "Megjegyeztem.",
            user_content=(
                "My name is Canary Alex, and I am 19 years old. "
                "Remember as a repo URL: https://example.com/example-lib"
            ),
            session_id="receipt-session",
        )

        assert result is not None
        validation = result["memory_commitment_validation"]
        assert validation["receipt_coverage"]["coverage_status"] == "complete"
        assert validation["ack_plan"]["ack_mode"] == "full"
        assert len(validation["memory_write_receipts"]) == 3
        assert result["can_ship"] is True

        assert provider._store is not None
        name = provider._store.get_profile_item(
            stable_key="identity:preferred_address_name",
            principal_scope_key=provider._principal_scope_key,
        )
        age = provider._store.get_profile_item(
            stable_key="identity:age",
            principal_scope_key=provider._principal_scope_key,
        )
        url = provider._store.get_profile_item(
            stable_key="reference:repository_url",
            principal_scope_key=provider._principal_scope_key,
        )
        assert name and name["content"] == "Canary Alex"
        assert age and age["content"] == "19"
        assert url and url["content"] == "https://example.com/example-lib"
    finally:
        provider.shutdown()


def test_final_output_validation_preserves_exact_source_url_literal(tmp_path: Path) -> None:
    def extractor(transcript_rows, *_args, **_kwargs):
        assert transcript_rows
        return {
            "profile_items": [
                {
                    "category": "reference",
                    "content": "https://example.com/hallucinated-lib",
                    "slot": "reference:repository_url",
                    "confidence": 0.96,
                },
            ],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
            "explicit_capture_validation_enabled": True,
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        result = provider.validate_assistant_output(
            "Megjegyeztem.",
            user_content="Remember this as a repo URL: https://example.com/example-lib",
            session_id="receipt-session",
        )

        assert result is not None
        validation = result["memory_commitment_validation"]
        assert validation["receipt_coverage"]["coverage_status"] == "complete"

        assert provider._store is not None
        url = provider._store.get_profile_item(
            stable_key="reference:repository_url",
            principal_scope_key=provider._principal_scope_key,
        )
        assert url and url["content"] == "https://example.com/example-lib"
    finally:
        provider.shutdown()


def test_final_output_validation_preserves_exact_source_age_literal(tmp_path: Path) -> None:
    def extractor(transcript_rows, *_args, **_kwargs):
        assert transcript_rows
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "content": "34",
                    "slot": "identity:age",
                    "confidence": 0.96,
                },
            ],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
            "explicit_capture_validation_enabled": True,
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        result = provider.validate_assistant_output(
            "Megjegyeztem.",
            user_content="My name is Canary Alex. I am 19 years old.",
            session_id="receipt-session",
        )

        assert result is not None
        validation = result["memory_commitment_validation"]
        assert validation["receipt_coverage"]["coverage_status"] == "complete"

        assert provider._store is not None
        age = provider._store.get_profile_item(
            stable_key="identity:age",
            principal_scope_key=provider._principal_scope_key,
        )
        assert age and age["content"] == "19"
    finally:
        provider.shutdown()


def test_live_receipt_enforcement_partial_coverage_forbids_full_ack(tmp_path: Path) -> None:
    def extractor(transcript_rows, *_args, **_kwargs):
        assert transcript_rows
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "content": "Canary Alex",
                    "slot": "identity:preferred_address_name",
                    "confidence": 0.96,
                },
                {
                    "category": "identity",
                    "content": "19",
                    "slot": "identity:age",
                    "confidence": 0.96,
                },
            ],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
            "explicit_capture_validation_enabled": True,
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    original_capture = provider._handle_brainstack_explicit_capture

    def partial_capture(action, args, *, trusted_operator_origin=""):
        if args.get("stable_key") == "identity:age":
            return {"status": "rejected", "reason_code": "TEST_FORCED_MISSING_RECEIPT"}
        return original_capture(action, args, trusted_operator_origin=trusted_operator_origin)

    provider._handle_brainstack_explicit_capture = partial_capture
    try:
        result = provider.validate_assistant_output(
            "Megjegyeztem.",
            user_content="My name is Canary Alex, and I am 19 years old.",
            session_id="receipt-session",
        )

        assert result is not None
        validation = result["memory_commitment_validation"]
        assert validation["receipt_coverage"]["coverage_status"] == COVERAGE_PARTIAL
        assert validation["ack_plan"]["ack_mode"] == ACK_PARTIAL
        assert result["blocked"] is True
        assert result["can_ship"] is False
        assert result["block_reason"] == "INCOMPLETE_RECEIPT_COVERAGE"
    finally:
        provider.shutdown()


def test_live_receipt_enforcement_no_capture_does_not_invent_memory_write(tmp_path: Path) -> None:
    def extractor(transcript_rows, *_args, **_kwargs):
        assert transcript_rows
        return {
            "profile_items": [],
            "style_contract": None,
            "states": [],
            "relations": [],
            "inferred_relations": [],
            "typed_entities": [],
            "temporal_events": [],
            "continuity_summary": "",
            "decisions": [],
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
            "explicit_capture_validation_enabled": True,
        }
    )
    provider.initialize(
        "receipt-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        result = provider.validate_assistant_output(
            "Generic answer.",
            user_content="Talk generally.",
            session_id="receipt-session",
        )

        assert result is not None
        validation = result["memory_commitment_validation"]
        assert validation["status"] == "no_capture"
        assert validation["memory_write_receipts"] == []
        assert validation["receipt_coverage"] is None
        assert result["blocked"] is False
        assert result["can_ship"] is True
    finally:
        provider.shutdown()
