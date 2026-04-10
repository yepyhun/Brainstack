"""Focused tests for the Brainstack transcript shelf."""

from pathlib import Path

from plugins.memory.brainstack import BrainstackMemoryProvider


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
