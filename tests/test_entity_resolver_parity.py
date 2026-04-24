from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.entity_resolver import resolve_entity_candidates

from graph_parity_fixtures import PRINCIPAL_SCOPE, seed_graph_parity_fixture


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(
        str(tmp_path / "brainstack.sqlite3"),
        graph_backend="sqlite",
        corpus_backend="sqlite",
    )
    store.open()
    return store


def _selected_graph(report: dict[str, Any]) -> list[dict[str, Any]]:
    return list(report["selected_evidence"]["graph"])


def test_explicit_alias_resolver_candidate_is_read_only_and_inspectable(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        seed_graph_parity_fixture(store)

        resolution = resolve_entity_candidates(
            store,
            query="ProjectAuroraDelta deployment",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        assert resolution["status"] == "active"
        candidate = resolution["candidates"][0]
        assert candidate["canonical_name"] == "AuroraDelta"
        assert candidate["matched_alias"] == "ProjectAuroraDelta"
        assert candidate["source_channel"] == "explicit_alias"
        assert candidate["merge_eligible"] is False
        assert "resolver_candidates_are_read_only" in resolution["no_merge_reasons"]

        report = build_query_inspect(
            store,
            query="ProjectAuroraDelta deployment",
            session_id="session:resolver-alias",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["subject"] == "AuroraDelta"
        assert graph_rows[0]["matched_alias"] == "ProjectAuroraDelta"
        assert graph_rows[0]["entity_resolution_source"] == "explicit_alias"
        assert graph_rows[0]["entity_resolution_merge_eligible"] is False
        assert report["entity_resolution"]["schema"] == "brainstack.entity_resolution.v1"
    finally:
        store.close()


def test_semantic_candidate_improves_recall_without_creating_alias_truth(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="NebulaCore",
            attribute="deployment",
            value_text="green",
            source="resolver-fixture",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "semantic_terms": ["northern lights release"],
            },
        )

        resolution = resolve_entity_candidates(
            store,
            query="northern lights release",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        assert resolution["status"] == "active"
        candidate = resolution["candidates"][0]
        assert candidate["canonical_name"] == "NebulaCore"
        assert candidate["source_channel"] == "semantic_evidence"
        assert candidate["merge_eligible"] is False

        report = build_query_inspect(
            store,
            query="northern lights release",
            session_id="session:resolver-semantic",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        graph_rows = _selected_graph(report)
        assert graph_rows
        assert graph_rows[0]["subject"] == "NebulaCore"
        assert graph_rows[0]["entity_resolution_source"] == "semantic_evidence"
        assert graph_rows[0]["entity_resolution_reason"] == "semantic_graph_evidence_candidate_read_only"
        alias_count = store.conn.execute("SELECT COUNT(*) AS count FROM graph_entity_aliases").fetchone()
        assert alias_count is not None
        assert alias_count["count"] == 0
    finally:
        store.close()


def test_similar_entity_names_remain_separate_without_alias_merge(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_graph_state(
            subject_name="Aurora",
            attribute="deployment",
            value_text="green",
            source="resolver-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.upsert_graph_state(
            subject_name="Aurorium",
            attribute="deployment",
            value_text="separate",
            source="resolver-fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        resolution = resolve_entity_candidates(
            store,
            query="Aurorium deployment",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        names = [candidate["canonical_name"] for candidate in resolution["candidates"]]
        assert names == ["Aurorium"]
        alias_rows = store.conn.execute("SELECT alias_name FROM graph_entity_aliases").fetchall()
        assert alias_rows == []
    finally:
        store.close()


def test_lexical_entity_resolution_filters_unrelated_semantic_graph_spillover(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
        store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="green",
            source="resolver-fixture",
            metadata=metadata,
        )
        store.upsert_graph_state(
            subject_name="Release Train",
            attribute="status",
            value_text="red",
            source="resolver-fixture",
            metadata=metadata,
        )
        store.upsert_graph_state(
            subject_name="NebulaCore",
            attribute="deployment",
            value_text="green",
            source="resolver-fixture",
            metadata={**metadata, "semantic_terms": ["northern lights release"]},
        )

        report = build_query_inspect(
            store,
            query="Release Train red status",
            session_id="session:resolver-spillover",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=6,
        )

        graph_rows = _selected_graph(report)
        assert any(row["subject"] == "Release Train" and row["fact_class"] == "conflict" for row in graph_rows)
        assert not any(row["subject"] == "NebulaCore" for row in graph_rows)
    finally:
        store.close()


def test_generic_runtime_identity_alias_is_not_created_without_explicit_alias_entity(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = store.merge_entity_alias(alias_name="User", target_name="Tomi")

        assert result["status"] == "noop"
        alias_count = store.conn.execute("SELECT COUNT(*) AS count FROM graph_entity_aliases").fetchone()
        assert alias_count is not None
        assert alias_count["count"] == 0
    finally:
        store.close()


def test_query_inspect_exposes_no_match_and_no_merge_reasons(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        report = build_query_inspect(
            store,
            query="unlinked resolver canary",
            session_id="session:resolver-empty",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=4,
        )

        resolution = report["entity_resolution"]
        assert resolution["status"] == "no_match"
        assert "no_exact_alias_or_semantic_candidate" in resolution["no_merge_reasons"]
        assert "resolver_candidates_are_read_only" in resolution["no_merge_reasons"]
    finally:
        store.close()
