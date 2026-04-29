from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect
from brainstack.provider_diagnostics import handle_brainstack_stats


PRIVATE_PATH = "/home/example/.hermes/brainstack/brainstack.chroma"


def _open_store(tmp_path: Path, **kwargs) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), **kwargs)
    store.open()
    return store


def test_backend_health_contract_reports_sqlite_active_without_raw_error(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        report = build_memory_kernel_doctor(store, strict=True, tier2_state={"enabled": False, "running": False})
        health = report["backend_health"]

        assert health["schema"] == "brainstack.backend_health_contract.v1"
        assert health["status"] == "active"
        assert health["backends"]["graph"]["reason_code"] == "BACKEND_SQLITE_ACTIVE"
        assert health["backends"]["corpus"]["reason_code"] == "BACKEND_SQLITE_ACTIVE"
        assert health["raw_private_data_included"] is False
    finally:
        store.close()


def test_backend_health_contract_sanitizes_degraded_chroma_embedding_error(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        store._corpus_backend_name = "chroma"
        store._corpus_backend = None
        store._corpus_backend_error = (
            f"Chroma default embedding is disabled. Configure local TEI. Path: {PRIVATE_PATH}"
        )

        report = build_memory_kernel_doctor(store, strict=False, tier2_state={"enabled": False, "running": False})
        health = report["backend_health"]
        corpus = health["backends"]["corpus"]

        assert health["status"] == "degraded"
        assert corpus["reason_code"] == "BACKEND_EMBEDDING_CONFIG_MISSING"
        assert PRIVATE_PATH not in corpus["safe_reason"]
        assert PRIVATE_PATH not in health["agent_summary"]
        assert health["fallback_channels"]["sqlite_storage"]["active"] is True
    finally:
        store.close()


def test_backend_health_contract_sanitizes_kuzu_active_lock(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        store._graph_backend_name = "kuzu"
        store._graph_backend = None
        store._graph_backend_error = "IO exception: Could not set lock on file : /private/brainstack.kuzu"

        report = build_memory_kernel_doctor(store, strict=False, tier2_state={"enabled": False, "running": False})
        graph = report["backend_health"]["backends"]["graph"]

        assert graph["reason_code"] == "BACKEND_ACTIVE_RUNTIME_LOCK_EXPECTED"
        assert "/private/brainstack.kuzu" not in graph["safe_reason"]
    finally:
        store.close()


def test_query_inspect_and_stats_expose_same_backend_health_contract(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        store._corpus_backend_name = "chroma"
        store._corpus_backend = None
        store._corpus_backend_error = "No module named chromadb"

        inspect = build_query_inspect(
            store,
            query="backend health",
            session_id="session:test",
            principal_scope_key="principal:test",
        )
        stats = handle_brainstack_stats(
            args={},
            principal_scope_key="principal:test",
            lifecycle_status=lambda: {"schema": "test.lifecycle", "status": "active"},
            memory_kernel_doctor=lambda strict=False: build_memory_kernel_doctor(
                store,
                strict=strict,
                tier2_state={"enabled": False, "running": False},
            ),
            last_maintenance_receipt=None,
        )

        inspect_health = inspect["capability_health"]["backend_health"]
        stats_health = stats["backend_health"]
        assert inspect_health["backends"]["corpus"]["reason_code"] == "BACKEND_DEPENDENCY_MISSING"
        assert stats_health["backends"]["corpus"]["reason_code"] == "BACKEND_DEPENDENCY_MISSING"
        assert inspect_health["agent_summary"] == stats_health["agent_summary"]
    finally:
        store.close()
