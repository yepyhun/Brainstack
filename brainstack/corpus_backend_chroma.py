from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
from typing import Any, Dict, List
import urllib.request
import warnings

warnings.filterwarnings(
    "ignore",
    message="'asyncio\\.iscoroutinefunction' is deprecated and slated for removal in Python 3\\.16; use inspect\\.iscoroutinefunction\\(\\) instead",
    category=DeprecationWarning,
)


class ChromaCorpusBackend:
    target_name = "corpus.chroma"
    collection_name = "brainstack_corpus_sections"

    def __init__(self, *, db_path: str) -> None:
        self._db_path = str(db_path)
        self._client: Any | None = None
        self._collection: Any | None = None
        self._embedding_client: _ExternalEmbeddingClient | None = None
        self._embedding_function: Any | None = None

    @property
    def collection(self) -> Any:
        if self._collection is None:
            raise RuntimeError("ChromaCorpusBackend is not open")
        return self._collection

    def _import_chromadb(self) -> tuple[Any, Any]:
        import chromadb
        from chromadb.config import Settings

        return chromadb, Settings

    def _build_embedding_function(self) -> Any:
        chromadb, _ = self._import_chromadb()
        return chromadb.utils.embedding_functions.DefaultEmbeddingFunction()

    def _build_embedding_client(self) -> "_ExternalEmbeddingClient | None":
        return _ExternalEmbeddingClient.from_env()

    def open(self) -> None:
        chromadb, Settings = self._import_chromadb()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._embedding_client = self._build_embedding_client()
        collection_name = self.collection_name
        metadata: Dict[str, Any] = {"hnsw:space": "cosine"}
        collection_kwargs: Dict[str, Any] = {
            "name": collection_name,
            "metadata": metadata,
        }
        if self._embedding_client is not None:
            collection_name = _collection_name_for_embedding(
                self.collection_name,
                self._embedding_client.fingerprint,
            )
            metadata.update(self._embedding_client.collection_metadata())
            collection_kwargs["name"] = collection_name
            self._embedding_function = None
        else:
            if not _allow_chroma_default_embedding():
                raise RuntimeError(
                    "Chroma default embedding is disabled. Configure local TEI via "
                    "BRAINSTACK_EMBEDDINGS_URL, or explicitly set "
                    "BRAINSTACK_CHROMA_ALLOW_DEFAULT_EMBEDDING=true for non-production diagnostics."
                )
            self._embedding_function = self._build_embedding_function()
            metadata["brainstack:embedding_provider"] = "chroma-default"
            collection_kwargs["embedding_function"] = self._embedding_function
        self._client = chromadb.PersistentClient(
            path=self._db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(**collection_kwargs)

    def close(self) -> None:
        self._collection = None
        self._client = None
        self._embedding_client = None
        self._embedding_function = None

    def is_empty(self) -> bool:
        return int(self.collection.count() or 0) == 0

    def publish_document(self, snapshot: Dict[str, Any]) -> None:
        document = dict(snapshot.get("document") or {})
        sections = list(snapshot.get("sections") or [])
        stable_key = str(document.get("stable_key") or "").strip()
        if not stable_key:
            raise RuntimeError("Corpus snapshot is missing stable_key")
        if not sections:
            self.collection.delete(where={"stable_key": stable_key})
            return

        ids: List[str] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []
        title = str(document.get("title") or "").strip()
        doc_kind = str(document.get("doc_kind") or "").strip()
        source = str(document.get("source") or "").strip()
        updated_at = str(document.get("updated_at") or "").strip()
        document_id = int(document.get("id") or 0)
        semantic_class = str(document.get("semantic_class") or "corpus").strip() or "corpus"
        document_metadata = json.dumps(document.get("metadata") or {}, ensure_ascii=True, sort_keys=True)

        for section in sections:
            section_id = int(section.get("section_id") or 0)
            section_index = int(section.get("section_index") or 0)
            content = str(section.get("content") or "").strip()
            if not content:
                continue
            heading = str(section.get("heading") or "").strip()
            token_estimate = int(section.get("token_estimate") or max(1, len(content) // 4))
            section_metadata = json.dumps(section.get("metadata") or {}, ensure_ascii=True, sort_keys=True)
            ids.append(f"{stable_key}:{section_index}")
            documents.append(content)
            metadatas.append(
                {
                    "document_id": document_id,
                    "stable_key": stable_key,
                    "semantic_class": semantic_class,
                    "title": title,
                    "doc_kind": doc_kind,
                    "source": source,
                    "updated_at": updated_at,
                    "section_id": section_id,
                    "section_index": section_index,
                    "heading": heading,
                    "token_estimate": token_estimate,
                    "document_metadata_json": document_metadata,
                    "section_metadata_json": section_metadata,
                }
            )

        if ids:
            upsert_kwargs: Dict[str, Any] = {
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            }
            if self._embedding_client is not None:
                upsert_kwargs["embeddings"] = self._embedding_client.embed_documents(documents)
            self.collection.upsert(**upsert_kwargs)

        existing = self.collection.get(where={"stable_key": stable_key}, include=[])
        existing_ids = [str(item) for item in (existing.get("ids") or [])]
        stale_ids = [item for item in existing_ids if item not in ids]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

    def search_semantic(
        self,
        *,
        query: str,
        limit: int,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        if limit <= 0 or not str(query or "").strip():
            return []
        query_kwargs = {
            "n_results": max(1, int(limit)),
            "include": ["documents", "metadatas", "distances"],
        }
        if self._embedding_client is not None:
            query_kwargs["query_embeddings"] = [self._embedding_client.embed_query(str(query or ""))]
        else:
            query_kwargs["query_texts"] = [str(query or "")]
        if where:
            query_kwargs["where"] = dict(where)
        result = self.collection.query(**query_kwargs)
        documents = list((result.get("documents") or [[]])[0] or [])
        metadatas = list((result.get("metadatas") or [[]])[0] or [])
        distances = list((result.get("distances") or [[]])[0] or [])

        rows: List[Dict[str, Any]] = []
        for index, metadata in enumerate(metadatas):
            payload = dict(metadata or {})
            content = str(documents[index] if index < len(documents) else "").strip()
            if not content:
                continue
            distance = float(distances[index]) if index < len(distances) and distances[index] is not None else None
            rows.append(
                {
                    "document_id": int(payload.get("document_id") or 0),
                    "title": str(payload.get("title") or ""),
                    "doc_kind": str(payload.get("doc_kind") or ""),
                    "source": str(payload.get("source") or ""),
                    "section_id": int(payload.get("section_id") or 0),
                    "section_index": int(payload.get("section_index") or 0),
                    "heading": str(payload.get("heading") or ""),
                    "content": content,
                    "token_estimate": int(payload.get("token_estimate") or max(1, len(content) // 4)),
                    "metadata": {
                        "stable_key": str(payload.get("stable_key") or ""),
                        "semantic_class": str(payload.get("semantic_class") or ""),
                        "document": _decode_json_object(payload.get("document_metadata_json")),
                        "section": _decode_json_object(payload.get("section_metadata_json")),
                    },
                    "distance": distance,
                    "semantic_score": (1.0 / (1.0 + distance)) if distance is not None else 0.0,
                    "retrieval_source": "corpus.semantic",
                    "match_mode": "semantic",
                }
            )
        return rows

    def score_texts(
        self,
        *,
        query: str,
        texts: List[str],
    ) -> List[float]:
        items = [str(text or "").strip() for text in texts]
        if not items:
            return []
        embedding_client = self._embedding_client or self._build_embedding_client()
        if embedding_client is not None:
            query_embedding = embedding_client.embed_query(str(query or ""))
            embeddings = embedding_client.embed_documents(items)
            return [
                _cosine_similarity(query_embedding, embedding)
                for embedding in embeddings
            ]
        if self._embedding_function is None:
            raise RuntimeError("ChromaCorpusBackend is not open")
        embeddings = self._embedding_function([str(query or "")] + items)
        if embeddings is None:
            return [0.0 for _ in items]
        embeddings_list = list(embeddings)
        if len(embeddings_list) != len(items) + 1:
            return [0.0 for _ in items]
        query_embedding = embeddings_list[0]
        return [
            _cosine_similarity(query_embedding, embedding)
            for embedding in embeddings_list[1:]
        ]


def _decode_json_object(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if left is None or right is None:
        return 0.0
    left_values = [float(value) for value in list(left)]
    right_values = [float(value) for value in list(right)]
    if not left_values or not right_values or len(left_values) != len(right_values):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left_values, right_values))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left_values))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right_values))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


class _ExternalEmbeddingClient:
    def __init__(
        self,
        *,
        url: str,
        model: str,
        api: str,
        query_prefix: str,
        document_prefix: str,
        timeout_seconds: float,
    ) -> None:
        self.url = str(url or "").strip()
        self.model = str(model or "").strip()
        self.api = str(api or "tei").strip().lower() or "tei"
        self.query_prefix = str(query_prefix or "")
        self.document_prefix = str(document_prefix or "")
        self.timeout_seconds = max(1.0, float(timeout_seconds or 15))
        self.fingerprint = _embedding_fingerprint(
            url=self.url,
            model=self.model,
            api=self.api,
            query_prefix=self.query_prefix,
            document_prefix=self.document_prefix,
        )

    @classmethod
    def from_env(cls) -> "_ExternalEmbeddingClient | None":
        url = _env_first("BRAINSTACK_EMBEDDINGS_URL", "BRAINSTACK_TEMPORAL_EMBEDDINGS_URL")
        if not url:
            return None
        provider = _env_first("BRAINSTACK_EMBEDDINGS_PROVIDER") or "tei"
        api = _env_first("BRAINSTACK_EMBEDDINGS_API") or provider
        model = _env_first("BRAINSTACK_EMBEDDINGS_MODEL", "BRAINSTACK_TEMPORAL_EMBEDDINGS_MODEL")
        query_prefix = _env_first(
            "BRAINSTACK_EMBEDDINGS_QUERY_PREFIX",
            "BRAINSTACK_TEMPORAL_EMBEDDINGS_QUERY_PREFIX",
        )
        document_prefix = _env_first(
            "BRAINSTACK_EMBEDDINGS_DOCUMENT_PREFIX",
            "BRAINSTACK_TEMPORAL_EMBEDDINGS_DOCUMENT_PREFIX",
        )
        timeout = _env_first(
            "BRAINSTACK_EMBEDDINGS_TIMEOUT_SECONDS",
            "BRAINSTACK_TEMPORAL_EMBEDDINGS_TIMEOUT_SECONDS",
        )
        return cls(
            url=url,
            model=model or "",
            api=api,
            query_prefix="query: " if query_prefix is None else query_prefix,
            document_prefix="document: " if document_prefix is None else document_prefix,
            timeout_seconds=float(timeout or 15),
        )

    def collection_metadata(self) -> Dict[str, Any]:
        return {
            "brainstack:embedding_provider": self.api,
            "brainstack:embedding_model": self.model or "server-default",
            "brainstack:embedding_fingerprint": self.fingerprint,
        }

    def embed_query(self, query: str) -> List[float]:
        return self.embed([f"{self.query_prefix}{str(query or '')}"])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.embed([f"{self.document_prefix}{str(text or '')}" for text in texts])

    def __call__(self, input: List[str]) -> List[List[float]]:
        return self.embed([str(text or "") for text in input])

    def embed(self, texts: List[str]) -> List[List[float]]:
        items = [str(text or "") for text in texts]
        if not items:
            return []
        body = self._post_embeddings(items)
        embeddings = _extract_embeddings(body)
        if len(embeddings) != len(items):
            raise RuntimeError(
                f"Embedding service returned {len(embeddings)} vectors for {len(items)} inputs"
            )
        return embeddings

    def _post_embeddings(self, texts: List[str]) -> Any:
        payload: Dict[str, Any]
        if self.api == "openai":
            payload = {"input": texts}
            if self.model:
                payload["model"] = self.model
        else:
            payload = {"inputs": texts}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))


def _extract_embeddings(body: Any) -> List[List[float]]:
    if isinstance(body, list):
        return [_coerce_embedding(item) for item in body]
    if not isinstance(body, dict):
        return []
    if isinstance(body.get("data"), list):
        return [_coerce_embedding(item.get("embedding")) for item in body.get("data") or []]
    if isinstance(body.get("embeddings"), list):
        return [_coerce_embedding(item) for item in body.get("embeddings") or []]
    if isinstance(body.get("embedding"), list):
        return [_coerce_embedding(body.get("embedding"))]
    return []


def _coerce_embedding(value: Any) -> List[float]:
    if not isinstance(value, list):
        return []
    return [float(item) for item in value]


def _env_first(*names: str) -> str | None:
    for name in names:
        value = str(os.getenv(name, "") or "").strip()
        if value:
            return value
    return None


def _allow_chroma_default_embedding() -> bool:
    if _env_bool("BRAINSTACK_DISABLE_CHROMA_DEFAULT_EMBEDDING", default=False):
        return False
    return _env_bool("BRAINSTACK_CHROMA_ALLOW_DEFAULT_EMBEDDING", default=False)


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _embedding_fingerprint(
    *,
    url: str,
    model: str,
    api: str,
    query_prefix: str,
    document_prefix: str,
) -> str:
    payload = {
        "api": api,
        "document_prefix": document_prefix,
        "model": model,
        "query_prefix": query_prefix,
        "url_hash": hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:16],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _collection_name_for_embedding(base_name: str, fingerprint: str) -> str:
    suffix = hashlib.sha256(str(fingerprint).encode("utf-8")).hexdigest()[:12]
    return f"{base_name}_{suffix}"
