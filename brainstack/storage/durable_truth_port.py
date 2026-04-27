from __future__ import annotations

from typing import Any, Mapping

from ..core.admission import TruthWritePermit


def merge_truth_write_permit_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    permit: TruthWritePermit,
) -> dict[str, Any]:
    payload = dict(metadata or {})
    payload.update(permit.metadata_payload())
    return payload


class DurableTruthPort:
    """Typed durable truth write boundary.

    Raw transcripts and support events do not use this port. Durable profile,
    graph, operating, and task truth writes do.
    """

    def __init__(self, store: Any) -> None:
        self.store = store

    def write_profile(
        self,
        *,
        stable_key: str,
        category: str,
        content: str,
        source: str,
        confidence: float,
        permit: TruthWritePermit,
        metadata: Mapping[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        return int(
            self.store.upsert_profile_item(
                stable_key=stable_key,
                category=category,
                content=content,
                source=source,
                confidence=confidence,
                metadata=merge_truth_write_permit_metadata(metadata, permit=permit),
                active=active,
            )
        )

    def write_graph_state(
        self,
        *,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        permit: TruthWritePermit,
        supersede: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return dict(
            self.store.upsert_graph_state(
                subject_name=subject_name,
                attribute=attribute,
                value_text=value_text,
                source=source,
                supersede=supersede,
                metadata=merge_truth_write_permit_metadata(metadata, permit=permit),
            )
        )

    def write_graph_relation(
        self,
        *,
        subject_name: str,
        predicate: str,
        object_name: str,
        source: str,
        permit: TruthWritePermit,
        metadata: Mapping[str, Any] | None = None,
        inferred: bool = False,
    ) -> dict[str, Any]:
        write = self.store.upsert_graph_inferred_relation if inferred else self.store.upsert_graph_relation
        return dict(
            write(
                subject_name=subject_name,
                predicate=predicate,
                object_name=object_name,
                source=source,
                metadata=merge_truth_write_permit_metadata(metadata, permit=permit),
            )
        )

    def write_operating(
        self,
        *,
        stable_key: str,
        principal_scope_key: str,
        record_type: str,
        content: str,
        owner: str,
        source: str,
        permit: TruthWritePermit,
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        return int(
            self.store.upsert_operating_record(
                stable_key=stable_key,
                principal_scope_key=principal_scope_key,
                record_type=record_type,
                content=content,
                owner=owner,
                source=source,
                source_session_id=source_session_id,
                source_turn_number=source_turn_number,
                metadata=merge_truth_write_permit_metadata(metadata, permit=permit),
            )
        )

    def write_task(
        self,
        *,
        stable_key: str,
        principal_scope_key: str,
        item_type: str,
        title: str,
        due_date: str,
        date_scope: str,
        optional: bool,
        status: str,
        owner: str,
        source: str,
        permit: TruthWritePermit,
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        return int(
            self.store.upsert_task_item(
                stable_key=stable_key,
                principal_scope_key=principal_scope_key,
                item_type=item_type,
                title=title,
                due_date=due_date,
                date_scope=date_scope,
                optional=optional,
                status=status,
                owner=owner,
                source=source,
                source_session_id=source_session_id,
                source_turn_number=source_turn_number,
                metadata=merge_truth_write_permit_metadata(metadata, permit=permit),
            )
        )
