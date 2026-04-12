from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ChromaCorpusBackend:
    target_name = "corpus.chroma"
    collection_name = "brainstack_corpus_sections"

    def __init__(self, *, db_path: str) -> None:
        self._db_path = str(db_path)
        self._client = None
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            raise RuntimeError("ChromaCorpusBackend is not open")
        return self._collection

    def _import_chromadb(self):
        import chromadb
        from chromadb.config import Settings

        return chromadb, Settings

    def _build_embedding_function(self):
        chromadb, _ = self._import_chromadb()
        return chromadb.utils.embedding_functions.DefaultEmbeddingFunction()

    def open(self) -> None:
        chromadb, Settings = self._import_chromadb()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self._db_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self._build_embedding_function(),
            metadata={"hnsw:space": "cosine"},
        )

    def close(self) -> None:
        self._collection = None
        self._client = None

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

    def search_semantic(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        result = self.collection.query(
            query_texts=[str(query or "")],
            n_results=max(1, int(limit)),
            include=["documents", "metadatas", "distances"],
        )
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


def _decode_json_object(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
