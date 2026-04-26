from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    SEMANTIC_EVIDENCE_INDEX_VERSION,
    _annotate_principal_scope,
    _attach_keyword_scores,
    _cursor_lastrowid,
    _decode_json_object,
    _graph_sort_key,
    _graph_structured_field_match_score,
    _locked,
    _merge_graph_record_metadata,
    _merge_record_metadata,
    _normalize_graph_record_metadata,
    _principal_scope_key_from_metadata,
    _row_to_dict,
    _should_auto_supersede_exact_value,
    attach_graph_source_lineage,
    build_like_tokens,
    infer_relative_duration_valid_to,
    is_background_relative_duration_source,
    is_unbounded_background_volatile_state,
    json,
    logger,
    merge_provenance,
    merge_temporal,
    semantic_evidence_fingerprint,
    utc_now_iso,
)

class GraphStateStoreMixin(StoreRuntimeBase):
    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
    def _sqlite_upsert_graph_state(
        self,
        *,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        supersede: bool = False,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        now = utc_now_iso()
        entity = self.get_or_create_entity(subject_name)
        normalized_metadata = _normalize_graph_record_metadata(
            metadata,
            source=source,
            graph_kind="state",
        )
        temporal = merge_temporal(
            normalized_metadata.get("temporal"),
            {"observed_at": normalized_metadata.get("temporal", {}).get("observed_at") or now},
        )
        if temporal:
            normalized_metadata["temporal"] = temporal
        inferred_valid_to = infer_relative_duration_valid_to(
            value_text=value_text,
            temporal=temporal,
            metadata=normalized_metadata,
            attribute=attribute,
        )
        if inferred_valid_to and not normalized_metadata.get("temporal", {}).get("valid_to"):
            if is_background_relative_duration_source(
                {
                    "source": source,
                    "metadata": normalized_metadata,
                    "attribute": attribute,
                    "value_text": value_text,
                }
            ):
                inferred_valid_to = str(temporal.get("valid_from") or temporal.get("observed_at") or now)
            temporal = merge_temporal(temporal, {"valid_to": inferred_valid_to})
            normalized_metadata["temporal"] = temporal
            normalized_metadata["relative_duration_validity"] = {
                "schema": "brainstack.relative_duration_validity.v1",
                "derived_valid_to": inferred_valid_to,
                "grammar": "numeric_duration_remaining",
                "current_authority": "disabled_for_background_relative_duration"
                if is_background_relative_duration_source(
                    {
                        "source": source,
                        "metadata": normalized_metadata,
                        "attribute": attribute,
                        "value_text": value_text,
                    }
                )
                else "valid_until_derived_window",
            }
        if not normalized_metadata.get("temporal", {}).get("valid_to") and is_unbounded_background_volatile_state(
            {
                "source": source,
                "metadata": normalized_metadata,
                "attribute": attribute,
                "value_text": value_text,
            }
        ):
            disabled_valid_to = str(temporal.get("valid_from") or temporal.get("observed_at") or now)
            temporal = merge_temporal(temporal, {"valid_to": disabled_valid_to})
            normalized_metadata["temporal"] = temporal
            normalized_metadata["background_current_authority"] = {
                "schema": "brainstack.background_current_authority.v1",
                "current_authority": "disabled_for_unbounded_volatile_background_state",
                "reason": "tier2_or_idle_window_source_without_explicit_valid_to",
            }
        valid_from = str(normalized_metadata.get("temporal", {}).get("valid_from") or now)
        valid_to = str(normalized_metadata.get("temporal", {}).get("valid_to") or "")
        current_candidates = self.conn.execute(
            """
            SELECT id, value_text, source, metadata_json, valid_from, valid_to
            FROM graph_states
            WHERE entity_id = ? AND attribute = ? AND is_current = 1
            ORDER BY valid_from DESC, id DESC
            """,
            (entity["id"], attribute),
        ).fetchall()
        new_scope_key = _principal_scope_key_from_metadata(normalized_metadata)
        current = None
        for candidate in current_candidates:
            candidate_scope_key = _principal_scope_key_from_metadata(_decode_json_object(candidate["metadata_json"]))
            if new_scope_key:
                if candidate_scope_key == new_scope_key:
                    current = candidate
                    break
                continue
            if not candidate_scope_key:
                current = candidate
                break
        if current is None and not new_scope_key and current_candidates:
            current = current_candidates[0]
        normalized_new = " ".join(value_text.lower().split())

        if current and " ".join(str(current["value_text"]).lower().split()) == normalized_new:
            merged = _merge_graph_record_metadata(
                current["metadata_json"],
                normalized_metadata,
                source=source,
                graph_kind="state",
            )
            merged_valid_to = str((merged.get("temporal") or {}).get("valid_to") or current["valid_to"] or "")
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ?, valid_to = ? WHERE id = ?",
                (
                    json.dumps(merged, ensure_ascii=True, sort_keys=True),
                    merged_valid_to or None,
                    int(current["id"]),
                ),
            )
            self.conn.commit()
            return {"status": "unchanged", "entity_id": entity["id"], "state_id": int(current["id"])}

        if current and not supersede and _should_auto_supersede_exact_value(current["value_text"], value_text):
            supersede = True
            normalized_metadata = _merge_record_metadata(
                None,
                {
                    **normalized_metadata,
                    "exact_value_update": True,
                    "status_reason": "numeric_exact_value_change",
                },
                source=source,
            )

        if current and not supersede:
            conflict = self.conn.execute(
                """
                SELECT id, metadata_json FROM graph_conflicts
                WHERE entity_id = ? AND attribute = ? AND current_state_id = ?
                  AND candidate_value_text = ? AND status = 'open'
                """,
                (entity["id"], attribute, int(current["id"]), value_text.strip()),
            ).fetchone()
            if conflict:
                merged = _merge_graph_record_metadata(
                    conflict["metadata_json"],
                    normalized_metadata,
                    source=source,
                    graph_kind="state_conflict",
                )
                self.conn.execute(
                    """
                    UPDATE graph_conflicts
                    SET metadata_json = ?, candidate_source = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(merged, ensure_ascii=True, sort_keys=True),
                        source,
                        now,
                        int(conflict["id"]),
                    ),
                )
                self.conn.commit()
                return {"status": "conflict", "entity_id": entity["id"], "conflict_id": int(conflict["id"])}
            conflict_metadata = _merge_graph_record_metadata(
                None,
                normalized_metadata,
                source=source,
                graph_kind="state_conflict",
            )
            cur = self.conn.execute(
                """
                INSERT INTO graph_conflicts (
                    entity_id, attribute, current_state_id, candidate_value_text,
                    candidate_source, metadata_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    entity["id"],
                    attribute,
                    int(current["id"]),
                    value_text.strip(),
                    source,
                    json.dumps(conflict_metadata, ensure_ascii=True, sort_keys=True),
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return {"status": "conflict", "entity_id": entity["id"], "conflict_id": _cursor_lastrowid(cur)}

        if current and supersede:
            prior_temporal = merge_temporal(
                _decode_json_object(current["metadata_json"]).get("temporal"),
                {"valid_to": valid_from},
            )
            prior_provenance = merge_provenance(
                _decode_json_object(current["metadata_json"]).get("provenance"),
                {"source_ids": [source]},
            )
            prior_metadata = _decode_json_object(current["metadata_json"])
            prior_metadata.setdefault("source_kind", "explicit")
            prior_metadata.setdefault("graph_kind", "state")
            if prior_temporal:
                prior_metadata["temporal"] = prior_temporal
            if prior_provenance:
                prior_metadata["provenance"] = prior_provenance
            prior_metadata = attach_graph_source_lineage(
                prior_metadata,
                source=source,
                graph_kind="state",
            )
            self.conn.execute(
                """
                UPDATE graph_states
                SET is_current = 0, valid_to = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    valid_from,
                    json.dumps(prior_metadata, ensure_ascii=True, sort_keys=True),
                    int(current["id"]),
                ),
            )

        state_metadata = _merge_graph_record_metadata(
            None,
            normalized_metadata,
            source=source,
            graph_kind="state",
        )
        cur = self.conn.execute(
            """
            INSERT INTO graph_states (
                entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                entity["id"],
                attribute,
                value_text.strip(),
                source,
                json.dumps(state_metadata, ensure_ascii=True, sort_keys=True),
                valid_from,
                valid_to or None,
            ),
        )
        new_state_id = _cursor_lastrowid(cur)

        if current and supersede:
            updated_prior_metadata = _decode_json_object(current["metadata_json"])
            updated_prior_metadata.setdefault("source_kind", "explicit")
            updated_prior_metadata.setdefault("graph_kind", "state")
            updated_prior_metadata["temporal"] = merge_temporal(
                updated_prior_metadata.get("temporal"),
                {"valid_to": valid_from, "superseded_by": str(new_state_id)},
            )
            updated_prior_metadata["provenance"] = merge_provenance(
                updated_prior_metadata.get("provenance"),
                {"source_ids": [source], "replacement_record_id": str(new_state_id)},
            )
            updated_prior_metadata = attach_graph_source_lineage(
                updated_prior_metadata,
                source=source,
                graph_kind="state",
            )
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(updated_prior_metadata, ensure_ascii=True, sort_keys=True),
                    int(current["id"]),
                ),
            )
            new_state_metadata = _merge_graph_record_metadata(
                state_metadata,
                {
                    "temporal": {"supersedes": str(current["id"]), "valid_from": valid_from},
                    "provenance": {"replacement_record_id": str(current["id"])},
                },
                source=source,
                graph_kind="state",
            )
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(new_state_metadata, ensure_ascii=True, sort_keys=True),
                    new_state_id,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO graph_supersessions (prior_state_id, new_state_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(current["id"]), new_state_id, "superseded_by_new_current_state", valid_from),
            )
            self.conn.commit()
            return {
                "status": "superseded",
                "entity_id": entity["id"],
                "state_id": new_state_id,
                "prior_state_id": int(current["id"]),
            }

        self.conn.commit()
        return {"status": "inserted", "entity_id": entity["id"], "state_id": new_state_id}

    @_locked
    def _sqlite_list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT gc.id, ge.canonical_name AS entity_name, gc.attribute, gs.value_text AS current_value,
                   gc.candidate_value_text, gc.status, gc.updated_at, gc.metadata_json
            FROM graph_conflicts gc
            JOIN graph_entities ge ON ge.id = gc.entity_id
            JOIN graph_states gs ON gs.id = gc.current_state_id
            WHERE gc.status = 'open'
            ORDER BY gc.updated_at DESC, gc.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
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

    @_locked
    def _sqlite_search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        patterns = build_like_tokens(query)
        if not patterns:
            raw_query = " ".join(str(query or "").split()).strip().lower()
            if not raw_query:
                return []
            patterns = [f"%{raw_query}%"]
        candidate_limit = max(limit * 8, 24)
        state_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gea.alias_name) LIKE ? OR lower(gs.value_text) LIKE ? OR lower(gs.attribute) LIKE ?"
            for _ in patterns
        )
        relation_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gea_subject.alias_name) LIKE ? OR lower(COALESCE(go.canonical_name, gr.object_text, '')) LIKE ? OR lower(gea_object.alias_name) LIKE ? OR lower(gr.predicate) LIKE ?"
            for _ in patterns
        )
        conflict_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gea.alias_name) LIKE ? OR lower(gc.attribute) LIKE ? OR lower(gc.candidate_value_text) LIKE ?"
            for _ in patterns
        )
        inferred_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gea_subject.alias_name) LIKE ? OR lower(COALESCE(go.canonical_name, gir.object_text, '')) LIKE ? OR lower(gea_object.alias_name) LIKE ? OR lower(gir.predicate) LIKE ?"
            for _ in patterns
        )
        params: List[Any] = []
        for pattern in patterns:
            params.extend([pattern, pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern, pattern, pattern])
        rows = self.conn.execute(
            f"""
            WITH state_hits AS (
                SELECT 'state' AS row_type,
                       gs.id AS row_id,
                       ge.canonical_name AS subject,
                       gs.attribute AS predicate,
                       gs.value_text AS object_value,
                       gs.is_current AS is_current,
                       gs.valid_from AS happened_at,
                       gs.valid_to AS valid_to,
                       gs.source AS source,
                       gs.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value,
                       COALESCE(gea.alias_name, '') AS matched_alias
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
                LEFT JOIN graph_entity_aliases gea ON gea.target_entity_id = ge.id
                WHERE {state_where}
            ),
            relation_hits AS (
                SELECT 'relation' AS row_type,
                       gr.id AS row_id,
                       ge.canonical_name AS subject,
                       gr.predicate AS predicate,
                       COALESCE(go.canonical_name, gr.object_text, '') AS object_value,
                       1 AS is_current,
                       gr.created_at AS happened_at,
                       '' AS valid_to,
                       gr.source AS source,
                       gr.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value,
                       COALESCE(gea_subject.alias_name, gea_object.alias_name, '') AS matched_alias
                FROM graph_relations gr
                JOIN graph_entities ge ON ge.id = gr.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
                LEFT JOIN graph_entity_aliases gea_subject ON gea_subject.target_entity_id = ge.id
                LEFT JOIN graph_entity_aliases gea_object ON gea_object.target_entity_id = go.id
                WHERE {relation_where}
            ),
            conflict_hits AS (
                SELECT 'conflict' AS row_type,
                       gc.id AS row_id,
                       ge.canonical_name AS subject,
                       gc.attribute AS predicate,
                       gs.value_text AS object_value,
                       1 AS is_current,
                       gc.updated_at AS happened_at,
                       '' AS valid_to,
                       gs.source AS source,
                       gs.metadata_json AS metadata_json,
                       gc.metadata_json AS conflict_metadata_json,
                       gc.candidate_source AS conflict_source,
                       gc.candidate_value_text AS conflict_value,
                       COALESCE(gea.alias_name, '') AS matched_alias
                FROM graph_conflicts gc
                JOIN graph_entities ge ON ge.id = gc.entity_id
                JOIN graph_states gs ON gs.id = gc.current_state_id
                LEFT JOIN graph_entity_aliases gea ON gea.target_entity_id = ge.id
                WHERE gc.status = 'open'
                  AND ({conflict_where})
            ),
            inferred_relation_hits AS (
                SELECT 'inferred_relation' AS row_type,
                       gir.id AS row_id,
                       ge.canonical_name AS subject,
                       gir.predicate AS predicate,
                       COALESCE(go.canonical_name, gir.object_text, '') AS object_value,
                       1 AS is_current,
                       gir.updated_at AS happened_at,
                       '' AS valid_to,
                       gir.source AS source,
                       gir.metadata_json AS metadata_json,
                       '' AS conflict_metadata_json,
                       '' AS conflict_source,
                       '' AS conflict_value,
                       COALESCE(gea_subject.alias_name, gea_object.alias_name, '') AS matched_alias
                FROM graph_inferred_relations gir
                JOIN graph_entities ge ON ge.id = gir.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gir.object_entity_id
                LEFT JOIN graph_entity_aliases gea_subject ON gea_subject.target_entity_id = ge.id
                LEFT JOIN graph_entity_aliases gea_object ON gea_object.target_entity_id = go.id
                WHERE gir.active = 1
                  AND ({inferred_where})
            )
            SELECT * FROM (
                SELECT * FROM state_hits
                UNION ALL
                SELECT * FROM relation_hits
                UNION ALL
                SELECT * FROM conflict_hits
                UNION ALL
                SELECT * FROM inferred_relation_hits
            )
            ORDER BY happened_at DESC
            LIMIT ?
            """,
            tuple(params + [candidate_limit]),
        ).fetchall()
        parsed = _attach_keyword_scores(_row_to_dict(row) for row in rows)
        token_fragments = [pattern.strip("%").lower() for pattern in patterns if pattern.strip("%")]
        deduped: Dict[tuple[str, int], Dict[str, Any]] = {}
        for item in parsed:
            matched_alias = str(item.get("matched_alias") or "").strip()
            if matched_alias and not any(fragment in matched_alias.lower() for fragment in token_fragments):
                item["matched_alias"] = ""
            row_key = (str(item.get("row_type") or ""), int(item.get("row_id") or 0))
            existing = deduped.get(row_key)
            if existing is None:
                deduped[row_key] = item
                continue
            if str(item.get("matched_alias") or "").strip() and not str(existing.get("matched_alias") or "").strip():
                deduped[row_key] = item
        parsed = list(deduped.values())
        for item in parsed:
            field_score = _graph_structured_field_match_score(item, query=query)
            if field_score:
                item["_brainstack_graph_field_match_score"] = field_score
                item["keyword_score"] = max(float(item.get("keyword_score") or 0.0), field_score)
        parsed = [item for item in parsed if _graph_sort_key(item)[0] > 0]
        parsed.sort(key=_graph_sort_key, reverse=True)
        return parsed[:limit]

    @_locked
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

    @_locked
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

    @_locked
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

    @_locked
    def upsert_graph_state(
        self,
        *,
        subject_name: str,
        attribute: str,
        value_text: str,
        source: str,
        supersede: bool = False,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        outcome = self._sqlite_upsert_graph_state(
            subject_name=subject_name,
            attribute=attribute,
            value_text=value_text,
            source=source,
            supersede=supersede,
            metadata=metadata,
        )
        if self._graph_backend is not None and int(outcome.get("entity_id") or 0) > 0:
            self._publish_entity_subgraph(int(outcome["entity_id"]))
        self._refresh_semantic_evidence_shelf(
            shelf="graph",
            metadata=metadata,
        )
        return outcome

    @_locked
    def upsert_typed_entity(
        self,
        *,
        entity_name: str,
        entity_type: str,
        subject_name: str,
        attributes: Mapping[str, Any],
        source: str,
        metadata: Dict[str, Any] | None = None,
        confidence: float = 0.78,
        supersede_existing: bool = False,
    ) -> List[Dict[str, Any]]:
        normalized_entity_name = " ".join(str(entity_name or "").strip().split())
        normalized_entity_type = " ".join(str(entity_type or "").strip().lower().split())
        normalized_subject_name = " ".join(str(subject_name or "").strip().split()) or "User"
        if not normalized_entity_name or not normalized_entity_type:
            return []

        base_metadata = dict(metadata or {})
        base_metadata.setdefault("confidence", float(confidence))
        actions: List[Dict[str, Any]] = []
        state_candidates: List[tuple[str, str]] = [
            ("entity_type", normalized_entity_type),
            ("owner_subject", normalized_subject_name),
        ]
        for attribute, value in dict(attributes or {}).items():
            normalized_attribute = " ".join(str(attribute or "").strip().lower().split())
            normalized_value = " ".join(str(value or "").strip().split())
            if not normalized_attribute or not normalized_value:
                continue
            state_candidates.append((normalized_attribute, normalized_value))

        for attribute, value_text in state_candidates:
            outcome = self.upsert_graph_state(
                subject_name=normalized_entity_name,
                attribute=attribute,
                value_text=value_text,
                source=source,
                supersede=supersede_existing,
                metadata=base_metadata,
            )
            actions.append(
                {
                    "kind": "typed_entity",
                    "entity_name": normalized_entity_name,
                    "entity_type": normalized_entity_type,
                    "attribute": attribute,
                    "action": "NONE" if str(outcome.get("status", "")).lower() in {"unchanged", "shadowed"} else "ADD",
                    **outcome,
                }
            )
        return actions

    @_locked
    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        if self._graph_backend is None:
            return self._sqlite_list_graph_conflicts(limit=limit)
        try:
            rows = self._graph_backend.list_graph_conflicts(limit=limit)
        except Exception as exc:
            self._disable_graph_backend(reason=str(exc))
            logger.warning("Brainstack graph conflict lookup failed; falling back to SQLite: %s", exc)
            return self._sqlite_list_graph_conflicts(limit=limit)
        self._graph_backend_error = ""
        return rows

    @_locked
    def search_graph(self, *, query: str, limit: int, principal_scope_key: str = "") -> List[Dict[str, Any]]:
        external_requested = self._graph_backend_name not in {"", "none", "sqlite"}
        retrieval_source = "graph.sqlite_lexical"
        match_mode = "sqlite_lexical"
        backend_status = "degraded" if external_requested and self._graph_backend is None else "active"
        fallback_reason = str(self._graph_backend_error or "") if backend_status == "degraded" else ""
        if self._graph_backend is None:
            rows = self._sqlite_search_graph(query=query, limit=limit)
        else:
            try:
                rows = self._graph_backend.search_graph(query=query, limit=max(limit * 8, 24))
            except Exception as exc:
                self._disable_graph_backend(reason=str(exc))
                logger.warning("Brainstack graph search failed; falling back to SQLite: %s", exc)
                rows = self._sqlite_search_graph(query=query, limit=limit)
                backend_status = "degraded"
                fallback_reason = str(exc)
            else:
                self._graph_backend_error = ""
                retrieval_source = f"graph.{getattr(self._graph_backend, 'target_name', '') or self._graph_backend_name}"
                match_mode = "external_graph"
                backend_status = "active"
                fallback_reason = ""
        keyword_rows = _attach_keyword_scores(rows)
        scored: List[Dict[str, Any]] = []
        for row in keyword_rows:
            item = dict(row)
            if str(item.get("row_type") or "") == "conflict":
                conflict_scope_key = _principal_scope_key_from_metadata(item.get("conflict_metadata"))
                if principal_scope_key and conflict_scope_key and conflict_scope_key != principal_scope_key:
                    continue
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            item.setdefault("retrieval_source", retrieval_source)
            item.setdefault("match_mode", "alias_lexical" if str(item.get("matched_alias") or "").strip() else match_mode)
            item.setdefault("graph_backend_requested", self._graph_backend_name)
            item.setdefault("graph_backend_status", backend_status)
            item.setdefault("graph_fallback_reason", fallback_reason)
            if _graph_sort_key(item)[0] <= 0:
                continue
            scored.append(item)
        scored.sort(key=_graph_sort_key, reverse=True)
        return scored[:limit]

    @_locked
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
