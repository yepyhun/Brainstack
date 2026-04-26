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
    _corpus_search_row_to_dict,
    _decode_json_array,
    _decode_json_object,
    _locked,
    _operating_row_to_dict,
    _principal_scope_key_from_metadata,
    _profile_row_to_dict,
    _row_to_dict,
    _task_row_to_dict,
    _volatile_operating_semantic_match,
    build_fts_query,
    build_like_tokens,
    decode_semantic_metadata,
    hashlib,
    json,
    logger,
    normalize_semantic_terms,
    record_is_effective_at,
    semantic_evidence_fingerprint,
    semantic_similarity,
    sqlite3,
    utc_now_iso,
)

class SemanticIndexStoreMixin(StoreRuntimeBase):
    @_locked
    def search_corpus(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if fts_query:
            try:
                rows = self.conn.execute(
                    """
                    SELECT
                        cd.id AS document_id,
                        cd.stable_key,
                        cd.title,
                        cd.doc_kind,
                        cd.source,
                        cd.metadata_json AS document_metadata_json,
                        cs.id AS section_id,
                        cs.section_index,
                        cs.heading,
                        cs.content,
                        cs.token_estimate,
                        cs.metadata_json AS section_metadata_json
                    FROM corpus_section_fts fts
                    JOIN corpus_sections cs ON cs.id = fts.rowid
                    JOIN corpus_documents cd ON cd.id = cs.document_id
                    WHERE corpus_section_fts MATCH ? AND cd.active = 1
                    ORDER BY bm25(corpus_section_fts), cs.token_estimate ASC, cs.id DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                output = [_corpus_search_row_to_dict(row) for row in rows]
                for row in output:
                    row["retrieval_source"] = "corpus.keyword"
                    row["match_mode"] = "keyword"
                return output
            except sqlite3.OperationalError:
                pass

        patterns = build_like_tokens(query)
        if not patterns:
            return []
        title_where = " OR ".join("lower(cd.title) LIKE ?" for _ in patterns)
        heading_where = " OR ".join("lower(cs.heading) LIKE ?" for _ in patterns)
        content_where = " OR ".join("lower(cs.content) LIKE ?" for _ in patterns)
        rows = self.conn.execute(
            f"""
            SELECT
                cd.id AS document_id,
                cd.stable_key,
                cd.title,
                cd.doc_kind,
                cd.source,
                cd.metadata_json AS document_metadata_json,
                cs.id AS section_id,
                cs.section_index,
                cs.heading,
                cs.content,
                cs.token_estimate,
                cs.metadata_json AS section_metadata_json
            FROM corpus_sections cs
            JOIN corpus_documents cd ON cd.id = cs.document_id
            WHERE cd.active = 1
              AND (
                {title_where} OR
                {heading_where} OR
                {content_where}
              )
            ORDER BY cd.updated_at DESC, cs.section_index ASC
            LIMIT ?
            """,
            tuple(patterns + patterns + patterns + [limit]),
        ).fetchall()
        output = [_corpus_search_row_to_dict(row) for row in rows]
        for row in output:
            row["retrieval_source"] = "corpus.keyword"
            row["match_mode"] = "keyword"
        return output

    @_locked
    def search_corpus_semantic(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        if self._corpus_backend is None:
            return []
        return self._search_semantic_backend(
            query=query,
            limit=limit,
            where={"semantic_class": "corpus"},
        )

    def _search_semantic_backend(
        self,
        *,
        query: str,
        limit: int,
        where: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        if self._corpus_backend is None:
            return []
        try:
            rows = self._corpus_backend.search_semantic(query=query, limit=limit, where=where)
        except Exception as exc:
            self._corpus_backend_error = str(exc)
            logger.warning("Brainstack corpus semantic search failed: %s", exc)
            return []
        self._corpus_backend_error = ""
        return rows

    @_locked
    def search_conversation_semantic(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        rows = self._search_semantic_backend(
            query=query,
            limit=max(limit * 4, 8),
            where={"semantic_class": "conversation"},
        )
        output: List[Dict[str, Any]] = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            document_meta = dict(metadata.get("document") or {})
            transcript_id = int(document_meta.get("transcript_id") or row.get("section_id") or 0)
            if transcript_id <= 0:
                continue
            created_at = str(document_meta.get("created_at") or "")
            item = {
                "id": transcript_id,
                "session_id": str(document_meta.get("session_id") or ""),
                "turn_number": int(document_meta.get("turn_number") or 0),
                "kind": str(document_meta.get("record_kind") or "turn"),
                "content": str(row.get("content") or ""),
                "source": str(row.get("source") or ""),
                "metadata": {
                    **metadata,
                    "semantic_class": "conversation",
                    "transcript_id": transcript_id,
                },
                "created_at": created_at,
                "same_session": str(document_meta.get("session_id") or "") == session_id,
                "semantic_score": float(row.get("semantic_score") or 0.0),
                "keyword_score": 0.0,
                "retrieval_source": "conversation.semantic",
                "match_mode": "semantic",
            }
            if not _annotate_principal_scope(
                item,
                principal_scope_key=principal_scope_key,
                session_id=session_id,
                allow_personal_scope_fallback=False,
            ):
                continue
            output.append(item)
        output.sort(
            key=lambda item: (
                float(item.get("semantic_score") or 0.0),
                1 if item["same_session"] else 0,
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return output[:limit]

    def _upsert_semantic_evidence_document(
        self,
        *,
        evidence_key: str,
        shelf: str,
        row_id: int,
        stable_key: str,
        principal_scope_key: str,
        source: str,
        content: str,
        metadata: Mapping[str, Any] | None,
        source_updated_at: str,
    ) -> None:
        normalized_metadata = dict(metadata or {})
        authority_class = str(normalized_metadata.get("authority_class") or shelf).strip()
        provenance_class = str(normalized_metadata.get("provenance_class") or normalized_metadata.get("source_kind") or source).strip()
        terms = normalize_semantic_terms(
            shelf,
            stable_key,
            authority_class,
            content,
            *decode_semantic_metadata(normalized_metadata),
        )
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO semantic_evidence_index (
                evidence_key, shelf, row_id, stable_key, principal_scope_key, source,
                authority_class, provenance_class, content_excerpt, normalized_text,
                terms_json, source_updated_at, fingerprint, index_version, active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(evidence_key) DO UPDATE SET
                shelf = excluded.shelf,
                row_id = excluded.row_id,
                stable_key = excluded.stable_key,
                principal_scope_key = excluded.principal_scope_key,
                source = excluded.source,
                authority_class = excluded.authority_class,
                provenance_class = excluded.provenance_class,
                content_excerpt = excluded.content_excerpt,
                normalized_text = excluded.normalized_text,
                terms_json = excluded.terms_json,
                source_updated_at = excluded.source_updated_at,
                fingerprint = excluded.fingerprint,
                index_version = excluded.index_version,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (
                evidence_key,
                shelf,
                int(row_id or 0),
                str(stable_key or "").strip(),
                str(principal_scope_key or "").strip(),
                str(source or "").strip(),
                authority_class,
                provenance_class,
                str(content or "").strip()[:900],
                " ".join(terms),
                json.dumps(terms, ensure_ascii=True, sort_keys=True),
                str(source_updated_at or "").strip(),
                semantic_evidence_fingerprint(),
                SEMANTIC_EVIDENCE_INDEX_VERSION,
                now,
                now,
            ),
        )

    def _refresh_semantic_evidence_shelf(
        self,
        *,
        shelf: str,
        principal_scope_key: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        index_shelf = "continuity_match" if str(shelf or "").strip() == "continuity" else str(shelf or "").strip()
        scope_key = str(principal_scope_key or "").strip() or _principal_scope_key_from_metadata(metadata)
        try:
            self.rebuild_semantic_evidence_index(
                principal_scope_key=scope_key,
                shelves=(index_shelf,),
            )
        except Exception as exc:
            logger.warning("Brainstack semantic evidence refresh failed for shelf %s: %s", index_shelf, exc)

    @_locked
    def rebuild_semantic_evidence_index(
        self,
        *,
        principal_scope_key: str = "",
        shelves: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        requested_scope_key = str(principal_scope_key or "").strip()
        shelf_filter = {str(shelf or "").strip() for shelf in (shelves or ()) if str(shelf or "").strip()}
        if shelf_filter:
            params: List[Any] = list(sorted(shelf_filter))
            sql = f"DELETE FROM semantic_evidence_index WHERE shelf IN ({','.join('?' for _ in shelf_filter)})"
            if requested_scope_key:
                sql += " AND principal_scope_key IN ('', ?)"
                params.append(requested_scope_key)
            self.conn.execute(sql, tuple(params))
        else:
            self.conn.execute("DELETE FROM semantic_evidence_index")

        counts: Dict[str, int] = {}

        def include_scope(scope_key: str) -> bool:
            normalized = str(scope_key or "").strip()
            return not requested_scope_key or normalized in {"", requested_scope_key}

        def bump(shelf: str) -> None:
            counts[shelf] = counts.get(shelf, 0) + 1

        if not shelf_filter or "profile" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
                FROM profile_items
                WHERE active = 1
                """
            ).fetchall():
                item = _profile_row_to_dict(row)
                if not include_scope(str(item.get("principal_scope_key") or "")):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"profile:{item.get('stable_key') or item.get('id')}",
                    shelf="profile",
                    row_id=int(item.get("id") or 0),
                    stable_key=str(item.get("stable_key") or ""),
                    principal_scope_key=str(item.get("principal_scope_key") or ""),
                    source=str(item.get("source") or ""),
                    content=f"{item.get('category') or ''} {item.get('content') or ''}",
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {},
                    source_updated_at=str(item.get("updated_at") or ""),
                )
                bump("profile")

        if not shelf_filter or "task" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT id, stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                       optional, status, owner, source, source_session_id, source_turn_number,
                       metadata_json, created_at, updated_at
                FROM task_items
                """
            ).fetchall():
                item = _task_row_to_dict(row)
                if not include_scope(str(item.get("principal_scope_key") or "")):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"task:{item.get('stable_key') or item.get('id')}",
                    shelf="task",
                    row_id=int(item.get("id") or 0),
                    stable_key=str(item.get("stable_key") or ""),
                    principal_scope_key=str(item.get("principal_scope_key") or ""),
                    source=str(item.get("source") or ""),
                    content=f"{item.get('item_type') or ''} {item.get('title') or ''} {item.get('due_date') or ''} {item.get('status') or ''}",
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {},
                    source_updated_at=str(item.get("updated_at") or ""),
                )
                bump("task")

        if not shelf_filter or "operating" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT id, stable_key, principal_scope_key, record_type, content, owner, source,
                       source_session_id, source_turn_number, metadata_json, created_at, updated_at
                FROM operating_records
                """
            ).fetchall():
                item = _operating_row_to_dict(row)
                if not include_scope(str(item.get("principal_scope_key") or "")):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"operating:{item.get('stable_key') or item.get('id')}",
                    shelf="operating",
                    row_id=int(item.get("id") or 0),
                    stable_key=str(item.get("stable_key") or ""),
                    principal_scope_key=str(item.get("principal_scope_key") or ""),
                    source=str(item.get("source") or ""),
                    content=f"{item.get('record_type') or ''} {item.get('content') or ''}",
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {},
                    source_updated_at=str(item.get("updated_at") or ""),
                )
                bump("operating")

        if not shelf_filter or "corpus" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT cd.id AS document_id, cd.stable_key, cd.title, cd.doc_kind, cd.source,
                       cd.metadata_json AS document_metadata_json, cd.updated_at,
                       cs.id AS section_id, cs.section_index, cs.heading, cs.content,
                       cs.metadata_json AS section_metadata_json, cs.created_at
                FROM corpus_sections cs
                JOIN corpus_documents cd ON cd.id = cs.document_id
                WHERE cd.active = 1
                """
            ).fetchall():
                document_metadata = _decode_json_object(row["document_metadata_json"])
                section_metadata = _decode_json_object(row["section_metadata_json"])
                metadata = {**document_metadata, **section_metadata}
                scope_key = _principal_scope_key_from_metadata(metadata)
                if not include_scope(scope_key):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"corpus:{int(row['document_id'] or 0)}:{int(row['section_index'] or 0)}",
                    shelf="corpus",
                    row_id=int(row["section_id"] or 0),
                    stable_key=str(row["stable_key"] or ""),
                    principal_scope_key=scope_key,
                    source=str(row["source"] or ""),
                    content=f"{row['title'] or ''} {row['heading'] or ''} {row['content'] or ''}",
                    metadata=metadata,
                    source_updated_at=str(row["updated_at"] or row["created_at"] or ""),
                )
                bump("corpus")

        if not shelf_filter or "graph" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT gs.id, ge.canonical_name AS subject, gs.attribute, gs.value_text,
                       gs.source, gs.metadata_json, gs.valid_from, gs.valid_to, gs.is_current
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
                WHERE gs.is_current = 1
                """
            ).fetchall():
                item = _row_to_dict(row)
                raw_graph_metadata = item.get("metadata")
                graph_metadata: Mapping[str, Any] = raw_graph_metadata if isinstance(raw_graph_metadata, Mapping) else {}
                scope_key = _principal_scope_key_from_metadata(graph_metadata)
                if not include_scope(scope_key):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"graph:state:{int(item.get('id') or 0)}",
                    shelf="graph",
                    row_id=int(item.get("id") or 0),
                    stable_key=f"{item.get('subject') or ''}:{item.get('attribute') or ''}",
                    principal_scope_key=scope_key,
                    source=str(item.get("source") or ""),
                    content=f"{item.get('subject') or ''} {item.get('attribute') or ''} {item.get('value_text') or ''}",
                    metadata=graph_metadata,
                    source_updated_at=str(item.get("valid_from") or ""),
                )
                bump("graph")

        if not shelf_filter or "continuity" in shelf_filter or "continuity_match" in shelf_filter:
            for row in self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
                FROM continuity_events
                """
            ).fetchall():
                item = _row_to_dict(row)
                raw_continuity_metadata = item.get("metadata")
                continuity_metadata: Mapping[str, Any] = (
                    raw_continuity_metadata if isinstance(raw_continuity_metadata, Mapping) else {}
                )
                scope_key = _principal_scope_key_from_metadata(continuity_metadata)
                if not include_scope(scope_key):
                    continue
                self._upsert_semantic_evidence_document(
                    evidence_key=f"continuity:{int(item.get('id') or 0)}",
                    shelf="continuity_match",
                    row_id=int(item.get("id") or 0),
                    stable_key="",
                    principal_scope_key=scope_key,
                    source=str(item.get("source") or ""),
                    content=f"{item.get('kind') or ''} {item.get('content') or ''}",
                    metadata=continuity_metadata,
                    source_updated_at=str(item.get("updated_at") or item.get("created_at") or ""),
                )
                bump("continuity_match")

        self.conn.commit()
        return {
            "schema": "brainstack.semantic_evidence_backfill.v1",
            "fingerprint": semantic_evidence_fingerprint(),
            "index_version": SEMANTIC_EVIDENCE_INDEX_VERSION,
            "counts": counts,
        }

    @_locked
    def semantic_evidence_channel_status(self) -> Dict[str, Any]:
        fingerprint = semantic_evidence_fingerprint()
        active_count = int(
            self.conn.execute("SELECT COUNT(*) AS count FROM semantic_evidence_index WHERE active = 1").fetchone()["count"]
        )
        stale_count = int(
            self.conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM semantic_evidence_index
                WHERE active = 1 AND (fingerprint != ? OR index_version != ?)
                """,
                (fingerprint, SEMANTIC_EVIDENCE_INDEX_VERSION),
            ).fetchone()["count"]
        )
        if stale_count:
            status = "degraded"
            reason = "Semantic evidence index contains stale derived rows."
        elif active_count:
            status = "active"
            reason = "Semantic evidence index is active."
        else:
            status = "idle"
            reason = "Semantic evidence index has no active rows."
        return {
            "status": status,
            "reason": reason,
            "active_count": active_count,
            "stale_count": stale_count,
            "fingerprint": fingerprint,
            "index_version": SEMANTIC_EVIDENCE_INDEX_VERSION,
        }

    @_locked
    def record_tier2_run_result(self, result: Mapping[str, Any]) -> str:
        run_id = str(result.get("run_id") or "").strip()
        if not run_id:
            basis = json.dumps(
                {
                    "session_id": result.get("session_id"),
                    "turn_number": result.get("turn_number"),
                    "trigger_reason": result.get("trigger_reason"),
                    "created_at": utc_now_iso(),
                },
                ensure_ascii=True,
                sort_keys=True,
            )
            run_id = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]
        now = utc_now_iso()
        no_op_reasons = result.get("no_op_reasons")
        if not isinstance(no_op_reasons, list):
            no_op_reasons = []
        metadata = result.get("metadata") if isinstance(result.get("metadata"), Mapping) else {}
        self.conn.execute(
            """
            INSERT INTO tier2_run_records (
                run_id, session_id, turn_number, trigger_reason, request_status,
                parse_status, status, transcript_count, extracted_counts_json,
                action_counts_json, writes_performed, no_op_reasons_json,
                error_reason, duration_ms, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                request_status = excluded.request_status,
                parse_status = excluded.parse_status,
                status = excluded.status,
                transcript_count = excluded.transcript_count,
                extracted_counts_json = excluded.extracted_counts_json,
                action_counts_json = excluded.action_counts_json,
                writes_performed = excluded.writes_performed,
                no_op_reasons_json = excluded.no_op_reasons_json,
                error_reason = excluded.error_reason,
                duration_ms = excluded.duration_ms,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                run_id,
                str(result.get("session_id") or ""),
                int(result.get("turn_number") or 0),
                str(result.get("trigger_reason") or ""),
                str(result.get("request_status") or ""),
                str(result.get("json_parse_status") or result.get("parse_status") or ""),
                str(result.get("status") or ""),
                int(result.get("transcript_count") or 0),
                json.dumps(result.get("extracted_counts") or {}, ensure_ascii=True, sort_keys=True),
                json.dumps(result.get("action_counts") or {}, ensure_ascii=True, sort_keys=True),
                int(result.get("writes_performed") or 0),
                json.dumps(no_op_reasons, ensure_ascii=True, sort_keys=True),
                str(result.get("error_reason") or ""),
                int(result.get("duration_ms") or 0),
                json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                str(result.get("created_at") or now),
                now,
            ),
        )
        self.conn.commit()
        return run_id

    @_locked
    def latest_tier2_run_record(self, *, session_id: str = "") -> Dict[str, Any] | None:
        params: list[Any] = []
        sql = """
            SELECT *
            FROM tier2_run_records
            WHERE 1 = 1
        """
        normalized_session_id = str(session_id or "").strip()
        if normalized_session_id:
            sql += " AND session_id = ?"
            params.append(normalized_session_id)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT 1"
        row = self.conn.execute(sql, tuple(params)).fetchone()
        if row is None:
            return None
        item = _row_to_dict(row)
        item["extracted_counts"] = _decode_json_object(item.pop("extracted_counts_json", {}))
        item["action_counts"] = _decode_json_object(item.pop("action_counts_json", {}))
        item["no_op_reasons"] = _decode_json_array(item.pop("no_op_reasons_json", []))
        return item

    def _materialize_semantic_evidence_row(self, row: Mapping[str, Any]) -> Dict[str, Any] | None:
        shelf = str(row.get("shelf") or "").strip()
        row_id = int(row.get("row_id") or 0)
        if shelf == "profile":
            source_row = self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
                FROM profile_items
                WHERE id = ? AND active = 1
                """,
                (row_id,),
            ).fetchone()
            item = _profile_row_to_dict(source_row) if source_row else None
        elif shelf == "task":
            source_row = self.conn.execute(
                """
                SELECT id, stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                       optional, status, owner, source, source_session_id, source_turn_number,
                       metadata_json, created_at, updated_at
                FROM task_items
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()
            item = _task_row_to_dict(source_row) if source_row else None
        elif shelf == "operating":
            source_row = self.conn.execute(
                """
                SELECT id, stable_key, principal_scope_key, record_type, content, owner, source,
                       source_session_id, source_turn_number, metadata_json, created_at, updated_at
                FROM operating_records
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()
            item = _operating_row_to_dict(source_row) if source_row else None
        elif shelf == "corpus":
            source_row = self.conn.execute(
                """
                SELECT cd.id AS document_id, cd.stable_key, cd.title, cd.doc_kind, cd.source,
                       cd.metadata_json AS document_metadata_json,
                       cs.id AS section_id, cs.section_index, cs.heading, cs.content, cs.token_estimate,
                       cs.metadata_json AS section_metadata_json
                FROM corpus_sections cs
                JOIN corpus_documents cd ON cd.id = cs.document_id
                WHERE cs.id = ? AND cd.active = 1
                """,
                (row_id,),
            ).fetchone()
            item = _corpus_search_row_to_dict(source_row) if source_row else None
        elif shelf == "graph":
            source_row = self.conn.execute(
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
                       '' AS conflict_value
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
                WHERE gs.id = ? AND gs.is_current = 1
                """,
                (row_id,),
            ).fetchone()
            item = _row_to_dict(source_row) if source_row else None
        elif shelf == "continuity_match":
            source_row = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
                FROM continuity_events
                WHERE id = ?
                """,
                (row_id,),
            ).fetchone()
            item = _row_to_dict(source_row) if source_row else None
        else:
            item = None
        if item is None:
            return None
        if shelf == "operating" and not record_is_effective_at(item):
            return None
        item["semantic_evidence_key"] = str(row.get("evidence_key") or "")
        item["semantic_shelf"] = shelf
        item["semantic_score"] = float(row.get("semantic_score") or 0.0)
        item["retrieval_source"] = "semantic_evidence"
        item["match_mode"] = "semantic"
        item["semantic_index_fingerprint"] = str(row.get("fingerprint") or "")
        return item

    @_locked
    def search_semantic_evidence(
        self,
        *,
        query: str,
        principal_scope_key: str = "",
        limit: int = 8,
        shelves: Iterable[str] | None = None,
    ) -> List[Dict[str, Any]]:
        query_terms = normalize_semantic_terms(query)
        if not query_terms:
            return []
        fingerprint = semantic_evidence_fingerprint()
        requested_scope_key = str(principal_scope_key or "").strip()
        requested_shelves = [str(shelf or "").strip() for shelf in (shelves or ()) if str(shelf or "").strip()]
        params: List[Any] = [fingerprint, SEMANTIC_EVIDENCE_INDEX_VERSION]
        sql = """
            SELECT *
            FROM semantic_evidence_index
            WHERE active = 1
              AND fingerprint = ?
              AND index_version = ?
        """
        if requested_scope_key:
            sql += " AND principal_scope_key IN ('', ?)"
            params.append(requested_scope_key)
        if requested_shelves:
            sql += f" AND shelf IN ({','.join('?' for _ in requested_shelves)})"
            params.extend(requested_shelves)
        sql += " ORDER BY updated_at DESC LIMIT 256"
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        scored: List[tuple[float, Dict[str, Any]]] = []
        for raw_row in rows:
            row = dict(raw_row)
            terms = _decode_json_array(row.get("terms_json"))
            score = semantic_similarity(query_terms, terms)
            if score <= 0.0:
                continue
            row["semantic_score"] = score
            materialized = self._materialize_semantic_evidence_row(row)
            if materialized is not None:
                if not _volatile_operating_semantic_match(materialized):
                    continue
                scored.append((score, materialized))
        scored.sort(
            key=lambda item: (
                item[0],
                str(item[1].get("updated_at") or item[1].get("created_at") or item[1].get("happened_at") or ""),
            ),
            reverse=True,
        )
        return [row for _, row in scored[: max(int(limit or 0), 1)]]

    @_locked
    def corpus_semantic_channel_status(self) -> Dict[str, str]:
        if self._corpus_backend is None:
            return {
                "status": "degraded",
                "reason": "Semantic retrieval is disabled until a donor-aligned corpus backend is configured.",
            }
        if self._corpus_backend_error:
            return {
                "status": "degraded",
                "reason": f"Semantic retrieval backend is unhealthy: {self._corpus_backend_error}",
            }
        return {
            "status": "active",
            "reason": f"Semantic retrieval is served by {self._corpus_backend.target_name}.",
        }
