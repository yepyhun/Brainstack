"""Focused tests for the Brainstack transcript shelf."""

# ruff: noqa: E402

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

    setattr(memory_provider_module, "MemoryProvider", MemoryProvider)
    sys.modules["agent.memory_provider"] = memory_provider_module

if "hermes_constants" not in sys.modules:
    hermes_constants = types.ModuleType("hermes_constants")
    setattr(hermes_constants, "get_hermes_home", lambda: REPO_ROOT)
    sys.modules["hermes_constants"] = hermes_constants

from brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id: str, **config):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(base / "brainstack.db"),
            **config,
        }
    )
    provider.initialize(session_id, hermes_home=str(base))
    return provider


class TestBrainstackTranscriptShelf:
    def test_sync_turn_writes_append_only_transcript_entries_separate_from_continuity(self, tmp_path):
        provider = _make_provider(tmp_path, "session-transcript")
        try:
            provider.sync_turn(
                "The deployment window stays on Friday at 18:00 UTC after the database migration.",
                "Understood. I will remember the Friday 18:00 UTC deployment window.",
                session_id="session-transcript",
            )
            provider.sync_turn(
                "Also note that the rollback owner is Nora.",
                "Noted. Nora is the rollback owner.",
                session_id="session-transcript",
            )

            transcript_rows = provider._store.recent_transcript(session_id="session-transcript", limit=10)
            continuity_rows = provider._store.recent_continuity(session_id="session-transcript", limit=10)

            assert len([row for row in transcript_rows if row["kind"] == "turn"]) == 2
            assert len([row for row in continuity_rows if row["kind"] == "turn"]) == 2

            newest_transcript = next(row for row in transcript_rows if row["kind"] == "turn")
            newest_continuity = next(row for row in continuity_rows if row["kind"] == "turn")

            assert "User:" in newest_transcript["content"]
            assert "Assistant:" in newest_transcript["content"]
            assert "user:" in newest_continuity["content"]
            assert "assistant:" in newest_continuity["content"]
            assert "\nAssistant:" in newest_transcript["content"]
            assert " | assistant:" in newest_continuity["content"]
            assert newest_transcript["content"] != newest_continuity["content"]
        finally:
            provider.shutdown()

    def test_prefetch_uses_bounded_transcript_evidence_for_continuity_only_queries(self, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-transcript-prefetch",
            continuity_match_limit=2,
            continuity_recent_limit=2,
            transcript_match_limit=1,
            transcript_char_budget=240,
        )
        try:
            provider.sync_turn(
                "The deployment window stays on Friday at 18:00 UTC after the database migration and the rollback owner is Nora.",
                "Understood. Friday 18:00 UTC stays reserved and Nora owns rollback.",
                session_id="session-transcript-prefetch",
            )

            block = provider.prefetch(
                "What is the deployment window after the database migration and who owns rollback?",
                session_id="session-transcript-prefetch",
            )

            assert "## Brainstack Continuity Match" in block
            assert "## Brainstack Transcript Evidence" in block
            assert "Friday at 18:00 UTC" in block
            assert "Nora" in block
            assert len(block) < 1400
            assert provider._last_prefetch_policy["transcript_limit"] == 1
        finally:
            provider.shutdown()

    def test_prefetch_keeps_event_date_and_specific_tail_detail_when_transcript_is_rendered(self, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-transcript-dates",
            continuity_match_limit=1,
            continuity_recent_limit=0,
            transcript_match_limit=2,
            transcript_char_budget=560,
            corpus_backend="sqlite",
        )
        try:
            provider.sync_turn(
                "I recently bought an eyeshadow palette at Sephora and earned 50 points, bringing my total to exactly 100 points.",
                "Saved.",
                session_id="session-transcript-dates",
                event_time="2024-04-02T00:00:00+00:00",
            )

            block = provider.prefetch(
                "How many Sephora points do I have now?",
                session_id="session-transcript-dates",
            )

            assert "## Brainstack Transcript Evidence" in block
            assert "2024-04-02" in block
            assert "100 points" in block
        finally:
            provider.shutdown()

    def test_prefetch_keeps_previous_occupation_tail_detail_without_mid_word_truncation(self, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-transcript-occupation",
            continuity_match_limit=2,
            continuity_recent_limit=0,
            transcript_match_limit=2,
            transcript_char_budget=420,
            corpus_backend="sqlite",
        )
        try:
            provider.sync_turn(
                (
                    "In my new role as a senior marketing analyst I'm automating reporting workflows, "
                    "but in my previous occupation I worked as a marketing specialist at a small startup "
                    "building consumer apps for parents."
                ),
                "Saved.",
                session_id="session-transcript-occupation",
                event_time="2024-05-24T00:00:00+00:00",
            )

            block = provider.prefetch(
                "What was my previous occupation?",
                session_id="session-transcript-occupation",
            )

            assert "marketing specialist at a small startup" in block
            assert "startu..." not in block
        finally:
            provider.shutdown()

    def test_prefetch_prefers_numeric_result_turn_when_query_asks_for_total(self, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-transcript-charity",
            continuity_match_limit=2,
            continuity_recent_limit=0,
            transcript_match_limit=2,
            transcript_char_budget=560,
            corpus_backend="sqlite",
        )
        try:
            provider.sync_turn(
                "I'm planning a charity cycling event and a Facebook Fundraiser for the local shelter.",
                "That sounds like a thoughtful plan.",
                session_id="session-transcript-charity",
                event_time="2024-03-20T00:00:00+00:00",
            )
            provider.sync_turn(
                "The fundraiser is done now, and in total I raised exactly $1,250 for the shelter.",
                "Great result.",
                session_id="session-transcript-charity",
                event_time="2024-03-28T00:00:00+00:00",
            )

            block = provider.prefetch(
                "How much money did I raise for charity in total?",
                session_id="session-transcript-charity",
            )

            assert "$1,250" in block
        finally:
            provider.shutdown()

    def test_search_transcript_is_scoped_to_current_session(self, tmp_path):
        provider = _make_provider(tmp_path, "session-a")
        try:
            provider.sync_turn(
                "Exact rollback phrase for session A: Atlas rollback stays frozen until Monday morning.",
                "Saved.",
                session_id="session-a",
            )
            provider.sync_turn(
                "Exact rollback phrase for session B: Atlas rollback stays frozen until Tuesday morning.",
                "Saved.",
                session_id="session-b",
            )

            rows_a = provider._store.search_transcript(
                query="Atlas rollback stays frozen morning",
                session_id="session-a",
                limit=5,
            )
            rows_b = provider._store.search_transcript(
                query="Atlas rollback stays frozen morning",
                session_id="session-b",
                limit=5,
            )

            assert rows_a
            assert rows_b
            assert all(row["session_id"] == "session-a" for row in rows_a)
            assert all(row["session_id"] == "session-b" for row in rows_b)
            assert any("Monday morning" in row["content"] for row in rows_a)
            assert all("Tuesday morning" not in row["content"] for row in rows_a)
            assert any("Tuesday morning" in row["content"] for row in rows_b)
            assert all("Monday morning" not in row["content"] for row in rows_b)
        finally:
            provider.shutdown()
