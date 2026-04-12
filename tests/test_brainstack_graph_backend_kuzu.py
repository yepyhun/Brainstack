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

    class MemoryProvider:  # pragma: no cover - simple import shim for source-repo tests
        pass

    memory_provider_module.MemoryProvider = MemoryProvider
    sys.modules["agent.memory_provider"] = memory_provider_module

if "hermes_constants" not in sys.modules:
    hermes_constants = types.ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = lambda: REPO_ROOT
    sys.modules["hermes_constants"] = hermes_constants

from brainstack.db import BrainstackStore


def _open_store(tmp_path: Path, *, db_name: str = "brainstack.db") -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / db_name),
        graph_backend="kuzu",
        graph_db_path=str(tmp_path / "brainstack.kuzu"),
    )
    store.open()
    return store


def test_kuzu_bootstrap_replays_sqlite_graph_and_handles_inflected_query(tmp_path):
    sqlite_store = BrainstackStore(str(tmp_path / "brainstack.db"))
    sqlite_store.open()
    try:
        sqlite_store.add_graph_relation(
            subject_name="Tomi",
            predicate="works_on",
            object_name="Brainstack",
            source="test",
        )
        sqlite_store.add_graph_relation(
            subject_name="Brainstack",
            predicate="integrates_with",
            object_name="Hermes Bestie",
            source="test",
        )
    finally:
        sqlite_store.close()

    store = _open_store(tmp_path)
    try:
        rows = store.search_graph(query="Brainstackkel, és mire van kötve?", limit=10)
        relation_pairs = {
            (row["subject"], row["predicate"], row["object_value"])
            for row in rows
            if row["row_type"] == "relation"
        }
        assert ("Tomi", "works_on", "Brainstack") in relation_pairs
        assert ("Brainstack", "integrates_with", "Hermes Bestie") in relation_pairs

        journal_rows = store.list_publish_journal(target_name="graph.kuzu", status="published", limit=10)
        assert {row["object_key"] for row in journal_rows} >= {"1", "2", "3"}
    finally:
        store.close()


def test_publish_journal_tracks_failure_then_successful_replay(tmp_path):
    store = _open_store(tmp_path)
    try:
        backend = store._graph_backend
        assert backend is not None
        original_publish = backend.publish_entity_subgraph
        failed_once = {"value": False}

        def _failing_publish(snapshot):
            if not failed_once["value"] and snapshot["entity"]["canonical_name"] == "Tomi":
                failed_once["value"] = True
                raise RuntimeError("boom")
            return original_publish(snapshot)

        backend.publish_entity_subgraph = _failing_publish

        try:
            store.add_graph_relation(
                subject_name="Tomi",
                predicate="works_on",
                object_name="Brainstack",
                source="test",
            )
        except RuntimeError as exc:
            assert "boom" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("expected failing publish path")

        failed_rows = store.list_publish_journal(target_name="graph.kuzu", status="failed", limit=10)
        assert any(row["object_key"] == "1" for row in failed_rows)

        backend.publish_entity_subgraph = original_publish
        store.upsert_graph_relation(
            subject_name="Tomi",
            predicate="works_on",
            object_name="Brainstack",
            source="test",
        )

        published_rows = store.list_publish_journal(target_name="graph.kuzu", status="published", limit=10)
        replayed = next(row for row in published_rows if row["object_key"] == "1")
        assert replayed["attempt_count"] >= 1
        assert replayed["published_at"]
    finally:
        store.close()
