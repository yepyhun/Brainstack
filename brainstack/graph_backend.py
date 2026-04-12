from __future__ import annotations

from typing import Any, Dict, List, Protocol


class GraphBackend(Protocol):
    target_name: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_empty(self) -> bool: ...

    def publish_entity_subgraph(self, snapshot: Dict[str, Any]) -> None: ...

    def search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]: ...

    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]: ...


def create_graph_backend(kind: str, *, db_path: str) -> GraphBackend | None:
    normalized = str(kind or "sqlite").strip().lower()
    if normalized in {"", "sqlite", "none"}:
        return None
    if normalized == "kuzu":
        from .graph_backend_kuzu import KuzuGraphBackend

        return KuzuGraphBackend(db_path=db_path)
    raise ValueError(f"Unsupported graph backend: {kind}")
