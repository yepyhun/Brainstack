from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.scope_identity import build_memory_scope_identity


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _scope(**overrides: Any) -> Dict[str, Any]:
    payload = {
        "platform": "test",
        "user_id": "same-user",
        "agent_identity": "agent-smoke",
        "agent_workspace": "workspace-a",
        "chat_type": "dm",
        "chat_id": "chat-a",
        "thread_id": "thread-a",
    }
    payload.update(overrides)
    scope = build_memory_scope_identity(**payload)
    assert scope.get("principal_scope_key")
    return scope


def test_hindsight_style_scope_a_does_not_leak_continuity_to_scope_b(tmp_path: Path) -> None:
    scope_a = _scope(agent_workspace="workspace-a", chat_id="chat-a", thread_id="thread-a")
    scope_b = _scope(agent_workspace="workspace-b", chat_id="chat-b", thread_id="thread-b")
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="session-a",
            turn_number=1,
            kind="session_summary",
            content="Aurora bank memory belongs only to workspace A.",
            source="phase97.proof",
            metadata={
                "principal_scope_key": scope_a["principal_scope_key"],
                "principal_scope": scope_a,
            },
        )

        leaked = store.search_continuity(
            query="Aurora bank memory",
            session_id="session-b",
            limit=5,
            principal_scope_key=str(scope_b["principal_scope_key"]),
        )
        assert leaked == []

        recalled = store.search_continuity(
            query="Aurora bank memory",
            session_id="session-a",
            limit=5,
            principal_scope_key=str(scope_a["principal_scope_key"]),
        )
        assert len(recalled) == 1
        assert recalled[0]["same_principal"] is True
        assert recalled[0]["same_personal_scope"] is True

        scope_b_report = build_query_inspect(
            store,
            query="Aurora bank memory",
            session_id="session-b",
            principal_scope_key=str(scope_b["principal_scope_key"]),
        )
        scope_b_text = " ".join(
            str(item.get("excerpt") or "")
            for rows in scope_b_report["selected_evidence"].values()
            for item in rows
        )
        assert "Aurora bank memory" not in scope_b_text
    finally:
        store.close()


def test_transient_runtime_ids_do_not_become_memory_bank_identity() -> None:
    base = _scope(
        session_id="session-one",
        container_id="container-one",
        connection_id="connection-one",
        runtime_thread_id="runtime-thread-one",
    )
    changed_runtime = _scope(
        session_id="session-two",
        container_id="container-two",
        connection_id="connection-two",
        runtime_thread_id="runtime-thread-two",
    )

    assert changed_runtime["principal_scope_key"] == base["principal_scope_key"]
    ignored = changed_runtime["transient_scope_fields_ignored"]
    assert ignored["session_id"] == "session-two"
    assert ignored["container_id"] == "container-two"
    assert ignored["connection_id"] == "connection-two"
    assert ignored["runtime_thread_id"] == "runtime-thread-two"


def test_durable_chat_thread_metadata_participates_in_bank_identity() -> None:
    scope_a = _scope(chat_id="chat-a", thread_id="thread-a")
    scope_b = _scope(chat_id="chat-a", thread_id="thread-b")

    assert scope_a["principal_scope_key"] != scope_b["principal_scope_key"]
    assert "thread_id:thread-a" in str(scope_a["principal_scope_key"])
