"""Runtime bridge for behavior-preserving BrainstackStore mixins."""

from __future__ import annotations

from typing import Any


class StoreRuntimeBase:
    """Mixin self-type bridge.

    Store slices are move-only pieces of one facade. Individual mixin classes
    intentionally do not define every cross-slice method or runtime attribute.
    """

    _conn: Any
    _corpus_backend: Any
    _corpus_backend_error: str
    _db_path: str
    _graph_backend: Any
    _graph_backend_error: str
    _lock: Any

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
