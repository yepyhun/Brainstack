from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    List,
    NUMERIC_TOKEN_RE,
    STATUS_OPEN,
    _annotate_principal_scope,
    _attach_keyword_scores,
    _cursor_lastrowid,
    _decode_json_object,
    _enrich_record_metadata_with_literals,
    _extract_query_terms,
    _locked,
    _merge_record_metadata,
    _scoped_row_priority,
    _task_match_score,
    _task_row_to_dict,
    build_like_tokens,
    json,
    utc_now_iso,
)

class TaskStoreMixin(StoreRuntimeBase):
    @_locked
    def upsert_task_item(
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
        source_session_id: str = "",
        source_turn_number: int = 0,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM task_items WHERE stable_key = ?",
            (str(stable_key or "").strip(),),
        ).fetchone()
        meta_json = json.dumps(
            _merge_record_metadata(
                existing["metadata_json"] if existing else None,
                _enrich_record_metadata_with_literals(metadata, text=title),
                source=source,
            ),
            ensure_ascii=True,
            sort_keys=True,
        )
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE task_items
                SET principal_scope_key = ?, item_type = ?, title = ?, due_date = ?, date_scope = ?,
                    optional = ?, status = ?, owner = ?, source = ?, source_session_id = ?,
                    source_turn_number = ?, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(principal_scope_key or "").strip(),
                    str(item_type or "").strip(),
                    str(title or "").strip(),
                    str(due_date or "").strip(),
                    str(date_scope or "").strip(),
                    1 if optional else 0,
                    str(status or STATUS_OPEN).strip() or STATUS_OPEN,
                    str(owner or "brainstack.task_memory").strip() or "brainstack.task_memory",
                    str(source or "").strip(),
                    str(source_session_id or "").strip(),
                    int(source_turn_number or 0),
                    meta_json,
                    now,
                    row_id,
                ),
            )
            self.conn.commit()
            self._refresh_semantic_evidence_shelf(
                shelf="task",
                principal_scope_key=principal_scope_key,
                metadata=_decode_json_object(meta_json),
            )
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO task_items (
                stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                optional, status, owner, source, source_session_id, source_turn_number,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(stable_key or "").strip(),
                str(principal_scope_key or "").strip(),
                str(item_type or "").strip(),
                str(title or "").strip(),
                str(due_date or "").strip(),
                str(date_scope or "").strip(),
                1 if optional else 0,
                str(status or STATUS_OPEN).strip() or STATUS_OPEN,
                str(owner or "brainstack.task_memory").strip() or "brainstack.task_memory",
                str(source or "").strip(),
                str(source_session_id or "").strip(),
                int(source_turn_number or 0),
                meta_json,
                now,
                now,
            ),
        )
        self.conn.commit()
        row_id = _cursor_lastrowid(cur)
        self._refresh_semantic_evidence_shelf(
            shelf="task",
            principal_scope_key=principal_scope_key,
            metadata=_decode_json_object(meta_json),
        )
        return row_id

    @_locked
    def list_task_items(
        self,
        *,
        principal_scope_key: str,
        due_date: str = "",
        item_type: str = "",
        statuses: Iterable[str] | None = None,
        limit: int = 24,
    ) -> List[Dict[str, Any]]:
        scope_key = str(principal_scope_key or "").strip()
        params: list[Any] = [scope_key]
        sql = """
            SELECT
                id, stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                optional, status, owner, source, source_session_id, source_turn_number,
                metadata_json, created_at, updated_at
            FROM task_items
            WHERE principal_scope_key = ?
        """
        normalized_due_date = str(due_date or "").strip()
        if normalized_due_date:
            sql += " AND due_date = ?"
            params.append(normalized_due_date)
        normalized_item_type = str(item_type or "").strip()
        if normalized_item_type:
            sql += " AND item_type = ?"
            params.append(normalized_item_type)
        status_values = [str(value or "").strip() for value in (statuses or ()) if str(value or "").strip()]
        if status_values:
            sql += f" AND status IN ({','.join('?' for _ in status_values)})"
            params.extend(status_values)
        sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, due_date ASC, optional ASC, updated_at DESC, id DESC LIMIT ?"
        params.append(max(int(limit or 0), 1))
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [_task_row_to_dict(row) for row in rows]

    @_locked
    def search_task_items(
        self,
        *,
        query: str,
        principal_scope_key: str,
        item_type: str = "",
        statuses: Iterable[str] | None = None,
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        requested_scope_key = str(principal_scope_key or "").strip()
        query_tokens = _extract_query_terms(query, limit=8)
        if not query_tokens:
            return []

        candidate_limit = max(int(limit or 0) * 8, 24)
        normalized_item_type = str(item_type or "").strip()
        normalized_statuses = [str(value or "").strip() for value in (statuses or ()) if str(value or "").strip()]

        params: list[Any] = [requested_scope_key]
        sql = """
            SELECT
                id, stable_key, principal_scope_key, item_type, title, due_date, date_scope,
                optional, status, owner, source, source_session_id, source_turn_number,
                metadata_json, created_at, updated_at
            FROM task_items
            WHERE principal_scope_key = ?
        """
        if normalized_item_type:
            sql += " AND item_type = ?"
            params.append(normalized_item_type)
        if normalized_statuses:
            sql += f" AND status IN ({','.join('?' for _ in normalized_statuses)})"
            params.extend(normalized_statuses)

        like_tokens = build_like_tokens(query, limit=8)
        if like_tokens:
            clauses: List[str] = []
            for _ in like_tokens:
                clauses.append(
                    "("
                    "lower(title) LIKE ? OR lower(item_type) LIKE ? OR lower(due_date) LIKE ? "
                    "OR lower(date_scope) LIKE ? OR lower(status) LIKE ? OR lower(metadata_json) LIKE ?"
                    ")"
                )
            sql += " AND (" + " OR ".join(clauses) + ")"
            for token in like_tokens:
                params.extend([token, token, token, token, token, token])

        sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, due_date ASC, optional ASC, updated_at DESC, id DESC LIMIT ?"
        params.append(candidate_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()

        numeric_tokens = NUMERIC_TOKEN_RE.findall(str(query or ""))
        ranked: List[Dict[str, Any]] = []
        for row in (_task_row_to_dict(item) for item in rows):
            if not _annotate_principal_scope(row, principal_scope_key=requested_scope_key):
                continue
            match_score, token_overlap = _task_match_score(
                row,
                query_tokens=query_tokens,
                numeric_tokens=numeric_tokens,
            )
            if match_score <= 0.0:
                continue
            row["_task_match_score"] = match_score
            row["_brainstack_query_token_overlap"] = token_overlap
            ranked.append(row)

        ranked.sort(
            key=lambda item: (
                _scoped_row_priority(item, principal_scope_key=requested_scope_key),
                float(item.get("_task_match_score") or 0.0),
                str(item.get("updated_at") or ""),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        output: List[Dict[str, Any]] = []
        for row in _attach_keyword_scores(ranked):
            item = dict(row)
            item["keyword_score"] = max(
                float(item.get("keyword_score") or 0.0),
                float(item.pop("_task_match_score", 0.0) or 0.0),
            )
            item["retrieval_source"] = "task.keyword"
            item["match_mode"] = "keyword"
            output.append(item)
        return output[: max(int(limit or 0), 1)]
