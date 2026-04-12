from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if "agent" not in sys.modules:
    agent_module = types.ModuleType("agent")
    agent_module.__path__ = []
    sys.modules["agent"] = agent_module

if "agent.memory_provider" not in sys.modules:
    memory_provider_module = types.ModuleType("agent.memory_provider")

    class MemoryProvider:  # pragma: no cover - import shim for source tests
        pass

    memory_provider_module.MemoryProvider = MemoryProvider
    sys.modules["agent.memory_provider"] = memory_provider_module

if "hermes_constants" not in sys.modules:
    hermes_constants = types.ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = lambda: REPO_ROOT
    sys.modules["hermes_constants"] = hermes_constants

from brainstack import BrainstackMemoryProvider
from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore


def test_build_working_memory_packet_marks_semantic_channel_degraded(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"))
    store.open()
    store.add_continuity_event(
        session_id="session-1",
        turn_number=1,
        kind="turn",
        content="We are working on Project Atlas.",
        source="test",
    )

    packet = build_working_memory_packet(
        store,
        query="What are we working on?",
        session_id="session-1",
        profile_match_limit=4,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=1,
        transcript_char_budget=240,
        graph_limit=3,
        corpus_limit=2,
        corpus_char_budget=320,
    )

    semantic = next(channel for channel in packet["channels"] if channel["name"] == "semantic")
    assert semantic["status"] == "degraded"
    assert "semantic" in semantic["reason"].lower()
    store.close()


def test_sync_turn_no_longer_turns_handwritten_tier1_matches_into_profile_rows(tmp_path):
    provider = BrainstackMemoryProvider(config={"db_path": str(tmp_path / "brainstack.db")})
    provider.initialize("session-style", hermes_home=str(tmp_path))
    try:
        provider.sync_turn(
            "My name is Laura. I prefer concise answers and do not use emoji.",
            "Understood.",
            session_id="session-style",
        )

        profile_rows = provider._store.list_profile_items(limit=10)
        continuity_rows = provider._store.recent_continuity(session_id="session-style", limit=10)
        transcript_rows = provider._store.recent_transcript(session_id="session-style", limit=10)

        assert profile_rows == []
        assert any("concise answers" in row["content"] for row in continuity_rows)
        assert any("do not use emoji" in row["content"] for row in transcript_rows)
    finally:
        provider.shutdown()
