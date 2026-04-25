from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.explicit_capture import EXPLICIT_CAPTURE_SCHEMA_VERSION
from brainstack.graph import ingest_graph_evidence_with_receipt
from brainstack.graph_evidence import GraphEvidenceItem
from brainstack.write_contract import WRITE_CONTRACT_TRACE_SCHEMA_VERSION


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
        agent_identity="agent-smoke",
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
        assert receipt["write_contract_trace"]["schema"] == WRITE_CONTRACT_TRACE_SCHEMA_VERSION
        assert receipt["write_contract_trace"]["lane"] == "profile"
        assert receipt["write_contract_trace"]["accepted"] is True
        assert receipt["write_contract_trace"]["canonical"] is True
        assert "gyökérok" not in json.dumps(receipt["write_contract_trace"], ensure_ascii=False)
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
        assert rejected["write_contract_trace"]["lane"] == "profile"
        assert rejected["write_contract_trace"]["accepted"] is False
        assert rejected["write_contract_trace"]["canonical"] is False
        assert rejected["write_contract_trace"]["reason_code"] == "invalid_source_role"
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
        assert missing["write_contract_trace"]["accepted"] is False
        assert missing["write_contract_trace"]["reason_code"] in {"missing_category", "missing_content"}
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
        assert operating["write_contract_trace"]["lane"] == "operating"
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
        assert task["write_contract_trace"]["lane"] == "task"
        tasks = provider._store.search_task_items(
            query="explicit capture proof",
            principal_scope_key=provider._principal_scope_key,
            limit=5,
        )
        assert tasks
    finally:
        provider.shutdown()


def test_write_contract_trace_routes_continuity_graph_and_corpus_to_evidence_lanes(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        continuity_id = store.add_continuity_event(
            session_id="session:continuity",
            turn_number=1,
            kind="summary",
            content="Evidence-only recap, not canonical user truth.",
            source="continuity-fixture",
            metadata={"principal_scope_key": "principal:lane-routing"},
        )
        continuity_row = store.conn.execute(
            "SELECT metadata_json FROM continuity_events WHERE id = ?",
            (continuity_id,),
        ).fetchone()
        continuity_trace = json.loads(continuity_row["metadata_json"])["write_contract_trace"]
        assert continuity_trace["schema"] == WRITE_CONTRACT_TRACE_SCHEMA_VERSION
        assert continuity_trace["lane"] == "continuity"
        assert continuity_trace["canonical"] is False
        assert "Evidence-only recap" not in json.dumps(continuity_trace)

        graph_result = ingest_graph_evidence_with_receipt(
            store,
            source="graph-fixture",
            metadata={"principal_scope_key": "principal:lane-routing"},
            evidence_items=[
                GraphEvidenceItem(
                    kind="state",
                    subject="Lane Routing Fixture",
                    attribute="status",
                    value_text="active",
                )
            ],
        )
        assert graph_result["receipt"]["write_contract_trace"]["lane"] == "graph"
        assert graph_result["receipt"]["write_contract_trace"]["canonical"] is False

        corpus_receipt = store.ingest_corpus_source(
            {
                "source_adapter": "test_fixture",
                "source_id": "doc:lane-routing",
                "stable_key": "doc:lane-routing",
                "title": "Lane Routing Corpus",
                "doc_kind": "project_note",
                "source_uri": "fixture://lane-routing",
                "content": "Corpus source body.",
                "metadata": {"principal_scope_key": "principal:lane-routing"},
            }
        )
        assert corpus_receipt["write_contract_trace"]["lane"] == "corpus"
        assert corpus_receipt["write_contract_trace"]["canonical"] is False
    finally:
        store.close()
