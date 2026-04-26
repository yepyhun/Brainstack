from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    List,
    OPERATING_RECORD_TYPES,
    _annotate_principal_scope,
    _attach_keyword_scores,
    _cursor_lastrowid,
    _decode_json_object,
    _enrich_record_metadata_with_literals,
    _locked,
    _merge_record_metadata,
    _operating_row_to_dict,
    _scoped_row_priority,
    _volatile_operating_keyword_match,
    build_fts_query,
    json,
    list_live_system_state_rows,
    normalize_operating_record_metadata,
    record_is_effective_at,
    search_live_system_state_rows,
    sqlite3,
    utc_now_iso,
)

class OperatingStoreMixin(StoreRuntimeBase):
    @_locked
    def upsert_operating_record(
        self,
        *,
        stable_key: str,
        principal_scope_key: str,
        record_type: str,
        content: str,
        owner: str,
        source: str,
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM operating_records WHERE stable_key = ?",
            (str(stable_key or "").strip(),),
        ).fetchone()
        merged_metadata = normalize_operating_record_metadata(
            record_type=str(record_type or "").strip(),
            stable_key=str(stable_key or "").strip(),
            source=str(source or "").strip(),
            metadata=_merge_record_metadata(
                existing["metadata_json"] if existing else None,
                _enrich_record_metadata_with_literals(metadata, text=content),
                source=source,
            ),
        )
        meta_json = json.dumps(
            merged_metadata,
            ensure_ascii=True,
            sort_keys=True,
        )
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE operating_records
                SET principal_scope_key = ?, record_type = ?, content = ?, owner = ?, source = ?,
                    source_session_id = ?, source_turn_number = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(principal_scope_key or "").strip(),
                    str(record_type or "").strip(),
                    str(content or "").strip(),
                    str(owner or "brainstack.operating_truth").strip() or "brainstack.operating_truth",
                    str(source or "").strip(),
                    str(source_session_id or "").strip(),
                    int(source_turn_number or 0),
                    meta_json,
                    now,
                    row_id,
                ),
            )
            self.conn.execute("DELETE FROM operating_fts WHERE rowid = ?", (row_id,))
            self.conn.execute(
                "INSERT INTO operating_fts(rowid, content, record_type, stable_key) VALUES (?, ?, ?, ?)",
                (
                    row_id,
                    str(content or "").strip(),
                    str(record_type or "").strip(),
                    str(stable_key or "").strip(),
                ),
            )
            self.conn.commit()
            self._refresh_semantic_evidence_shelf(
                shelf="operating",
                principal_scope_key=principal_scope_key,
                metadata=_decode_json_object(meta_json),
            )
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO operating_records (
                stable_key, principal_scope_key, record_type, content, owner, source,
                source_session_id, source_turn_number, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(stable_key or "").strip(),
                str(principal_scope_key or "").strip(),
                str(record_type or "").strip(),
                str(content or "").strip(),
                str(owner or "brainstack.operating_truth").strip() or "brainstack.operating_truth",
                str(source or "").strip(),
                str(source_session_id or "").strip(),
                int(source_turn_number or 0),
                meta_json,
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        self.conn.execute(
            "INSERT INTO operating_fts(rowid, content, record_type, stable_key) VALUES (?, ?, ?, ?)",
            (
                row_id,
                str(content or "").strip(),
                str(record_type or "").strip(),
                str(stable_key or "").strip(),
            ),
        )
        self.conn.commit()
        self._refresh_semantic_evidence_shelf(
            shelf="operating",
            principal_scope_key=principal_scope_key,
            metadata=_decode_json_object(meta_json),
        )
        return row_id

    @_locked
    def list_operating_records(
        self,
        *,
        principal_scope_key: str,
        record_types: Iterable[str] | None = None,
        limit: int = 12,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        candidate_limit = max(int(limit or 0) * 6, 24)
        params: List[Any] = []
        sql = """
            SELECT
                id, stable_key, principal_scope_key, record_type, content, owner, source,
                source_session_id, source_turn_number, metadata_json, created_at, updated_at
            FROM operating_records
            WHERE 1 = 1
        """
        normalized_record_types = [
            str(value or "").strip()
            for value in (record_types or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        if normalized_record_types:
            sql += f" AND record_type IN ({','.join('?' for _ in normalized_record_types)})"
            params.extend(normalized_record_types)
        sql += " ORDER BY updated_at DESC, id DESC LIMIT ?"
        params.append(candidate_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()

        scoped: Dict[str, Dict[str, Any]] = {}
        for candidate_row in rows:
            item = _operating_row_to_dict(candidate_row)
            if not _annotate_principal_scope(item, principal_scope_key=requested_scope_key):
                continue
            if not record_is_effective_at(item):
                continue
            logical_key = str(item.get("stable_key") or "").strip() or f"row:{item.get('id')}"
            existing = scoped.get(logical_key)
            if existing is None or _scoped_row_priority(item, principal_scope_key=requested_scope_key) > _scoped_row_priority(
                existing,
                principal_scope_key=requested_scope_key,
            ):
                scoped[logical_key] = item
        output = sorted(
            scoped.values(),
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        live_rows = [
            dict(row)
            for row in list_live_system_state_rows(
                principal_scope_key=requested_scope_key,
                limit=max(int(limit or 0), 1),
            )
            if not normalized_record_types or str(row.get("record_type") or "").strip() in normalized_record_types
            if record_is_effective_at(row)
        ]
        return (live_rows + output)[: max(int(limit or 0), 1)]

    @_locked
    def search_operating_records(
        self,
        *,
        query: str,
        principal_scope_key: str,
        record_types: Iterable[str] | None = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        candidate_limit = max(int(limit or 0) * 8, 24)
        normalized_record_types = [
            str(value or "").strip()
            for value in (record_types or ())
            if str(value or "").strip() in OPERATING_RECORD_TYPES
        ]
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        params: List[Any]
        rows: List[sqlite3.Row]
        sql = """
            SELECT
                o.id, o.stable_key, o.principal_scope_key, o.record_type, o.content, o.owner, o.source,
                o.source_session_id, o.source_turn_number, o.metadata_json, o.created_at, o.updated_at
            FROM operating_fts fts
            JOIN operating_records o ON o.id = fts.rowid
            WHERE operating_fts MATCH ?
        """
        params = [fts_query]
        if normalized_record_types:
            sql += f" AND o.record_type IN ({','.join('?' for _ in normalized_record_types)})"
            params.extend(normalized_record_types)
        sql += " ORDER BY bm25(operating_fts), o.updated_at DESC LIMIT ?"
        params.append(candidate_limit)
        try:
            rows = self.conn.execute(sql, tuple(params)).fetchall()
        except sqlite3.OperationalError:
            rows = []

        scored = _attach_keyword_scores(_operating_row_to_dict(row) for row in rows)
        filtered: List[Dict[str, Any]] = []
        for row in scored:
            if not _annotate_principal_scope(row, principal_scope_key=requested_scope_key):
                continue
            if not record_is_effective_at(row):
                continue
            if not _volatile_operating_keyword_match(row, query=query):
                continue
            row["retrieval_source"] = "operating.keyword"
            row["match_mode"] = "keyword"
            filtered.append(row)
        filtered.sort(
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                float(item.get("keyword_score") or 0.0),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        live_rows = [
            dict(row)
            for row in search_live_system_state_rows(
                query=query,
                principal_scope_key=requested_scope_key,
                limit=max(int(limit or 0), 1),
            )
            if not normalized_record_types or str(row.get("record_type") or "").strip() in normalized_record_types
            if record_is_effective_at(row)
        ]
        merged = _attach_keyword_scores(live_rows + filtered)
        merged.sort(
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                float(item.get("keyword_score") or 0.0),
                str(item.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return merged[: max(int(limit or 0), 1)]
