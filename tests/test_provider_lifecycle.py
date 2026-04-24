from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    return BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )


def _initialize(provider: BrainstackMemoryProvider) -> None:
    provider.initialize(
        "lifecycle-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )


def test_lifecycle_status_reports_activation_hooks_and_tool_exports(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    before = provider.lifecycle_status()
    assert before["status"] == "unavailable"
    assert before["store_initialized"] is False

    _initialize(provider)
    try:
        provider.on_turn_start(3, "hello")
        status = provider.lifecycle_status()

        assert status["schema"] == "brainstack.provider_lifecycle.v1"
        assert status["status"] == "active"
        assert status["store_initialized"] is True
        assert status["session_id"] == "lifecycle-session"
        assert "principal_scope_key" in status
        hook_names = {hook["name"] for hook in status["hooks"]}
        assert {"initialize", "prefetch", "sync_turn", "on_session_end", "shutdown"}.issubset(hook_names)
        exported = {tool["name"]: tool["tool_class"] for tool in status["exported_tools"]}
        assert exported["brainstack_recall"].startswith("read_only_memory")
        assert exported["brainstack_inspect"].startswith("read_only_memory")
        assert exported["brainstack_stats"].startswith("read_only_memory")
        assert "runtime_handoff_update" not in exported
        operator_tools = {tool["name"]: tool for tool in status["operator_only_tools"]}
        assert operator_tools["runtime_handoff_update"]["x_brainstack_model_callable"] is False
        assert "brainstack_invalidate" in status["disabled_memory_write_tools"]
        assert status["shared_state_safety"]["runtime_authority"].startswith("Hermes owns")
    finally:
        provider.shutdown()

    after = provider.lifecycle_status()
    assert after["status"] == "unavailable"
    assert after["store_initialized"] is False


def test_brainstack_stats_includes_lifecycle_snapshot(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    _initialize(provider)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": False}))
        lifecycle = payload["lifecycle"]
        assert lifecycle["schema"] == "brainstack.provider_lifecycle.v1"
        assert lifecycle["status"] == "active"
        assert payload["report"]["schema"] == "brainstack.memory_kernel_doctor.v1"
        assert "brainstack_recall" in {tool["name"] for tool in lifecycle["exported_tools"]}
    finally:
        provider.shutdown()
