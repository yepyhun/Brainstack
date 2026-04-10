from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .transcript import count_overlap, tokenize_match_text


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


class BrainstackStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BrainstackStore is not open")
        return self._conn

    def open(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

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
                json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
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
                json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
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

    def recent_continuity(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, created_at
            FROM continuity_events
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def search_continuity(self, *, query: str, session_id: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return []
        try:
            rows = self.conn.execute(
                """
                SELECT ce.id, ce.session_id, ce.turn_number, ce.kind, ce.content, ce.source, ce.created_at
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
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                """
                SELECT id, session_id, turn_number, kind, content, source, created_at
                FROM continuity_events
                WHERE content LIKE ?
                ORDER BY CASE WHEN session_id = ? THEN 0 ELSE 1 END, created_at DESC
                LIMIT ?
                """,
                (like, session_id, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def recent_transcript(self, *, session_id: str, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, created_at
            FROM transcript_entries
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

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
                SELECT te.id, te.session_id, te.turn_number, te.kind, te.content, te.source, te.created_at
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
                SELECT id, session_id, turn_number, kind, content, source, created_at
                FROM transcript_entries
                WHERE session_id = ? AND ({where})
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple([session_id] + patterns + [candidate_limit]),
            ).fetchall()

        scored: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
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
            "SELECT id FROM profile_items WHERE stable_key = ?",
            (stable_key,),
        ).fetchone()
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)

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

    def list_profile_items(self, *, limit: int, categories: Iterable[str] | None = None) -> List[Dict[str, Any]]:
        params: list[Any] = []
        sql = """
            SELECT id, stable_key, category, content, source, confidence, updated_at
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
        return [dict(row) for row in rows]

    def search_profile(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        if not fts_query:
            return self.list_profile_items(limit=limit)
        try:
            rows = self.conn.execute(
                """
                SELECT pi.id, pi.stable_key, pi.category, pi.content, pi.source, pi.confidence, pi.updated_at
                FROM profile_fts fts
                JOIN profile_items pi ON pi.id = fts.rowid
                WHERE profile_fts MATCH ? AND pi.active = 1
                ORDER BY bm25(profile_fts), pi.confidence DESC, pi.updated_at DESC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.OperationalError:
            like = f"%{query.strip()}%"
            rows = self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, updated_at
                FROM profile_items
                WHERE active = 1 AND content LIKE ?
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (like, limit),
            ).fetchall()
            return [dict(row) for row in rows]

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
            SELECT id FROM graph_relations
            WHERE subject_entity_id = ? AND predicate = ? AND object_entity_id = ? AND active = 1
            """,
            (subject["id"], predicate, obj["id"]),
        ).fetchone()
        if existing:
            return int(existing["id"])
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
                json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

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
        current = self.conn.execute(
            """
            SELECT id, value_text
            FROM graph_states
            WHERE entity_id = ? AND attribute = ? AND is_current = 1
            ORDER BY valid_from DESC, id DESC
            LIMIT 1
            """,
            (entity["id"], attribute),
        ).fetchone()
        normalized_new = " ".join(value_text.lower().split())
        meta_json = json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)

        if current and " ".join(str(current["value_text"]).lower().split()) == normalized_new:
            return {"status": "unchanged", "entity_id": entity["id"], "state_id": int(current["id"])}

        if current and not supersede:
            conflict = self.conn.execute(
                """
                SELECT id FROM graph_conflicts
                WHERE entity_id = ? AND attribute = ? AND current_state_id = ?
                  AND candidate_value_text = ? AND status = 'open'
                """,
                (entity["id"], attribute, int(current["id"]), value_text.strip()),
            ).fetchone()
            if conflict:
                return {"status": "conflict", "entity_id": entity["id"], "conflict_id": int(conflict["id"])}
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
                    meta_json,
                    now,
                    now,
                ),
            )
            self.conn.commit()
            return {"status": "conflict", "entity_id": entity["id"], "conflict_id": int(cur.lastrowid)}

        if current and supersede:
            self.conn.execute(
                """
                UPDATE graph_states
                SET is_current = 0, valid_to = ?
                WHERE id = ?
                """,
                (now, int(current["id"])),
            )

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
                meta_json,
                now,
            ),
        )
        new_state_id = int(cur.lastrowid)

        if current and supersede:
            self.conn.execute(
                """
                INSERT INTO graph_supersessions (prior_state_id, new_state_id, reason, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (int(current["id"]), new_state_id, "superseded_by_new_current_state", now),
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

    def list_graph_conflicts(self, *, limit: int) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT gc.id, ge.canonical_name AS entity_name, gc.attribute, gs.value_text AS current_value,
                   gc.candidate_value_text, gc.status, gc.updated_at
            FROM graph_conflicts gc
            JOIN graph_entities ge ON ge.id = gc.entity_id
            JOIN graph_states gs ON gs.id = gc.current_state_id
            WHERE gc.status = 'open'
            ORDER BY gc.updated_at DESC, gc.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def search_graph(self, *, query: str, limit: int) -> List[Dict[str, Any]]:
        patterns = build_like_tokens(query)
        if not patterns:
            return []
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
                       ge.canonical_name AS subject,
                       gs.attribute AS predicate,
                       gs.value_text AS object_value,
                       gs.is_current AS is_current,
                       gs.valid_from AS happened_at,
                       gs.source AS source,
                       '' AS conflict_source,
                       '' AS conflict_value
                FROM graph_states gs
                JOIN graph_entities ge ON ge.id = gs.entity_id
                WHERE {state_where}
            ),
            relation_hits AS (
                SELECT 'relation' AS row_type,
                       ge.canonical_name AS subject,
                       gr.predicate AS predicate,
                       COALESCE(go.canonical_name, gr.object_text, '') AS object_value,
                       1 AS is_current,
                       gr.created_at AS happened_at,
                       gr.source AS source,
                       '' AS conflict_source,
                       '' AS conflict_value
                FROM graph_relations gr
                JOIN graph_entities ge ON ge.id = gr.subject_entity_id
                LEFT JOIN graph_entities go ON go.id = gr.object_entity_id
                WHERE {relation_where}
            ),
            conflict_hits AS (
                SELECT 'conflict' AS row_type,
                       ge.canonical_name AS subject,
                       gc.attribute AS predicate,
                       gs.value_text AS object_value,
                       1 AS is_current,
                       gc.updated_at AS happened_at,
                       gs.source AS source,
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
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]
