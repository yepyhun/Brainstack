"""Public proactive projection SDK.

This is the supported seam for host/runtime integrations. It lets a runtime
project proactive events into Brainstack memory without importing Brainstack
private storage modules or owning scheduling/delivery inside the memory kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from ..core.proactive import (
    PROACTIVE_CONTROL_SCHEMA,
    PROACTIVE_EVENT_SCHEMA,
    PROACTIVE_OUTBOX_SCHEMA,
    ProactiveAuthority,
    ProactiveCandidate,
    ProactiveEventKind,
    ProactiveEventState,
    ProactiveIntendedNextAction,
    ProactiveReasonCode,
)


@runtime_checkable
class ProactiveEventSink(Protocol):
    def project_event(
        self,
        *,
        source: str,
        kind: str,
        principal_scope_key: str,
        workspace_scope_key: str = "",
        workstream_scope_key: str = "",
        title: str = "",
        summary: str = "",
        priority: str = "normal",
        evidence_ids: Iterable[str] = (),
        source_ref: str = "",
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        """Project one proactive event into Brainstack memory."""


@runtime_checkable
class ProactiveProjectionStore(ProactiveEventSink, Protocol):
    def create_outbox(
        self,
        *,
        event_id: str,
        delivery_target: str,
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
    ) -> dict[str, Any]:
        """Create a delivery outbox projection row. Runtime still owns delivery."""


@runtime_checkable
class ProactiveInspectPort(Protocol):
    def list_items(
        self,
        *,
        principal_scope_key: str = "",
        state: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List proactive projection items."""

    def inspect_item(self, *, event_id: str) -> dict[str, Any]:
        """Inspect one proactive projection item."""


@dataclass(frozen=True)
class StoreProactiveProjection:
    """Adapter from public SDK to a BrainstackStore-like object."""

    store: Any

    def project_event(
        self,
        *,
        source: str,
        kind: str,
        principal_scope_key: str,
        workspace_scope_key: str = "",
        workstream_scope_key: str = "",
        title: str = "",
        summary: str = "",
        priority: str = "normal",
        evidence_ids: Iterable[str] = (),
        source_ref: str = "",
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
        metadata: Mapping[str, Any] | None = None,
        trace_id: str = "",
    ) -> dict[str, Any]:
        return self.store.upsert_proactive_event(
            source=source,
            kind=kind,
            principal_scope_key=principal_scope_key,
            workspace_scope_key=workspace_scope_key,
            workstream_scope_key=workstream_scope_key,
            title=title,
            summary=summary,
            priority=priority,
            evidence_ids=evidence_ids,
            source_ref=source_ref,
            idempotency_key=idempotency_key,
            intended_next_action=intended_next_action,
            metadata=metadata,
            trace_id=trace_id,
        )

    def create_outbox(
        self,
        *,
        event_id: str,
        delivery_target: str,
        idempotency_key: str = "",
        intended_next_action: str = ProactiveIntendedNextAction.NONE.value,
    ) -> dict[str, Any]:
        return self.store.create_proactive_outbox(
            event_id=event_id,
            delivery_target=delivery_target,
            idempotency_key=idempotency_key,
            intended_next_action=intended_next_action,
        )

    def list_items(
        self,
        *,
        principal_scope_key: str = "",
        state: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self.store.list_proactive_items(
            principal_scope_key=principal_scope_key,
            state=state,
            limit=limit,
        )

    def inspect_item(self, *, event_id: str) -> dict[str, Any]:
        return self.store.inspect_proactive_item(event_id=event_id)


__all__ = [
    "PROACTIVE_CONTROL_SCHEMA",
    "PROACTIVE_EVENT_SCHEMA",
    "PROACTIVE_OUTBOX_SCHEMA",
    "ProactiveAuthority",
    "ProactiveCandidate",
    "ProactiveEventKind",
    "ProactiveEventSink",
    "ProactiveEventState",
    "ProactiveInspectPort",
    "ProactiveIntendedNextAction",
    "ProactiveProjectionStore",
    "ProactiveReasonCode",
    "StoreProactiveProjection",
]
