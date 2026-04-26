from __future__ import annotations

from typing import Any, Dict, List

import pytest

from brainstack.corpus_backend_chroma import (
    ChromaCorpusBackend,
    _ExternalEmbeddingClient,
    _extract_embeddings,
)


class FakeCollection:
    def __init__(self) -> None:
        self.upserts: List[Dict[str, Any]] = []
        self.queries: List[Dict[str, Any]] = []

    def upsert(self, **kwargs: Any) -> None:
        self.upserts.append(dict(kwargs))

    def get(self, **_: Any) -> Dict[str, Any]:
        return {"ids": []}

    def delete(self, **_: Any) -> None:
        return None

    def query(self, **kwargs: Any) -> Dict[str, Any]:
        self.queries.append(dict(kwargs))
        return {
            "documents": [["stored section"]],
            "metadatas": [[{
                "document_id": 7,
                "title": "Doc",
                "doc_kind": "note",
                "source": "test",
                "section_id": 70,
                "section_index": 0,
                "heading": "Head",
                "token_estimate": 3,
                "stable_key": "doc:key",
                "semantic_class": "corpus",
                "document_metadata_json": "{}",
                "section_metadata_json": "{}",
            }]],
            "distances": [[0.25]],
        }

    def count(self) -> int:
        return 0


class FakePersistentClient:
    def __init__(self, **_: Any) -> None:
        self.collection = FakeCollection()
        self.collection_kwargs: Dict[str, Any] = {}

    def get_or_create_collection(self, **kwargs: Any) -> FakeCollection:
        self.collection_kwargs = dict(kwargs)
        return self.collection


class FakeChromaModule:
    PersistentClient = FakePersistentClient

    class utils:
        class embedding_functions:
            @staticmethod
            def DefaultEmbeddingFunction() -> Any:
                raise AssertionError("default embedding function must not be built")


class FakeSettings:
    def __init__(self, **_: Any) -> None:
        return None


class FakeEmbeddingClient:
    fingerprint = "a" * 64

    def __init__(self) -> None:
        self.document_inputs: List[str] = []
        self.query_inputs: List[str] = []

    def collection_metadata(self) -> Dict[str, Any]:
        return {
            "brainstack:embedding_provider": "tei",
            "brainstack:embedding_model": "jina-test",
            "brainstack:embedding_fingerprint": self.fingerprint,
        }

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        self.document_inputs.extend(texts)
        return [[float(index + 1), 0.0, 0.0] for index, _ in enumerate(texts)]

    def embed_query(self, query: str) -> List[float]:
        self.query_inputs.append(query)
        return [1.0, 0.0, 0.0]


class FakeBackend(ChromaCorpusBackend):
    def __init__(self, *, embedding_client: FakeEmbeddingClient | None) -> None:
        super().__init__(db_path="/tmp/fake-chroma")
        self.fake_embedding_client = embedding_client

    def _import_chromadb(self) -> tuple[Any, Any]:
        return FakeChromaModule, FakeSettings

    def _build_embedding_client(self) -> FakeEmbeddingClient | None:
        return self.fake_embedding_client


def test_chroma_uses_explicit_tei_embeddings_for_upsert_and_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING", "true")
    embedding_client = FakeEmbeddingClient()
    backend = FakeBackend(embedding_client=embedding_client)

    backend.open()
    client = backend._client
    assert isinstance(client, FakePersistentClient)
    assert client.collection_kwargs["name"].startswith(f"{backend.collection_name}_")
    assert "embedding_function" not in client.collection_kwargs
    assert client.collection_kwargs["metadata"]["brainstack:embedding_provider"] == "tei"

    backend.publish_document(
        {
            "document": {
                "id": 7,
                "stable_key": "doc:key",
                "title": "Doc",
                "doc_kind": "note",
                "source": "test",
            },
            "sections": [{"section_id": 70, "section_index": 0, "content": "stored section"}],
        }
    )
    assert client.collection.upserts
    assert client.collection.upserts[0]["documents"] == ["stored section"]
    assert client.collection.upserts[0]["embeddings"] == [[1.0, 0.0, 0.0]]

    rows = backend.search_semantic(query="find doc", limit=1)
    assert rows[0]["content"] == "stored section"
    assert client.collection.queries
    assert "query_embeddings" in client.collection.queries[0]
    assert "query_texts" not in client.collection.queries[0]
    assert embedding_client.query_inputs == ["find doc"]


def test_chroma_default_embedding_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BRAINSTACK_EMBEDDINGS_URL", raising=False)
    monkeypatch.delenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_URL", raising=False)
    monkeypatch.delenv("BRAINSTACK_CHROMA_ALLOW_DEFAULT_EMBEDDING", raising=False)
    monkeypatch.setenv("BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING", "true")

    backend = FakeBackend(embedding_client=None)

    with pytest.raises(RuntimeError, match="Chroma default embedding is disabled"):
        backend.open()


class RecordingEmbeddingClient(_ExternalEmbeddingClient):
    def __init__(self, *, api: str) -> None:
        super().__init__(
            url="http://127.0.0.1:7997/embed",
            model="jinaai/jina-embeddings-v5-text-small-retrieval",
            api=api,
            query_prefix="query: ",
            document_prefix="document: ",
            timeout_seconds=5,
        )
        self.calls: List[List[str]] = []

    def _post_embeddings(self, texts: List[str]) -> Any:
        self.calls.append(list(texts))
        return [[float(index + 1), 0.0] for index, _ in enumerate(texts)]


def test_external_embedding_client_applies_query_document_prefixes() -> None:
    client = RecordingEmbeddingClient(api="tei")

    assert client.embed_query("marker") == [1.0, 0.0]
    assert client.embed_documents(["alpha", "beta"]) == [[1.0, 0.0], [2.0, 0.0]]
    assert client.calls == [["query: marker"], ["document: alpha", "document: beta"]]


def test_external_embedding_parser_accepts_tei_and_openai_shapes() -> None:
    assert _extract_embeddings([[1, 2], [3, 4]]) == [[1.0, 2.0], [3.0, 4.0]]
    assert _extract_embeddings({"data": [{"embedding": [5, 6]}]}) == [[5.0, 6.0]]
    assert _extract_embeddings({"embeddings": [[7, 8]]}) == [[7.0, 8.0]]
