"""Integration invariants guarding against half-wired Brainstack behavior."""

import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault("fire", types.SimpleNamespace(Fire=lambda *a, **k: None))
sys.modules.setdefault("firecrawl", types.SimpleNamespace(Firecrawl=object))
sys.modules.setdefault("fal_client", types.SimpleNamespace())

from plugins.memory.brainstack import BrainstackMemoryProvider
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


class TestBrainstackIntegrationInvariants:
    def test_prefetch_injection_is_api_only_and_does_not_mutate_session_history(self, monkeypatch, tmp_path):
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
            final_api_user = next(msg for msg in reversed(api_messages) if msg.get("role") == "user")
            assert "<memory-context>" in final_api_user["content"]

            persisted_user = next(msg for msg in reversed(agent._session_messages) if msg.get("role") == "user")
            assert "<memory-context>" not in persisted_user["content"]
            assert persisted_user["content"] == "What do I prefer?"
        finally:
            agent._memory_manager.shutdown_all()

    def test_single_live_memory_path_is_brainstack_when_builtin_store_is_off(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            assert agent._memory_store is None
            assert agent._memory_manager is not None
            assert "memory" not in agent.valid_tool_names

            provider = agent._memory_manager._providers[-1]
            agent._memory_manager.sync_all("We are proving the replacement contract.", "Continue.")
            rows = provider._store.recent_continuity(session_id=agent.session_id, limit=10)
            assert any("replacement contract" in row["content"] for row in rows)
        finally:
            agent._memory_manager.shutdown_all()
