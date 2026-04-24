from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect
from brainstack.semantic_evidence import decode_semantic_metadata


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    return store


def test_semantic_metadata_rejects_mapping_as_term_collection() -> None:
    assert decode_semantic_metadata({"semantic_terms": {"bad": "implicit keys"}}) == []
    assert decode_semantic_metadata({"semantic_terms": ["explicit term", 42]}) == ["explicit term", "42"]


def test_semantic_evidence_backfill_retrieves_profile_paraphrase(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:kernel",
            category="identity",
            content="Brainstack is the memory kernel.",
            source="semantic-test",
            confidence=0.98,
            metadata={
                "principal_scope_key": "principal:semantic",
                "authority_class": "profile",
                "provenance_class": "typed_fixture",
                "semantic_terms": ["persistent recall substrate"],
            },
        )
        backfill = store.rebuild_semantic_evidence_index(principal_scope_key="principal:semantic")
        assert backfill["counts"]["profile"] == 1
        assert store.semantic_evidence_channel_status()["status"] == "active"

        report = build_query_inspect(
            store,
            query="persistent recall substrate",
            session_id="semantic-session",
            principal_scope_key="principal:semantic",
        )

        selected_profile = report["selected_evidence"]["profile"]
        assert selected_profile
        assert selected_profile[0]["stable_key"] == "identity:kernel"
        semantic_channel = [channel for channel in report["channels"] if channel["name"] == "semantic"][0]
        assert semantic_channel["status"] == "active"
        assert semantic_channel["candidate_count"] >= 1
    finally:
        store.close()


def test_semantic_evidence_profile_write_refreshes_index(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:kernel",
            category="identity",
            content="Brainstack is the memory kernel.",
            source="semantic-test",
            confidence=0.98,
            metadata={
                "principal_scope_key": "principal:semantic",
                "semantic_terms": ["persistent recall substrate"],
            },
        )

        rows = store.search_semantic_evidence(
            query="persistent recall substrate",
            principal_scope_key="principal:semantic",
        )
        assert rows
        assert rows[0]["stable_key"] == "identity:kernel"
        assert rows[0]["retrieval_source"] == "semantic_evidence"
    finally:
        store.close()


def test_semantic_evidence_stale_fingerprint_is_visible_and_not_searched(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:kernel",
            category="identity",
            content="Brainstack is the memory kernel.",
            source="semantic-test",
            confidence=0.98,
            metadata={
                "principal_scope_key": "principal:semantic",
                "semantic_terms": ["persistent recall substrate"],
            },
        )
        store.rebuild_semantic_evidence_index(principal_scope_key="principal:semantic")
        store.conn.execute("UPDATE semantic_evidence_index SET fingerprint = 'stale-fingerprint'")
        store.conn.commit()

        status = store.semantic_evidence_channel_status()
        assert status["status"] == "degraded"
        assert status["stale_count"] == 1
        assert store.search_semantic_evidence(
            query="persistent recall substrate",
            principal_scope_key="principal:semantic",
        ) == []

        doctor = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )
        assert doctor["verdict"] == "fail"
        assert doctor["capabilities"]["semantic_index"]["status"] == "degraded"
    finally:
        store.close()
