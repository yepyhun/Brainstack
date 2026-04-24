from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "tool-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def test_agent_tool_surface_exposes_read_tools_and_schema_gated_capture_tools(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        schemas = provider.get_tool_schemas()
        names = {schema["name"] for schema in schemas}

        assert {"brainstack_recall", "brainstack_inspect", "brainstack_stats"}.issubset(names)
        assert "brainstack_remember" in names
        assert "brainstack_supersede" in names
        assert "brainstack_invalidate" not in names
        assert "brainstack_consolidate" in names
        assert "runtime_handoff_update" not in names
        for schema in schemas:
            if schema["name"] in {"brainstack_recall", "brainstack_inspect", "brainstack_stats"}:
                assert str(schema.get("x_brainstack_tool_class", "")).startswith("read_only_memory")
            if schema["name"] in {"brainstack_remember", "brainstack_supersede"}:
                assert schema.get("x_brainstack_tool_class") == "explicit_memory_write"
            if schema["name"] == "brainstack_consolidate":
                assert schema.get("x_brainstack_tool_class") == "bounded_memory_maintenance"
    finally:
        provider.shutdown()


def test_brainstack_recall_tool_returns_evidence_without_mutating_profile(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="ExampleUser uses Brainstack as the memory kernel.",
            source="tool-test",
            confidence=0.99,
            metadata=provider._scoped_metadata(),
        )
        before = provider._store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE content LIKE '%memory kernel%'"
        ).fetchone()

        payload = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "ExampleUser memory kernel"}))

        after = provider._store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE content LIKE '%memory kernel%'"
        ).fetchone()
        assert before is not None and after is not None
        assert dict(before) == dict(after)
        assert payload["schema"] == "brainstack.tool_recall.v1"
        assert payload["read_only"] is True
        assert payload["evidence_count"] >= 1
        assert payload["selected_evidence"]["profile"]
        assert "ExampleUser" in payload["final_packet"]["preview"]
    finally:
        provider.shutdown()


def test_disabled_memory_write_tools_return_explicit_phase_gate(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_invalidate",
                {"content": "do not write this through a disabled tool"},
            )
        )
        assert payload["schema"] == "brainstack.tool_error.v1"
        assert payload["error_code"] == "tool_disabled_pending_contract"
        assert payload["read_only"] is False
    finally:
        provider.shutdown()


def test_brainstack_stats_tool_wraps_doctor_report(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))
        assert payload["schema"] == "brainstack.tool_stats.v1"
        assert payload["read_only"] is True
        assert payload["report"]["schema"] == "brainstack.memory_kernel_doctor.v1"
        assert payload["report"]["strict"] is True
    finally:
        provider.shutdown()
