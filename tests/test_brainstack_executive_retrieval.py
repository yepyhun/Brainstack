# ruff: noqa: E402
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore
from brainstack.executive_retrieval import _graph_match_text, _select_temporal_rows, retrieve_executive_context


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


def test_temporal_route_uses_temporal_graph_rows_for_selection():
    class DummyStore:
        def get_profile_item(self, stable_key, principal_scope_key=""):
            return None

        def search_profile(self, query, limit):
            return []

        def search_continuity(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_transcript(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_transcript_global(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus(self, query, limit, principal_scope_key=None):
            return []

        def search_conversation_semantic(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus_semantic(self, query, limit, principal_scope_key=None):
            return []

        def search_graph(self, query, limit, principal_scope_key=None):
            return [
                {
                    "row_type": "relation",
                    "row_id": 1,
                    "subject": "User",
                    "predicate": "mentioned",
                    "object_value": "generic travel chatter",
                    "keyword_score": 10,
                    "happened_at": "2026-04-01T10:00:00Z",
                },
                {
                    "row_type": "state",
                    "row_id": 2,
                    "attribute": "trip_order",
                    "value": "Muir Woods before Big Sur before Yosemite",
                    "is_current": True,
                    "keyword_score": 0,
                    "happened_at": "2026-04-05T10:00:00Z",
                },
            ]

        def recent_continuity(self, session_id, limit):
            return [
                {
                    "id": 11,
                    "created_at": "2026-04-04T09:00:00Z",
                    "content": "Recent trip planning note",
                    "metadata": {"temporal": {"observed_at": "2026-04-04T09:00:00Z"}},
                },
                {
                    "id": 12,
                    "created_at": "2026-04-06T09:00:00Z",
                    "content": "Follow-up trip note",
                    "metadata": {"temporal": {"observed_at": "2026-04-06T09:00:00Z"}},
                },
            ]

        def search_temporal_continuity(self, query, session_id, limit, principal_scope_key=None):
            return []

        def graph_backend_channel_status(self):
            return {"status": "active", "reason": "ok"}

        def corpus_semantic_channel_status(self):
            return {"status": "active", "reason": "ok"}

    retrieval = retrieve_executive_context(
        DummyStore(),
        query="What is the order of the trips from earliest to latest?",
        session_id="session-1",
        analysis={"temporal": True, "preference": False},
        policy={
            "profile_limit": 0,
            "continuity_match_limit": 0,
            "continuity_recent_limit": 2,
            "transcript_limit": 0,
            "graph_limit": 1,
            "corpus_limit": 0,
        },
        route_resolver=lambda query: {"mode": "temporal", "reason": "test"},
    )

    assert retrieval["routing"]["applied_mode"] == "temporal"
    assert retrieval["graph_rows"]
    assert retrieval["graph_rows"][0]["row_type"] == "state"
    assert retrieval["graph_rows"][0]["value"] == "Muir Woods before Big Sur before Yosemite"


def test_temporal_route_prioritizes_temporal_continuity_before_generic_recent_rows():
    class DummyStore:
        def get_profile_item(self, stable_key, principal_scope_key=""):
            return None

        def search_profile(self, query, limit):
            return []

        def search_continuity(self, query, session_id, limit, principal_scope_key=None):
            return [
                {
                    "id": 1,
                    "session_id": "seed",
                    "turn_number": 25,
                    "kind": "turn",
                    "created_at": "2026-04-14T16:18:48.248641+00:00",
                    "content": "User requested reminder to order Luna's grain-free wet food in blue packets",
                    "keyword_score": 1,
                },
                {
                    "id": 2,
                    "session_id": "seed",
                    "turn_number": 60,
                    "kind": "turn",
                    "created_at": "2026-04-14T16:19:06.981994+00:00",
                    "content": "User finished The Seven Husbands of Evelyn Hugo audiobook",
                    "keyword_score": 1,
                },
            ]

        def search_transcript(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_transcript_global(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus(self, query, limit, principal_scope_key=None):
            return []

        def search_conversation_semantic(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus_semantic(self, query, limit, principal_scope_key=None):
            return []

        def search_graph(self, query, limit, principal_scope_key=None):
            return []

        def recent_continuity(self, session_id, limit):
            return [
                {
                    "id": 1,
                    "session_id": "seed",
                    "turn_number": 25,
                    "kind": "turn",
                    "created_at": "2026-04-14T16:18:48.248641+00:00",
                    "content": "User requested reminder to order Luna's grain-free wet food in blue packets",
                    "keyword_score": 1,
                },
                {
                    "id": 2,
                    "session_id": "seed",
                    "turn_number": 60,
                    "kind": "turn",
                    "created_at": "2026-04-14T16:19:06.981994+00:00",
                    "content": "User finished The Seven Husbands of Evelyn Hugo audiobook",
                    "keyword_score": 1,
                },
            ]

        def search_temporal_continuity(self, query, session_id, limit, principal_scope_key=None):
            return [
                {
                    "id": 10,
                    "session_id": "seed",
                    "turn_number": 230,
                    "kind": "temporal_event",
                    "created_at": "2026-04-14T16:21:09.833893+00:00",
                    "content": "User returned from solo Yosemite camping, started planning Eastern Sierra trip",
                    "keyword_score": 1,
                    "metadata": {"temporal": {"observed_at": "2023-05-15T09:00:00Z"}},
                },
                {
                    "id": 11,
                    "session_id": "seed",
                    "turn_number": 231,
                    "kind": "temporal_event",
                    "created_at": "2026-04-14T16:21:09.834047+00:00",
                    "content": "User requested off-the-beaten-path car-accessible campsites",
                    "keyword_score": 0,
                    "metadata": {"temporal": {"observed_at": "2023-05-15T09:05:00Z"}},
                },
            ]

        def graph_backend_channel_status(self):
            return {"status": "active", "reason": "ok"}

        def corpus_semantic_channel_status(self):
            return {"status": "active", "reason": "ok"}

    retrieval = retrieve_executive_context(
        DummyStore(),
        query="What is the order of the three trips I took in the past three months, from earliest to latest?",
        session_id="session-1",
        analysis={"temporal": True, "preference": False},
        policy={
            "profile_limit": 0,
            "continuity_match_limit": 3,
            "continuity_recent_limit": 3,
            "transcript_limit": 0,
            "graph_limit": 0,
            "corpus_limit": 0,
        },
        route_resolver=lambda query: {"mode": "temporal", "reason": "test"},
    )

    assert retrieval["routing"]["applied_mode"] == "temporal"
    assert [row["kind"] for row in retrieval["recent"][:2]] == ["temporal_event", "temporal_event"]
    assert [row["turn_number"] for row in retrieval["recent"][:2]] == [231, 230]


def test_temporal_selection_prefers_distinct_temporal_buckets_and_avoids_reusing_recent_rows():
    temporal_rows = [
        {
            "id": 1,
            "session_id": "seed",
            "turn_number": 1,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:22.622108+00:00",
            "content": "User started planning Eastern Sierra summer camping trip",
            "metadata": {"temporal": {"observed_at": "2023-03-10T23:32:00Z"}},
        },
        {
            "id": 2,
            "session_id": "seed",
            "turn_number": 2,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:22.622029+00:00",
            "content": "User referenced prior Dipsea Trail hike at Muir Woods",
            "metadata": {"temporal": {"observed_at": "2023-03-10T23:32:00Z"}},
        },
        {
            "id": 5,
            "session_id": "seed",
            "turn_number": 5,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:22.621907+00:00",
            "content": "User returned from day hike at Muir Woods with family",
            "metadata": {"temporal": {"observed_at": "2023-03-10T23:32:00Z"}},
        },
        {
            "id": 7,
            "session_id": "seed",
            "turn_number": 7,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:39.814413+00:00",
            "content": "User returned from solo Yosemite camping trip and Big Sur/Monterey road trip with friends",
            "metadata": {"temporal": {"observed_at": "2023-04-20T04:17:00Z"}},
        },
        {
            "id": 13,
            "session_id": "seed",
            "turn_number": 13,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:58.009605+00:00",
            "content": "User mentioned recent/ongoing Yosemite solo camping trip and requested Eastern Sierra camping recommendations",
            "metadata": {"temporal": {"observed_at": "2023-04-28T10:00:00Z"}},
        },
        {
            "id": 15,
            "session_id": "seed",
            "turn_number": 15,
            "kind": "temporal_event",
            "created_at": "2026-04-14T19:48:58.009947+00:00",
            "content": "User confirmed planning to explore John Muir Wilderness and asked about JMT trailhead proximity",
            "metadata": {"temporal": {"observed_at": "2023-04-28T10:05:00Z"}},
        },
    ]

    selected = _select_temporal_rows(
        keyword_continuity_rows=[],
        recent_rows=[],
        temporal_continuity_rows=temporal_rows,
        temporal_transcript_rows=[],
        graph_rows=[],
        limits={
            "continuity_match_limit": 3,
            "continuity_recent_limit": 3,
            "transcript_limit": 0,
            "graph_limit": 0,
        },
    )

    assert [row["turn_number"] for row in selected["recent"]] == [5, 7, 15]
    assert {row["turn_number"] for row in selected["recent"]}.isdisjoint(
        {row["turn_number"] for row in selected["matched"]}
    )


def test_graph_match_text_includes_state_attribute_and_value():
    text = _graph_match_text(
        {
            "row_type": "state",
            "subject": "User",
            "attribute": "trip_order",
            "value": "Muir Woods before Big Sur before Yosemite",
        }
    )
    assert "trip_order" in text
    assert "Muir Woods before Big Sur before Yosemite" in text


def test_temporal_route_prefers_temporal_graph_rows_without_lexical_overlap_scoring():
    class DummyStore:
        def get_profile_item(self, stable_key, principal_scope_key=""):
            return None

        def search_profile(self, query, limit):
            return []

        def search_continuity(self, query, session_id, limit, principal_scope_key=None):
            return []

        def recent_continuity(self, session_id, limit):
            return []

        def search_transcript(self, query, session_id, limit):
            return []

        def search_transcript_global(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus(self, query, limit):
            return []

        def search_conversation_semantic(self, query, session_id, limit, principal_scope_key=None):
            return []

        def search_corpus_semantic(self, query, limit, principal_scope_key=None):
            return []

        def search_graph(self, query, limit, principal_scope_key=None):
            return [
                {
                    "row_type": "state",
                    "row_id": 2,
                    "attribute": "trip_order",
                    "value": "Muir Woods before Big Sur before Yosemite",
                    "is_current": True,
                    "keyword_score": 0.2,
                    "happened_at": "2026-04-05T10:00:00Z",
                },
                {
                    "row_type": "state",
                    "row_id": 3,
                    "attribute": "trip_order",
                    "value": "Big Sur before Yosemite",
                    "is_current": False,
                    "keyword_score": 0.1,
                    "happened_at": "2026-04-04T10:00:00Z",
                },
            ]

        def graph_backend_channel_status(self):
            return {"status": "active", "reason": "ok"}

        def corpus_semantic_channel_status(self):
            return {"status": "active", "reason": "ok"}

    retrieval = retrieve_executive_context(
        DummyStore(),
        query="What is the order of the trips from earliest to latest?",
        session_id="session-1",
        analysis={"temporal": True, "preference": False},
        policy={
            "profile_limit": 0,
            "continuity_match_limit": 0,
            "continuity_recent_limit": 0,
            "transcript_limit": 0,
            "graph_limit": 2,
            "corpus_limit": 0,
        },
        route_resolver=lambda query: {"mode": "temporal", "reason": "test"},
    )

    assert retrieval["routing"]["applied_mode"] == "temporal"
    assert retrieval["graph_rows"][0]["row_type"] == "state"
