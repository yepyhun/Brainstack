"""Pragmatic real-world scenario tests for the current Brainstack layer."""

from pathlib import Path

from plugins.memory.brainstack.extraction_pipeline import build_turn_ingest_plan
from plugins.memory.brainstack.stable_memory_guardrails import should_admit_stable_memory
from plugins.memory.brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(config={"db_path": str(base / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(base))
    return provider


class TestBrainstackRealWorldFlows:
    def test_tier0_hygiene_rejects_known_noise_families_but_allows_direct_self_statement(self):
        blocked = {
            "markdown_table": "| Column | Value |\n| --- | --- |\n| Preference | concise |",
            "code_blob": "```python\nprint('prefer concise answers')\nreturn True\n```",
            "quoted_transcript_dump": "User: I prefer concise answers.\nAssistant: Noted.\nUser: We are working on Atlas.",
            "document_wrapper": (
                "Attached file\n"
                "File name: medical_notes.pdf\n"
                "Pages: 12-13\n"
                "Excerpt:\n"
                "The patient notes are listed here."
            ),
            "structured_technical_blob": (
                "# Architecture review\n"
                "- Tier-0 ingest hygiene\n"
                "- Tier-1 bootstrap extractor\n"
                "- Tier-2 multilingual worker\n"
                "- Reconciler slot\n"
                "- Write-policy slot"
            ),
        }

        for reason, content in blocked.items():
            decision = should_admit_stable_memory(fact_text=content)
            assert decision.allowed is False
            assert decision.reason == reason

        allowed = should_admit_stable_memory(
            fact_text="My name is Tomi. I prefer short Hungarian answers."
        )
        assert allowed.allowed is True
        assert allowed.reason == "allowed"

    def test_sync_turn_blocks_noise_profile_but_keeps_raw_transcript(self, tmp_path):
        provider = _make_provider(tmp_path, "session-noise")
        try:
            noise = (
                "| Graph | State |\n"
                "| --- | --- |\n"
                "| Preference | concise |\n"
                "| Project | Atlas |\n"
            )
            provider.sync_turn(noise, "Ignored.", session_id="session-noise")

            profile_rows = provider._store.list_profile_items(limit=10)
            transcript_rows = provider._store.recent_transcript(session_id="session-noise", limit=10)
            continuity_rows = provider._store.recent_continuity(session_id="session-noise", limit=10)

            assert profile_rows == []
            assert any("User:" in row["content"] for row in transcript_rows)
            assert any(row["kind"] == "turn" for row in continuity_rows)
        finally:
            provider.shutdown()

    def test_turn_ingest_plan_exposes_batch_schedule_seam(self):
        waiting = build_turn_ingest_plan(
            user_content="I prefer concise answers.",
            pending_turns=4,
            idle_seconds=5,
            idle_window_seconds=30,
            batch_turn_limit=5,
        )
        assert waiting.tier2_schedule.should_queue is False
        assert waiting.tier2_schedule.reason == "waiting_for_batch"
        assert waiting.tier2_schedule.pending_turns == 4

        queued = build_turn_ingest_plan(
            user_content="I prefer concise answers.",
            pending_turns=5,
            idle_seconds=5,
            idle_window_seconds=30,
            batch_turn_limit=5,
        )
        assert queued.tier2_schedule.should_queue is True
        assert queued.tier2_schedule.reason == "turn_batch_limit"
        assert queued.tier2_schedule.pending_turns == 0

    def test_cross_session_prefetch_recalls_preference_and_shared_work(self, tmp_path):
        writer = _make_provider(tmp_path, "session-a")
        try:
            writer.sync_turn(
                "My name is Laura. I prefer concise answers. We are working on Project Atlas.",
                "Understood. I will keep answers concise and continue Project Atlas.",
                session_id="session-a",
            )
            writer.on_session_end(
                [
                    {
                        "role": "user",
                        "content": "My name is Laura. I prefer concise answers. We are working on Project Atlas.",
                    },
                    {
                        "role": "assistant",
                        "content": "Understood. I will keep answers concise and continue Project Atlas.",
                    },
                ]
            )
        finally:
            writer.shutdown()

        reader = _make_provider(tmp_path, "session-b")
        try:
            block = reader.prefetch(
                "Do I prefer concise answers and what project are we working on?",
                session_id="session-b",
            )
            assert "## Brainstack Profile Match" in block
            assert "I prefer concise answers" in block
            assert "We are working on Project Atlas" in block
            assert "## Brainstack Continuity Match" in block
        finally:
            reader.shutdown()

    def test_temporal_graph_truth_shows_current_and_prior_state(self, tmp_path):
        provider = _make_provider(tmp_path, "session-graph")
        try:
            provider.sync_turn("Project Atlas is active.", "Noted.", session_id="session-graph")
            provider.sync_turn("Project Atlas is paused now.", "Noted, current status paused.", session_id="session-graph")

            block = provider.prefetch(
                "What is the current status of Project Atlas and what changed?",
                session_id="session-graph",
            )
            assert "## Brainstack Graph Truth" in block
            assert "[state:current] Project Atlas status=paused" in block
            assert "[state:prior] Project Atlas status=active" in block
        finally:
            provider.shutdown()

    def test_corpus_recall_returns_relevant_bounded_document_sections(self, tmp_path):
        provider = _make_provider(tmp_path, "session-corpus")
        try:
            result = provider.ingest_corpus_document(
                title="Biochemistry Notes",
                content=(
                    "## Citrate cycle\n"
                    "The citrate cycle connects carbohydrate metabolism to ATP production.\n"
                    "## Glycolysis\n"
                    "Glycolysis happens in the cytosol."
                ),
                source="unit-test",
            )
            assert result["section_count"] >= 2

            block = provider.prefetch(
                "How does the citrate cycle connect to energy production?",
                session_id="session-corpus",
            )
            assert "## Brainstack Corpus Recall" in block
            assert "Biochemistry Notes > Citrate cycle" in block
            assert "ATP production" in block
            assert len(block) < 1600
        finally:
            provider.shutdown()
