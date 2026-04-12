import logging
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
from brainstack.executive_retrieval import _should_attempt_route_hint


class DeterministicEmbeddingFunction:
    def __call__(self, input):
        rows = []
        for text in list(input):
            vector = [0.0] * 8
            for token in re.findall(r"[^\W_]+", str(text or "").lower(), flags=re.UNICODE):
                slot = hash(token) % len(vector)
                vector[slot] += 1.0
            magnitude = sum(value * value for value in vector) ** 0.5 or 1.0
            rows.append([value / magnitude for value in vector])
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
        graph_backend="kuzu",
        graph_db_path=str(tmp_path / "brainstack.kuzu"),
        corpus_backend="chroma",
        corpus_db_path=str(tmp_path / "brainstack.chroma"),
    )
    store.open()
    return store


def _seed_shared_facts(store: BrainstackStore) -> None:
    store.add_continuity_event(
        session_id="phase20",
        turn_number=1,
        kind="turn",
        content="We are working on Project Atlas and answers should stay concise.",
        source="test",
    )
    store.add_continuity_event(
        session_id="phase20",
        turn_number=2,
        kind="turn",
        content="Project Atlas is the active effort right now.",
        source="test",
    )
    store.add_graph_relation(
        subject_name="Project Atlas",
        predicate="integrates_with",
        object_name="Hermes Bestie",
        source="test",
    )
    store.ingest_corpus_document(
        stable_key="atlas:biochem",
        title="Biochemistry Notes",
        doc_kind="doc",
        source="test",
        sections=[
            {
                "heading": "Citrate cycle",
                "content": "The citrate cycle connects carbohydrate metabolism to ATP production.",
            },
            {
                "heading": "Glycolysis",
                "content": "Glycolysis happens in the cytosol before the citrate cycle.",
            },
        ],
    )


def _packet(
    store: BrainstackStore,
    *,
    query: str,
    graph_limit: int,
    corpus_limit: int,
    route_resolver=None,
) -> dict:
    return build_working_memory_packet(
        store,
        query=query,
        session_id="phase20",
        profile_match_limit=0,
        continuity_recent_limit=2,
        continuity_match_limit=2,
        transcript_match_limit=0,
        transcript_char_budget=0,
        graph_limit=graph_limit,
        corpus_limit=corpus_limit,
        corpus_char_budget=480,
        route_resolver=route_resolver,
    )


def _channel(packet: dict, name: str) -> dict:
    return next(item for item in packet["channels"] if item["name"] == name)


def test_stream_a_can_isolate_l1_smartening_without_graph_or_corpus(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        _seed_shared_facts(store)
        packet = _packet(
            store,
            query="What are we working on and how should you answer?",
            graph_limit=0,
            corpus_limit=0,
        )
        assert "## Brainstack Evidence Priority" in packet["block"]
        assert "treat it as authoritative over assistant suggestions or generic prior knowledge" in packet["block"]
        assert "## Brainstack Active Communication Contract" not in packet["block"]
        assert "## Brainstack Continuity Match" in packet["block"] or "## Brainstack Recent Continuity" in packet["block"]
        assert "Project Atlas" in packet["block"]
        assert "concise" in packet["block"]
        assert "## Brainstack Graph Truth" not in packet["block"]
        assert "## Brainstack Corpus Recall" not in packet["block"]
        assert _channel(packet, "graph")["candidate_count"] == 0
        assert _channel(packet, "semantic")["candidate_count"] == 0
        assert _channel(packet, "keyword")["candidate_count"] > 0 or _channel(packet, "temporal")["candidate_count"] > 0
    finally:
        store.close()


def test_stream_b_proves_graph_delta_above_l1_baseline(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        _seed_shared_facts(store)
        baseline = _packet(
            store,
            query="What does Project Atlas integrate with?",
            graph_limit=0,
            corpus_limit=0,
        )
        graph_enabled = _packet(
            store,
            query="What does Project Atlas integrate with?",
            graph_limit=3,
            corpus_limit=0,
        )
        assert "## Brainstack Graph Truth" not in baseline["block"]
        assert "## Brainstack Graph Truth" in graph_enabled["block"]
        assert "Project Atlas integrates_with Hermes Bestie" in graph_enabled["block"]
        assert _channel(graph_enabled, "graph")["candidate_count"] > 0
    finally:
        store.close()


def test_stream_c_proves_corpus_delta_above_non_corpus_baseline(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        _seed_shared_facts(store)
        baseline = _packet(
            store,
            query="How does the citrate cycle connect to energy production?",
            graph_limit=0,
            corpus_limit=0,
        )
        corpus_enabled = _packet(
            store,
            query="How does the citrate cycle connect to energy production?",
            graph_limit=0,
            corpus_limit=2,
        )
        assert "## Brainstack Corpus Recall" not in baseline["block"]
        assert "## Brainstack Corpus Recall" in corpus_enabled["block"]
        assert "ATP production" in corpus_enabled["block"]
        semantic = _channel(corpus_enabled, "semantic")
        assert semantic["status"] == "active"
        assert semantic["candidate_count"] > 0
    finally:
        store.close()


def test_phase20_3_fact_route_does_not_inherit_legacy_decomposition_gate(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content=(
                "User: I signed up for the ShopRite rewards program today. "
                "Assistant: Nice."
            ),
            source="test",
            created_at="2024-04-15T00:00:00+00:00",
        )
        store.add_transcript_entry(
            session_id="phase20",
            turn_number=2,
            kind="turn",
            content=(
                "User: I used a Buy One Get One Free Walmart coupon on Luvs diapers. "
                "Assistant: Great savings."
            ),
            source="test",
            created_at="2024-04-09T00:00:00+00:00",
        )
        store.add_transcript_entry(
            session_id="phase20",
            turn_number=3,
            kind="turn",
            content=(
                "User: I redeemed Ibotta cashback for a $10 Amazon gift card. "
                "Assistant: Nice."
            ),
            source="test",
            created_at="2024-04-10T00:00:00+00:00",
        )

        packet = build_working_memory_packet(
            store,
            query="What was the order of these events: ShopRite, Walmart coupon, Ibotta?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=3,
            transcript_char_budget=720,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "fact", "reason": "fact route test"},
        )

        assert packet["decomposition"]["used"] is False
        assert packet["decomposition"]["legacy_disabled"] is True
        assert packet["routing"]["requested_mode"] == "fact"
        assert packet["routing"]["applied_mode"] == "fact"
        assert "## Brainstack Transcript Evidence" in packet["block"]
        recovered = [
            item
            for item in ("ShopRite rewards program", "Walmart coupon", "Ibotta cashback")
            if item in packet["block"]
        ]
        assert recovered
        assert len(recovered) < 3
    finally:
        store.close()


def test_phase20_3_temporal_route_orders_timestamped_transcript_evidence(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="books-a",
            turn_number=1,
            kind="turn",
            content="User: I finished The Hate U Give today. Assistant: Noted.",
            source="test",
            created_at="2024-03-15T00:00:00+00:00",
        )
        store.add_transcript_entry(
            session_id="books-b",
            turn_number=1,
            kind="turn",
            content="User: I finished The Nightingale last week. Assistant: Noted.",
            source="test",
            created_at="2024-04-02T00:00:00+00:00",
        )

        packet = build_working_memory_packet(
            store,
            query="Which book did I finish first, The Hate U Give or The Nightingale?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=720,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "temporal", "reason": "ordering test"},
        )

        assert packet["routing"]["requested_mode"] == "temporal"
        assert packet["routing"]["applied_mode"] == "temporal"
        assert packet["routing"]["fallback_used"] is False
        assert packet["routing"]["bounds"]["kind"] == "row_cap"
        assert packet["block"].index("The Hate U Give") < packet["block"].index("The Nightingale")
    finally:
        store.close()


def test_phase20_3_aggregate_route_widens_cross_session_recall_with_explicit_bound(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        for index, content in enumerate(
            [
                ("trip-a", "User: I drove 120 miles on the first road trip."),
                ("trip-b", "User: I drove 180 miles on the second road trip."),
                ("trip-c", "User: I drove 210 miles on the third road trip."),
                ("trip-d", "User: I drove 95 miles on the fourth road trip."),
            ],
            start=1,
        ):
            session_id, text = content
            store.add_transcript_entry(
                session_id=session_id,
                turn_number=1,
                kind="turn",
                content=f"{text} Assistant: Logged.",
                source="test",
                created_at=f"2024-04-{10 + index:02d}T00:00:00+00:00",
            )

        packet = build_working_memory_packet(
            store,
            query="How many miles did I drive in total across the four road trips?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "aggregate", "reason": "total test"},
        )

        assert packet["routing"]["requested_mode"] == "aggregate"
        assert packet["routing"]["applied_mode"] == "aggregate"
        assert packet["routing"]["bounds"]["kind"] == "row_cap"
        assert packet["routing"]["bounds"]["transcript"] >= 6
        assert "120 miles" in packet["block"]
        assert "180 miles" in packet["block"]
        assert "210 miles" in packet["block"]
        assert "95 miles" in packet["block"]
    finally:
        store.close()


def test_phase20_3_route_remains_fail_open_when_structural_mode_is_too_thin(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content="Project Atlas is the active effort right now.",
            source="test",
        )
        packet = build_working_memory_packet(
            store,
            query="What are we working on right now?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=1,
            transcript_match_limit=0,
            transcript_char_budget=0,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "aggregate", "reason": "thin route test"},
        )

        assert packet["routing"]["requested_mode"] == "aggregate"
        assert packet["routing"]["applied_mode"] == "fact"
        assert packet["routing"]["fallback_used"] is True
        assert "Project Atlas" in packet["block"]
    finally:
        store.close()


def test_phase20_3_temporal_route_falls_back_when_only_one_distinct_temporal_anchor(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        for turn_number, text in enumerate(
            [
                "User: I updated the Atlas note. Assistant: Logged.",
                "User: I clarified the same Atlas note. Assistant: Logged.",
            ],
            start=1,
        ):
            store.add_transcript_entry(
                session_id="phase20",
                turn_number=turn_number,
                kind="turn",
                content=text,
                source="test",
                created_at="2024-04-15T00:00:00+00:00",
            )

        packet = build_working_memory_packet(
            store,
            query="Which Atlas note happened first?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=520,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "temporal", "reason": "fallback test"},
        )

        assert packet["routing"]["requested_mode"] == "temporal"
        assert packet["routing"]["applied_mode"] == "fact"
        assert packet["routing"]["fallback_used"] is True
    finally:
        store.close()


def test_phase20_3_routing_hint_gate_does_not_trigger_on_plain_question_mark_only():
    assert _should_attempt_route_hint("What are we working on right now?") is False
    assert _should_attempt_route_hint("Order these events: ShopRite, Walmart coupon, Ibotta") is True


def test_phase20_2_exact_numeric_value_change_auto_supersedes_current_graph_state(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        first = store.upsert_graph_state(
            subject_name="Coin collection",
            attribute="pre_1920_count",
            value_text="37 coins",
            source="test",
            supersede=False,
        )
        second = store.upsert_graph_state(
            subject_name="Coin collection",
            attribute="pre_1920_count",
            value_text="38 coins",
            source="test",
            supersede=False,
        )

        rows = store.search_graph(query="Coin collection", limit=10)
        current = next(
            row for row in rows
            if row["row_type"] == "state" and row.get("is_current") and row["object_value"] == "38 coins"
        )
        prior = next(
            row for row in rows
            if row["row_type"] == "state" and not row.get("is_current") and row["object_value"] == "37 coins"
        )

        assert first["status"] == "inserted"
        assert second["status"] == "superseded"
        assert current["metadata"]["temporal"]["supersedes"]
        assert prior["metadata"]["temporal"]["superseded_by"]
    finally:
        store.close()


def test_phase20_2_tokenization_stays_unicode_safe_without_language_stopword_lists():
    from brainstack.transcript import tokenize_match_text

    tokens = tokenize_match_text("Mi történt a ShopRite és Ibotta eseményekkel?")

    assert "shoprite" in tokens
    assert "ibotta" in tokens
    assert "assistant" not in tokenize_match_text("Assistant: ShopRite update")


def test_cross_store_publish_journal_tracks_graph_and_corpus_targets(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        _seed_shared_facts(store)
        published = store.list_publish_journal(status="published", limit=20)
        targets = {row["target_name"] for row in published}
        assert "graph.kuzu" in targets
        assert "corpus.chroma" in targets
    finally:
        store.close()


def test_cross_store_degradation_remains_coherent(monkeypatch, tmp_path, caplog):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        _seed_shared_facts(store)
        graph_backend = store._graph_backend
        corpus_backend = store._corpus_backend
        assert graph_backend is not None
        assert corpus_backend is not None

        graph_backend.search_graph = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("graph degraded"))
        corpus_backend.search_semantic = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("corpus degraded"))

        with caplog.at_level(logging.WARNING):
            packet = _packet(
                store,
                query="What are we working on and how does the citrate cycle relate to energy?",
                graph_limit=3,
                corpus_limit=2,
            )

        assert "Project Atlas" in packet["block"] or "citrate cycle" in packet["block"]
        assert _channel(packet, "graph")["status"] == "degraded"
        assert _channel(packet, "semantic")["status"] == "degraded"
        assert any("graph degraded" in record.message or "corpus degraded" in record.message for record in caplog.records)
    finally:
        store.close()
