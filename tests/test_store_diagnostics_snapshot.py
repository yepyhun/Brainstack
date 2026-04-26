from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect


def test_doctor_reports_active_db_substrate_for_fresh_store(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite"))
    try:
        store.open()
        report = build_memory_kernel_doctor(store, strict=True)
        substrate = report["capabilities"]["db_substrate"]

        assert report["verdict"] == "pass"
        assert substrate["status"] == "active"
        assert substrate["missing_schema_object_count"] == 0
        assert substrate["missing_known_migration_count"] == 0
        assert substrate["unknown_applied_migration_count"] == 0
    finally:
        store.close()


def test_doctor_fails_strict_when_schema_object_is_missing(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite"))
    try:
        store.open()
        store.conn.execute("DROP TABLE applied_migrations")
        store.conn.commit()

        report = build_memory_kernel_doctor(store, strict=True)
        substrate = report["capabilities"]["db_substrate"]

        assert report["verdict"] == "fail"
        assert substrate["status"] == "degraded"
        assert substrate["missing_schema_object_count"] >= 1
        assert any(item["name"] == "applied_migrations" for item in substrate["missing_schema_objects"])
        assert any(issue["capability"] == "db_substrate" for issue in report["issues"])
        assert any(issue["severity"] == "fatal" for issue in report["issues"])
    finally:
        store.close()


def test_query_inspect_reports_capability_health_and_backend_severity(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite"), graph_backend="kuzu", corpus_backend="chroma")
    try:
        store.open()
        store._graph_backend = None
        store._graph_backend_error = "kuzu unavailable in fixture"
        store._corpus_backend = None
        store._corpus_backend_error = "chroma unavailable in fixture"

        report = build_query_inspect(
            store,
            query="diagnostic capability health",
            session_id="diagnostic-session",
            principal_scope_key="principal:diagnostic",
        )

        health = report["capability_health"]
        assert health["schema"] == "brainstack.query_capability_health.v1"
        assert health["kuzu"]["status"] == "degraded"
        assert health["chroma"]["status"] == "degraded"
        assert health["lexical_index"]["status"] == "active"
        assert {issue["severity"] for issue in health["issues"]} >= {"warn"}
    finally:
        store.close()


def test_doctor_surfaces_unknown_applied_migration(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite"))
    try:
        store.open()
        store.conn.execute(
            "INSERT INTO applied_migrations(name, applied_at) VALUES(?, ?)",
            ("future_unknown_migration", "2026-04-25T00:00:00+00:00"),
        )
        store.conn.commit()

        report = build_memory_kernel_doctor(store, strict=True)
        substrate = report["capabilities"]["db_substrate"]

        assert report["verdict"] == "fail"
        assert substrate["status"] == "degraded"
        assert substrate["unknown_applied_migrations"] == ["future_unknown_migration"]
        assert substrate["unknown_applied_migration_count"] == 1
    finally:
        store.close()
