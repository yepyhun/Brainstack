"""Replacement-contract tests for Brainstack host ownership."""

# ruff: noqa: E402

from pathlib import Path
from unittest.mock import MagicMock

from tests._host_import_shims import install_host_import_shims

install_host_import_shims()

from plugins.memory.brainstack import BrainstackMemoryProvider
from plugins.memory.brainstack.db import BrainstackStore
from run_agent import AIAgent


def _tool_defs(*names):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in names
    ]


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", "test")
        self.base_url = kwargs.get("base_url", "https://api.openai.com/v1")

    def close(self):
        pass


def _make_agent(monkeypatch, tmp_path, *, memory_enabled=False, user_profile_enabled=False, provider="brainstack"):
    monkeypatch.setattr("run_agent.get_tool_definitions", lambda **kw: _tool_defs("memory", "terminal", "skill_manage"))
    monkeypatch.setattr("run_agent.check_toolset_requirements", lambda: {})
    monkeypatch.setattr("run_agent.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("run_agent.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "memory": {
                "memory_enabled": memory_enabled,
                "user_profile_enabled": user_profile_enabled,
                "provider": provider,
                "nudge_interval": 1,
                "flush_min_turns": 1,
            },
            "skills": {"creation_nudge_interval": 99},
        },
    )

    def _load_provider(name):
        if name != "brainstack":
            return None
        return BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})

    monkeypatch.setattr("plugins.memory.load_memory_provider", _load_provider)

    agent = AIAgent(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        model="gpt-test",
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=False,
        max_iterations=4,
    )
    agent.client = MagicMock()
    agent.api_mode = "chat_completions"
    return agent


def _fake_response(content="ok"):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = None
    choice.message.refusal = None
    choice.message.reasoning_content = None
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    response.model = "test-model"
    response.id = "test-id"
    return response


class TestBrainstackReplacementContract:
    def test_prefetch_is_injected_into_api_messages(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            agent._memory_manager.sync_all(
                "I prefer concise answers.",
                "Understood.",
            )
            captured = {}

            def _capture(api_kwargs):
                captured.update(api_kwargs)
                return _fake_response("ok")

            agent._interruptible_api_call = MagicMock(side_effect=_capture)

            agent.run_conversation(
                user_message="What do I prefer?",
                conversation_history=[],
            )

            api_messages = captured["messages"]
            final_user = next(msg for msg in reversed(api_messages) if msg.get("role") == "user")
            assert "<memory-context>" in final_user["content"]
            assert "concise answers" in final_user["content"]
        finally:
            agent._memory_manager.shutdown_all()

    def test_pre_compress_hook_persists_compression_snapshot(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            agent.flush_memories = MagicMock()
            agent.context_compressor = MagicMock()
            agent.context_compressor.compress.return_value = [{"role": "assistant", "content": "compressed"}]
            agent.context_compressor.compression_count = 0
            agent.context_compressor.threshold_tokens = 0
            agent.context_compressor.warning_tier = None

            messages = [
                {"role": "user", "content": "We were working on the Brainstack replacement proof."},
                {"role": "assistant", "content": "Next we need the audit matrix and summary."},
            ]

            agent._compress_context(messages, system_message="sys", approx_tokens=200)

            rows = agent._memory_manager._providers[-1]._store.recent_continuity(
                session_id=agent.session_id,
                limit=10,
            )
            kinds = {row["kind"] for row in rows}
            assert "compression_snapshot" in kinds
        finally:
            agent._memory_manager.shutdown_all()

    def test_shutdown_memory_provider_persists_session_end_summary(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        db_path = Path(tmp_path) / "brainstack.db"
        try:
            agent.shutdown_memory_provider(
                messages=[
                    {"role": "user", "content": "I prefer concise answers."},
                    {"role": "assistant", "content": "Understood."},
                ]
            )
            assert agent._memory_manager._providers[-1]._store is None

            store = BrainstackStore(str(db_path))
            store.open()
            try:
                rows = store.recent_continuity(session_id=agent.session_id, limit=10)
                kinds = {row["kind"] for row in rows}
                assert "session_summary" in kinds
                summaries = [row["content"] for row in rows if row["kind"] == "session_summary"]
                assert any("concise answers" in content for content in summaries)
            finally:
                store.close()
        finally:
            try:
                agent._memory_manager.shutdown_all()
            except Exception:
                pass
