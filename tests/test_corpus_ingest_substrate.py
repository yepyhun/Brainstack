from __future__ import annotations

from pathlib import Path


from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect


PRINCIPAL_SCOPE = "principal:corpus-ingest"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _source_payload(content: str, *, stable_key: str = "doc:phase76:source") -> dict:
    return {
        "source_adapter": "test_fixture",
        "source_id": stable_key,
        "stable_key": stable_key,
        "title": "Phase 76 Corpus Source",
        "doc_kind": "project_note",
        "source_uri": "fixture://phase76",
        "content": content,
        "metadata": {
            "principal_scope_key": PRINCIPAL_SCOPE,
            "authority_class": "corpus",
            "provenance_class": "typed_fixture",
        },
    }


def test_corpus_source_ingest_is_idempotent_and_citation_backed(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        receipt = store.ingest_corpus_source(_source_payload("Alpha section.\n\nBeta section."))
        second = store.ingest_corpus_source(_source_payload("Alpha section.\n\nBeta section."))

        assert receipt["status"] == "inserted"
        assert second["status"] == "unchanged"
        assert second["document_id"] == receipt["document_id"]
        assert second["citation_ids"] == ["doc:phase76:source#s0"]
        assert store.conn.execute("SELECT COUNT(*) AS count FROM corpus_documents").fetchone()["count"] == 1
        assert store.conn.execute("SELECT COUNT(*) AS count FROM corpus_sections").fetchone()["count"] == 1

        rows = store.search_corpus(query="Alpha section", limit=3)
        assert rows
        assert rows[0]["citation_id"] == "doc:phase76:source#s0"
        assert rows[0]["document_hash"]
        assert rows[0]["section_hash"]
    finally:
        store.close()


def test_corpus_reingest_replaces_stale_sections_without_duplicate_documents(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        first = store.ingest_corpus_source(_source_payload("Old alpha body."))
        updated = store.ingest_corpus_source(_source_payload("New gamma body."))

        assert first["document_id"] == updated["document_id"]
        assert updated["status"] == "updated"
        assert store.conn.execute("SELECT COUNT(*) AS count FROM corpus_documents").fetchone()["count"] == 1
        assert store.search_corpus(query="Old alpha", limit=3) == []
        assert store.search_corpus(query="New gamma", limit=3)
    finally:
        store.close()


def test_corpus_ingest_status_detects_stale_legacy_document_metadata(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.ingest_corpus_document(
            stable_key="doc:legacy",
            title="Legacy Corpus",
            doc_kind="project_note",
            source="legacy-fixture",
            sections=[{"heading": "Legacy", "content": "Legacy document without corpus ingest metadata."}],
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        assert store.corpus_ingest_status(principal_scope_key=PRINCIPAL_SCOPE)["status"] == "degraded"

        store.ingest_corpus_source(_source_payload("Fresh source document.", stable_key="doc:fresh"))
        status = store.corpus_ingest_status(principal_scope_key=PRINCIPAL_SCOPE)
        assert status["stale_count"] == 1
        assert status["missing_metadata_count"] == 1
    finally:
        store.close()


def test_corpus_recall_uses_bounded_section_citations_not_raw_document_dump(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        long_body = "Noise paragraph. " * 240
        store.ingest_corpus_source(
            {
                **_source_payload("", stable_key="doc:large"),
                "sections": [
                    {"heading": "Noise", "content": long_body},
                    {"heading": "Target", "content": "Needle77 answer lives in this bounded section only."},
                ],
            }
        )

        report = build_query_inspect(
            store,
            query="Needle77 answer",
            session_id="corpus-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            corpus_limit=2,
            corpus_char_budget=280,
        )

        selected = report["selected_evidence"]["corpus"]
        assert selected
        assert selected[0]["citation_id"] == "doc:large#s1"
        assert "Needle77 answer" in report["final_packet"]["preview"]
        assert long_body[:500] not in report["final_packet"]["preview"]
        assert report["final_packet"]["char_count"] < len(long_body)
    finally:
        store.close()
