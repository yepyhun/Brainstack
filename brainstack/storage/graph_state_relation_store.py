from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    _cursor_lastrowid,
    _merge_graph_record_metadata,
    _normalize_graph_record_metadata,
    json,
    utc_now_iso,
)

class GraphStateRelationMixin(StoreRuntimeBase):
    def _sqlite_add_graph_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> int:
            now = utc_now_iso()
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            existing = self.conn.execute(
                """
                SELECT id, metadata_json FROM graph_relations
                WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
                """,
                (subject["id"], predicate, obj["id"]),
            ).fetchone()
            if existing:
                merged = _merge_graph_record_metadata(
                    existing["metadata_json"],
                    metadata,
                    source=source,
                    graph_kind="relation",
                )
                self.conn.execute(
                    "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                    (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
                )
                self.conn.execute(
                    """
                    UPDATE graph_inferred_relations
                    SET active = 0, updated_at = ?
                    WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                    """,
                    (now, subject["id"], predicate, obj["id"]),
                )
                self.conn.commit()
                return int(existing["id"])
            normalized_metadata = _normalize_graph_record_metadata(
                metadata,
                source=source,
                graph_kind="relation",
            )
            cur = self.conn.execute(
                """
                INSERT INTO graph_relations (
                    subject_entity_id, predicate, object_entity_id, object_text, source, metadata_json, created_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    subject["id"],
                    predicate,
                    obj["id"],
                    object_name.strip(),
                    source,
                    json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                ),
            )
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET active = 0, updated_at = ?
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                """,
                (now, subject["id"], predicate, obj["id"]),
            )
            self.conn.commit()
            return _cursor_lastrowid(cur)

    def _sqlite_upsert_graph_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            now = utc_now_iso()
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            existing = self.conn.execute(
                """
                SELECT id, metadata_json FROM graph_relations
                WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
                """,
                (subject["id"], predicate, obj["id"]),
            ).fetchone()
            if existing:
                merged = _merge_graph_record_metadata(
                    existing["metadata_json"],
                    metadata,
                    source=source,
                    graph_kind="relation",
                )
                self.conn.execute(
                    "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                    (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
                )
                self.conn.execute(
                    """
                    UPDATE graph_inferred_relations
                    SET active = 0, updated_at = ?
                    WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                    """,
                    (now, subject["id"], predicate, obj["id"]),
                )
                self.conn.commit()
                return {"status": "unchanged", "relation_id": int(existing["id"])}
            normalized_metadata = _normalize_graph_record_metadata(
                metadata,
                source=source,
                graph_kind="relation",
            )
            cur = self.conn.execute(
                """
                INSERT INTO graph_relations (
                    subject_entity_id, predicate, object_entity_id, object_text, source, metadata_json, created_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    subject["id"],
                    predicate,
                    obj["id"],
                    object_name.strip(),
                    source,
                    json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                ),
            )
            self.conn.execute(
                """
                UPDATE graph_inferred_relations
                SET active = 0, updated_at = ?
                WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                """,
                (now, subject["id"], predicate, obj["id"]),
            )
            self.conn.commit()
            return {"status": "inserted", "relation_id": _cursor_lastrowid(cur)}

    def _sqlite_upsert_graph_inferred_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            now = utc_now_iso()
            subject = self.get_or_create_entity(subject_name)
            obj = self.get_or_create_entity(object_name)
            explicit = self.conn.execute(
                """
                SELECT id FROM graph_relations
                WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
                LIMIT 1
                """,
                (subject["id"], predicate, obj["id"]),
            ).fetchone()
            if explicit:
                self.conn.execute(
                    """
                    UPDATE graph_inferred_relations
                    SET active = 0, updated_at = ?
                    WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                    """,
                    (now, subject["id"], predicate, obj["id"]),
                )
                self.conn.commit()
                return {"status": "shadowed", "relation_id": int(explicit["id"])}

            normalized_metadata = _normalize_graph_record_metadata(
                metadata,
                source=source,
                graph_kind="inferred_relation",
            )
            existing = self.conn.execute(
                """
                SELECT id, metadata_json FROM graph_inferred_relations
                WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
                LIMIT 1
                """,
                (subject["id"], predicate, obj["id"]),
            ).fetchone()
            if existing:
                merged = _merge_graph_record_metadata(
                    existing["metadata_json"],
                    normalized_metadata,
                    source=source,
                    graph_kind="inferred_relation",
                )
                self.conn.execute(
                    """
                    UPDATE graph_inferred_relations
                    SET metadata_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (json.dumps(merged, ensure_ascii=True, sort_keys=True), now, int(existing["id"])),
                )
                self.conn.commit()
                return {"status": "unchanged", "relation_id": int(existing["id"])}

            cur = self.conn.execute(
                """
                INSERT INTO graph_inferred_relations (
                    subject_entity_id, predicate, object_entity_id, object_text,
                    source, metadata_json, created_at, updated_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    subject["id"],
                    predicate,
                    obj["id"],
                    object_name.strip(),
                    source,
                    json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return {"status": "inserted", "relation_id": _cursor_lastrowid(cur)}

    def add_graph_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> int:
            relation_id = self._sqlite_add_graph_relation(
                subject_name=subject_name,
                predicate=predicate,
                object_name=object_name,
                source=source,
                metadata=metadata,
            )
            if self._graph_backend is not None:
                subject = self.get_or_create_entity(subject_name)
                obj = self.get_or_create_entity(object_name)
                self._publish_entity_subgraph(int(subject["id"]))
                self._publish_entity_subgraph(int(obj["id"]))
            return relation_id

    def upsert_graph_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            outcome = self._sqlite_upsert_graph_relation(
                subject_name=subject_name,
                predicate=predicate,
                object_name=object_name,
                source=source,
                metadata=metadata,
            )
            if self._graph_backend is not None:
                subject = self.get_or_create_entity(subject_name)
                obj = self.get_or_create_entity(object_name)
                self._publish_entity_subgraph(int(subject["id"]))
                self._publish_entity_subgraph(int(obj["id"]))
            return outcome

    def upsert_graph_inferred_relation(
            self,
            *,
            subject_name: str,
            predicate: str,
            object_name: str,
            source: str,
            metadata: Dict[str, Any] | None = None,
        ) -> Dict[str, Any]:
            outcome = self._sqlite_upsert_graph_inferred_relation(
                subject_name=subject_name,
                predicate=predicate,
                object_name=object_name,
                source=source,
                metadata=metadata,
            )
            if self._graph_backend is not None:
                subject = self.get_or_create_entity(subject_name)
                obj = self.get_or_create_entity(object_name)
                self._publish_entity_subgraph(int(subject["id"]))
                self._publish_entity_subgraph(int(obj["id"]))
            return outcome
