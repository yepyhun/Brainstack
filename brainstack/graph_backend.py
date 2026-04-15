from __future__ import annotations

import logging
from typing import Any, Dict, List, Protocol


logger = logging.getLogger(__name__)


class GraphBackend(Protocol):
    target_name: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_empty(self) -> bool: ...

    def publish_entity_subgraph(self, snapshot: Dict[str, Any]) -> None: ...

    def search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]: ...

    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]: ...

    def query_typed_metric_sum(
        self,
        *,
        owner_subject: str | None,
        entity_type: str | None,
        entity_type_contains: List[str] | None = None,
        entity_type_excludes: List[str] | None = None,
        metric_attribute: str,
        limit: int,
    ) -> Dict[str, Any] | None: ...


def create_graph_backend(kind: str, *, db_path: str) -> GraphBackend | None:
    normalized = str(kind or "sqlite").strip().lower()
    if normalized in {"", "sqlite", "none"}:
        return None
    if normalized == "kuzu":
        try:
            from .graph_backend_kuzu import KuzuGraphBackend
        except (ImportError, ModuleNotFoundError) as exc:
            if getattr(exc, "name", "") not in {"", "kuzu"} and "kuzu" not in str(exc).lower():
                raise
            logger.warning("Brainstack Kuzu backend unavailable; continuing without graph backend")
            return None

        return KuzuGraphBackend(db_path=db_path)
    raise ValueError(f"Unsupported graph backend: {kind}")
