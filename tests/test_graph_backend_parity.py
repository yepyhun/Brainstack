from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect

from graph_parity_fixtures import (
    PRINCIPAL_SCOPE,
    graph_trace_snapshot,
    seed_graph_parity_fixture,
)


def _open_store(tmp_path: Path, *, graph_backend: str) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / f"brainstack-{graph_backend}.sqlite3"),
        graph_backend=graph_backend,
        graph_db_path=str(tmp_path / f"brainstack-{graph_backend}.kuzu"),
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _selected_graph(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list(report["selected_evidence"]["graph"])


def _inspect(store: BrainstackStore, query: str) -> dict[str, Any]:
    return build_query_inspect(
        store,
        query=query,
        session_id="session:graph-backend-parity",
        principal_scope_key=PRINCIPAL_SCOPE,
        graph_limit=6,
    )


def _graph_row_for_subject(report: dict[str, Any], subject: str, *, row_type: str = "") -> dict[str, Any]:
    for row in _selected_graph(report):
        if row.get("subject") == subject and (not row_type or row.get("row_type") == row_type):
            return row
    raise AssertionError(f"Missing graph row for subject: {subject}")


def test_configured_missing_kuzu_reports_degraded_status_without_false_success(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="kuzu")
    try:
        fixture = seed_graph_parity_fixture(store)
        doctor = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )

        graph_capability = doctor["capabilities"]["graph"]
        if store._graph_backend is None:
            assert doctor["verdict"] == "fail"
            assert graph_capability["status"] == "degraded"
            assert graph_capability["sqlite_fallback_active"] is True
            assert graph_capability["reason"]

            report = _inspect(store, fixture["queries"]["current"])
            graph_rows = _selected_graph(report)
            assert graph_rows
            snapshot = graph_trace_snapshot(graph_rows[0])
            assert snapshot["graph_backend_status"] == "degraded"
            assert snapshot["graph_fallback_reason"]
        else:
            assert graph_capability["status"] == "active"
    finally:
        store.close()


def test_sqlite_trace_schema_snapshot_uses_shared_parity_fixture(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite")
    try:
        fixture = seed_graph_parity_fixture(store)

        expired = graph_trace_snapshot(
            _graph_row_for_subject(_inspect(store, fixture["queries"]["expired"]), "ExpiredWindowAlpha")
        )
        current = graph_trace_snapshot(
            _graph_row_for_subject(_inspect(store, fixture["queries"]["current"]), "CurrentWindowBeta")
        )
        conflict = graph_trace_snapshot(
            _graph_row_for_subject(_inspect(store, fixture["queries"]["conflict"]), "ReleaseTrainGamma", row_type="conflict")
        )
        alias = graph_trace_snapshot(
            _graph_row_for_subject(_inspect(store, fixture["queries"]["alias"]), "AuroraDelta")
        )

        assert expired["fact_class"] == "explicit_state_expired"
        assert expired["valid_to"] == "2000-01-01T12:00:00+00:00"
        assert current["fact_class"] == "explicit_state_current"
        assert conflict["fact_class"] == "conflict"
        assert conflict["conflict_value"] == "blocked"
        assert alias["matched_alias"] == "ProjectAuroraDelta"
        assert alias["match_mode"] == "alias_lexical"
        assert {expired["retrieval_source"], current["retrieval_source"]} == {"graph.sqlite_lexical"}
    finally:
        store.close()


def test_kuzu_backend_matches_sqlite_truth_classes_when_available(tmp_path: Path) -> None:
    pytest.importorskip("kuzu")
    sqlite_store = _open_store(tmp_path, graph_backend="sqlite")
    kuzu_store = _open_store(tmp_path, graph_backend="kuzu")
    try:
        sqlite_fixture = seed_graph_parity_fixture(sqlite_store)
        kuzu_fixture = seed_graph_parity_fixture(kuzu_store)
        if kuzu_store._graph_backend is None:
            pytest.skip(f"Kuzu backend unavailable: {kuzu_store._graph_backend_error}")

        for key in ("expired", "current", "conflict", "alias"):
            expected_subject = {
                "expired": "ExpiredWindowAlpha",
                "current": "CurrentWindowBeta",
                "conflict": "ReleaseTrainGamma",
                "alias": "AuroraDelta",
            }[key]
            row_type = "conflict" if key == "conflict" else ""
            sqlite_row = graph_trace_snapshot(
                _graph_row_for_subject(_inspect(sqlite_store, sqlite_fixture["queries"][key]), expected_subject, row_type=row_type)
            )
            kuzu_row = graph_trace_snapshot(
                _graph_row_for_subject(_inspect(kuzu_store, kuzu_fixture["queries"][key]), expected_subject, row_type=row_type)
            )

            assert kuzu_row["graph_backend_status"] == "active"
            assert kuzu_row["retrieval_source"] == "graph.graph.kuzu"
            assert kuzu_row["fact_class"] == sqlite_row["fact_class"]
            if key == "expired":
                assert kuzu_row["valid_to"] == sqlite_row["valid_to"]
            if key == "conflict":
                assert kuzu_row["conflict_value"] == sqlite_row["conflict_value"]
            if key == "alias":
                assert kuzu_row["matched_alias"] == sqlite_row["matched_alias"]
                assert kuzu_row["match_mode"] == "alias_lexical"
    finally:
        sqlite_store.close()
        kuzu_store.close()
