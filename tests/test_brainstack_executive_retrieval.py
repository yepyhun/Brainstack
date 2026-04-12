from plugins.memory.brainstack import BrainstackMemoryProvider
from plugins.memory.brainstack.control_plane import build_working_memory_packet
from plugins.memory.brainstack.db import BrainstackStore


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
    assert "disabled" in semantic["reason"]
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
