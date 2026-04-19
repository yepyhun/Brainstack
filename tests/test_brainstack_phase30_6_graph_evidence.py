# ruff: noqa: E402

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tests._host_import_shims import install_host_import_shims

install_host_import_shims(hermes_home=REPO_ROOT)

from brainstack import BrainstackMemoryProvider
from brainstack.extraction_pipeline import build_session_message_ingest_plan, build_turn_ingest_plan
from brainstack.graph import ingest_graph_evidence
from brainstack.graph_evidence import GraphEvidenceItem, extract_graph_evidence_from_text
from brainstack.db import BrainstackStore


def test_turn_ingest_plan_emits_typed_graph_evidence():
    plan = build_turn_ingest_plan(
        user_content="Project Atlas is active now. Laura is in Budapest.",
        pending_turns=0,
        idle_seconds=60.0,
        idle_window_seconds=30,
        batch_turn_limit=5,
    )

    assert plan.graph_evidence_items
    assert all(isinstance(item, GraphEvidenceItem) for item in plan.graph_evidence_items)
    assert any(item.kind == "state" and item.attribute == "status" for item in plan.graph_evidence_items)
    assert any(item.kind == "state" and item.attribute == "location" for item in plan.graph_evidence_items)


def test_session_message_ingest_plan_fails_closed_without_typed_graph_evidence():
    plan = build_session_message_ingest_plan(
        role="user",
        content="Do you think his rejection is a defense mechanism?",
    )

    assert plan.graph_evidence_items == []


def test_graph_truth_write_requires_typed_evidence(tmp_path):
    store = BrainstackStore(str(tmp_path / "brainstack.db"), graph_backend="none", corpus_backend="none")
    store.open()
    try:
        try:
            ingest_graph_evidence(
                store,
                evidence_items=["Project Atlas is active now."],
                source="test",
                metadata={"session_id": "session-1"},
            )
            raised = False
        except TypeError:
            raised = True
        assert raised
        assert store.search_graph(query="Project Atlas", limit=5) == []
    finally:
        store.close()


def test_provider_sync_turn_keeps_graph_truth_empty_without_typed_evidence(tmp_path):
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "graph_backend": "none",
            "corpus_backend": "none",
        }
    )
    provider.initialize("session-no-graph-write", hermes_home=str(tmp_path))
    try:
        provider.sync_turn(
            "Do you think his rejection is a defense mechanism?",
            "I do not know.",
            session_id="session-no-graph-write",
        )

        assert provider._store is not None
        assert provider._store.search_graph(query="rejection", limit=5) == []
    finally:
        provider.shutdown()


def test_provider_sync_turn_persists_typed_graph_evidence(tmp_path):
    provider = BrainstackMemoryProvider(
        config={
            "db_path": str(tmp_path / "brainstack.db"),
            "graph_backend": "none",
            "corpus_backend": "none",
        }
    )
    provider.initialize("session-typed-graph", hermes_home=str(tmp_path))
    try:
        provider.sync_turn(
            "Project Atlas is active now. Laura is in Budapest.",
            "Saved.",
            session_id="session-typed-graph",
        )

        assert provider._store is not None
        graph_rows = provider._store.search_graph(query="Project Atlas", limit=5)
        assert any(
            row["subject"] == "Project Atlas" and row["object_value"] == "active"
            for row in graph_rows
        )
    finally:
        provider.shutdown()


def test_text_extraction_produces_bounded_evidence_spans():
    evidence_items = extract_graph_evidence_from_text("Project Atlas is active now.")

    assert len(evidence_items) == 1
    span = evidence_items[0].evidence_span
    assert span is not None
    assert span.excerpt == "Project Atlas is active now"
    assert span.start_char == 0
    assert span.end_char > span.start_char
