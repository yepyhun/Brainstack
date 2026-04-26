from __future__ import annotations

from .graph_state_core_store import GraphStateCoreMixin
from .graph_state_relation_store import GraphStateRelationMixin
from .graph_state_snapshot_store import GraphStateSnapshotMixin


class GraphStateStoreMixin(
    GraphStateCoreMixin,
    GraphStateRelationMixin,
    GraphStateSnapshotMixin,
):
    """Compatibility facade for graph-state storage mixins."""
