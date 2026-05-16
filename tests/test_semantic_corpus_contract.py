from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import OPERATING_RECORD_ACTIVE_WORK


PRINCIPAL_SCOPE = "principal:semantic-corpus-contract"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_profile_operating_truth_does_not_pretend_to_be_document_corpus(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        metadata = {
            "principal_scope_key": PRINCIPAL_SCOPE,
            "semantic_terms": ["scoped recall parity"],
        }
        store.upsert_profile_item(
            stable_key="preference:semantic-contract",
            category="preference",
            content="The semantic contract fixture prefers scoped recall parity.",
            source="semantic-corpus-contract.fixture",
            confidence=0.99,
            metadata=metadata,
        )
        store.upsert_operating_record(
            stable_key="work:semantic-contract",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="The semantic contract fixture is active work.",
            owner="user_project",
            source="semantic-corpus-contract.fixture",
            metadata=metadata,
        )

        report = build_query_inspect(
            store,
            query="scoped recall parity active work",
            session_id="semantic-corpus-contract",
            principal_scope_key=PRINCIPAL_SCOPE,
            corpus_limit=4,
        )

        contract = report["semantic_corpus_contract"]
        assert contract["schema"] == "brainstack.semantic_corpus_contract.v1"
        assert contract["reason_code"] == "NO_CORPUS_DOCUMENTS_INDEXED"
        assert contract["profile_operating_truth_contract"]["expected_corpus_parity"] is False
        assert contract["document_corpus"]["document_count"] == 0
        assert contract["document_corpus"]["selected_count"] == 0
        assert contract["semantic_evidence_shelf_counts"]["profile"] == 1
        assert contract["semantic_evidence_shelf_counts"]["operating"] == 1
        assert report["selected_evidence"]["profile"] or report["selected_evidence"]["operating"]
        assert report["selected_evidence"]["operating"]
        assert not report["selected_evidence"]["corpus"]
    finally:
        store.close()


def test_document_corpus_selection_is_counted_separately_from_truth_shelves(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.ingest_corpus_source(
            {
                "source_adapter": "semantic_contract_fixture",
                "source_id": "corpus-note",
                "stable_key": "doc:semantic-contract:corpus-note",
                "title": "Semantic Contract Corpus Note",
                "doc_kind": "note",
                "source_uri": "fixture://semantic-contract/corpus-note",
                "content": "The corpus note documents an approval packet checksum for backend parity.",
                "metadata": {"principal_scope_key": PRINCIPAL_SCOPE},
            }
        )

        report = build_query_inspect(
            store,
            query="approval packet checksum backend parity",
            session_id="semantic-corpus-contract",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=4,
        )

        contract = report["semantic_corpus_contract"]
        assert contract["reason_code"] == "CORPUS_EVIDENCE_SELECTED"
        assert contract["document_corpus"]["document_count"] == 1
        assert contract["document_corpus"]["section_count"] == 1
        assert contract["document_corpus"]["selected_count"] >= 1
        assert report["selected_evidence"]["corpus"]
    finally:
        store.close()
