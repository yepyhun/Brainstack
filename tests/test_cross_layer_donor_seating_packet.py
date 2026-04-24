from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.scope_identity import build_memory_scope_identity


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_cross_layer_packet_is_scoped_graph_cited_and_bounded(tmp_path: Path) -> None:
    scope = build_memory_scope_identity(
        platform="test",
        user_id="cross-layer-user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
        chat_type="dm",
        chat_id="chat-cross-layer",
    )
    scope_key = str(scope["principal_scope_key"])
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="session-a",
            turn_number=1,
            kind="session_summary",
            content="Delta continuity anchor says the donor seating work needs bounded recall.",
            source="phase100.proof",
            metadata={"principal_scope_key": scope_key, "principal_scope": scope},
        )
        store.upsert_graph_state(
            subject_name="Delta Kernel",
            attribute="risk",
            value_text="bounded graph trace required",
            source="phase100.proof",
            metadata={"principal_scope_key": scope_key},
        )
        store.ingest_corpus_source(
            {
                "source_adapter": "phase100_fixture",
                "source_id": "delta-corpus",
                "stable_key": "doc:phase100:delta",
                "title": "Delta Corpus",
                "doc_kind": "proof_note",
                "source_uri": "fixture://phase100/delta",
                "content": "Delta corpus citation explains bounded packet construction.",
                "metadata": {"principal_scope_key": scope_key},
            }
        )

        report = build_query_inspect(
            store,
            query="Delta donor seating bounded recall graph citation",
            session_id="session-a",
            principal_scope_key=scope_key,
            graph_limit=2,
            corpus_limit=2,
            corpus_char_budget=320,
        )

        selected = report["selected_evidence"]
        assert selected["continuity_match"]
        assert selected["graph"]
        assert selected["corpus"]
        assert selected["graph"][0]["graph_backend_requested"] == "sqlite"
        assert selected["graph"][0]["graph_backend_status"] == "active"
        assert selected["graph"][0]["match_mode"]
        assert selected["corpus"][0]["citation_id"] == "doc:phase100:delta#s0"
        assert report["final_packet"]["char_count"] < 1600
        assert "Delta corpus citation" in report["final_packet"]["preview"]
    finally:
        store.close()
