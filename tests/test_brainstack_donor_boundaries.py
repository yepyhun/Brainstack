from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.donors import continuity_adapter, corpus_adapter, graph_adapter


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


class TestBrainstackDonorBoundaries:
    def test_provider_exposes_structured_donor_registry(self, tmp_path):
        provider = _make_provider(tmp_path, "session-registry")
        try:
            registry = provider.donor_registry()
            assert set(registry) == {"continuity", "graph_truth", "corpus"}
            assert registry["continuity"]["local_adapter"].endswith("continuity_adapter.py")
            assert registry["graph_truth"]["local_adapter"].endswith("graph_adapter.py")
            assert registry["corpus"]["local_adapter"].endswith("corpus_adapter.py")
        finally:
            provider.shutdown()

    def test_provider_sync_turn_uses_donor_continuity_adapter(self, monkeypatch, tmp_path):
        provider = _make_provider(tmp_path, "session-continuity")
        calls = []
        original = continuity_adapter.write_turn_records

        def _wrapped(store, **kwargs):
            calls.append(kwargs.copy())
            return original(store, **kwargs)

        monkeypatch.setattr(continuity_adapter, "write_turn_records", _wrapped)
        try:
            provider.sync_turn("Atlas rollout stays on Friday.", "Saved.", session_id="session-continuity")
            assert calls
            assert calls[0]["session_id"] == "session-continuity"
            rows = provider._store.recent_transcript(session_id="session-continuity", limit=10)
            assert any("Atlas rollout stays on Friday" in row["content"] for row in rows)
        finally:
            provider.shutdown()

    def test_provider_sync_turn_does_not_emit_graph_writes_from_untyped_raw_text(self, monkeypatch, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-graph",
            graph_backend="kuzu",
            graph_db_path=str(Path(tmp_path) / "brainstack.kuzu"),
        )
        calls = []
        original = graph_adapter.ingest_turn_graph_candidates

        def _wrapped(store, **kwargs):
            calls.append(kwargs.copy())
            return original(store, **kwargs)

        monkeypatch.setattr(graph_adapter, "ingest_turn_graph_candidates", _wrapped)
        try:
            provider.sync_turn("Project Atlas is active now.", "Saved.", session_id="session-graph")
            assert calls == []
            graph_rows = provider._store.search_graph(query="Project Atlas", limit=5)
            assert graph_rows == []
        finally:
            provider.shutdown()

    def test_provider_on_pre_compress_uses_donor_snapshot_adapter(self, monkeypatch, tmp_path):
        provider = _make_provider(tmp_path, "session-snapshot")
        calls = []
        original = continuity_adapter.write_snapshot_records

        def _wrapped(store, **kwargs):
            calls.append(kwargs.copy())
            return original(store, **kwargs)

        monkeypatch.setattr(continuity_adapter, "write_snapshot_records", _wrapped)
        try:
            hint = provider.on_pre_compress(
                [
                    {"role": "user", "content": "We moved the histology notes to the anatomy shelf."},
                    {"role": "assistant", "content": "Saved the continuity snapshot."},
                ]
            )
            assert calls
            assert calls[0]["kind"] == "compression_snapshot"
            rows = provider._store.recent_continuity(session_id="session-snapshot", limit=10)
            assert any(row["kind"] == "compression_snapshot" for row in rows)
            assert hint
        finally:
            provider.shutdown()

    def test_provider_on_session_end_keeps_snapshot_write_but_skips_untyped_graph_scan(self, monkeypatch, tmp_path):
        provider = _make_provider(
            tmp_path,
            "session-end",
            graph_backend="kuzu",
            graph_db_path=str(Path(tmp_path) / "brainstack.kuzu"),
        )
        snapshot_calls = []
        graph_calls = []
        original_snapshot = continuity_adapter.write_snapshot_records
        original_graph = graph_adapter.ingest_session_graph_candidates

        def _snapshot_wrapped(store, **kwargs):
            snapshot_calls.append(kwargs.copy())
            return original_snapshot(store, **kwargs)

        def _graph_wrapped(store, **kwargs):
            graph_calls.append(kwargs.copy())
            return original_graph(store, **kwargs)

        monkeypatch.setattr(continuity_adapter, "write_snapshot_records", _snapshot_wrapped)
        monkeypatch.setattr(graph_adapter, "ingest_session_graph_candidates", _graph_wrapped)
        try:
            provider.on_session_end(
                [
                    {"role": "user", "content": "Project Atlas is active now."},
                    {"role": "assistant", "content": "I will preserve the state."},
                ]
            )
            assert snapshot_calls
            assert snapshot_calls[0]["kind"] == "session_summary"
            assert graph_calls == []
            rows = provider._store.recent_continuity(session_id="session-end", limit=10)
            assert any(row["kind"] == "session_summary" for row in rows)
            graph_rows = provider._store.search_graph(query="Project Atlas", limit=5)
            assert graph_rows == []
        finally:
            provider.shutdown()

    def test_provider_ingest_corpus_document_uses_donor_corpus_adapter(self, monkeypatch, tmp_path):
        provider = _make_provider(tmp_path, "session-corpus")
        calls = []
        original = corpus_adapter.prepare_corpus_payload

        def _wrapped(**kwargs):
            calls.append(kwargs.copy())
            return original(**kwargs)

        monkeypatch.setattr(corpus_adapter, "prepare_corpus_payload", _wrapped)
        try:
            result = provider.ingest_corpus_document(
                title="Biochemistry Notes",
                source="unit-test",
                doc_kind="notes",
                content="# Krebs\nCitrate cycle regulation matters.",
            )
            assert calls
            assert calls[0]["title"] == "Biochemistry Notes"
            assert result["document_id"] > 0
        finally:
            provider.shutdown()
