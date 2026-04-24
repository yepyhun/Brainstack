from __future__ import annotations

from pathlib import Path


from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect


PRINCIPAL_SCOPE = "principal:associative"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _seed_alias_graph(store: BrainstackStore) -> None:
    metadata = {
        "principal_scope_key": PRINCIPAL_SCOPE,
        "provenance_class": "typed_fixture",
        "authority_class": "graph",
    }
    store.upsert_graph_relation(
        subject_name="Meridian",
        predicate="project_code_for",
        object_name="Aurora",
        source="associative-test",
        metadata=metadata,
    )
    store.upsert_graph_state(
        subject_name="Aurora",
        attribute="deployment",
        value_text="green",
        source="associative-test",
        metadata={
            **metadata,
            "context_id": "readiness",
        },
    )


def test_associative_expansion_finds_related_graph_state_through_bounded_anchor(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_alias_graph(store)

        report = build_query_inspect(
            store,
            query="Meridian readiness",
            session_id="associative-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=6,
        )

        expansion = report["associative_expansion"]
        assert expansion["status"] == "active"
        assert expansion["bounds"]["max_depth"] == 1
        included_keys = {row["evidence_key"] for row in expansion["included_candidates"]}
        assert "graph:state:1" in included_keys
        assert any(row["anchor"] == "Aurora" for row in expansion["included_candidates"])

        selected_graph = report["selected_evidence"]["graph"]
        assert any(row["evidence_key"] == "graph:state:1" for row in selected_graph)
    finally:
        store.close()


def test_associative_expansion_suppresses_superficially_related_state(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_alias_graph(store)

        report = build_query_inspect(
            store,
            query="Meridian weather",
            session_id="associative-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            graph_limit=6,
        )

        expansion = report["associative_expansion"]
        assert expansion["included_candidates"] == []
        assert any(
            row["evidence_key"] == "graph:state:1"
            and row["reason"] == "insufficient_query_relevance"
            for row in expansion["suppressed_candidates"]
        )
        assert not any(row["evidence_key"] == "graph:state:1" for row in report["selected_evidence"]["graph"])
    finally:
        store.close()


def test_associative_expansion_does_not_drown_authoritative_profile_truth(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_alias_graph(store)
        store.upsert_profile_item(
            stable_key="identity:primary-project",
            category="identity",
            content="Primary project is Mercury.",
            source="associative-test",
            confidence=0.99,
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "provenance_class": "typed_fixture",
                "authority_class": "profile",
            },
        )

        report = build_query_inspect(
            store,
            query="Primary project Meridian readiness",
            session_id="associative-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=3,
            graph_limit=6,
        )

        assert any(
            row["stable_key"] == "identity:primary-project"
            for row in report["selected_evidence"]["profile"]
        )
        assert report["associative_expansion"]["status"] == "active"
        assert len(report["selected_evidence"]["graph"]) <= 6
    finally:
        store.close()
