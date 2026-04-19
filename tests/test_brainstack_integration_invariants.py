"""Integration invariants guarding against half-wired Brainstack behavior."""

# ruff: noqa: E402

from unittest.mock import MagicMock

from tests._host_import_shims import install_host_import_shims
install_host_import_shims()

from brainstack import BrainstackMemoryProvider
from brainstack.extraction_pipeline import Tier2ScheduleDecision, TurnIngestPlan
from brainstack.graph_evidence import GraphEvidenceItem
from brainstack.stable_memory_guardrails import StableMemoryAdmissionDecision
from agent.brainstack_mode import blocked_brainstack_only_tool_error
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
    def test_donor_registry_does_not_create_new_live_tool_surface(self, monkeypatch, tmp_path):
        agent = _make_agent(monkeypatch, tmp_path)
        try:
            provider = agent._memory_manager._providers[-1]
            registry = provider.donor_registry()
            assert set(registry) == {"continuity", "graph_truth", "corpus"}
            assert provider.get_tool_schemas() == []
            assert agent._memory_store is None
        finally:
            agent._memory_manager.shutdown_all()

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

            provider = agent._memory_manager._providers[-1]
            agent._memory_manager.sync_all("We are proving the replacement contract.", "Continue.")
            rows = provider._store.recent_continuity(session_id=agent.session_id, limit=10)
            assert any("replacement contract" in row["content"] for row in rows)
        finally:
            agent._memory_manager.shutdown_all()

    def test_sync_turn_uses_pipeline_plan_for_durable_admission(self, monkeypatch, tmp_path):
        provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
        provider.initialize("session-pipeline", hermes_home=str(tmp_path))
        try:
            fake_plan = TurnIngestPlan(
                durable_admission=StableMemoryAdmissionDecision(False, "forced_test_reject"),
                profile_candidates=[],
                graph_evidence_items=[
                    GraphEvidenceItem(
                        kind="state",
                        subject="Project Atlas",
                        attribute="status",
                        value_text="active",
                        confidence=0.95,
                    )
                ],
                tier2_schedule=Tier2ScheduleDecision(
                    should_queue=True,
                    reason="turn_batch_limit",
                    idle_window_seconds=30,
                    batch_turn_limit=5,
                    pending_turns=0,
                    idle_seconds=0.0,
                ),
            )
            monkeypatch.setattr("brainstack.build_turn_ingest_plan", lambda **kwargs: fake_plan)

            provider.sync_turn(
                "My name is Laura. I prefer concise answers.",
                "Understood.",
                session_id="session-pipeline",
            )

            profile_rows = provider._store.list_profile_items(limit=10)
            graph_rows = provider._store.search_graph(query="Project Atlas", limit=10)

            assert profile_rows == []
            assert provider._last_tier2_schedule["reason"] == "turn_batch_limit"
            assert any(
                row["subject"] == "Project Atlas" and row["object_value"] == "active"
                for row in graph_rows
            )
        finally:
            provider.shutdown()

    def test_scoped_skill_manage_boundary_blocks_personal_memory_but_keeps_procedural_skill_learning(self):
        blocked = blocked_brainstack_only_tool_error(
            "skill_manage",
            {
                "action": "create",
                "name": "tomi-user-profile",
                "content": "Store Tomi's communication preferences.",
            },
        )
        allowed = blocked_brainstack_only_tool_error(
            "skill_manage",
            {
                "action": "create",
                "name": "git-rebase-recovery",
                "content": "Reusable workflow for recovering a broken rebase.",
            },
        )

        assert blocked is not None
        assert "personal profile" in blocked
        assert allowed is None

    def test_file_tool_boundary_blocks_hermes_side_memory_but_keeps_normal_files_available(self):
        blocked_notes = blocked_brainstack_only_tool_error(
            "write_file",
            {"path": "~/.hermes/notes/lauratom-preferences.md"},
        )
        blocked_memory_md = blocked_brainstack_only_tool_error(
            "read_file",
            {"path": "/root/.hermes/MEMORY.md"},
        )
        allowed_workspace_file = blocked_brainstack_only_tool_error(
            "write_file",
            {"path": "/workspace/project/README.md"},
        )

        assert blocked_notes is not None
        assert "side-memory files" in blocked_notes
        assert blocked_memory_md is not None
        assert allowed_workspace_file is None

    def test_session_search_remains_available_as_bounded_conversation_search(self):
        blocked = blocked_brainstack_only_tool_error(
            "session_search",
            {"query": "how did we solve docker networking last time?"},
        )

        assert blocked is None

    def test_execution_and_autonomy_detours_cannot_be_used_as_shadow_memory(self):
        blocked_execute = blocked_brainstack_only_tool_error(
            "execute_code",
            {"code": "open('/root/.hermes/persona.md').read(); plur_recall_hybrid('tomi')"},
        )
        blocked_terminal = blocked_brainstack_only_tool_error(
            "terminal",
            {"command": "cat ~/.hermes/memory.md"},
        )
        blocked_cron = blocked_brainstack_only_tool_error(
            "cronjob",
            {
                "action": "create",
                "name": "remember-user-style",
                "prompt": "Store user communication style and persona for later",
            },
        )
        allowed_terminal = blocked_brainstack_only_tool_error(
            "terminal",
            {"command": "git status"},
        )

        assert blocked_execute is not None
        assert "secondary memory apis" in blocked_execute.lower()
        assert blocked_terminal is not None
        assert "side-memory files" in blocked_terminal.lower()
        assert blocked_cron is not None
        assert "automation jobs" in blocked_cron.lower()
        assert allowed_terminal is None
