from __future__ import annotations

from functools import wraps
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, TypeVar

from .provenance import merge_provenance, normalize_provenance
from .temporal import merge_temporal, normalize_temporal_fields
from .transcript import count_overlap, tokenize_match_text
from .usefulness import apply_retrieval_telemetry


F = TypeVar("F", bound=Callable[..., Any])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_fts_query(query: str) -> str:
    tokens = [token.strip() for token in query.replace('"', " ").split() if token.strip()]
    if not tokens:
        return ""
    return " OR ".join(f'"{token}"' for token in tokens[:8])


def build_like_tokens(query: str, *, limit: int = 8) -> List[str]:
    tokens = [token.strip().lower() for token in query.replace('"', " ").split() if token.strip()]
    return [f"%{token}%" for token in tokens[:limit]]


def _decode_json_object(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalize_record_metadata(metadata: Dict[str, Any] | None, *, source: str = "") -> Dict[str, Any]:
    payload = dict(metadata or {})

    nested_temporal = payload.pop("temporal", None)
    temporal_payload: Dict[str, Any] = {}
    if isinstance(nested_temporal, dict):
        temporal_payload.update(nested_temporal)
    for key in ("observed_at", "valid_at", "valid_from", "valid_to", "supersedes", "superseded_by", "episode_id"):
        if key in payload:
            temporal_payload[key] = payload.pop(key)
    temporal = normalize_temporal_fields(**temporal_payload)

    nested_provenance = payload.pop("provenance", None)
    provenance_seed: Dict[str, Any] = {}
    if source:
        provenance_seed["source_ids"] = [source]
    for key in (
        "session_id",
        "turn_number",
        "tier",
        "target",
        "admission_reason",
        "origin",
        "status_reason",
        "trace_id",
        "correlation_id",
    ):
        if key in payload:
            provenance_seed[key] = payload.pop(key)
    provenance = merge_provenance(provenance_seed, nested_provenance)

    normalized: Dict[str, Any] = dict(payload)
    if temporal:
        normalized["temporal"] = temporal
    if provenance:
        normalized["provenance"] = provenance
    return normalized


def _merge_record_metadata(
    existing_metadata_json: Any,
    incoming_metadata: Dict[str, Any] | None,
    *,
    source: str = "",
) -> Dict[str, Any]:
    existing = _decode_json_object(existing_metadata_json)
    incoming = _normalize_record_metadata(incoming_metadata, source=source)

    merged: Dict[str, Any] = {}
    for payload in (existing, incoming):
        for key, value in payload.items():
            if key in {"temporal", "provenance"}:
                continue
            merged[key] = value

    temporal = merge_temporal(existing.get("temporal"), incoming.get("temporal"))
    provenance = merge_provenance(existing.get("provenance"), incoming.get("provenance"))
    if temporal:
        merged["temporal"] = temporal
    if provenance:
        merged["provenance"] = provenance
    return merged


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)
    if "metadata_json" in item:
        item["metadata"] = _decode_json_object(item.pop("metadata_json"))
    if "conflict_metadata_json" in item:
        item["conflict_metadata"] = _decode_json_object(item.pop("conflict_metadata_json"))
    return item


def _locked(method: F) -> F:
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


class BrainstackStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BrainstackStore is not open")
        return self._conn

    @_locked
    def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    @_locked
    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS continuity_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_continuity_session_created
            ON continuity_events(session_id, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS continuity_fts USING fts5(
                content,
                session_id UNINDEXED,
                kind UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS transcript_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_number INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_transcript_session_created
            ON transcript_entries(session_id, created_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                content,
                session_id UNINDEXED,
                kind UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS profile_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 0.5,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                first_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_profile_category_updated
            ON profile_items(category, updated_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS profile_fts USING fts5(
                content,
                category UNINDEXED,
                stable_key UNINDEXED,
                tokenize = 'unicode61'
            );

            CREATE TABLE IF NOT EXISTS graph_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS graph_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_entity_id INTEGER NOT NULL,
                predicate TEXT NOT NULL,
                object_entity_id INTEGER,
                object_text TEXT,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(subject_entity_id) REFERENCES graph_entities(id),
                FOREIGN KEY(object_entity_id) REFERENCES graph_entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_relations_subject
            ON graph_relations(subject_entity_id, predicate, created_at DESC);

            CREATE TABLE IF NOT EXISTS graph_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                attribute TEXT NOT NULL,
                value_text TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                valid_from TEXT NOT NULL,
                valid_to TEXT,
                is_current INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(entity_id) REFERENCES graph_entities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_states_entity_attribute
            ON graph_states(entity_id, attribute, is_current, valid_from DESC);

            CREATE TABLE IF NOT EXISTS graph_supersessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prior_state_id INTEGER NOT NULL,
                new_state_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(prior_state_id) REFERENCES graph_states(id),
                FOREIGN KEY(new_state_id) REFERENCES graph_states(id)
            );

            CREATE TABLE IF NOT EXISTS graph_conflicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id INTEGER NOT NULL,
                attribute TEXT NOT NULL,
                current_state_id INTEGER NOT NULL,
                candidate_value_text TEXT NOT NULL,
                candidate_source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(entity_id) REFERENCES graph_entities(id),
                FOREIGN KEY(current_state_id) REFERENCES graph_states(id)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_conflicts_entity
            ON graph_conflicts(entity_id, attribute, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS corpus_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stable_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                doc_kind TEXT NOT NULL DEFAULT 'document',
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_corpus_documents_kind_updated
            ON corpus_documents(doc_kind, updated_at DESC);

            CREATE TABLE IF NOT EXISTS corpus_sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                section_index INTEGER NOT NULL,
                heading TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                token_estimate INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY(document_id) REFERENCES corpus_documents(id) ON DELETE CASCADE,
                UNIQUE(document_id, section_index)
            );

            CREATE INDEX IF NOT EXISTS idx_corpus_sections_document
            ON corpus_sections(document_id, section_index);

            CREATE VIRTUAL TABLE IF NOT EXISTS corpus_section_fts USING fts5(
                title,
                heading,
                content,
                document_id UNINDEXED,
                section_index UNINDEXED,
                tokenize = 'unicode61'
            );
            """
        )
        self.conn.commit()

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
    ) -> int:
        now = utc_now_iso()
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
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
        row_id = int(cur.lastrowid)
        self.conn.execute(
            "INSERT INTO continuity_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
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
    ) -> int:
        now = utc_now_iso()
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
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
        row_id = int(cur.lastrowid)
        self.conn.execute(
            "INSERT INTO transcript_fts(rowid, content, session_id, kind) VALUES (?, ?, ?, ?)",
            (row_id, content, session_id, kind),
        )
        self.conn.commit()
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
    def search_continuity(self, *, query: str, session_id: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
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
            return [_row_to_dict(row) for row in rows]
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
            return [_row_to_dict(row) for row in rows]

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
        tokens = tokenize_match_text(query)
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
        for row in rows:
            item = _row_to_dict(row)
            overlap_count = count_overlap(query, item["content"])
            if overlap_count <= 0:
                continue
            item["overlap_count"] = overlap_count
            item["same_session"] = item["session_id"] == session_id
            scored.append(item)

        scored.sort(
            key=lambda item: (
                1 if item["same_session"] else 0,
                int(item["overlap_count"]),
                int(item["turn_number"]),
                int(item["id"]),
            ),
            reverse=True,
        )
        return scored[:limit]

    @_locked
    def upsert_profile_item(
        self,
        *,
        stable_key: str,
        category: str,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        now = utc_now_iso()
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
            (stable_key,),
        ).fetchone()
        normalized_metadata = _merge_record_metadata(
            existing["metadata_json"] if existing else None,
            metadata,
            source=source,
        )
        meta_json = json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True)

        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE profile_items
                SET category = ?, content = ?, source = ?, confidence = ?, metadata_json = ?,
                    updated_at = ?, active = ?
                WHERE id = ?
                """,
                (
                    category,
                    content,
                    source,
                    confidence,
                    meta_json,
                    now,
                    1 if active else 0,
                    row_id,
                ),
            )
            self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (row_id,))
        else:
            cur = self.conn.execute(
                """
                INSERT INTO profile_items (
                    stable_key, category, content, source, confidence,
                    metadata_json, first_seen_at, updated_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_key,
                    category,
                    content,
                    source,
                    confidence,
                    meta_json,
                    now,
                    now,
                    1 if active else 0,
                ),
            )
            row_id = int(cur.lastrowid)

        self.conn.execute(
            "INSERT INTO profile_fts(rowid, content, category, stable_key) VALUES (?, ?, ?, ?)",
            (row_id, content, category, stable_key),
        )
        self.conn.commit()
        return row_id

    @_locked
    def list_profile_items(self, *, limit: int, categories: Iterable[str] | None = None) -> List[Dict[str, Any]]:
        params: list[Any] = []
        sql = """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
            FROM profile_items
            WHERE active = 1
        """
        if categories:
            cats = list(categories)
            sql += f" AND category IN ({','.join('?' for _ in cats)})"
            params.extend(cats)
        sql += " ORDER BY confidence DESC, updated_at DESC, id DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_dict(row) for row in rows]

    @_locked
    def get_profile_item(self, *, stable_key: str) -> Dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE stable_key = ?
            LIMIT 1
            """,
            (stable_key,),
        ).fetchone()
        return _row_to_dict(row) if row else None

    @_locked
    def record_profile_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        for row in rows:
            stable_key = str(row.get("stable_key") or "").strip()
            if not stable_key:
                continue
            existing = self.conn.execute(
                "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
                (stable_key,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=bool(row.get("matched")),
                fallback=bool(row.get("fallback")),
                served_at=now,
            )
            self.conn.execute(
                "UPDATE profile_items SET metadata_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, int(existing["id"])),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated

    @_locked
    def search_profile(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return self.list_profile_items(limit=limit)
        try:
            rows = self.conn.execute(
                """
                SELECT pi.id, pi.stable_key, pi.category, pi.content, pi.source, pi.confidence, pi.metadata_json, pi.updated_at
                FROM profile_fts fts
                JOIN profile_items pi ON pi.id = fts.rowid
                WHERE profile_fts MATCH ? AND pi.active = 1
                ORDER BY bm25(profile_fts), pi.confidence DESC, pi.updated_at DESC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]
        except sqlite3.OperationalError:
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
                FROM profile_items
                WHERE active = 1 AND content LIKE ?
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (like, limit),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    @_locked
    def upsert_corpus_document(
        self,
        *,
        stable_key: str,
        title: str,
        doc_kind: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        now = utc_now_iso()
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)
        existing = self.conn.execute(
            "SELECT id FROM corpus_documents WHERE stable_key = ?",
            (stable_key,),
        ).fetchone()
        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE corpus_documents
                SET title = ?, doc_kind = ?, source = ?, metadata_json = ?, updated_at = ?, active = ?
                WHERE id = ?
                """,
                (title, doc_kind, source, meta_json, now, 1 if active else 0, row_id),
            )
            self.conn.commit()
            return row_id

        cur = self.conn.execute(
            """
            INSERT INTO corpus_documents (
                stable_key, title, doc_kind, source, metadata_json, created_at, updated_at, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (stable_key, title, doc_kind, source, meta_json, now, now, 1 if active else 0),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    @_locked
    def replace_corpus_sections(
        self,
        *,
        document_id: int,
        title: str,
        sections: Iterable[Dict[str, Any]],
    ) -> int:
        existing_rows = self.conn.execute(
            "SELECT id FROM corpus_sections WHERE document_id = ?",
            (document_id,),
        ).fetchall()
        for row in existing_rows:
            self.conn.execute("DELETE FROM corpus_section_fts WHERE rowid = ?", (int(row["id"]),))
        self.conn.execute("DELETE FROM corpus_sections WHERE document_id = ?", (document_id,))

        inserted = 0
        now = utc_now_iso()
        for index, section in enumerate(sections):
            heading = str(section.get("heading", "")).strip() or title
            content = str(section.get("content", "")).strip()
            if not content:
                continue
            token_estimate = int(section.get("token_estimate", max(1, len(content) // 4)))
            metadata_json = json.dumps(section.get("metadata", {}), ensure_ascii=True, sort_keys=True)
            cur = self.conn.execute(
                """
                INSERT INTO corpus_sections (
                    document_id, section_index, heading, content, token_estimate, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, index, heading, content, token_estimate, metadata_json, now),
            )
            row_id = int(cur.lastrowid)
            self.conn.execute(
                """
                INSERT INTO corpus_section_fts(rowid, title, heading, content, document_id, section_index)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row_id, title, heading, content, document_id, index),
            )
            inserted += 1

        self.conn.commit()
        return inserted

    @_locked
    def ingest_corpus_document(
        self,
        *,
        stable_key: str,
        title: str,
        doc_kind: str,
        source: str,
        sections: Iterable[Dict[str, Any]],
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        document_id = self.upsert_corpus_document(
            stable_key=stable_key,
            title=title,
            doc_kind=doc_kind,
            source=source,
            metadata=metadata,
            active=True,
        )
        section_count = self.replace_corpus_sections(
            document_id=document_id,
            title=title,
            sections=sections,
        )
        return {"document_id": document_id, "section_count": section_count, "stable_key": stable_key}

    @_locked
    def search_corpus(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if fts_query:
            try:
                rows = self.conn.execute(
                    """
                    SELECT
                        cd.id AS document_id,
                        cd.title,
                        cd.doc_kind,
                        cd.source,
                        cs.id AS section_id,
                        cs.section_index,
                        cs.heading,
                        cs.content,
                        cs.token_estimate
                    FROM corpus_section_fts fts
                    JOIN corpus_sections cs ON cs.id = fts.rowid
                    JOIN corpus_documents cd ON cd.id = cs.document_id
                    WHERE corpus_section_fts MATCH ? AND cd.active = 1
                    ORDER BY bm25(corpus_section_fts), cs.token_estimate ASC, cs.id DESC
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
                return [dict(row) for row in rows]
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
                cd.title,
                cd.doc_kind,
                cd.source,
                cs.id AS section_id,
                cs.section_index,
                cs.heading,
                cs.content,
                cs.token_estimate
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
        return [dict(row) for row in rows]

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
        cur = self.conn.execute(
            """
            INSERT INTO graph_entities (canonical_name, normalized_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), normalized, now, now),
        )
        self.conn.commit()
        return {
            "id": int(cur.lastrowid),
            "canonical_name": name.strip(),
            "normalized_name": normalized,
        }

    @_locked
    def merge_entity_alias(self, *, alias_name: str, target_name: str) -> Dict[str, Any]:
        alias_normalized = self._normalize_entity_name(alias_name)
        target_normalized = self._normalize_entity_name(target_name)
        if not alias_normalized or not target_normalized or alias_normalized == target_normalized:
            return {"status": "noop"}

        alias = self.conn.execute(
            "SELECT id FROM graph_entities WHERE normalized_name = ?",
            (alias_normalized,),
        ).fetchone()
        if not alias:
            return {"status": "noop"}

        target = self.get_or_create_entity(target_name)
        alias_id = int(alias["id"])
        target_id = int(target["id"])

        self.conn.execute("UPDATE graph_states SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
        self.conn.execute("UPDATE graph_conflicts SET entity_id = ? WHERE entity_id = ?", (target_id, alias_id))
        self.conn.execute("UPDATE graph_relations SET subject_entity_id = ? WHERE subject_entity_id = ?", (target_id, alias_id))
        self.conn.execute(
            "UPDATE graph_relations SET object_entity_id = ?, object_text = ? WHERE object_entity_id = ?",
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

        refs = self.conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM graph_states WHERE entity_id = ?) AS state_refs,
                (SELECT COUNT(*) FROM graph_conflicts WHERE entity_id = ?) AS conflict_refs,
                (SELECT COUNT(*) FROM graph_relations WHERE subject_entity_id = ? OR object_entity_id = ?) AS relation_refs
            """,
            (alias_id, alias_id, alias_id, alias_id),
        ).fetchone()
        if refs and int(refs["state_refs"]) == 0 and int(refs["conflict_refs"]) == 0 and int(refs["relation_refs"]) == 0:
            self.conn.execute("DELETE FROM graph_entities WHERE id = ?", (alias_id,))

        self.conn.commit()
        return {"status": "merged", "alias_id": alias_id, "target_id": target_id}

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
            merged = _merge_record_metadata(existing["metadata_json"], metadata, source=source)
            self.conn.execute(
                "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
            )
            self.conn.commit()
            return int(existing["id"])
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
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
        self.conn.commit()
        return int(cur.lastrowid)

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
            merged = _merge_record_metadata(existing["metadata_json"], metadata, source=source)
            self.conn.execute(
                "UPDATE graph_relations SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(existing["id"])),
            )
            self.conn.commit()
            return {"status": "unchanged", "relation_id": int(existing["id"])}
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
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
        self.conn.commit()
        return {"status": "inserted", "relation_id": int(cur.lastrowid)}

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
        now = utc_now_iso()
        entity = self.get_or_create_entity(subject_name)
        normalized_metadata = _normalize_record_metadata(metadata, source=source)
        temporal = merge_temporal(
            normalized_metadata.get("temporal"),
            {"observed_at": normalized_metadata.get("temporal", {}).get("observed_at") or now},
        )
        if temporal:
            normalized_metadata["temporal"] = temporal
        valid_from = str(normalized_metadata.get("temporal", {}).get("valid_from") or now)
        current = self.conn.execute(
            """
            SELECT id, value_text, source, metadata_json, valid_from, valid_to
            FROM graph_states
            WHERE entity_id = ? AND attribute = ? AND is_current = 1
            ORDER BY valid_from DESC, id DESC
            LIMIT 1
            """,
            (entity["id"], attribute),
        ).fetchone()
        normalized_new = " ".join(value_text.lower().split())

        if current and " ".join(str(current["value_text"]).lower().split()) == normalized_new:
            merged = _merge_record_metadata(current["metadata_json"], normalized_metadata, source=source)
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (json.dumps(merged, ensure_ascii=True, sort_keys=True), int(current["id"])),
            )
            self.conn.commit()
            return {"status": "unchanged", "entity_id": entity["id"], "state_id": int(current["id"])}

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
                merged = _merge_record_metadata(conflict["metadata_json"], normalized_metadata, source=source)
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
            conflict_metadata = _merge_record_metadata(
                None,
                normalized_metadata,
                source=source,
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
            return {"status": "conflict", "entity_id": entity["id"], "conflict_id": int(cur.lastrowid)}

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
            if prior_temporal:
                prior_metadata["temporal"] = prior_temporal
            if prior_provenance:
                prior_metadata["provenance"] = prior_provenance
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

        state_metadata = _merge_record_metadata(None, normalized_metadata, source=source)
        cur = self.conn.execute(
            """
            INSERT INTO graph_states (
                entity_id, attribute, value_text, source, metadata_json, valid_from, valid_to, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 1)
            """,
            (
                entity["id"],
                attribute,
                value_text.strip(),
                source,
                json.dumps(state_metadata, ensure_ascii=True, sort_keys=True),
                valid_from,
            ),
        )
        new_state_id = int(cur.lastrowid)

        if current and supersede:
            updated_prior_metadata = _decode_json_object(current["metadata_json"])
            updated_prior_metadata["temporal"] = merge_temporal(
                updated_prior_metadata.get("temporal"),
                {"valid_to": valid_from, "superseded_by": str(new_state_id)},
            )
            updated_prior_metadata["provenance"] = merge_provenance(
                updated_prior_metadata.get("provenance"),
                {"source_ids": [source], "replacement_record_id": str(new_state_id)},
            )
            self.conn.execute(
                "UPDATE graph_states SET metadata_json = ? WHERE id = ?",
                (
                    json.dumps(updated_prior_metadata, ensure_ascii=True, sort_keys=True),
                    int(current["id"]),
                ),
            )
            new_state_metadata = _merge_record_metadata(
                state_metadata,
                {
                    "temporal": {"supersedes": str(current["id"]), "valid_from": valid_from},
                    "provenance": {"replacement_record_id": str(current["id"])},
                },
                source=source,
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
    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
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
    def search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        patterns = build_like_tokens(query)
        if not patterns:
            return []
        candidate_limit = max(limit * 4, limit)
        state_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gs.value_text) LIKE ? OR lower(gs.attribute) LIKE ?"
            for _ in patterns
        )
        relation_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(COALESCE(go.canonical_name, gr.object_text, '')) LIKE ? OR lower(gr.predicate) LIKE ?"
            for _ in patterns
        )
        conflict_where = " OR ".join(
            "lower(ge.canonical_name) LIKE ? OR lower(gc.attribute) LIKE ? OR lower(gc.candidate_value_text) LIKE ?"
            for _ in patterns
        )
        params: List[Any] = []
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        for pattern in patterns:
            params.extend([pattern, pattern, pattern])
        params.append(limit)
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
                       '' AS conflict_value
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
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
                       '' AS conflict_value
                FROM graph_relations gr
                JOIN graph_entities ge ON ge.id = gr.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
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
                       gc.candidate_value_text AS conflict_value
                FROM graph_conflicts gc
                JOIN graph_entities ge ON ge.id = gc.entity_id
                JOIN graph_states gs ON gs.id = gc.current_state_id
                WHERE gc.status = 'open'
                  AND ({conflict_where})
            )
            SELECT * FROM (
                SELECT * FROM state_hits
                UNION ALL
                SELECT * FROM relation_hits
                UNION ALL
                SELECT * FROM conflict_hits
            )
            ORDER BY happened_at DESC
            LIMIT ?
            """,
            tuple(params[:-1] + [candidate_limit]),
        ).fetchall()
        parsed = [_row_to_dict(row) for row in rows]
        parsed.sort(
            key=lambda item: (
                3 if item["row_type"] == "conflict" else 0,
                2 if item["row_type"] == "state" and item.get("is_current") else 0,
                1 if item["row_type"] == "relation" else 0,
                str(item.get("happened_at") or ""),
            ),
            reverse=True,
        )
        return parsed[:limit]

    @_locked
    def record_graph_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        table_by_type = {
            "state": "graph_states",
            "relation": "graph_relations",
            "conflict": "graph_conflicts",
        }
        for row in rows:
            row_type = str(row.get("row_type") or "").strip()
            row_id = int(row.get("row_id") or 0)
            table = table_by_type.get(row_type)
            if not table or row_id <= 0:
                continue
            existing = self.conn.execute(
                f"SELECT metadata_json FROM {table} WHERE id = ?",
                (row_id,),
            ).fetchone()
            if not existing:
                continue
            metadata = _decode_json_object(existing["metadata_json"])
            metadata = apply_retrieval_telemetry(
                metadata,
                matched=True,
                fallback=False,
                served_at=now,
            )
            self.conn.execute(
                f"UPDATE {table} SET metadata_json = ?{', updated_at = ?' if table == 'graph_conflicts' else ''} WHERE id = ?",
                ((json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, row_id) if table == "graph_conflicts" else (json.dumps(metadata, ensure_ascii=True, sort_keys=True), row_id)),
            )
            updated += 1
        if updated:
            self.conn.commit()
        return updated
