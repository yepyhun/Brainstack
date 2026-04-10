"""Pragmatic real-world scenario tests for the current Brainstack layer."""

from pathlib import Path

from plugins.memory.brainstack import BrainstackMemoryProvider


def _make_provider(tmp_path, session_id):
    base = Path(tmp_path)
    provider = BrainstackMemoryProvider(config={"db_path": str(base / "brainstack.db")})
    provider.initialize(session_id, hermes_home=str(base))
    return provider


class TestBrainstackRealWorldFlows:
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
