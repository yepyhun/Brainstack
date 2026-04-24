from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect


def _open_store(tmp_path: Path, **kwargs: Any) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), **kwargs)
    store.open()
    return store


def test_strict_doctor_fails_when_requested_external_backends_are_missing(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store._graph_backend_name = "kuzu"
        store._graph_backend = None
        store._graph_backend_error = "kuzu import failed"
        store._corpus_backend_name = "chroma"
        store._corpus_backend = None
        store._corpus_backend_error = "chroma import failed"

        report = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": True, "running": False, "last_result": {"status": "failed"}},
        )

        assert report["schema"] == "brainstack.memory_kernel_doctor.v1"
        assert report["verdict"] == "fail"
        capabilities = report["capabilities"]
        assert capabilities["graph"]["status"] == "degraded"
        assert capabilities["corpus"]["status"] == "degraded"
        assert capabilities["tier2"]["status"] == "degraded"
        assert {issue["capability"] for issue in report["issues"]} == {"graph", "corpus", "tier2"}
    finally:
        store.close()


def test_sqlite_only_doctor_reports_active_honest_capabilities(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        report = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )

        assert report["verdict"] == "pass"
        assert report["capabilities"]["graph"]["status"] == "active"
        assert report["capabilities"]["graph"]["active"] is True
        assert report["capabilities"]["graph"]["external_requested"] is False
        assert report["capabilities"]["corpus"]["status"] == "active"
        assert report["capabilities"]["corpus"]["active"] is True
        assert report["capabilities"]["corpus"]["external_requested"] is False
    finally:
        store.close()


def test_query_inspect_is_read_only_for_retrieval_telemetry(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="ExampleUser prefers proof-backed memory-kernel work.",
            source="test",
            confidence=0.95,
            metadata={"principal_scope_key": "principal:test"},
        )
        before = store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE active = 1 LIMIT 1"
        ).fetchone()

        report = build_query_inspect(
            store,
            query="ExampleUser memory kernel proof",
            session_id="session:test",
            principal_scope_key="principal:test",
        )

        after = store.conn.execute(
            "SELECT metadata_json, updated_at FROM profile_items WHERE active = 1 LIMIT 1"
        ).fetchone()
        assert before is not None and after is not None
        assert dict(before) == dict(after)
        assert report["schema"] == "brainstack.query_inspect.v1"
        assert report["query"] == "ExampleUser memory kernel proof"
        assert report["routing"]["applied_mode"]
        assert report["selected_evidence"]["profile"]
        assert all(
            item["evidence_key"] != "profile:identity:name"
            for item in report["suppressed_evidence"]
        )
        assert "ExampleUser" in report["final_packet"]["preview"]
    finally:
        store.close()
