from __future__ import annotations

from typing import Any, Dict, List, Protocol


class CorpusBackend(Protocol):
    target_name: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_empty(self) -> bool: ...

    def publish_document(self, snapshot: Dict[str, Any]) -> None: ...

    def search_semantic(
        self,
        *,
        query: str,
        limit: int,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]: ...

    def score_texts(
        self,
        *,
        query: str,
        texts: List[str],
    ) -> List[float]: ...


def create_corpus_backend(kind: str, *, db_path: str) -> CorpusBackend | None:
    normalized = str(kind or "sqlite").strip().lower()
    if normalized in {"", "sqlite", "none"}:
        return None
    if normalized == "chroma":
        from .corpus_backend_chroma import ChromaCorpusBackend

        return ChromaCorpusBackend(db_path=db_path)
    raise ValueError(f"Unsupported corpus backend: {kind}")
