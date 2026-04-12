import hashlib
import logging
import math
import re
import sys
import types
from pathlib import Path


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

from brainstack.control_plane import build_working_memory_packet
from brainstack.corpus_backend_chroma import ChromaCorpusBackend
from brainstack.db import BrainstackStore


class DeterministicEmbeddingFunction:
    def __call__(self, input):
        rows = []
        for text in list(input):
            vector = [0.0] * 8
            for token in re.findall(r"[^\W_]+", str(text or "").lower(), flags=re.UNICODE):
                digest = hashlib.sha1(token.encode("utf-8")).digest()
                for index in range(len(vector)):
                    vector[index] += digest[index] / 255.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            rows.append([value / norm for value in vector])
        return rows


def _patch_embeddings(monkeypatch):
    monkeypatch.setattr(
        ChromaCorpusBackend,
        "_build_embedding_function",
        lambda self: DeterministicEmbeddingFunction(),
    )


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.db"),
        corpus_backend="chroma",
        corpus_db_path=str(tmp_path / "brainstack.chroma"),
    )
    store.open()
    return store


def test_chroma_bootstrap_replays_sqlite_corpus_and_activates_semantic_channel(tmp_path, monkeypatch):
    sqlite_store = BrainstackStore(str(tmp_path / "brainstack.db"))
    sqlite_store.open()
    try:
        sqlite_store.ingest_corpus_document(
            stable_key="atlas:roadmap",
            title="Project Atlas Roadmap",
            doc_kind="doc",
            source="test",
            sections=[
                {"heading": "Overview", "content": "Project Atlas planning roadmap and delivery schedule."},
                {"heading": "Scope", "content": "The roadmap tracks planning milestones and architecture recovery."},
            ],
        )
    finally:
        sqlite_store.close()

    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        semantic_rows = store.search_corpus_semantic(query="atlas planning roadmap", limit=4)
        assert semantic_rows
        assert semantic_rows[0]["retrieval_source"] == "corpus.semantic"

        packet = build_working_memory_packet(
            store,
            query="What is the Atlas roadmap about?",
            session_id="session-1",
            profile_match_limit=4,
            continuity_recent_limit=1,
            continuity_match_limit=1,
            transcript_match_limit=1,
            transcript_char_budget=240,
            graph_limit=2,
            corpus_limit=3,
            corpus_char_budget=360,
        )
        semantic = next(channel for channel in packet["channels"] if channel["name"] == "semantic")
        assert semantic["status"] == "active"
        assert semantic["candidate_count"] > 0
        assert packet["fused_candidates"]

        journal_rows = store.list_publish_journal(target_name="corpus.chroma", status="published", limit=10)
        assert any(row["object_key"] == "atlas:roadmap" for row in journal_rows)
    finally:
        store.close()


def test_chroma_publish_journal_tracks_failure_then_successful_replay(tmp_path, monkeypatch):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        backend = store._corpus_backend
        assert backend is not None
        original_publish = backend.publish_document
        failed_once = {"value": False}

        def _failing_publish(snapshot):
            if not failed_once["value"] and snapshot["document"]["stable_key"] == "brainstack:l3":
                failed_once["value"] = True
                raise RuntimeError("boom")
            return original_publish(snapshot)

        backend.publish_document = _failing_publish

        try:
            store.ingest_corpus_document(
                stable_key="brainstack:l3",
                title="Brainstack Layer 3",
                doc_kind="doc",
                source="test",
                sections=[
                    {"heading": "Raw retrieval", "content": "Layer 3 focuses on raw corpus retrieval before packing."},
                ],
            )
        except RuntimeError as exc:
            assert "boom" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("expected failing publish path")

        failed_rows = store.list_publish_journal(target_name="corpus.chroma", status="failed", limit=10)
        assert any(row["object_key"] == "brainstack:l3" for row in failed_rows)

        backend.publish_document = original_publish
        store.ingest_corpus_document(
            stable_key="brainstack:l3",
            title="Brainstack Layer 3",
            doc_kind="doc",
            source="test",
            sections=[
                {"heading": "Raw retrieval", "content": "Layer 3 focuses on raw corpus retrieval before packing."},
                {"heading": "Packing", "content": "Packing stays bounded and secondary to retrieval quality."},
            ],
        )

        semantic_rows = store.search_corpus_semantic(query="raw corpus retrieval", limit=4)
        assert semantic_rows

        published_rows = store.list_publish_journal(target_name="corpus.chroma", status="published", limit=10)
        replayed = next(row for row in published_rows if row["object_key"] == "brainstack:l3")
        assert replayed["attempt_count"] >= 1
        assert replayed["published_at"]
    finally:
        store.close()


def test_chroma_publish_replaces_sections_without_losing_document_identity(tmp_path, monkeypatch):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.ingest_corpus_document(
            stable_key="brainstack:l3",
            title="Brainstack Layer 3",
            doc_kind="doc",
            source="test",
            sections=[
                {"heading": "One", "content": "First section about raw retrieval."},
                {"heading": "Two", "content": "Second section about bounded packing."},
                {"heading": "Three", "content": "Third section about semantic search."},
            ],
        )
        store.ingest_corpus_document(
            stable_key="brainstack:l3",
            title="Brainstack Layer 3",
            doc_kind="doc",
            source="test",
            sections=[
                {"heading": "One", "content": "First section about raw retrieval."},
                {"heading": "Two", "content": "Second section about bounded packing."},
            ],
        )

        backend = store._corpus_backend
        assert backend is not None
        payload = backend.collection.get(where={"stable_key": "brainstack:l3"}, include=[])
        ids = sorted(str(item) for item in (payload.get("ids") or []))
        assert ids == ["brainstack:l3:0", "brainstack:l3:1"]
    finally:
        store.close()


def test_semantic_search_logs_warning_and_degrades_when_backend_raises(tmp_path, monkeypatch, caplog):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        backend = store._corpus_backend
        assert backend is not None
        monkeypatch.setattr(backend, "search_semantic", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("search boom")))

        with caplog.at_level(logging.WARNING):
            rows = store.search_corpus_semantic(query="atlas roadmap", limit=3)

        assert rows == []
        status = store.corpus_semantic_channel_status()
        assert status["status"] == "degraded"
        assert "search boom" in status["reason"]
        assert any("Brainstack corpus semantic search failed" in record.message for record in caplog.records)
    finally:
        store.close()


def test_conversation_transcript_is_published_to_chroma_and_found_semantically(tmp_path, monkeypatch):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content="User: I used Uber Eats and Grubhub this month.\nAssistant: Saved.",
            source="test",
            created_at="2024-03-15T00:00:00+00:00",
        )

        rows = store.search_conversation_semantic(
            query="How many food delivery services have I used?",
            session_id="phase20",
            limit=3,
        )
        assert rows
        assert rows[0]["match_mode"] == "semantic"
        assert rows[0]["retrieval_source"] == "conversation.semantic"
        assert "Uber Eats" in rows[0]["content"]

        packet = build_working_memory_packet(
            store,
            query="How many food delivery services have I used?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=2,
            transcript_char_budget=560,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )
        assert "## Brainstack Transcript Evidence" in packet["block"]
        assert "Uber Eats" in packet["block"]
        assert "2024-03-15" in packet["block"]
        semantic = next(channel for channel in packet["channels"] if channel["name"] == "semantic")
        assert semantic["status"] == "active"
        assert semantic["candidate_count"] > 0
    finally:
        store.close()
