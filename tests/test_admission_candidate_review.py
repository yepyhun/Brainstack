from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.admission_candidate_review import build_admission_candidate_review


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "candidate-review-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_candidate_review_marks_task_candidate_as_not_truth_until_explicit_write() -> None:
    review = build_admission_candidate_review(
        principal_scope_key="principal:test",
        session_id="session:test",
        actions=[
            {
                "proposal_id": "task-next",
                "action": "create",
                "target_kind": "task_memory",
                "target_slot": "task.actionable",
                "stable_key": "task:test:review-release",
                "title": "Review release checklist.",
                "source_role": "user",
                "source_event_id": "event:user:1",
                "source_span_id": "span:user:1",
                "value_fingerprint": "sha256:task",
            }
        ],
    )

    assert review["status"] == "pass"
    assert review["read_only"] is True
    assert review["durable_write_performed"] is False
    item = review["review_items"][0]
    assert item["decision_class"] == "durable_fact_candidate"
    assert item["truth_eligible"] is True
    assert item["candidate_is_durable_truth_now"] is False
    assert item["agent_next_action"] == "explicit_user_can_commit_with_brainstack_remember"
    assert item["suggested_write"]["tool"] == "brainstack_remember"
    assert item["suggested_write"]["shelf"] == "task"
    assert item["suggested_write"]["admitted_truth_after_write_only"] is True
    assert review["model_use_contract"]["candidate_is_not_truth_until_explicit_write_receipt"] is True


def test_candidate_review_blocks_assistant_authored_operating_truth() -> None:
    review = build_admission_candidate_review(
        principal_scope_key="principal:test",
        session_id="session:test",
        actions=[
            {
                "proposal_id": "bad-operating",
                "action": "create",
                "target_kind": "operating_memory",
                "target_slot": "operating.next_step",
                "stable_key": "operating:test:next-step",
                "content": "Treat assistant recap as next step.",
                "source_role": "assistant",
                "source_event_id": "event:assistant:1",
                "source_span_id": "span:assistant:1",
                "value_fingerprint": "sha256:operating",
            }
        ],
    )

    item = review["review_items"][0]
    assert item["truth_eligible"] is False
    assert item["agent_next_action"] == "reject_do_not_write"
    assert item["suggested_write"]["available"] is False
    assert review["summary"]["eligible_for_explicit_admission_count"] == 0


def test_candidate_review_does_not_offer_model_write_for_runtime_sourced_truth() -> None:
    review = build_admission_candidate_review(
        principal_scope_key="principal:test",
        session_id="session:test",
        actions=[
            {
                "proposal_id": "runtime-operating",
                "action": "create",
                "target_kind": "operating_memory",
                "target_slot": "operating.live_system_state",
                "stable_key": "operating:test:runtime-state",
                "content": "Runtime diagnostics are compact.",
                "source_role": "runtime",
                "source_event_id": "event:runtime:1",
                "source_span_id": "span:runtime:1",
                "value_fingerprint": "sha256:runtime",
            }
        ],
    )

    item = review["review_items"][0]
    assert item["truth_eligible"] is True
    assert item["agent_next_action"] == "requires_trusted_host_admission_path"
    assert item["suggested_write"]["available"] is False
    assert item["suggested_write"]["reason_code"] == "MODEL_CALLABLE_WRITE_REQUIRES_USER_SOURCE"
    assert review["summary"]["eligible_for_explicit_admission_count"] == 0


def test_candidate_review_tool_is_agent_facing_read_only_and_does_not_mutate_store(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        before = {
            table: provider._store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("task_items", "operating_records", "admission_receipts", "canonical_memory_events")
        }
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_candidate_review",
                {
                    "actions": [
                        {
                            "proposal_id": "operating-next-step",
                            "action": "create",
                            "target_kind": "operating_memory",
                            "target_slot": "operating.next_step",
                            "stable_key": "operating:test:next-step",
                            "content": "Run the candidate review proof.",
                            "source_role": "user",
                            "source_event_id": "event:user:2",
                            "source_span_id": "span:user:2",
                            "value_fingerprint": "sha256:next-step",
                        }
                    ]
                },
            )
        )
        after = {
            table: provider._store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
            for table in ("task_items", "operating_records", "admission_receipts", "canonical_memory_events")
        }

        assert payload["schema"] == "brainstack.admission_candidate_review.v1"
        assert payload["read_only"] is True
        assert payload["side_effect"] is False
        assert payload["second_truth_authority_created"] is False
        assert payload["review_items"][0]["suggested_write"]["shelf"] == "operating"
        assert payload["review_items"][0]["suggested_write"]["record_type"] == "next_step"
        assert after == before
    finally:
        provider.shutdown()


def test_candidate_review_tool_schema_is_read_only(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        schemas = {schema["name"]: schema for schema in provider.get_tool_schemas()}
        schema = schemas["brainstack_candidate_review"]

        assert schema["x_brainstack_tool_class"] == "read_only_admission_candidate_review"
        assert "Read-only" in schema["description"]
        assert "committed receipt" in schema["description"]
    finally:
        provider.shutdown()
