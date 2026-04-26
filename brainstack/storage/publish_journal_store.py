from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    List,
    TRANSCRIPT_HYGIENE_MARKERS,
    _env_truthy,
    _locked,
    _row_to_dict,
    json,
    logger,
    utc_now_iso,
)

class PublishJournalStoreMixin(StoreRuntimeBase):
    def _bootstrap_graph_backend_if_needed(self) -> None:
        if self._graph_backend is None or not self._graph_backend.is_empty():
            return
        entity_ids = [
            int(row["id"])
            for row in self.conn.execute("SELECT id FROM graph_entities ORDER BY id ASC").fetchall()
        ]
        for entity_id in entity_ids:
            self._publish_entity_subgraph(entity_id)

    def _bootstrap_corpus_backend_if_needed(self) -> None:
        if self._corpus_backend is None or not self._corpus_backend.is_empty():
            return
        document_ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM corpus_documents WHERE active = 1 ORDER BY updated_at ASC, id ASC"
            ).fetchall()
        ]
        for document_id in document_ids:
            self._publish_corpus_document(document_id)
        transcript_ids = [
            int(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM transcript_entries ORDER BY created_at ASC, id ASC"
            ).fetchall()
        ]
        for transcript_id in transcript_ids:
            self._publish_conversation_transcript(transcript_id, raise_on_error=False)

    def _replay_corpus_publications_if_needed(self) -> None:
        if self._corpus_backend is None:
            return
        statuses = ["pending"]
        if _env_truthy("BRAINSTACK_REPLAY_FAILED_PUBLICATIONS_ON_OPEN", default=False):
            statuses.append("failed")
        placeholders = ", ".join("?" for _ in statuses)
        pending = self.conn.execute(
            f"""
            SELECT object_kind, object_key
            FROM publish_journal
            WHERE target_name = ? AND object_kind IN ('corpus_document', 'conversation_transcript') AND status IN ({placeholders})
            ORDER BY updated_at ASC, id ASC
            """,
            (self._corpus_backend.target_name, *statuses),
        ).fetchall()
        seen: set[tuple[str, str]] = set()
        for row in pending:
            object_kind = str(row["object_kind"] or "").strip()
            object_key = str(row["object_key"] or "").strip()
            composite = (object_kind, object_key)
            if not object_kind or not object_key or composite in seen:
                continue
            seen.add(composite)
            if object_kind == "corpus_document":
                document = self.conn.execute(
                    "SELECT id FROM corpus_documents WHERE stable_key = ? AND active = 1",
                    (object_key,),
                ).fetchone()
                if document:
                    self._publish_corpus_document(int(document["id"]))
                continue
            if object_kind == "conversation_transcript":
                transcript_id = self._parse_conversation_object_key(object_key)
                if transcript_id is None:
                    continue
                transcript_row = self.conn.execute(
                    "SELECT id FROM transcript_entries WHERE id = ?",
                    (transcript_id,),
                ).fetchone()
                if transcript_row:
                    self._publish_conversation_transcript(transcript_id, raise_on_error=False)

    def _upsert_publish_journal(
        self,
        *,
        target_name: str,
        object_kind: str,
        object_key: str,
        payload: Dict[str, Any],
        status: str = "pending",
        last_error: str = "",
        published: bool = False,
    ) -> None:
        now = utc_now_iso()
        published_at = now if published else None
        existing = self.conn.execute(
            """
            SELECT id, attempt_count FROM publish_journal
            WHERE target_name = ? AND object_kind = ? AND object_key = ?
            """,
            (target_name, object_kind, object_key),
        ).fetchone()
        payload_json = json.dumps(payload, ensure_ascii=True, sort_keys=True)
        if existing:
            attempt_count = int(existing["attempt_count"] or 0)
            self.conn.execute(
                """
                UPDATE publish_journal
                SET payload_json = ?, status = ?, last_error = ?, updated_at = ?, published_at = ?,
                    attempt_count = CASE WHEN ? = 'failed' THEN ? + 1 ELSE attempt_count END
                WHERE id = ?
                """,
                (
                    payload_json,
                    status,
                    last_error,
                    now,
                    published_at,
                    status,
                    attempt_count,
                    int(existing["id"]),
                ),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO publish_journal (
                    target_name, object_kind, object_key, payload_json, status,
                    attempt_count, last_error, created_at, updated_at, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_name,
                    object_kind,
                    object_key,
                    payload_json,
                    status,
                    0 if status != "failed" else 1,
                    last_error,
                    now,
                    now,
                    published_at,
                ),
            )
        self.conn.commit()

    def _conversation_semantic_object_key(self, transcript_id: int) -> str:
        return f"transcript:{int(transcript_id)}"

    def _conversation_document_stable_key(self, *, session_id: str, turn_number: int, transcript_id: int) -> str:
        return f"conversation:{str(session_id or '').strip()}:{int(turn_number)}:{int(transcript_id)}"

    def _parse_conversation_object_key(self, object_key: str) -> int | None:
        text = str(object_key or "").strip()
        if not text.startswith("transcript:"):
            return None
        try:
            return int(text.split(":", 1)[1])
        except (TypeError, ValueError):
            return None

    def _conversation_transcript_snapshot(self, transcript_id: int) -> Dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            WHERE id = ?
            """,
            (transcript_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Transcript entry {transcript_id} is missing")
        item = _row_to_dict(row)
        metadata = dict(item.get("metadata") or {})
        stable_key = (
            self._conversation_document_stable_key(
                session_id=str(item.get("session_id") or ""),
                turn_number=int(item.get("turn_number") or 0),
                transcript_id=int(item["id"]),
            )
        )
        document = {
            "id": int(item["id"]),
            "stable_key": stable_key,
            "title": f"Conversation turn {int(item.get('turn_number') or 0)}",
            "doc_kind": "conversation",
            "source": str(item.get("source") or ""),
            "updated_at": str(item.get("created_at") or ""),
            "semantic_class": "conversation",
            "metadata": {
                **metadata,
                "semantic_class": "conversation",
                "session_id": str(item.get("session_id") or ""),
                "turn_number": int(item.get("turn_number") or 0),
                "record_kind": str(item.get("kind") or "turn"),
                "transcript_id": int(item["id"]),
                "created_at": str(item.get("created_at") or ""),
            },
        }
        sections = [
            {
                "section_id": int(item["id"]),
                "section_index": 0,
                "heading": str(item.get("kind") or "turn"),
                "content": str(item.get("content") or ""),
                "token_estimate": max(1, len(str(item.get("content") or "")) // 4),
                "metadata": {
                    **metadata,
                    "semantic_class": "conversation",
                    "session_id": str(item.get("session_id") or ""),
                    "turn_number": int(item.get("turn_number") or 0),
                    "record_kind": str(item.get("kind") or "turn"),
                    "transcript_id": int(item["id"]),
                    "created_at": str(item.get("created_at") or ""),
                },
            }
        ]
        return {"document": document, "sections": sections}

    def _publish_semantic_snapshot(
        self,
        *,
        object_kind: str,
        object_key: str,
        snapshot: Dict[str, Any],
        raise_on_error: bool,
    ) -> None:
        if self._corpus_backend is None:
            return
        target_name = self._corpus_backend.target_name
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind=object_kind,
            object_key=object_key,
            payload=snapshot,
            status="pending",
        )
        try:
            self._corpus_backend.publish_document(snapshot)
        except Exception as exc:
            self._corpus_backend_error = str(exc)
            self._upsert_publish_journal(
                target_name=target_name,
                object_kind=object_kind,
                object_key=object_key,
                payload=snapshot,
                status="failed",
                last_error=self._corpus_backend_error,
            )
            if raise_on_error:
                raise
            logger.warning(
                "Brainstack semantic publication failed for %s %s: %s",
                object_kind,
                object_key,
                exc,
            )
            return
        self._corpus_backend_error = ""
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind=object_kind,
            object_key=object_key,
            payload=snapshot,
            status="published",
            published=True,
        )

    def _publish_conversation_transcript(self, transcript_id: int, *, raise_on_error: bool) -> None:
        snapshot = self._conversation_transcript_snapshot(transcript_id)
        self._publish_semantic_snapshot(
            object_kind="conversation_transcript",
            object_key=self._conversation_semantic_object_key(transcript_id),
            snapshot=snapshot,
            raise_on_error=raise_on_error,
        )

    @_locked
    def list_publish_journal(self, *, target_name: str | None = None, status: str | None = None, limit: int = 100) -> List[Dict[str, Any]]:
        where: List[str] = []
        params: List[Any] = []
        if target_name:
            where.append("target_name = ?")
            params.append(target_name)
        if status:
            where.append("status = ?")
            params.append(status)
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.conn.execute(
            f"""
            SELECT id, target_name, object_kind, object_key, payload_json, status,
                   attempt_count, last_error, created_at, updated_at, published_at
            FROM publish_journal
            {where_clause}
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            tuple(params + [limit]),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def scrub_transcript_hygiene_residue(self) -> Dict[str, Any]:
        patterns = [f"%{marker}%" for marker in TRANSCRIPT_HYGIENE_MARKERS]
        if not patterns:
            return {"deleted_transcript_rows": 0, "deleted_publish_journal_rows": 0, "deleted_corpus_snapshots": 0, "deleted_ids": []}

        where = " OR ".join("content LIKE ?" for _ in patterns)
        rows = self.conn.execute(
            f"""
            SELECT id, session_id, turn_number
            FROM transcript_entries
            WHERE {where}
            ORDER BY id ASC
            """,
            tuple(patterns),
        ).fetchall()
        if not rows:
            return {"deleted_transcript_rows": 0, "deleted_publish_journal_rows": 0, "deleted_corpus_snapshots": 0, "deleted_ids": []}

        deleted_publish_journal_rows = 0
        deleted_corpus_snapshots = 0
        deleted_ids: List[int] = []
        for row in rows:
            transcript_id = int(row["id"])
            session_id = str(row["session_id"] or "")
            turn_number = int(row["turn_number"] or 0)
            stable_key = self._conversation_document_stable_key(
                session_id=session_id,
                turn_number=turn_number,
                transcript_id=transcript_id,
            )
            if self._corpus_backend is not None:
                self._corpus_backend.publish_document(
                    {
                        "document": {"stable_key": stable_key},
                        "sections": [],
                    }
                )
                deleted_corpus_snapshots += 1
            object_key = self._conversation_semantic_object_key(transcript_id)
            deleted_publish_journal_rows += int(
                self.conn.execute(
                    """
                    DELETE FROM publish_journal
                    WHERE object_kind = 'conversation_transcript' AND object_key = ?
                    """,
                    (object_key,),
                ).rowcount
                or 0
            )
            self.conn.execute("DELETE FROM transcript_fts WHERE rowid = ?", (transcript_id,))
            self.conn.execute("DELETE FROM transcript_entries WHERE id = ?", (transcript_id,))
            deleted_ids.append(transcript_id)

        self.conn.commit()
        return {
            "deleted_transcript_rows": len(deleted_ids),
            "deleted_publish_journal_rows": deleted_publish_journal_rows,
            "deleted_corpus_snapshots": deleted_corpus_snapshots,
            "deleted_ids": deleted_ids,
        }

    def _entity_snapshot(self, entity_id: int) -> Dict[str, Any]:
        entity_row = self.conn.execute(
            """
            SELECT id, canonical_name, normalized_name, COALESCE(updated_at, created_at) AS updated_at
            FROM graph_entities
            WHERE id = ?
            """,
            (entity_id,),
        ).fetchone()
        if not entity_row:
            raise RuntimeError(f"Missing graph entity for snapshot: {entity_id}")
        entity = dict(entity_row)

        alias_rows = self.conn.execute(
            """
            SELECT alias_name, normalized_alias, source, metadata_json, updated_at
            FROM graph_entity_aliases
            WHERE target_entity_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (entity_id,),
        ).fetchall()
        aliases = [_row_to_dict(row) for row in alias_rows]

        state_rows = self.conn.execute(
            """
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
                   1 AS active
            FROM graph_states gs
            JOIN graph_entities ge ON ge.id = gs.entity_id
            WHERE gs.entity_id = ?
            ORDER BY gs.valid_from DESC, gs.id DESC
            """,
            (entity_id,),
        ).fetchall()
        states = [_row_to_dict(row) for row in state_rows]

        conflict_rows = self.conn.execute(
            """
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
                   1 AS active,
                   gc.current_state_id AS current_state_id
            FROM graph_conflicts gc
            JOIN graph_entities ge ON ge.id = gc.entity_id
            JOIN graph_states gs ON gs.id = gc.current_state_id
            WHERE gc.entity_id = ? AND gc.status = 'open'
            ORDER BY gc.updated_at DESC, gc.id DESC
            """,
            (entity_id,),
        ).fetchall()
        conflicts = [_row_to_dict(row) for row in conflict_rows]

        relation_rows = self.conn.execute(
            """
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
                   gr.active AS active,
                   go.id AS object_entity_id,
                   go.canonical_name AS object_canonical_name,
                   go.normalized_name AS object_normalized_name
            FROM graph_relations gr
            JOIN graph_entities ge ON ge.id = gr.subject_entity_id
            LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
            WHERE gr.subject_entity_id = ?
            ORDER BY gr.created_at DESC, gr.id DESC
            """,
            (entity_id,),
        ).fetchall()
        relations = []
        for row in relation_rows:
            item = _row_to_dict(row)
            item["object_entity"] = {
                "id": int(item.pop("object_entity_id") or 0),
                "canonical_name": str(item.pop("object_canonical_name") or item.get("object_value") or ""),
                "normalized_name": str(item.pop("object_normalized_name") or ""),
                "updated_at": "",
            }
            relations.append(item)

        inferred_rows = self.conn.execute(
            """
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
                   gir.active AS active,
                   go.id AS object_entity_id,
                   go.canonical_name AS object_canonical_name,
                   go.normalized_name AS object_normalized_name
            FROM graph_inferred_relations gir
            JOIN graph_entities ge ON ge.id = gir.subject_entity_id
            LEFT JOIN graph_entities go ON go.id = gir.object_entity_id
            WHERE gir.subject_entity_id = ?
            ORDER BY gir.updated_at DESC, gir.id DESC
            """,
            (entity_id,),
        ).fetchall()
        inferred_relations = []
        for row in inferred_rows:
            item = _row_to_dict(row)
            item["object_entity"] = {
                "id": int(item.pop("object_entity_id") or 0),
                "canonical_name": str(item.pop("object_canonical_name") or item.get("object_value") or ""),
                "normalized_name": str(item.pop("object_normalized_name") or ""),
                "updated_at": "",
            }
            inferred_relations.append(item)

        return {
            "entity": entity,
            "aliases": aliases,
            "states": states,
            "conflicts": conflicts,
            "relations": relations,
            "inferred_relations": inferred_relations,
        }

    def _publish_entity_subgraph(self, entity_id: int) -> None:
        if self._graph_backend is None:
            return
        snapshot = self._entity_snapshot(entity_id)
        target_name = self._graph_backend.target_name
        object_key = str(entity_id)
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind="entity_subgraph",
            object_key=object_key,
            payload=snapshot,
            status="pending",
        )
        try:
            self._graph_backend.publish_entity_subgraph(snapshot)
        except Exception as exc:
            self._upsert_publish_journal(
                target_name=target_name,
                object_kind="entity_subgraph",
                object_key=object_key,
                payload=snapshot,
                status="failed",
                last_error=str(exc),
            )
            logger.warning(
                "Brainstack graph publish failed; disabling graph backend and continuing with SQLite: %s",
                exc,
            )
            self._disable_graph_backend(reason=str(exc))
            return
        self._upsert_publish_journal(
            target_name=target_name,
            object_kind="entity_subgraph",
            object_key=object_key,
            payload=snapshot,
            status="published",
            published=True,
        )

    def _corpus_document_snapshot(self, document_id: int) -> Dict[str, Any]:
        document_row = self.conn.execute(
            """
            SELECT id, stable_key, title, doc_kind, source, metadata_json, updated_at, active
            FROM corpus_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        if not document_row:
            raise RuntimeError(f"Missing corpus document for snapshot: {document_id}")
        document = _row_to_dict(document_row)
        if not bool(document.get("active")):
            return {"document": document, "sections": []}
        section_rows = self.conn.execute(
            """
            SELECT
                id AS section_id,
                section_index,
                heading,
                content,
                token_estimate,
                metadata_json
            FROM corpus_sections
            WHERE document_id = ?
            ORDER BY section_index ASC, id ASC
            """,
            (document_id,),
        ).fetchall()
        sections = [_row_to_dict(row) for row in section_rows]
        return {"document": document, "sections": sections}

    def _publish_corpus_document(self, document_id: int) -> None:
        if self._corpus_backend is None:
            return
        snapshot = self._corpus_document_snapshot(document_id)
        document = dict(snapshot.get("document") or {})
        object_key = str(document.get("stable_key") or "").strip()
        if not object_key:
            raise RuntimeError(f"Corpus snapshot missing stable_key for document {document_id}")
        self._publish_semantic_snapshot(
            object_kind="corpus_document",
            object_key=object_key,
            snapshot=snapshot,
            raise_on_error=True,
        )
