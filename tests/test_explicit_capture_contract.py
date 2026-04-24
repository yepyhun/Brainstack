from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.explicit_capture import EXPLICIT_CAPTURE_SCHEMA_VERSION


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "capture-session",
        platform="test",
        user_id="user",
        agent_identity="bestie",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_explicit_profile_remember_writes_multilingual_user_truth_and_recall(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        receipt = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "preference:engineering_style",
                    "category": "preference",
                    "content": "Nem raktapasz megoldást kérünk, hanem gyökérok alapú mérnöki javítást.",
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": 0.98,
                    "metadata": {"semantic_terms": ["root cause engineering preference"]},
                },
            )
        )

        assert receipt["schema"] == EXPLICIT_CAPTURE_SCHEMA_VERSION
        assert receipt["status"] == "committed"
        assert receipt["tool_name"] == "brainstack_remember"
        row = provider._store.get_profile_item(
            stable_key="preference:engineering_style",
            principal_scope_key=provider._principal_scope_key,
        )
        assert row is not None
        assert "gyökérok" in row["content"]

        recall = json.loads(
            provider.handle_tool_call("brainstack_recall", {"query": "root cause engineering preference"})
        )
        assert recall["selected_evidence"]["profile"]
    finally:
        provider.shutdown()


def test_explicit_supersede_replaces_prior_profile_truth_without_duplicate_spam(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        base_payload = {
            "shelf": "profile",
            "stable_key": "preference:default_model",
            "category": "preference",
            "content": "The default model preference is Gemini.",
            "source_role": "user",
            "authority_class": "profile",
        }
        assert json.loads(provider.handle_tool_call("brainstack_remember", base_payload))["status"] == "committed"

        updated_payload = {
            **base_payload,
            "content": "The default model preference is Kimi K2.6.",
            "supersedes_stable_key": "preference:default_model",
        }
        receipt = json.loads(provider.handle_tool_call("brainstack_supersede", updated_payload))

        assert receipt["status"] == "committed"
        assert receipt["operation"] == "supersede"
        assert receipt["supersedes_stable_key"] == "preference:default_model"
        row = provider._store.get_profile_item(
            stable_key="preference:default_model",
            principal_scope_key=provider._principal_scope_key,
        )
        assert row is not None
        assert "Kimi K2.6" in row["content"]
        assert "Gemini" not in row["content"]
        count = provider._store.conn.execute(
            "SELECT COUNT(*) AS count FROM profile_items WHERE stable_key LIKE ?",
            ("%preference:default_model%",),
        ).fetchone()["count"]
        assert count == 1
    finally:
        provider.shutdown()


def test_explicit_capture_rejects_assistant_authored_or_insufficient_payload(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        rejected = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "profile",
                    "stable_key": "identity:bad",
                    "category": "identity",
                    "content": "Assistant-authored recap must not become user truth.",
                    "source_role": "assistant",
                },
            )
        )
        assert rejected["status"] == "rejected"
        assert any(error["code"] == "invalid_source_role" for error in rejected["errors"])
        assert (
            provider._store.get_profile_item(
                stable_key="identity:bad",
                principal_scope_key=provider._principal_scope_key,
            )
            is None
        )

        missing = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {"shelf": "profile", "stable_key": "identity:missing", "source_role": "user"},
            )
        )
        assert missing["status"] == "rejected"
        assert any(error["code"] == "missing_content" for error in missing["errors"])
    finally:
        provider.shutdown()


def test_explicit_operating_and_task_capture_use_typed_shelf_fields(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        operating = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "operating",
                    "stable_key": "operating:procedure:no_bandaid",
                    "record_type": "canonical_policy",
                    "content": "Procedure: root-cause analysis must precede implementation.",
                    "source_role": "operator",
                    "authority_class": "operating",
                },
            )
        )
        assert operating["status"] == "committed"
        operating_rows = provider._store.search_operating_records(
            query="root-cause analysis",
            principal_scope_key=provider._principal_scope_key,
            limit=5,
        )
        assert operating_rows

        task = json.loads(
            provider.handle_tool_call(
                "brainstack_remember",
                {
                    "shelf": "task",
                    "stable_key": "task:phase72:proof",
                    "title": "Run Phase 72 explicit capture proof",
                    "source_role": "operator",
                    "authority_class": "task",
                    "status": "open",
                },
            )
        )
        assert task["status"] == "committed"
        tasks = provider._store.search_task_items(
            query="explicit capture proof",
            principal_scope_key=provider._principal_scope_key,
            limit=5,
        )
        assert tasks
    finally:
        provider.shutdown()
