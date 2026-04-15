"""Host-level tests for Brainstack native memory displacement."""

# ruff: noqa: E402

import json
from unittest.mock import MagicMock, patch

from tests._host_import_shims import install_host_import_shims
install_host_import_shims()

from plugins.memory.brainstack import BrainstackMemoryProvider
from run_agent import AIAgent, MEMORY_GUIDANCE


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


class TestBrainstackNativeMemoryDisplacement:
    def test_memory_tool_removed_from_live_surface_when_builtin_store_is_off(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            assert agent._memory_store is None
            assert agent._memory_manager is not None
            assert "memory" not in agent.valid_tool_names
            assert {tool["function"]["name"] for tool in agent.tools} == {"terminal", "skill_manage"}
        finally:
            agent._memory_manager.shutdown_all()

    def test_system_prompt_omits_builtin_memory_guidance_but_keeps_brainstack_block(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            agent._memory_manager.sync_all(
                "My name is Laura and I prefer concise answers.",
                "Understood.",
            )
            prompt = agent._build_system_prompt()
            assert MEMORY_GUIDANCE not in prompt
            assert "Brainstack owns personal memory in this mode." in prompt
        finally:
            agent._memory_manager.shutdown_all()

    def test_flush_and_direct_builtin_memory_calls_fail_closed(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            agent._interruptible_api_call = MagicMock()
            agent._interruptible_streaming_api_call = MagicMock()
            agent._user_turn_count = 5

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
            agent.flush_memories(messages=messages, min_turns=0)

            assert not agent._interruptible_api_call.called
            assert not agent._interruptible_streaming_api_call.called

            result = json.loads(
                agent._invoke_tool(
                    "memory",
                    {"action": "add", "target": "memory", "content": "remember this"},
                    effective_task_id="task-1",
                )
            )
            assert result["success"] is False
            assert "disabled" in result["error"].lower()
        finally:
            agent._memory_manager.shutdown_all()

    @patch("run_agent.AIAgent._build_system_prompt", return_value="system prompt")
    @patch("run_agent.AIAgent._interruptible_streaming_api_call")
    @patch("run_agent.AIAgent._interruptible_api_call")
    def test_background_memory_review_stays_off_when_builtin_memory_is_displaced(
        self,
        mock_api,
        mock_stream,
        _mock_system_prompt,
        monkeypatch,
        tmp_path,
    ):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            response = _fake_response("response")
            mock_api.return_value = response
            mock_stream.return_value = response
            agent._memory_nudge_interval = 1
            agent._spawn_background_review = MagicMock()

            agent.run_conversation(
                user_message="Please remember our preferences.",
                conversation_history=[],
            )

            agent._spawn_background_review.assert_not_called()
        finally:
            agent._memory_manager.shutdown_all()
