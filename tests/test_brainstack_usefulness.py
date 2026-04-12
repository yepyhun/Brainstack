from plugins.memory.brainstack.control_plane import build_working_memory_packet
from plugins.memory.brainstack.db import BrainstackStore
from plugins.memory.brainstack.usefulness import graph_priority_adjustment, profile_priority_adjustment


def test_profile_priority_adjustment_demotes_repeated_fallback_only_non_core_rows():
    row = {
        "category": "note",
        "stable_key": "note:stale",
        "metadata": {
            "retrieval_telemetry": {
                "served_count": 6,
                "match_served_count": 0,
                "fallback_served_count": 5,
            }
        },
    }
    assert profile_priority_adjustment(row) < 0


def test_profile_priority_adjustment_keeps_core_preference_rows_protected():
    row = {
        "category": "preference",
        "stable_key": "preference:emoji_usage",
        "metadata": {
            "retrieval_telemetry": {
                "served_count": 8,
                "match_served_count": 0,
                "fallback_served_count": 8,
            }
        },
    }
    assert profile_priority_adjustment(row) >= 0


def test_graph_priority_adjustment_rewards_repeated_matched_graph_rows():
    row = {
        "row_type": "state",
        "is_current": True,
        "metadata": {
            "retrieval_telemetry": {
                "served_count": 4,
                "match_served_count": 4,
                "fallback_served_count": 0,
            }
        },
    }
    assert graph_priority_adjustment(row) > 0


def test_build_working_memory_packet_records_profile_and_graph_retrieval_telemetry(tmp_path):
    store = BrainstackStore(str(tmp_path / "profile.db"))
    store.open()
    store.upsert_profile_item(
        stable_key="preference:communication_style",
        category="preference",
        content="Explain things clearly without jargon.",
        source="test",
        confidence=0.92,
        metadata={"session_id": "session-usefulness"},
    )

    style_packet = build_working_memory_packet(
        store,
        query="Explain things without jargon.",
        session_id="session-usefulness",
        profile_match_limit=4,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=1,
        transcript_char_budget=240,
        graph_limit=3,
        corpus_limit=2,
        corpus_char_budget=320,
    )
    profile = store.get_profile_item(stable_key="preference:communication_style")
    assert profile is not None
    telemetry = (profile.get("metadata") or {}).get("retrieval_telemetry") or {}
    assert telemetry.get("served_count") == 1
    assert telemetry.get("match_served_count") == 1
    assert telemetry.get("fallback_served_count") == 0
    assert "## Brainstack Active Communication Contract" in style_packet["block"]
    assert any(channel["name"] == "semantic" and channel["status"] == "degraded" for channel in style_packet["channels"])
    store.close()

    graph_store = BrainstackStore(str(tmp_path / "graph.db"))
    graph_store.open()
    graph_store.upsert_graph_state(
        subject_name="BrainStack",
        attribute="status",
        value_text="active",
        source="test",
        supersede=True,
    )
    graph_packet = build_working_memory_packet(
        graph_store,
        query="BrainStack status",
        session_id="session-usefulness",
        profile_match_limit=4,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=1,
        transcript_char_budget=240,
        graph_limit=3,
        corpus_limit=2,
        corpus_char_budget=320,
    )
    graph_rows = graph_store.search_graph(query="BrainStack status", limit=5)
    state_row = next(row for row in graph_rows if row["row_type"] == "state")
    graph_telemetry = (state_row.get("metadata") or {}).get("retrieval_telemetry") or {}
    assert graph_telemetry.get("served_count") == 1
    assert graph_telemetry.get("match_served_count") == 1
    assert "## Brainstack Graph Truth" in graph_packet["block"]
    graph_store.close()
