from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.corpus_backend_chroma import ChromaCorpusBackend
from brainstack.db import BrainstackStore
from scripts.verify_corpus_semantic_filtering import build_report


class FakeSemanticBackend:
    target_name = "fake.semantic"

    def __init__(self, rows_by_where: dict[tuple[tuple[str, str], ...], list[dict[str, Any]]] | None = None) -> None:
        self.calls: list[dict[str, Any] | None] = []
        self.rows_by_where = rows_by_where or {}

    def open(self) -> None:
        return None

    def close(self) -> None:
        return None

    def is_empty(self) -> bool:
        return False

    def publish_document(self, snapshot: dict[str, Any]) -> None:
        del snapshot

    def score_texts(self, *, query: str, texts: list[str]) -> list[float]:
        del query
        return [0.0 for _ in texts]

    def search_semantic(self, *, query: str, limit: int, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        del query, limit
        self.calls.append(dict(where or {}))
        key = tuple(sorted((str(k), str(v)) for k, v in dict(where or {}).items()))
        return [dict(row) for row in self.rows_by_where.get(key, [])]


class FakeCollection:
    def __init__(self) -> None:
        self.upsert_kwargs: dict[str, Any] = {}

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_kwargs = kwargs

    def get(self, *, where: dict[str, Any], include: list[Any]) -> dict[str, Any]:
        del where, include
        return {"ids": self.upsert_kwargs.get("ids", [])}

    def delete(self, **kwargs: Any) -> None:
        del kwargs


class FakeQueryCollection(FakeCollection):
    def __init__(self) -> None:
        super().__init__()
        self.query_kwargs: dict[str, Any] = {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_kwargs = kwargs
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


class FakeEmbeddingClient:
    def embed_query(self, query: str) -> list[float]:
        del query
        return [0.0, 1.0]


def _store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_chroma_semantic_search_wraps_multi_key_filters_for_chroma() -> None:
    backend = ChromaCorpusBackend(db_path=":memory:")
    collection = FakeQueryCollection()
    backend._collection = collection
    backend._embedding_client = FakeEmbeddingClient()  # type: ignore[assignment]

    rows = backend.search_semantic(
        query="hello",
        limit=2,
        where={"semantic_class": "corpus", "principal_scope_key": "principal:m008"},
    )

    assert rows == []
    assert collection.query_kwargs["where"] == {
        "$and": [
            {"principal_scope_key": "principal:m008"},
            {"semantic_class": "corpus"},
        ]
    }


def test_corpus_semantic_filtering_verifier_passes() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.corpus_semantic_filtering_verifier.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert {case["case_id"] for case in report["cases"]} == {
        "filtered_first",
        "visible_fallback",
        "chroma_flat_filter_metadata",
    }


def test_search_corpus_semantic_starts_with_scope_filter_and_annotates_rows(tmp_path: Path) -> None:
    filtered_where = tuple(sorted({"semantic_class": "corpus", "principal_scope_key": "principal:m008"}.items()))
    backend = FakeSemanticBackend(
        rows_by_where={
            filtered_where: [
                {
                    "content": "Filtered row",
                    "metadata": {"stable_key": "doc:m008"},
                    "retrieval_source": "corpus.semantic",
                    "match_mode": "semantic",
                }
            ]
        }
    )
    store = _store(tmp_path)
    try:
        store._corpus_backend = backend

        rows = store.search_corpus_semantic(query="filtered", limit=4, principal_scope_key="principal:m008")

        assert backend.calls == [{"semantic_class": "corpus", "principal_scope_key": "principal:m008"}]
        assert rows[0]["metadata"]["semantic_filter"] == {
            "schema": "brainstack.corpus_semantic_filter.v1",
            "requested_where": {"semantic_class": "corpus", "principal_scope_key": "principal:m008"},
            "fallback_used": False,
        }
    finally:
        store.close()


def test_search_corpus_semantic_fallback_is_visible_when_filtered_query_empty(tmp_path: Path) -> None:
    fallback_where = tuple(sorted({"semantic_class": "corpus"}.items()))
    backend = FakeSemanticBackend(
        rows_by_where={
            fallback_where: [
                {
                    "content": "Fallback row",
                    "metadata": {"stable_key": "doc:legacy"},
                    "retrieval_source": "corpus.semantic",
                    "match_mode": "semantic",
                }
            ]
        }
    )
    store = _store(tmp_path)
    try:
        store._corpus_backend = backend

        rows = store.search_corpus_semantic(query="legacy", limit=4, principal_scope_key="principal:m008")

        assert backend.calls == [
            {"semantic_class": "corpus", "principal_scope_key": "principal:m008"},
            {"semantic_class": "corpus"},
        ]
        assert rows[0]["metadata"]["semantic_filter"]["fallback_used"] is True
        assert rows[0]["metadata"]["semantic_filter"]["requested_where"] == {
            "semantic_class": "corpus",
            "principal_scope_key": "principal:m008",
        }
    finally:
        store.close()


def test_chroma_publish_flattens_filter_metadata_for_corpus_scope_and_language() -> None:
    backend = ChromaCorpusBackend(db_path=":memory:")
    collection = FakeCollection()
    backend._collection = collection

    backend.publish_document(
        {
            "document": {
                "id": 7,
                "stable_key": "doc:m008:filter",
                "title": "Filter proof",
                "doc_kind": "note",
                "source": "fixture://m008/filter",
                "updated_at": "2026-05-03T00:00:00Z",
                "metadata": {
                    "principal_scope_key": "principal:m008",
                    "workspace_scope_key": "workspace:m008",
                    "language": "hu",
                    "source_uri": "fixture://m008/filter",
                },
            },
            "sections": [
                {
                    "section_id": 11,
                    "section_index": 0,
                    "heading": "Filter metadata",
                    "content": "Corpus semantic filter metadata proof.",
                    "token_estimate": 9,
                    "metadata": {"language": "de", "doc_type": "note-section"},
                }
            ],
        }
    )

    metadata = collection.upsert_kwargs["metadatas"][0]
    assert metadata["principal_scope_key"] == "principal:m008"
    assert metadata["workspace_scope_key"] == "workspace:m008"
    assert metadata["language"] == "de"
    assert metadata["source_uri"] == "fixture://m008/filter"
    assert metadata["doc_type"] == "note-section"
