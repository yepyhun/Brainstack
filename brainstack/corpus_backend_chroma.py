from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List
import urllib.request


class ChromaCorpusBackend:
    target_name = "corpus.chroma"
    collection_name = "brainstack_corpus_sections"

    def __init__(self, *, db_path: str) -> None:
        self._db_path = str(db_path)
        self._client: Any | None = None
        self._collection: Any | None = None
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

    def open(self) -> None:
        chromadb, Settings = self._import_chromadb()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._embedding_function = self._build_embedding_function()
        self._client = chromadb.PersistentClient(
            path=self._db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self._embedding_function,
            metadata={"hnsw:space": "cosine"},
        )

    def close(self) -> None:
        self._collection = None
        self._client = None
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
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

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
        query_kwargs = {
            "query_texts": [str(query or "")],
            "n_results": max(1, int(limit)),
            "include": ["documents", "metadatas", "distances"],
        }
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
        external_url = str(os.getenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_URL", "") or "").strip()
        if external_url:
            return self._score_texts_via_external_embeddings(
                url=external_url,
                model=str(os.getenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_MODEL", "") or "").strip(),
                query_prefix=str(os.getenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_QUERY_PREFIX", "query: ") or ""),
                document_prefix=str(os.getenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_DOCUMENT_PREFIX", "document: ") or ""),
                timeout_seconds=float(os.getenv("BRAINSTACK_TEMPORAL_EMBEDDINGS_TIMEOUT_SECONDS", "15") or 15),
                query=str(query or ""),
                texts=items,
            )
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

    def _score_texts_via_external_embeddings(
        self,
        *,
        url: str,
        model: str,
        query_prefix: str,
        document_prefix: str,
        timeout_seconds: float,
        query: str,
        texts: List[str],
    ) -> List[float]:
        payload: Dict[str, Any] = {
            "input": [f"{query_prefix}{query}"] + [f"{document_prefix}{text}" for text in texts],
        }
        if model:
            payload["model"] = model
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=max(1.0, float(timeout_seconds))) as response:
            body = json.loads(response.read().decode("utf-8"))
        data = list(body.get("data") or [])
        embeddings = [item.get("embedding") for item in data]
        if len(embeddings) != len(texts) + 1:
            return [0.0 for _ in texts]
        query_embedding = embeddings[0]
        return [
            _cosine_similarity(query_embedding, embedding)
            for embedding in embeddings[1:]
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
