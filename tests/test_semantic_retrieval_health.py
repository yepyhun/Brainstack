from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect


PRINCIPAL_SCOPE = "principal:semantic-health"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _simulate_unhealthy_chroma(store: BrainstackStore) -> None:
    store._corpus_backend_name = "chroma"
    store._corpus_backend = None
    store._corpus_backend_error = "chroma import failed"


def test_semantic_backend_unhealthy_is_explicit_in_doctor_and_query_inspect(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _simulate_unhealthy_chroma(store)

        doctor = build_memory_kernel_doctor(store, strict=False)
        report = build_query_inspect(
            store,
            query="semantic corpus lookup",
            session_id="semantic-health-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            corpus_limit=4,
        )

        assert doctor["verdict"] == "degraded"
        assert doctor["capabilities"]["corpus"]["status"] == "degraded"
        assert doctor["capabilities"]["corpus"]["error_class"] == "backend_dependency_missing"
        assert report["capability_health"]["chroma"]["requested"] is True
        assert report["capability_health"]["chroma"]["status"] == "degraded"
        assert any(channel["name"] == "semantic" and channel["status"] == "degraded" for channel in report["channels"])
    finally:
        store.close()


def test_exact_durable_profile_truth_survives_unhealthy_semantic_backend(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _simulate_unhealthy_chroma(store)
        store.upsert_profile_item(
            stable_key="identity:nimbus-owner",
            category="identity",
            content="Project Nimbus owner is Alex.",
            source="semantic-health.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="Project Nimbus owner",
            session_id="semantic-health-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            corpus_limit=4,
        )

        assert report["capability_health"]["chroma"]["status"] == "degraded"
        assert report["selected_evidence"]["profile"]
        assert report["packet_answerability"]["can_answer"] is True
        assert report["packet_answerability"]["can_claim_memory_truth"] is True
        assert "Project Nimbus owner is Alex" in report["final_packet"]["preview"]
    finally:
        store.close()


def test_support_only_transcript_does_not_become_memory_truth_when_semantic_backend_unhealthy(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _simulate_unhealthy_chroma(store)
        store.add_transcript_entry(
            session_id="semantic-health-session",
            turn_number=1,
            kind="assistant",
            content="Assistant once guessed that Project Zephyr belongs to Morgan.",
            source="semantic-health.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="Project Zephyr belongs Morgan",
            session_id="semantic-health-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=4,
            corpus_limit=4,
            graph_limit=0,
            operating_match_limit=0,
        )

        assert report["capability_health"]["chroma"]["status"] == "degraded"
        assert report["selected_evidence"]["transcript"]
        assert report["packet_answerability"]["can_claim_memory_truth"] is False
        assert "memory_truth" in report["packet_answerability"]["must_not_claim"]
    finally:
        store.close()


def test_semantic_only_corpus_gap_is_not_answerable_when_backend_unhealthy(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _simulate_unhealthy_chroma(store)
        store.ingest_corpus_source(
            {
                "source_adapter": "semantic_health_fixture",
                "source_id": "ocean-note",
                "stable_key": "doc:semantic-health:ocean-note",
                "title": "Ocean Note",
                "doc_kind": "note",
                "source_uri": "fixture://semantic-health/ocean-note",
                "content": "The azure turtle migration note states that delta reef timing changed.",
                "metadata": {"principal_scope_key": PRINCIPAL_SCOPE},
            }
        )

        report = build_query_inspect(
            store,
            query="aquatic reptile relocation schedule",
            session_id="semantic-health-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            continuity_recent_limit=0,
            continuity_match_limit=0,
            transcript_match_limit=0,
            corpus_limit=4,
            graph_limit=0,
            operating_match_limit=0,
        )

        assert report["capability_health"]["chroma"]["status"] == "degraded"
        assert not report["selected_evidence"]["corpus"]
        assert report["packet_answerability"]["can_answer"] is False
        assert report["packet_answerability"]["can_claim_memory_truth"] is False
    finally:
        store.close()
