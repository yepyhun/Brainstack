from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    List,
    _annotate_principal_scope,
    _attach_keyword_scores,
    _cursor_lastrowid,
    _enrich_record_metadata_with_literals,
    _extract_query_terms,
    _locked,
    _normalize_record_metadata,
    _row_to_dict,
    build_fts_query,
    build_write_decision_trace,
    json,
    logger,
    sqlite3,
    utc_now_iso,
)

class ContinuityStoreMixin(StoreRuntimeBase):
    @_locked
    def add_continuity_event(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        now = str(created_at or "").strip() or utc_now_iso()
        if created_at:
            metadata = dict(metadata or {})
            metadata.setdefault("observed_at", now)
        normalized_metadata = _normalize_record_metadata(
            _enrich_record_metadata_with_literals(metadata, text=content),
            source=source,
        )
        normalized_metadata.setdefault("source_kind", "explicit")
        normalized_metadata.setdefault("graph_kind", "relation")
        normalized_metadata.setdefault(
            "write_contract_trace",
            build_write_decision_trace(
                lane="continuity",
                accepted=True,
                reason_code="continuity_event",
                authority_class="continuity",
                canonical=False,
                source_present=bool(str(source or "").strip()),
            ),
        )
        cur = self.conn.execute(
            """
            INSERT INTO continuity_events (
                session_id, turn_number, kind, content, source, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                turn_number,
                kind,
                content,
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        normalized_metadata = _enrich_record_metadata_with_literals(
            normalized_metadata,
            text=content,
            row_id=row_id,
            session_id=session_id,
            turn_number=turn_number,
            kind=kind,
            include_event=True,
        )
        self.conn.execute(
            "UPDATE continuity_events SET metadata_json = ? WHERE id = ?",
            (json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True), row_id),
        )
        self.conn.execute(
            "INSERT INTO continuity_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
        self._refresh_semantic_evidence_shelf(
            shelf="continuity",
            metadata=normalized_metadata,
        )
        return row_id

    @_locked
    def add_transcript_entry(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        now = str(created_at or "").strip() or utc_now_iso()
        if created_at:
            metadata = dict(metadata or {})
            metadata.setdefault("observed_at", now)
        normalized_metadata = _normalize_record_metadata(
            _enrich_record_metadata_with_literals(metadata, text=content),
            source=source,
        )
        normalized_metadata.setdefault("source_kind", "explicit")
        normalized_metadata.setdefault("graph_kind", "relation")
        cur = self.conn.execute(
            """
            INSERT INTO transcript_entries (
                session_id, turn_number, kind, content, source, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                turn_number,
                kind,
                content,
                source,
                json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        normalized_metadata = _enrich_record_metadata_with_literals(
            normalized_metadata,
            text=content,
            row_id=row_id,
            session_id=session_id,
            turn_number=turn_number,
            kind=kind,
            include_event=True,
        )
        self.conn.execute(
            "UPDATE transcript_entries SET metadata_json = ? WHERE id = ?",
            (json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True), row_id),
        )
        self.conn.execute(
            "INSERT INTO transcript_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
        if self._corpus_backend is not None:
            self._publish_conversation_transcript(row_id, raise_on_error=False)
        return row_id

    @_locked
    def recent_continuity(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM continuity_events
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def recent_principal_continuity(
        self,
        *,
        principal_scope_key: str,
        session_id: str = "",
        kinds: Iterable[str] | None = None,
        limit: int,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        candidate_limit = max(int(limit or 0) * 8, 24)
        normalized_kinds = [
            str(value or "").strip()
            for value in (kinds or ())
            if str(value or "").strip()
        ]
        params: List[Any] = []
        sql = """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM continuity_events
            WHERE 1 = 1
        """
        if normalized_kinds:
            sql += f" AND kind IN ({','.join('?' for _ in normalized_kinds)})"
            params.extend(normalized_kinds)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(candidate_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()

        output: List[Dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for row in rows:
            item = _row_to_dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=requested_scope_key,
                session_id=session_id,
                allow_personal_scope_fallback=False,
            ):
                continue
            key = (str(item.get("session_id") or ""), int(item.get("id") or 0))
            if key in seen:
                continue
            seen.add(key)
            item["same_session"] = str(item.get("session_id") or "").strip() == str(session_id or "").strip()
            item["retrieval_source"] = "continuity.principal_recent"
            item["match_mode"] = "recent"
            output.append(item)
            if len(output) >= max(int(limit or 0), 1):
                break
        return output

    @_locked
    def get_continuity_lifecycle_state(self, *, session_id: str) -> Dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            FROM continuity_lifecycle_state
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        return _row_to_dict(row) if row is not None else None

    @_locked
    def record_continuity_snapshot_state(
        self,
        *,
        session_id: str,
        turn_number: int,
        kind: str,
        message_count: int = 0,
        input_message_count: int = 0,
        digest: str = "",
        created_at: str | None = None,
    ) -> Dict[str, Any]:
        now = str(created_at or "").strip() or utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO continuity_lifecycle_state (
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?)
            ON CONFLICT(session_id) DO UPDATE SET
                current_frontier_turn_number = MAX(
                    continuity_lifecycle_state.current_frontier_turn_number,
                    excluded.current_frontier_turn_number
                ),
                last_snapshot_kind = excluded.last_snapshot_kind,
                last_snapshot_turn_number = excluded.last_snapshot_turn_number,
                last_snapshot_message_count = excluded.last_snapshot_message_count,
                last_snapshot_input_count = excluded.last_snapshot_input_count,
                last_snapshot_digest = excluded.last_snapshot_digest,
                last_snapshot_at = excluded.last_snapshot_at,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                max(0, int(turn_number or 0)),
                str(kind or "").strip(),
                max(0, int(turn_number or 0)),
                max(0, int(message_count or 0)),
                max(0, int(input_message_count or 0)),
                str(digest or "").strip(),
                now,
                now,
            ),
        )
        self.conn.commit()
        state = self.get_continuity_lifecycle_state(session_id=session_id)
        assert state is not None
        return state

    @_locked
    def finalize_continuity_session_state(
        self,
        *,
        session_id: str,
        turn_number: int,
        created_at: str | None = None,
    ) -> Dict[str, Any]:
        now = str(created_at or "").strip() or utc_now_iso()
        finalized_turn = max(0, int(turn_number or 0))
        self.conn.execute(
            """
            INSERT INTO continuity_lifecycle_state (
                session_id,
                current_frontier_turn_number,
                last_snapshot_kind,
                last_snapshot_turn_number,
                last_snapshot_message_count,
                last_snapshot_input_count,
                last_snapshot_digest,
                last_snapshot_at,
                last_finalized_turn_number,
                last_finalized_at,
                updated_at
            ) VALUES (?, ?, '', 0, 0, 0, '', '', ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                current_frontier_turn_number = MAX(
                    continuity_lifecycle_state.current_frontier_turn_number,
                    excluded.current_frontier_turn_number
                ),
                last_finalized_turn_number = MAX(
                    continuity_lifecycle_state.last_finalized_turn_number,
                    excluded.last_finalized_turn_number
                ),
                last_finalized_at = excluded.last_finalized_at,
                updated_at = excluded.updated_at
            """,
            (
                session_id,
                finalized_turn,
                finalized_turn,
                now,
                now,
            ),
        )
        self.conn.commit()
        state = self.get_continuity_lifecycle_state(session_id=session_id)
        assert state is not None
        return state

    @_locked
    def search_temporal_continuity(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        row_limit = max(limit * 6, 24)
        current_principal_scope_key = str(principal_scope_key or "").strip()
        fts_query = build_fts_query(query)
        if fts_query:
            try:
                rows = self.conn.execute(
                    """
                    SELECT ce.id, ce.session_id, ce.turn_number, ce.kind, ce.content, ce.source, ce.metadata_json, ce.created_at
                    FROM continuity_fts fts
                    JOIN continuity_events ce ON ce.id = fts.rowid
                    WHERE ce.kind = 'temporal_event' AND continuity_fts MATCH ?
                    ORDER BY
                        CASE WHEN ce.session_id = ? THEN 0 ELSE 1 END,
                        bm25(continuity_fts),
                        ce.created_at DESC
                    LIMIT ?
                    """,
                    (fts_query, session_id, row_limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        else:
            rows = []
        keyword_rows = _attach_keyword_scores(_row_to_dict(row) for row in rows) if rows else []
        if not rows:
            rows = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM continuity_events
                WHERE kind = 'temporal_event'
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (row_limit,),
            ).fetchall()
        fallback_rows = [_row_to_dict(row) for row in rows] if not keyword_rows else []
        scored: List[Dict[str, Any]] = []
        for row in keyword_rows or fallback_rows:
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
                allow_personal_scope_fallback=False,
            ):
                continue
            metadata = dict(item.get("metadata") or {})
            temporal_payload = metadata.get("temporal")
            temporal = temporal_payload if isinstance(temporal_payload, dict) else {}
            item["same_session"] = item["session_id"] == session_id
            item.setdefault("keyword_score", 0.0)
            item["semantic_score"] = 0.0
            item["retrieval_source"] = "continuity.temporal_keyword" if keyword_rows else "continuity.temporal_recent"
            item["match_mode"] = "keyword" if keyword_rows else "recent"
            item["_temporal_observed_at"] = str(
                temporal.get("observed_at")
                or temporal.get("valid_at")
                or item.get("created_at")
                or ""
            )
            scored.append(item)

        semantic_scorer = getattr(self._corpus_backend, "score_texts", None)
        if callable(semantic_scorer) and scored:
            try:
                semantic_scores = semantic_scorer(
                    query=query,
                    texts=[str(item.get("content") or "") for item in scored],
                )
            except Exception as exc:
                self._corpus_backend_error = str(exc)
                logger.warning("Brainstack temporal continuity semantic scoring failed: %s", exc)
            else:
                self._corpus_backend_error = ""
                for item, semantic_score in zip(scored, semantic_scores):
                    item["semantic_score"] = float(semantic_score or 0.0)

        scored.sort(
            key=lambda item: (
                1 if float(item.get("semantic_score") or 0.0) > 0.0 else 0,
                float(item.get("semantic_score") or 0.0),
                float(item.get("keyword_score") or 0.0),
                1 if item.get("same_session") else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("_temporal_observed_at") or ""),
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def search_continuity(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        current_principal_scope_key = str(principal_scope_key or "").strip()
        try:
            rows = self.conn.execute(
                """
                SELECT ce.id, ce.session_id, ce.turn_number, ce.kind, ce.content, ce.source, ce.metadata_json, ce.created_at
                FROM continuity_fts fts
                JOIN continuity_events ce ON ce.id = fts.rowid
                WHERE continuity_fts MATCH ?
                ORDER BY
                    CASE WHEN ce.session_id = ? THEN 0 ELSE 1 END,
                    bm25(continuity_fts),
                    ce.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM continuity_events
                WHERE content LIKE ?
                ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                (like, session_id, limit),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
                allow_personal_scope_fallback=False,
            ):
                continue
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "continuity.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                float(item.get("keyword_score") or 0.0),
                1 if item["same_session"] else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("created_at") or ""),
                int(item.get("turn_number") or 0),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def recent_transcript(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def search_transcript(self, *, query: str, session_id: str, limit: int) -> List[Dict[str, Any]]:
        tokens = _extract_query_terms(query, limit=8)
        if not tokens:
            return []

        candidate_limit = max(limit * 4, 8)
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:8])
        rows: List[sqlite3.Row]

        try:
            rows = self.conn.execute(
                """
                SELECT te.id, te.session_id, te.turn_number, te.kind, te.content, te.source, te.metadata_json, te.created_at
                FROM transcript_fts fts
                JOIN transcript_entries te ON te.id = fts.rowid
                WHERE transcript_fts MATCH ?
                  AND te.session_id = ?
                ORDER BY
                    bm25(transcript_fts),
                    te.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, candidate_limit),
            ).fetchall()
        except sqlite3.OperationalError:
            patterns = [f"%{token}%" for token in tokens[:8]]
            where = " OR ".join("lower(content) LIKE ?" for _ in patterns)
            rows = self.conn.execute(
                f"""
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM transcript_entries
                WHERE session_id = ? AND ({where})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple([session_id] + patterns + [candidate_limit]),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "transcript.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                1 if item["same_session"] else 0,
                float(item.get("keyword_score") or 0.0),
                int(item["turn_number"]),
                int(item["id"]),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def search_transcript_global(
        self,
        *,
        query: str,
        session_id: str,
        limit: int,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        tokens = _extract_query_terms(query, limit=8)
        if not tokens:
            return []

        candidate_limit = max(limit * 6, 12)
        fts_query = " OR ".join(f'"{token}"' for token in tokens[:8])
        rows: List[sqlite3.Row]
        current_principal_scope_key = str(principal_scope_key or "").strip()

        try:
            rows = self.conn.execute(
                """
                SELECT te.id, te.session_id, te.turn_number, te.kind, te.content, te.source, te.metadata_json, te.created_at
                FROM transcript_fts fts
                JOIN transcript_entries te ON te.id = fts.rowid
                WHERE transcript_fts MATCH ?
                ORDER BY
                    CASE WHEN te.session_id = ? THEN 0 ELSE 1 END,
                    bm25(transcript_fts),
                    te.created_at DESC
                LIMIT ?
                """,
                (fts_query, session_id, candidate_limit),
            ).fetchall()
        except sqlite3.OperationalError:
            patterns = [f"%{token}%" for token in tokens[:8]]
            where = " OR ".join("lower(content) LIKE ?" for _ in patterns)
            rows = self.conn.execute(
                f"""
                SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
                FROM transcript_entries
                WHERE {where}
                ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                tuple(patterns + [session_id, candidate_limit]),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(
                item,
                principal_scope_key=current_principal_scope_key,
                session_id=session_id,
            ):
                continue
            item["same_session"] = item["session_id"] == session_id
            item["retrieval_source"] = "transcript.keyword"
            item["match_mode"] = "keyword"
            scored.append(item)

        scored.sort(
            key=lambda item: (
                float(item.get("keyword_score") or 0.0),
                1 if item["same_session"] else 0,
                1 if item.get("same_principal") else 0,
                str(item.get("created_at") or ""),
                int(item["turn_number"]),
                int(item["id"]),
            ),
            reverse=True,
        )
        return scored[:limit]
