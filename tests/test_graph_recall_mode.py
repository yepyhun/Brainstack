from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect


def test_graph_recall_reports_lexical_only_mode_without_semantic_seed(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        store.upsert_graph_state(
            subject_name="Phase 69 Lexical Graph",
            attribute="status",
            value_text="lexical graph row only",
            source="graph-test",
            metadata={"principal_scope_key": "principal:graph"},
        )
        store.conn.execute("DELETE FROM semantic_evidence_index WHERE shelf = 'graph'")
        store.conn.commit()

        doctor = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )

        graph_recall = doctor["capabilities"]["graph_recall"]
        assert graph_recall["status"] == "active"
        assert graph_recall["recall_mode"] == "lexical_seeded"
        assert graph_recall["graph_row_count"] == 1
        assert graph_recall["semantic_graph_seed_count"] == 0
    finally:
        store.close()


def test_graph_recall_reports_semantic_seed_mode_separately_from_storage(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        store.upsert_graph_state(
            subject_name="Phase 69 Graph Recall",
            attribute="status",
            value_text="lexical honesty implemented",
            source="graph-test",
            metadata={
                "principal_scope_key": "principal:graph",
                "semantic_terms": ["relationship memory substrate"],
            },
        )

        doctor = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )
        assert doctor["capabilities"]["graph"]["status"] == "active"
        assert doctor["capabilities"]["graph_recall"]["recall_mode"] == "hybrid_seeded"

        report = build_query_inspect(
            store,
            query="relationship memory substrate",
            session_id="graph-session",
            principal_scope_key="principal:graph",
        )

        selected_graph = report["selected_evidence"]["graph"]
        assert selected_graph
        graph_recall_channel = [channel for channel in report["channels"] if channel["name"] == "graph_recall"][0]
        assert graph_recall_channel["status"] == "active"
        assert "semantic_seeded" in graph_recall_channel["reason"]
    finally:
        store.close()
