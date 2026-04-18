# ruff: noqa: E402
import logging
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack.control_plane import build_working_memory_packet
from brainstack.corpus_backend_chroma import ChromaCorpusBackend
from brainstack.db import BrainstackStore
from brainstack.executive_retrieval import (
    _default_route_resolver,
    _parse_time_value,
    retrieve_executive_context,
)


class DeterministicEmbeddingFunction:
    @staticmethod
    def name() -> str:
        return "default"

    @staticmethod
    def is_legacy() -> bool:
        return False

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine"]

    @staticmethod
    def get_config() -> dict:
        return {}

    @classmethod
    def build_from_config(cls, _config: dict):
        return cls()

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

    def embed_query(self, input):
        return self([input])


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
        object_name="Hermes Agent",
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
        assert "Project Atlas integrates_with Hermes Agent" in graph_enabled["block"]
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


def test_phase20_20_aggregate_route_preserves_corpus_rows(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content="I bought three books this week for 4200 HUF, 3100 HUF, and 2600 HUF.",
            source="test",
        )
        store.add_continuity_event(
            session_id="phase20",
            turn_number=2,
            kind="turn",
            content="I want to remember the total without reopening my banking app.",
            source="test",
        )
        store.ingest_corpus_document(
            stable_key="books:total",
            title="Book spending note",
            doc_kind="note",
            source="test",
            sections=[
                {
                    "heading": "Total",
                    "content": "The three book purchases totaled 9,900 HUF.",
                }
            ],
        )

        packet = build_working_memory_packet(
            store,
            query="What was the total I spent on those three books?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=2,
            transcript_match_limit=0,
            transcript_char_budget=0,
            graph_limit=0,
            corpus_limit=2,
            corpus_char_budget=480,
            route_resolver=lambda _query: {"mode": "aggregate", "reason": "aggregate corpus bridge test"},
        )

        assert packet["routing"]["requested_mode"] == "aggregate"
        assert packet["routing"]["applied_mode"] == "aggregate"
        assert packet["corpus_rows"]
        assert "## Brainstack Corpus Recall" in packet["block"]
        assert "9,900 HUF" in packet["block"]
    finally:
        store.close()


def test_phase20_20_aggregate_route_accepts_corpus_only_support(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.ingest_corpus_document(
            stable_key="books:aggregate-support",
            title="Book spending note",
            doc_kind="note",
            source="test",
            sections=[
                {
                    "heading": "Prices",
                    "content": "The three books cost 4200 HUF, 3100 HUF, and 2600 HUF.",
                },
                {
                    "heading": "Total",
                    "content": "The combined total for the three books was 9,900 HUF.",
                },
            ],
        )

        packet = build_working_memory_packet(
            store,
            query="What was the total I spent on those three books?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=0,
            transcript_char_budget=0,
            graph_limit=0,
            corpus_limit=2,
            corpus_char_budget=480,
            route_resolver=lambda _query: {"mode": "aggregate", "reason": "aggregate corpus-only support"},
        )

        assert packet["routing"]["requested_mode"] == "aggregate"
        assert packet["routing"]["applied_mode"] == "aggregate"
        assert not packet["routing"]["fallback_used"]
        assert len(packet["corpus_rows"]) >= 2
        assert "## Brainstack Corpus Recall" in packet["block"]
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
        assert packet["routing"]["requested_mode"] == "temporal"
        assert packet["routing"]["applied_mode"] == "temporal"
        assert "## Brainstack Transcript Evidence" in packet["block"]
        recovered = [
            item
            for item in ("ShopRite rewards program", "Walmart coupon", "Ibotta cashback")
            if item in packet["block"]
        ]
        assert recovered
        assert len(packet["transcript_rows"]) <= 3
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


def test_phase20_17_noun_order_query_stays_fact_routed():
    route = _default_route_resolver("Write my cafe order in one line with size and extras.")
    assert route["mode"] == "fact"


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


def test_phase20_15_native_kuzu_sum_surfaces_typed_road_trip_total(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        owner = "Senior Digital Advertising Strategist at Middle Seat Digital with 4+ years of experience"

        for index, (name, entity_type, miles) in enumerate(
            [
                ("1,800-mile road trip total", "mileage_history", "1800"),
                ("Yellowstone family road trip", "family_road_trip", "1200"),
                ("Denver to Aspen scenic route", "planned_road_trip", "160"),
            ],
            start=1,
        ):
            observed_at = f"2024-05-{10 + index:02d}T00:00:00+00:00"
            metadata = {"temporal": {"observed_at": observed_at}}
            store.upsert_graph_state(
                subject_name=name,
                attribute="entity_type",
                value_text=entity_type,
                source="test",
                metadata=metadata,
            )
            store.upsert_graph_state(
                subject_name=name,
                attribute="owner_subject",
                value_text=owner,
                source="test",
                metadata=metadata,
            )
            store.upsert_graph_state(
                subject_name=name,
                attribute="distance_miles",
                value_text=miles,
                source="test",
                metadata=metadata,
            )

        packet = build_working_memory_packet(
            store,
            query="What is the total distance I covered in my four road trips?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=2,
            transcript_match_limit=0,
            transcript_char_budget=0,
            graph_limit=4,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "aggregate", "reason": "native aggregate test"},
        )

        assert packet["routing"]["requested_mode"] == "aggregate"
        assert packet["routing"]["applied_mode"] == "aggregate"
        assert packet["matched"][0]["kind"] == "native_aggregate"
        assert "3,000 miles" in packet["block"]
        assert "Yellowstone family road trip" in packet["block"]
        assert "Denver to Aspen scenic route" not in packet["block"]
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


def test_phase20_3_default_route_resolver_matches_current_bounded_cues():
    assert _default_route_resolver("What are we working on right now?")["mode"] == "fact"
    assert _default_route_resolver("What are my running shoes?")["mode"] == "fact"
    assert _default_route_resolver("How much money did I raise for charity in total?")["mode"] == "aggregate"
    assert _default_route_resolver("Which book did I finish reading first?")["mode"] == "temporal"
    assert _default_route_resolver("What is the order of the three trips I took?")["mode"] == "temporal"
    assert _default_route_resolver("Order these events: ShopRite, Walmart coupon, Ibotta")["mode"] == "fact"


def test_phase20_8_default_route_resolver_uses_bounded_deterministic_modes():
    assert _default_route_resolver("How much money did I raise for charity in total?")["mode"] == "aggregate"
    assert _default_route_resolver("What is the order of the three trips I took in the past three months?")["mode"] == "temporal"
    assert _default_route_resolver("How many days between Sunday mass and Ash Wednesday?")["mode"] == "temporal"
    assert _default_route_resolver(
        "I'm planning to revisit Orlando. Can you remind me of that unique dessert shop with the giant milkshakes we talked about last time?"
    )["mode"] == "fact"
    assert _default_route_resolver("What was I doing before getting the Air Fryer?")["mode"] == "fact"


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
    from brainstack.db import build_fts_query

    query = build_fts_query("Mi történt a ShopRite és Ibotta eseményekkel?")

    assert '"shoprite"' in query
    assert '"ibotta"' in query
    assert '"történt"' in query


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


def test_phase20_11_fact_route_surfaces_cross_session_keyword_transcript(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content="I need help organizing Harvest Market sales again this week.",
            source="test",
        )
        store.add_transcript_entry(
            session_id="career-history",
            turn_number=1,
            kind="turn",
            content=(
                "User: I've used Trello in my previous role as a marketing specialist at a small startup. "
                "Assistant: Noted."
            ),
            source="test",
            created_at="2024-01-05T00:00:00+00:00",
        )

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=1,
            continuity_match_limit=1,
            transcript_match_limit=2,
            transcript_char_budget=720,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        assert "marketing specialist at a small startup" in packet["block"]
    finally:
        store.close()


def test_phase20_11_temporal_channel_counts_cross_session_transcript_supply(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        trips = [
            ("trip-a", "User: I took a trip to Muir Woods last month. Assistant: Logged.", "2024-02-01T00:00:00+00:00"),
            ("trip-b", "User: I took a trip to Big Sur a few weeks later. Assistant: Logged.", "2024-03-01T00:00:00+00:00"),
            ("trip-c", "User: I took a trip to Yosemite after that. Assistant: Logged.", "2024-04-01T00:00:00+00:00"),
        ]
        for session_id, content, created_at in trips:
            store.add_transcript_entry(
                session_id=session_id,
                turn_number=1,
                kind="turn",
                content=content,
                source="test",
                created_at=created_at,
            )

        packet = build_working_memory_packet(
            store,
            query="What is the order of the three trips I took in the past three months, from earliest to latest?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=3,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "temporal", "reason": "test"},
        )

        assert packet["routing"]["applied_mode"] == "temporal"
        assert _channel(packet, "temporal")["candidate_count"] > 0
        assert "Muir Woods" in packet["block"]
        assert "Yosemite" in packet["block"]
    finally:
        store.close()


def test_phase20_11_search_profile_does_not_crash_on_priority_sort(tmp_path):
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:occupation",
            category="identity",
            content="I used to work as a marketing specialist at a small startup.",
            source="test",
            confidence=0.92,
            metadata={"session_id": "profile-session"},
        )
        hits = store.search_profile(query="marketing specialist", limit=5)
        assert hits
        assert any("marketing specialist" in str(row.get("content") or "") for row in hits)
    finally:
        store.close()


def test_phase20_11_transcript_query_normalization_demotes_question_word_junk(tmp_path):
    store = _open_store(tmp_path)
    try:
        session_id = "longmemeval:5d3d2817:seed"
        store.add_transcript_entry(
            session_id=session_id,
            turn_number=88,
            kind="turn",
            content=(
                "User: The occupation certificate process for residential work requires several dates "
                "to be established before completion."
            ),
            source="test",
            created_at="2023-05-22T17:30:00+00:00",
        )
        store.add_transcript_entry(
            session_id=session_id,
            turn_number=126,
            kind="turn",
            content=(
                "User: I've used Trello in my previous role as a marketing specialist at a small startup "
                "and I'm familiar with its features."
            ),
            source="test",
            created_at="2023-05-24T23:58:00+00:00",
        )

        hits = store.search_transcript_global(
            query="What was my previous occupation?",
            session_id=session_id,
            limit=5,
        )

        assert hits
        assert hits[0]["id"] == 2
        assert "marketing specialist" in str(hits[0].get("content") or "")
    finally:
        store.close()


def test_phase20_17_search_transcript_global_filters_other_principal_rows(tmp_path):
    store = _open_store(tmp_path)
    try:
        store.add_transcript_entry(
            session_id="session-alice",
            turn_number=1,
            kind="turn",
            content="User: My usual coffee order is an oat flat white, extra hot, no vanilla syrup.",
            source="test",
            metadata={"principal_scope_key": "platform:discord|user_id:alice"},
            created_at="2026-04-15T10:00:00Z",
        )
        store.add_transcript_entry(
            session_id="session-bob",
            turn_number=1,
            kind="turn",
            content="User: My usual coffee order is a vanilla cold brew with caramel foam.",
            source="test",
            metadata={"principal_scope_key": "platform:discord|user_id:bob"},
            created_at="2026-04-15T10:01:00Z",
        )

        hits = store.search_transcript_global(
            query="What is my usual coffee order?",
            session_id="prefetch-session",
            principal_scope_key="platform:discord|user_id:alice",
            limit=5,
        )

        assert hits
        assert all(str(row.get("principal_scope_key") or "") != "platform:discord|user_id:bob" for row in hits)
        assert any("oat flat white" in str(row.get("content") or "") for row in hits)
    finally:
        store.close()


def test_phase20_17_search_temporal_continuity_filters_other_principal_rows(tmp_path):
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="session-alice",
            turn_number=5,
            kind="temporal_event",
            content="Road trip to Big Sur and Monterey",
            source="test",
            metadata={
                "principal_scope_key": "platform:discord|user_id:alice",
                "temporal": {"observed_at": "2026-04-10T09:00:00Z"},
            },
            created_at="2026-04-10T09:00:00Z",
        )
        store.add_continuity_event(
            session_id="session-bob",
            turn_number=6,
            kind="temporal_event",
            content="Solo camping trip to Yosemite",
            source="test",
            metadata={
                "principal_scope_key": "platform:discord|user_id:bob",
                "temporal": {"observed_at": "2026-04-12T09:00:00Z"},
            },
            created_at="2026-04-12T09:00:00Z",
        )

        hits = store.search_temporal_continuity(
            query="What is the order of my trips?",
            session_id="prefetch-session",
            principal_scope_key="platform:discord|user_id:alice",
            limit=5,
        )

        assert hits
        assert all(str(row.get("principal_scope_key") or "") != "platform:discord|user_id:bob" for row in hits)
        assert any("Big Sur" in str(row.get("content") or "") for row in hits)
    finally:
        store.close()


def test_pre20_22_search_graph_filters_other_principal_rows(tmp_path):
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Project Atlas",
            attribute="status",
            value_text="active",
            source="test",
            metadata={"principal_scope_key": "platform:discord|user_id:alice"},
        )
        store.upsert_graph_state(
            subject_name="Project Atlas",
            attribute="status",
            value_text="archived",
            source="test",
            metadata={"principal_scope_key": "platform:discord|user_id:bob"},
        )

        hits = store.search_graph(
            query="Project Atlas status",
            principal_scope_key="platform:discord|user_id:alice",
            limit=10,
        )

        assert hits
        assert all(str(row.get("principal_scope_key") or "") != "platform:discord|user_id:bob" for row in hits)
        assert any(
            row.get("predicate") == "status" and str(row.get("object_value") or "") == "active"
            for row in hits
        )
        assert not any(str(row.get("object_value") or "") == "archived" for row in hits)
    finally:
        store.close()


def test_phase20_11_fact_route_keeps_semantic_transcript_evidence(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        keyword_row = {
            "id": 88,
            "session_id": "other-session",
            "turn_number": 88,
            "kind": "turn",
            "content": "User: The occupation certificate process for residential work requires several dates to be established.",
            "source": "test",
            "metadata": {},
            "created_at": "2023-05-22T10:00:00+00:00",
            "keyword_score": 1,
            "same_session": False,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }
        semantic_row = {
            "id": 99,
            "session_id": "career-session",
            "turn_number": 12,
            "kind": "turn",
            "content": "User: I used to work as a marketing specialist at a small startup before my current role.",
            "source": "test",
            "metadata": {"semantic_class": "conversation"},
            "created_at": "2023-04-03T08:30:00+00:00",
            "keyword_score": 0,
            "same_session": False,
            "semantic_score": 0.93,
            "retrieval_source": "conversation.semantic",
            "match_mode": "semantic",
        }
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [keyword_row])
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [semantic_row])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=800,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )
        assert "marketing specialist at a small startup" in packet["block"]
    finally:
        store.close()


def test_phase20_11_temporal_route_surfaces_cross_session_temporal_events(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        temporal_rows = [
            {
                "id": 501,
                "session_id": "seed-session",
                "turn_number": 18,
                "kind": "temporal_event",
                "content": "Family trip to Muir Woods National Monument",
                "source": "tier2:test",
                "metadata": {"temporal": {"observed_at": "2026-04-11T09:15:00Z"}},
                "created_at": "2026-04-11T09:15:00Z",
                "same_session": False,
            },
            {
                "id": 502,
                "session_id": "seed-session",
                "turn_number": 230,
                "kind": "temporal_event",
                "content": "Solo camping trip to Yosemite National Park",
                "source": "tier2:test",
                "metadata": {"temporal": {"observed_at": "2026-04-13T11:00:00Z"}},
                "created_at": "2026-04-13T11:00:00Z",
                "same_session": False,
            },
        ]
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_temporal_continuity", lambda **kwargs: list(temporal_rows))
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        result = retrieve_executive_context(
            store,
            query="What is the order of the three trips I told you about?",
            session_id="prefetch-session",
            analysis={"temporal": True},
            policy={
                "profile_limit": 0,
                "continuity_match_limit": 2,
                "continuity_recent_limit": 2,
                "transcript_limit": 0,
                "graph_limit": 0,
                "corpus_limit": 0,
            },
            route_resolver=lambda _query: {"mode": "temporal", "source": "test", "reason": "force temporal"},
        )

        assert result["routing"]["applied_mode"] == "temporal"
        assert [row["content"] for row in result["recent"]] == [
            "Family trip to Muir Woods National Monument",
            "Solo camping trip to Yosemite National Park",
        ]
        temporal_channel = next(channel for channel in result["channels"] if channel["name"] == "temporal")
        assert temporal_channel["candidate_count"] >= 2
    finally:
        store.close()


def test_phase20_11_fact_route_transcript_block_can_use_fused_transcript_rank(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        bad_keyword_row = {
            "id": 202,
            "session_id": "phase20",
            "turn_number": 202,
            "kind": "turn",
            "content": "User: give it to me in the form of a comma delimited list like: [name] [hex]",
            "source": "test",
            "metadata": {},
            "created_at": "2023-05-28T18:05:00+00:00",
            "keyword_score": 1,
            "same_session": True,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }
        good_keyword_row = {
            "id": 126,
            "session_id": "phase20",
            "turn_number": 126,
            "kind": "turn",
            "content": "User: I've used Trello in my previous role as a marketing specialist at a small startup.",
            "source": "test",
            "metadata": {},
            "created_at": "2023-05-24T23:58:00+00:00",
            "keyword_score": 1,
            "same_session": True,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }
        bad_semantic_row = {
            "id": 88,
            "session_id": "phase20",
            "turn_number": 88,
            "kind": "turn",
            "content": "User: The occupation certificate process for residential work requires several dates to be established.",
            "source": "test",
            "metadata": {"semantic_class": "conversation"},
            "created_at": "2023-05-22T10:00:00+00:00",
            "keyword_score": 1,
            "same_session": True,
            "semantic_score": 0.91,
            "retrieval_source": "conversation.semantic",
            "match_mode": "semantic",
        }
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [bad_keyword_row, good_keyword_row])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [bad_keyword_row, good_keyword_row])
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [bad_semantic_row])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        assert "marketing specialist at a small startup" in packet["block"]
    finally:
        store.close()


def test_phase20_11_fact_transcript_rows_prioritize_higher_overlap(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        broader_semantic_row = {
            "id": 48,
            "session_id": "phase20",
            "turn_number": 48,
            "kind": "turn",
            "content": "User: Orlando has many family-friendly dining options including Toothsome and Cheesecake Factory.",
            "source": "test",
            "metadata": {"semantic_class": "conversation"},
            "created_at": "2023-05-21T17:19:00+00:00",
            "keyword_score": 6,
            "same_session": True,
            "semantic_score": 0.73,
            "retrieval_source": "conversation.semantic",
            "match_mode": "semantic",
        }
        specific_keyword_row = {
            "id": 50,
            "session_id": "phase20",
            "turn_number": 50,
            "kind": "turn",
            "content": "User: Dessert spots after dinner. Assistant: The Sugar Factory at Icon Park is famous for giant milkshakes.",
            "source": "test",
            "metadata": {},
            "created_at": "2023-05-21T17:20:00+00:00",
            "keyword_score": 10,
            "same_session": True,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [specific_keyword_row])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [specific_keyword_row])
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [broader_semantic_row])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="Remind me of that unique dessert shop with the giant milkshakes.",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=1,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        assert packet["transcript_rows"]
        assert "Sugar Factory" in str(packet["transcript_rows"][0].get("content") or "")
    finally:
        store.close()


def test_phase20_11_fact_transcript_rows_carry_selected_continuity_ids(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        continuity_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": "User: Harvest Market planning and soap sales.",
                "source": "test",
                "created_at": "2023-05-23T14:15:00+00:00",
            },
            {
                "id": 88,
                "session_id": "phase20",
                "turn_number": 88,
                "kind": "turn",
                "content": "User: Occupation certificate process for residential work.",
                "source": "test",
                "created_at": "2023-05-22T17:30:00+00:00",
            },
            {
                "id": 128,
                "session_id": "phase20",
                "turn_number": 128,
                "kind": "turn",
                "content": (
                    "User: In my previous role at the startup, I worked as a marketing specialist "
                    "and managed interns."
                ),
                "source": "test",
                "created_at": "2023-05-24T23:58:00+00:00",
            },
        ]
        transcript_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": "User: Harvest Market planning and soap sales.",
                "source": "test",
                "created_at": "2023-05-23T14:15:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
            {
                "id": 200,
                "session_id": "phase20",
                "turn_number": 200,
                "kind": "turn",
                "content": "User: Hex color processing request.",
                "source": "test",
                "created_at": "2023-05-28T18:05:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
            {
                "id": 202,
                "session_id": "phase20",
                "turn_number": 202,
                "kind": "turn",
                "content": "User: Comma-delimited color formatting request.",
                "source": "test",
                "created_at": "2023-05-28T18:05:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
            {
                "id": 128,
                "session_id": "phase20",
                "turn_number": 128,
                "kind": "turn",
                "content": (
                    "User: In my previous role at the startup, I worked as a marketing specialist "
                    "and managed interns."
                ),
                "source": "test",
                "created_at": "2023-05-24T23:58:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
        ]
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: continuity_rows)
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=3,
            transcript_match_limit=3,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        transcript_ids = [int(row.get("id") or 0) for row in packet["transcript_rows"]]
        assert 128 in transcript_ids
        assert "marketing specialist" in packet["block"].lower()
    finally:
        store.close()


def test_phase20_11_search_continuity_filters_zero_overlap_rows(tmp_path):
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="phase20",
            turn_number=88,
            kind="turn",
            content="User: Part 36 (3) occupation certificate process for residential work.",
            source="test",
        )
        store.add_continuity_event(
            session_id="phase20",
            turn_number=126,
            kind="turn",
            content=(
                "User: I've used Trello in my previous role as a marketing specialist at a small startup "
                "and I'm familiar with its features."
            ),
            source="test",
        )

        rows = store.search_continuity(
            query="What was my previous occupation?",
            session_id="phase20",
            limit=8,
        )

        ids = [int(row.get("id") or 0) for row in rows]
        assert ids
        assert all(float(row.get("keyword_score") or 0) > 0 for row in rows)
    finally:
        store.close()


def test_phase20_11_fact_transcript_rows_only_carry_transcript_competitive_matches(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        continuity_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": "User: Harvest Market planning and previous vendor notes.",
                "source": "test",
                "created_at": "2023-05-23T14:15:00+00:00",
                "keyword_score": 1,
                "same_session": True,
            },
            {
                "id": 88,
                "session_id": "phase20",
                "turn_number": 88,
                "kind": "turn",
                "content": "User: Occupation certificate process for residential work.",
                "source": "test",
                "created_at": "2023-05-22T17:30:00+00:00",
                "keyword_score": 1,
                "same_session": True,
            },
            {
                "id": 512,
                "session_id": "phase20",
                "turn_number": 126,
                "kind": "turn",
                "content": (
                    "User: I've used Trello in my previous occupation as a marketing specialist at a small startup "
                    "and I'm familiar with its features."
                ),
                "source": "test",
                "created_at": "2023-05-24T23:57:30+00:00",
                "keyword_score": 2,
                "same_session": True,
            },
        ]
        transcript_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": "User: Harvest Market planning and previous vendor notes.",
                "source": "test",
                "created_at": "2023-05-23T14:15:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 88,
                "session_id": "phase20",
                "turn_number": 88,
                "kind": "turn",
                "content": "User: Occupation certificate process for residential work.",
                "source": "test",
                "created_at": "2023-05-22T17:30:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 126,
                "session_id": "phase20",
                "turn_number": 126,
                "kind": "turn",
                "content": (
                    "User: I've used Trello in my previous occupation as a marketing specialist at a small startup "
                    "and I'm familiar with its features."
                ),
                "source": "test",
                "created_at": "2023-05-24T23:57:00+00:00",
                "keyword_score": 2,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 200,
                "session_id": "phase20",
                "turn_number": 200,
                "kind": "turn",
                "content": "User: Comma-delimited color formatting request from previous export.",
                "source": "test",
                "created_at": "2023-05-28T18:05:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 202,
                "session_id": "phase20",
                "turn_number": 202,
                "kind": "turn",
                "content": "User: Previous export format for color processing request.",
                "source": "test",
                "created_at": "2023-05-28T18:06:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 204,
                "session_id": "phase20",
                "turn_number": 204,
                "kind": "turn",
                "content": "User: Previous report export requested for vendor dashboard.",
                "source": "test",
                "created_at": "2023-05-28T18:07:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
            {
                "id": 128,
                "session_id": "phase20",
                "turn_number": 128,
                "kind": "turn",
                "content": (
                    "User: In my previous role at the startup, I managed interns and assigned tasks "
                    "across several tools and projects for multiple teams."
                ),
                "source": "test",
                "created_at": "2023-05-24T23:58:00+00:00",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            },
        ]
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: continuity_rows)
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=3,
            transcript_match_limit=2,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        transcript_ids = [int(row.get("id") or 0) for row in packet["transcript_rows"]]
        assert 126 in transcript_ids
        assert 128 not in transcript_ids
    finally:
        store.close()


def test_phase20_11_fact_block_keeps_relevant_third_transcript_row(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        continuity_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": "User: Harvest Market planning and soap sales.",
                "source": "test",
                "created_at": "2023/05/23 (Tue) 14:15",
            },
            {
                "id": 88,
                "session_id": "phase20",
                "turn_number": 88,
                "kind": "turn",
                "content": "User: Occupation certificate process for residential work.",
                "source": "test",
                "created_at": "2023/05/22 (Mon) 17:30",
            },
            {
                "id": 128,
                "session_id": "phase20",
                "turn_number": 128,
                "kind": "turn",
                "content": (
                    "User: In my previous role at the startup, I worked as a marketing specialist "
                    "and managed interns."
                ),
                "source": "test",
                "created_at": "2023/05/24 (Wed) 23:58",
            },
        ]
        transcript_rows = [
            {
                "id": 93,
                "session_id": "phase20",
                "turn_number": 93,
                "kind": "turn",
                "content": (
                    "User: I'm preparing for the upcoming Harvest Market on September 18th and I need "
                    "some help with tracking my sales data from previous markets."
                ),
                "source": "test",
                "created_at": "2023/05/23 (Tue) 14:15",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
            {
                "id": 88,
                "session_id": "phase20",
                "turn_number": 88,
                "kind": "turn",
                "content": (
                    "User: The occupation certificate process for residential work requires several "
                    "dates to be established before completion."
                ),
                "source": "test",
                "created_at": "2023/05/22 (Mon) 17:30",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
            {
                "id": 128,
                "session_id": "phase20",
                "turn_number": 128,
                "kind": "turn",
                "content": (
                    "User: In my previous role at the startup, I worked as a marketing specialist "
                    "and managed interns."
                ),
                "source": "test",
                "created_at": "2023/05/24 (Wed) 23:58",
                "keyword_score": 1,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
            },
        ]
        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: continuity_rows)
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: transcript_rows)
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was my previous occupation?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=2,
            transcript_match_limit=3,
            transcript_char_budget=560,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )

        assert "marketing specialist" in packet["block"].lower()
    finally:
        store.close()


def test_phase20_11_temporal_sort_handles_slash_and_iso_timestamps(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        older_trip = {
            "id": 37,
            "session_id": "phase20",
            "turn_number": 37,
            "kind": "turn",
            "content": "User: I took a day hike to Muir Woods with my family.",
            "source": "test",
            "created_at": "2023/02/15 (Wed) 01:17",
            "keyword_score": 4,
            "semantic_score": 0.61,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }
        middle_trip = {
            "id": 68,
            "session_id": "phase20",
            "turn_number": 68,
            "kind": "turn",
            "content": "User: During my road trip to Yosemite National Park, I also thought about Big Sur and Monterey.",
            "source": "test",
            "created_at": "2023/02/20 (Mon) 05:52",
            "keyword_score": 2,
            "semantic_score": 0.58,
            "retrieval_source": "conversation.semantic",
            "match_mode": "semantic",
        }
        recent_summary = {
            "id": 284,
            "session_id": "phase20",
            "turn_number": 283,
            "kind": "turn",
            "content": "session summary | user: I've been collecting stamps for three months now...",
            "source": "test",
            "created_at": "2026-04-14T10:24:28.816720+00:00",
            "keyword_score": 4,
            "semantic_score": 0.0,
            "retrieval_source": "transcript.keyword",
            "match_mode": "keyword",
        }

        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [recent_summary, older_trip])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [recent_summary, older_trip])
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [middle_trip])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        assert _parse_time_value("2023/02/15 (Wed) 01:17") is not None

        packet = build_working_memory_packet(
            store,
            query="What is the order of the three trips I took in the past three months, from earliest to latest?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=3,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "temporal", "reason": "test"},
        )

        transcript_ids = [int(row.get("id") or 0) for row in packet["transcript_rows"]]
        assert transcript_ids[:2] == [37, 68]
        assert 284 in transcript_ids
    finally:
        store.close()


def test_phase20_11_control_plane_packet_exposes_selected_rows(monkeypatch, tmp_path):
    _patch_embeddings(monkeypatch)
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="phase20",
            turn_number=1,
            kind="turn",
            content="Nike has been my favourite brand so far for running shoes.",
            source="test",
        )
        store.add_transcript_entry(
            session_id="phase20",
            turn_number=2,
            kind="turn",
            content="User: I want the same Nike running shoes as last time.",
            source="test",
        )
        packet = build_working_memory_packet(
            store,
            query="What brand are my favorite running shoes?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=2,
            transcript_match_limit=1,
            transcript_char_budget=400,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
        )
        assert "matched" in packet
        assert "transcript_rows" in packet
        assert isinstance(packet["matched"], list)
        assert isinstance(packet["transcript_rows"], list)
    finally:
        store.close()


def test_phase20_18_fact_packet_carries_same_principal_session_support_rows(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        continuity_rows = [
            {
                "id": 810,
                "session_id": "coffee-memory",
                "turn_number": 9,
                "kind": "session_summary",
                "content": "Cafe preference summary for the same principal.",
                "source": "test",
                "created_at": "2026-04-15T09:00:00Z",
                "same_session": False,
                "same_principal": True,
            }
        ]
        transcript_rows = [
            {
                "id": 811,
                "session_id": "phase20",
                "turn_number": 11,
                "kind": "turn",
                "content": "My usual cafe order is an oat flat white.",
                "source": "test",
                "created_at": "2026-04-15T09:02:00Z",
                "keyword_score": 2,
                "retrieval_source": "transcript.keyword",
                "match_mode": "keyword",
                "same_session": True,
            }
        ]

        def _recent_transcript(**kwargs):
            if kwargs.get("session_id") != "coffee-memory":
                return []
            return [
                {
                    "id": 812,
                    "session_id": "coffee-memory",
                    "turn_number": 10,
                    "kind": "session_summary",
                    "content": "Coffee memory session summary.",
                    "source": "test",
                    "created_at": "2026-04-15T09:03:00Z",
                },
                {
                    "id": 813,
                    "session_id": "coffee-memory",
                    "turn_number": 12,
                    "kind": "turn",
                    "content": "Make it extra hot and skip the vanilla syrup.",
                    "source": "test",
                    "created_at": "2026-04-15T09:04:00Z",
                },
            ]

        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: list(continuity_rows))
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: list(transcript_rows))
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: list(transcript_rows))
        monkeypatch.setattr(store, "recent_transcript", _recent_transcript)
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="Write my cafe order in one line.",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=1,
            transcript_match_limit=3,
            transcript_char_budget=800,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "fact", "reason": "test"},
        )

        transcript_contents = [str(row.get("content") or "") for row in packet["transcript_rows"]]
        assert any("oat flat white" in content.lower() for content in transcript_contents)
        assert any("extra hot" in content.lower() and "vanilla" in content.lower() for content in transcript_contents)
    finally:
        store.close()


def test_phase20_18_temporal_packet_carries_same_principal_support_turns(tmp_path, monkeypatch):
    store = _open_store(tmp_path)
    try:
        temporal_rows = [
            {
                "id": 901,
                "session_id": "dentist-session",
                "turn_number": 3,
                "kind": "temporal_event",
                "content": "Dentist visit on Monday morning.",
                "source": "test",
                "created_at": "2026-04-11T09:00:00Z",
                "metadata": {"temporal": {"observed_at": "2026-04-11T09:00:00Z"}},
                "same_session": False,
                "same_principal": True,
            },
            {
                "id": 902,
                "session_id": "bike-session",
                "turn_number": 5,
                "kind": "temporal_event",
                "content": "Brake pads replaced on Tuesday afternoon.",
                "source": "test",
                "created_at": "2026-04-12T14:00:00Z",
                "metadata": {"temporal": {"observed_at": "2026-04-12T14:00:00Z"}},
                "same_session": False,
                "same_principal": True,
            },
        ]
        recent_rows = [
            {
                "id": 903,
                "session_id": "accountant-session",
                "turn_number": 7,
                "kind": "session_summary",
                "content": "Errands summary for the same principal.",
                "source": "test",
                "created_at": "2026-04-13T18:00:00Z",
                "same_session": False,
                "same_principal": True,
            }
        ]

        def _recent_transcript(**kwargs):
            if kwargs.get("session_id") != "accountant-session":
                return []
            return [
                {
                    "id": 904,
                    "session_id": "accountant-session",
                    "turn_number": 8,
                    "kind": "session_summary",
                    "content": "Accountant summary row.",
                    "source": "test",
                    "created_at": "2026-04-13T18:05:00Z",
                },
                {
                    "id": 905,
                    "session_id": "accountant-session",
                    "turn_number": 9,
                    "kind": "turn",
                    "content": "I stopped by the tax accountant after lunch.",
                    "source": "test",
                    "created_at": "2026-04-13T18:06:00Z",
                },
            ]

        monkeypatch.setattr(store, "search_profile", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_continuity", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_temporal_continuity", lambda **kwargs: list(temporal_rows))
        monkeypatch.setattr(store, "recent_continuity", lambda **kwargs: list(recent_rows))
        monkeypatch.setattr(store, "search_transcript", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_transcript_global", lambda **kwargs: [])
        monkeypatch.setattr(store, "recent_transcript", _recent_transcript)
        monkeypatch.setattr(store, "search_conversation_semantic", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_graph", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus", lambda **kwargs: [])
        monkeypatch.setattr(store, "search_corpus_semantic", lambda **kwargs: [])

        packet = build_working_memory_packet(
            store,
            query="What was the order of the dentist, brake pad, and accountant errands?",
            session_id="phase20",
            profile_match_limit=0,
            continuity_recent_limit=1,
            continuity_match_limit=2,
            transcript_match_limit=3,
            transcript_char_budget=900,
            graph_limit=0,
            corpus_limit=0,
            corpus_char_budget=0,
            route_resolver=lambda _query: {"mode": "temporal", "reason": "test"},
        )

        transcript_contents = [str(row.get("content") or "") for row in packet["transcript_rows"]]
        assert any("tax accountant" in content.lower() for content in transcript_contents)
    finally:
        store.close()
