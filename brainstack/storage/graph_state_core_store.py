from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    SEMANTIC_EVIDENCE_INDEX_VERSION,
    _cursor_lastrowid,
    _merge_record_metadata,
    _row_to_dict,
    json,
    logger,
    semantic_evidence_fingerprint,
    utc_now_iso,
)

class GraphStateCoreMixin(StoreRuntimeBase):
    def graph_backend_channel_status(self) -> Dict[str, str]:
            if self._graph_backend is None:
                if self._graph_backend_error:
                    return {
                        "status": "degraded",
                        "reason": f"Graph backend retrieval is unhealthy and fell back to SQLite: {self._graph_backend_error}",
                    }
                return {
                    "status": "degraded",
                    "reason": "Graph backend retrieval is disabled until a donor-aligned graph backend is configured.",
                }
            if self._graph_backend_error:
                return {
                    "status": "degraded",
                    "reason": f"Graph backend retrieval is unhealthy and fell back to SQLite: {self._graph_backend_error}",
                }
            return {
                "status": "active",
                "reason": f"Graph retrieval is served by {self._graph_backend.target_name}.",
            }

    def graph_recall_channel_status(self) -> Dict[str, Any]:
            storage_status = self.graph_backend_channel_status()
            graph_rows = self.conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM graph_states WHERE is_current = 1) +
                    (SELECT COUNT(*) FROM graph_relations WHERE active = 1) +
                    (SELECT COUNT(*) FROM graph_inferred_relations WHERE active = 1) AS count
                """
            ).fetchone()
            graph_row_count = int(graph_rows["count"] if graph_rows is not None else 0)
            semantic_graph_rows = self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM semantic_evidence_index
                WHERE active = 1
                  AND shelf = 'graph'
                  AND fingerprint = ?
                  AND index_version = ?
                """,
                (semantic_evidence_fingerprint(), SEMANTIC_EVIDENCE_INDEX_VERSION),
            ).fetchone()
            semantic_graph_count = int(semantic_graph_rows["count"] if semantic_graph_rows is not None else 0)
            if graph_row_count <= 0:
                mode = "unavailable"
                status = "idle"
                reason = "No current graph rows are available for recall."
            elif semantic_graph_count > 0:
                mode = "hybrid_seeded"
                status = "active"
                reason = "Graph recall can use lexical graph search plus typed semantic evidence seeds."
            else:
                mode = "lexical_seeded"
                status = "active"
                reason = "Graph recall uses lexical graph search seeds only."
            return {
                "status": status,
                "reason": reason,
                "recall_mode": mode,
                "graph_row_count": graph_row_count,
                "semantic_graph_seed_count": semantic_graph_count,
                "storage_status": dict(storage_status),
            }

    def _normalize_entity_name(self, name: str) -> str:
            return " ".join(name.lower().split())

    def get_or_create_entity(self, name: str) -> Dict[str, Any]:
            now = utc_now_iso()
            normalized = self._normalize_entity_name(name)
            row = self.conn.execute(
                "SELECT id, canonical_name, normalized_name FROM graph_entities WHERE normalized_name = ?",
                (normalized,),
            ).fetchone()
            if row:
                return dict(row)
            alias_row = self.conn.execute(
                """
                SELECT ge.id, ge.canonical_name, ge.normalized_name, ga.alias_name AS matched_alias
                FROM graph_entity_aliases ga
                JOIN graph_entities ge ON ge.id = ga.target_entity_id
                WHERE ga.normalized_alias = ?
                ORDER BY ga.updated_at DESC, ga.id DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if alias_row:
                return dict(alias_row)
            cur = self.conn.execute(
                """
                INSERT INTO graph_entities (canonical_name, normalized_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip(), normalized, now, now),
            )
            self.conn.commit()
            return {
                "id": _cursor_lastrowid(cur),
                "canonical_name": name.strip(),
                "normalized_name": normalized,
            }

    def merge_entity_alias(self, *, alias_name: str, target_name: str) -> Dict[str, Any]:
            alias_normalized = self._normalize_entity_name(alias_name)
            target_normalized = self._normalize_entity_name(target_name)
            if not alias_normalized or not target_normalized or alias_normalized == target_normalized:
                return {"status": "noop"}
            now = utc_now_iso()

            alias = self.conn.execute(
                "SELECT id FROM graph_entities WHERE normalized_name = ?",
                (alias_normalized,),
            ).fetchone()
            if not alias:
                return {"status": "noop"}

            target = self.get_or_create_entity(target_name)
            alias_id = int(alias["id"])
            target_id = int(target["id"])
            alias_metadata = _merge_record_metadata(
                None,
                {
                    "graph_identity": {
                        "kind": "alias_merge",
                        "alias_name": alias_name.strip(),
                        "target_name": target_name.strip(),
                    },
                    "provenance": {"source_ids": ["merge_entity_alias"]},
                },
                source="entity_alias_merge",
            )
            self.conn.execute(
                """
                INSERT INTO graph_entity_aliases (
                    alias_name, normalized_alias, target_entity_id, source, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(normalized_alias, target_entity_id)
                DO UPDATE SET alias_name = excluded.alias_name,
                              source = excluded.source,
                              metadata_json = excluded.metadata_json,
                              updated_at = excluded.updated_at
                """,
                (
                    alias_name.strip(),
                    alias_normalized,
                    target_id,
                    "entity_alias_merge",
                    json.dumps(alias_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                    now,
                ),
            )

            self.conn.execute("UPDATE graph_states SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
            self.conn.execute("UPDATE graph_conflicts SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
            self.conn.execute("UPDATE graph_relations SET subject_entity_id = ? WHERE subject_entity_id = ?", (target_id, alias_id))
            self.conn.execute(
                "UPDATE graph_inferred_relations SET subject_entity_id = ? WHERE subject_entity_id = ?",
                (target_id, alias_id),
            )
            self.conn.execute(
                "UPDATE graph_relations SET object_entity_id = ?, object_text = ? WHERE object_entity_id = ?",
                (target_id, target_name.strip(), alias_id),
            )
            self.conn.execute(
                "UPDATE graph_inferred_relations SET object_entity_id = ?, object_text = ? WHERE object_entity_id = ?",
                (target_id, target_name.strip(), alias_id),
            )

            duplicate_groups = self.conn.execute(
                """
                SELECT subject_entity_id, predicate, object_entity_id, COUNT(*) AS relation_count
                FROM graph_relations
                WHERE active = 1
                GROUP BY subject_entity_id, predicate, object_entity_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for group in duplicate_groups:
                rows = self.conn.execute(
                    """
                    SELECT id
                    FROM graph_relations
                    WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                    ORDER BY id DESC
                    """,
                    (int(group["subject_entity_id"]), str(group["predicate"]), int(group["object_entity_id"])),
                ).fetchall()
                for row in rows[1:]:
                    self.conn.execute("UPDATE graph_relations SET active = 0 WHERE id = ?", (int(row["id"]),))

            inferred_duplicate_groups = self.conn.execute(
                """
                SELECT subject_entity_id, predicate, object_entity_id, COUNT(*) AS relation_count
                FROM graph_inferred_relations
                WHERE active = 1
                GROUP BY subject_entity_id, predicate, object_entity_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
            for group in inferred_duplicate_groups:
                rows = self.conn.execute(
                    """
                    SELECT id
                    FROM graph_inferred_relations
                    WHERE active = 1 AND subject_entity_id = ? AND predicate = ? AND object_entity_id = ?
                    ORDER BY id DESC
                    """,
                    (int(group["subject_entity_id"]), str(group["predicate"]), int(group["object_entity_id"])),
                ).fetchall()
                for row in rows[1:]:
                    self.conn.execute(
                        "UPDATE graph_inferred_relations SET active = 0, updated_at = ? WHERE id = ?",
                        (now, int(row["id"])),
                    )

            refs = self.conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM graph_states WHERE entity_id = ?) AS state_refs,
                    (SELECT COUNT(*) FROM graph_conflicts WHERE entity_id = ?) AS conflict_refs,
                    (SELECT COUNT(*) FROM graph_relations WHERE subject_entity_id = ? OR object_entity_id = ?) AS relation_refs,
                    (SELECT COUNT(*) FROM graph_inferred_relations WHERE subject_entity_id = ? OR object_entity_id = ?) AS inferred_relation_refs
                """,
                (alias_id, alias_id, alias_id, alias_id, alias_id, alias_id),
            ).fetchone()
            if (
                refs
                and int(refs["state_refs"]) == 0
                and int(refs["conflict_refs"]) == 0
                and int(refs["relation_refs"]) == 0
                and int(refs["inferred_relation_refs"]) == 0
            ):
                self.conn.execute("DELETE FROM graph_entities WHERE id = ?", (alias_id,))

            self.conn.commit()
            if self._graph_backend is not None:
                self._publish_entity_subgraph(target_id)
            return {"status": "merged", "alias_id": alias_id, "target_id": target_id}

    def find_continuity_event(
            self,
            *,
            session_id: str,
            kind: str,
            content: str,
        ) -> Dict[str, Any] | None:
            row = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM continuity_events
                WHERE session_id = ? AND kind = ? AND content = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id, kind, content),
            ).fetchone()
            return _row_to_dict(row) if row else None

    def query_native_typed_metric_sum(
            self,
            *,
            owner_subject: str | None,
            entity_type: str | None,
            entity_type_contains: Iterable[str] | None = None,
            entity_type_excludes: Iterable[str] | None = None,
            metric_attribute: str,
            limit: int = 16,
        ) -> Dict[str, Any] | None:
            if self._graph_backend is None:
                return None
            query_method = getattr(self._graph_backend, "query_typed_metric_sum", None)
            if not callable(query_method):
                return None
            try:
                result = query_method(
                    owner_subject=owner_subject,
                    entity_type=entity_type,
                    entity_type_contains=list(entity_type_contains or []),
                    entity_type_excludes=list(entity_type_excludes or []),
                    metric_attribute=metric_attribute,
                    limit=max(1, int(limit)),
                )
            except Exception as exc:
                self._disable_graph_backend(reason=str(exc))
                logger.warning("Brainstack native typed metric query failed: %s", exc)
                return None
            self._graph_backend_error = ""
            return dict(result) if isinstance(result, dict) else None
