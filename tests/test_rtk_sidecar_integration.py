import sys
import types
from unittest.mock import MagicMock, patch

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


def _make_agent(monkeypatch, tmp_path, *, rtk_enabled=False, skip_memory=True):
    monkeypatch.setattr("run_agent.get_tool_definitions", lambda **kw: _tool_defs("web_search", "memory"))
    monkeypatch.setattr("run_agent.check_toolset_requirements", lambda: {})
    monkeypatch.setattr("run_agent.OpenAI", _FakeOpenAI)
    monkeypatch.setattr("run_agent.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "memory": {
                "memory_enabled": False,
                "user_profile_enabled": False,
                "provider": "brainstack",
                "nudge_interval": 1,
                "flush_min_turns": 1,
            },
            "sidecars": {
                "rtk": {
                    "enabled": rtk_enabled,
                    "mode": "balanced",
                }
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
        skip_memory=skip_memory,
        max_iterations=4,
    )
    agent.client = MagicMock()
    return agent


def _mock_tool_call(name="web_search", arguments="{}", call_id="c1"):
    function = MagicMock()
    function.name = name
    function.arguments = arguments
    tc = MagicMock()
    tc.id = call_id
    tc.function = function
    return tc


def _mock_assistant_message(*tool_calls):
    msg = MagicMock()
    msg.tool_calls = list(tool_calls)
    return msg


class TestRTKSidecarIntegration:
    def test_rtk_sidecar_tightens_large_tool_result_budget_and_records_savings(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path, rtk_enabled=True, skip_memory=True)
        tc = _mock_tool_call(name="web_search", call_id="c1")
        msg = _mock_assistant_message(tc)
        messages = []

        with patch("run_agent.handle_function_call", return_value=("x" * 60_000)):
            agent._execute_tool_calls(msg, messages, "task-1")

        assert len(messages) == 1
        assert len(messages[0]["content"]) < 60_000
        assert (
            "<persisted-output>" in messages[0]["content"]
            or "[Truncated:" in messages[0]["content"]
        )
        assert agent._rtk_sidecar.enabled is True
        assert agent._rtk_sidecar_stats.total_chars_saved > 0
        assert agent._rtk_sidecar_stats.persisted_results + agent._rtk_sidecar_stats.truncated_results >= 1

    def test_rtk_sidecar_does_not_take_memory_ownership(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path, rtk_enabled=True, skip_memory=False)
        try:
            assert agent._rtk_sidecar.enabled is True
            assert agent._memory_manager is not None
            assert "memory" not in agent.valid_tool_names
            assert len(agent._memory_manager._providers) == 1
            assert agent._memory_manager._providers[0].name == "brainstack"
        finally:
            agent._memory_manager.shutdown_all()
