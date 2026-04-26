from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    Dict,
    Iterable,
    Mapping,
    _cursor_lastrowid,
    _decode_json_object,
    _enrich_record_metadata_with_literals,
    _locked,
    _principal_scope_key_from_metadata,
    _profile_storage_key,
    build_write_decision_trace,
    corpus_ingest_versions,
    enrich_metadata_with_literal_sidecar,
    json,
    normalize_corpus_source,
    user_turn_event_sidecar,
    utc_now_iso,
)

class CorpusStoreMixin(StoreRuntimeBase):
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
        enriched_metadata = _enrich_record_metadata_with_literals(metadata, text=title)
        meta_json = json.dumps(enriched_metadata, ensure_ascii=True, sort_keys=True)
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
        return _cursor_lastrowid(cur)

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
            section_metadata = _enrich_record_metadata_with_literals(section.get("metadata", {}), text=content)
            metadata_json = json.dumps(section_metadata, ensure_ascii=True, sort_keys=True)
            cur = self.conn.execute(
                """
                INSERT INTO corpus_sections (
                    document_id, section_index, heading, content, token_estimate, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, index, heading, content, token_estimate, metadata_json, now),
            )
            row_id = _cursor_lastrowid(cur)
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
    def backfill_literal_event_sidecars(self, *, dry_run: bool = True, limit: int = 0) -> Dict[str, Any]:
        """Populate literal/event sidecars without rewriting record content or authority."""
        specs = [
            ("profile_items", "content", ""),
            ("operating_records", "content", ""),
            ("task_items", "title", ""),
            ("corpus_documents", "title", ""),
            ("corpus_sections", "content", ""),
            ("continuity_events", "content", "event"),
            ("transcript_entries", "content", "event"),
        ]
        report: Dict[str, Any] = {
            "schema": "brainstack.literal_event_backfill.v1",
            "dry_run": bool(dry_run),
            "tables": {},
            "updated": 0,
            "scanned": 0,
        }
        remaining = int(limit or 0)
        for table, text_column, mode in specs:
            sql = f"SELECT * FROM {table} ORDER BY id ASC"
            if remaining > 0:
                sql += " LIMIT ?"
                rows = self.conn.execute(sql, (remaining,)).fetchall()
            else:
                rows = self.conn.execute(sql).fetchall()
            scanned = 0
            updated = 0
            for row in rows:
                scanned += 1
                metadata = _decode_json_object(row["metadata_json"]) if "metadata_json" in row.keys() else {}
                text = str(row[text_column] or "")
                event_payload = None
                if mode == "event":
                    event_payload = user_turn_event_sidecar(
                        row_id=int(row["id"]),
                        session_id=str(row["session_id"] or ""),
                        turn_number=int(row["turn_number"] or 0),
                        kind=str(row["kind"] or ""),
                        content=text,
                        metadata=metadata,
                    )
                enriched = enrich_metadata_with_literal_sidecar(metadata, text=text, event=event_payload)
                if enriched == metadata:
                    continue
                updated += 1
                if not dry_run:
                    self.conn.execute(
                        f"UPDATE {table} SET metadata_json = ? WHERE id = ?",
                        (json.dumps(enriched, ensure_ascii=True, sort_keys=True), int(row["id"])),
                    )
            report["tables"][table] = {"scanned": scanned, "updated": updated}
            report["scanned"] += scanned
            report["updated"] += updated
            if remaining > 0:
                remaining = max(0, remaining - scanned)
                if remaining == 0:
                    break
        if not dry_run:
            self.conn.commit()
        return report

    @_locked
    def annotate_explicit_truth_parity(
        self,
        *,
        target: str,
        stable_key: str,
        category: str = "",
        principal_scope_key: str = "",
        parity: Mapping[str, Any],
    ) -> bool:
        """Attach parity diagnostics to the projected row without changing content or authority."""
        normalized_target = str(target or "").strip()
        normalized_key = str(stable_key or "").strip()
        if not normalized_key or not isinstance(parity, Mapping):
            return False

        table = ""
        where = ""
        params: tuple[Any, ...] = ()
        if normalized_target in {"user", "profile"}:
            storage_key = _profile_storage_key(
                stable_key=normalized_key,
                category=str(category or "").strip(),
                principal_scope_key=str(principal_scope_key or "").strip(),
            )
            table = "profile_items"
            where = "stable_key = ?"
            params = (storage_key,)
        elif normalized_target == "operating":
            table = "operating_records"
            where = "stable_key = ?"
            params = (normalized_key,)
        elif normalized_target == "task":
            table = "task_items"
            where = "stable_key = ?"
            params = (normalized_key,)
        else:
            return False

        row = self.conn.execute(f"SELECT id, metadata_json FROM {table} WHERE {where}", params).fetchone()
        if row is None:
            return False
        metadata = _decode_json_object(row["metadata_json"])
        metadata["explicit_truth_parity"] = dict(parity)
        self.conn.execute(
            f"UPDATE {table} SET metadata_json = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=True, sort_keys=True), int(row["id"])),
        )
        self.conn.commit()
        return True

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
        if self._corpus_backend is not None:
            self._publish_corpus_document(document_id)
        self._refresh_semantic_evidence_shelf(
            shelf="corpus",
            metadata=metadata,
        )
        return {"document_id": document_id, "section_count": section_count, "stable_key": stable_key}

    @_locked
    def ingest_corpus_source(self, source_payload: Mapping[str, Any]) -> Dict[str, Any]:
        normalized = normalize_corpus_source(source_payload)
        write_contract_trace = build_write_decision_trace(
            lane="corpus",
            accepted=True,
            reason_code="corpus_source_ingest",
            authority_class="corpus",
            canonical=False,
            source_present=bool(str(normalized.get("source_id") or normalized.get("source") or "").strip()),
            stable_key=str(normalized.get("stable_key") or ""),
        )
        normalized["metadata"] = {
            **dict(normalized.get("metadata") or {}),
            "write_contract_trace": dict(write_contract_trace),
        }
        existing = self.conn.execute(
            "SELECT id, metadata_json FROM corpus_documents WHERE stable_key = ?",
            (normalized["stable_key"],),
        ).fetchone()
        existing_hash = ""
        existing_fingerprint = ""
        if existing is not None:
            existing_metadata = _decode_json_object(existing["metadata_json"])
            ingest_metadata = existing_metadata.get("corpus_ingest")
            if isinstance(ingest_metadata, Mapping):
                existing_hash = str(ingest_metadata.get("document_hash") or "")
                existing_fingerprint = str(ingest_metadata.get("fingerprint") or "")
        if (
            existing is not None
            and existing_hash == normalized["document_hash"]
            and existing_fingerprint == normalized["fingerprint"]
        ):
            section_count = int(
                self.conn.execute(
                    "SELECT COUNT(*) AS count FROM corpus_sections WHERE document_id = ?",
                    (int(existing["id"]),),
                ).fetchone()["count"]
            )
            return {
                "schema": "brainstack.corpus_ingest_receipt.v1",
                "status": "unchanged",
                "document_id": int(existing["id"]),
                "stable_key": normalized["stable_key"],
                "section_count": section_count,
                "document_hash": normalized["document_hash"],
                "corpus_fingerprint": normalized["fingerprint"],
                "citation_ids": list(normalized["citation_ids"]),
                "source_adapter": normalized["source_adapter"],
                "write_contract_trace": dict(write_contract_trace),
                "read_only": False,
            }

        status = "updated" if existing is not None else "inserted"
        result = self.ingest_corpus_document(
            stable_key=normalized["stable_key"],
            title=normalized["title"],
            doc_kind=normalized["doc_kind"],
            source=normalized["source"],
            sections=normalized["sections"],
            metadata=normalized["metadata"],
        )
        return {
            "schema": "brainstack.corpus_ingest_receipt.v1",
            "status": status,
            "document_id": int(result["document_id"]),
            "stable_key": normalized["stable_key"],
            "section_count": int(result["section_count"]),
            "document_hash": normalized["document_hash"],
            "corpus_fingerprint": normalized["fingerprint"],
            "citation_ids": list(normalized["citation_ids"]),
            "source_adapter": normalized["source_adapter"],
            "write_contract_trace": dict(write_contract_trace),
            "read_only": False,
        }

    @_locked
    def deactivate_corpus_source(self, *, stable_key: str) -> Dict[str, Any]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            raise ValueError("corpus source stable_key is required")
        row = self.conn.execute(
            """
            SELECT id, stable_key, title, doc_kind, source, active, metadata_json, updated_at
            FROM corpus_documents
            WHERE stable_key = ?
            """,
            (normalized_key,),
        ).fetchone()
        if row is None:
            return {
                "schema": "brainstack.corpus_lifecycle_receipt.v1",
                "status": "not_found",
                "stable_key": normalized_key,
                "document_id": None,
                "semantic_backend_status": "not_applicable",
            }

        document_id = int(row["id"])
        was_active = bool(row["active"])
        semantic_backend_status = "not_configured"
        if self._corpus_backend is not None:
            delete_snapshot = {
                "document": {
                    "id": document_id,
                    "stable_key": str(row["stable_key"] or normalized_key),
                    "title": str(row["title"] or ""),
                    "doc_kind": str(row["doc_kind"] or ""),
                    "source": str(row["source"] or ""),
                    "metadata": _decode_json_object(row["metadata_json"]),
                    "updated_at": str(row["updated_at"] or ""),
                    "active": False,
                },
                "sections": [],
            }
            try:
                self._publish_semantic_snapshot(
                    object_kind="corpus_document",
                    object_key=normalized_key,
                    snapshot=delete_snapshot,
                    raise_on_error=True,
                )
            except Exception as exc:
                self._corpus_backend_error = str(exc)
                semantic_backend_status = "failed"
                return {
                    "schema": "brainstack.corpus_lifecycle_receipt.v1",
                    "status": "degraded",
                    "stable_key": normalized_key,
                    "document_id": document_id,
                    "active": False,
                    "semantic_backend_status": semantic_backend_status,
                    "error": str(exc),
                }
            semantic_backend_status = "deleted"

        if was_active:
            now = utc_now_iso()
            self.conn.execute(
                "UPDATE corpus_documents SET active = 0, updated_at = ? WHERE id = ?",
                (now, document_id),
            )
            self.conn.commit()

        self._refresh_semantic_evidence_shelf(
            shelf="corpus",
            metadata=_decode_json_object(row["metadata_json"]),
        )
        return {
            "schema": "brainstack.corpus_lifecycle_receipt.v1",
            "status": "deactivated" if was_active else "unchanged",
            "stable_key": normalized_key,
            "document_id": document_id,
            "active": False,
            "semantic_backend_status": semantic_backend_status,
        }

    @_locked
    def corpus_ingest_status(self, *, principal_scope_key: str = "") -> Dict[str, Any]:
        requested_scope = str(principal_scope_key or "").strip()
        versions = corpus_ingest_versions()
        rows = self.conn.execute(
            """
            SELECT id, stable_key, title, metadata_json, active
            FROM corpus_documents
            WHERE active = 1
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        document_count = 0
        stale_documents: list[Dict[str, Any]] = []
        missing_metadata_count = 0
        for row in rows:
            document_metadata = _decode_json_object(row["metadata_json"])
            scope_key = _principal_scope_key_from_metadata(document_metadata)
            if requested_scope and scope_key not in {"", requested_scope}:
                continue
            document_count += 1
            ingest_metadata = document_metadata.get("corpus_ingest")
            if not isinstance(ingest_metadata, Mapping):
                missing_metadata_count += 1
                stale_documents.append(
                    {
                        "document_id": int(row["id"]),
                        "stable_key": str(row["stable_key"] or ""),
                        "reason": "missing_corpus_ingest_metadata",
                    }
                )
                continue
            reasons: list[str] = []
            expected_pairs = {
                "schema": versions["schema"],
                "source_adapter_contract": versions["adapter_contract"],
                "normalizer": versions["normalizer"],
                "sectioner": versions["sectioner"],
                "embedder": versions["embedder"],
            }
            for key, expected in expected_pairs.items():
                if str(ingest_metadata.get(key) or "") != expected:
                    reasons.append(f"{key}_version_mismatch")
            document_hash = str(ingest_metadata.get("document_hash") or "")
            fingerprint = str(ingest_metadata.get("fingerprint") or "")
            section_rows = self.conn.execute(
                "SELECT metadata_json FROM corpus_sections WHERE document_id = ? ORDER BY section_index ASC",
                (int(row["id"]),),
            ).fetchall()
            for section_row in section_rows:
                section_metadata = _decode_json_object(section_row["metadata_json"])
                if not section_metadata.get("section_hash"):
                    reasons.append("section_hash_missing")
                if not section_metadata.get("citation_id"):
                    reasons.append("citation_id_missing")
                if document_hash and str(section_metadata.get("document_hash") or "") != document_hash:
                    reasons.append("section_document_hash_mismatch")
                if fingerprint and str(section_metadata.get("corpus_fingerprint") or "") != fingerprint:
                    reasons.append("section_fingerprint_mismatch")
            if reasons:
                stale_documents.append(
                    {
                        "document_id": int(row["id"]),
                        "stable_key": str(row["stable_key"] or ""),
                        "reason": ",".join(sorted(set(reasons))),
                    }
                )
        if not document_count:
            status = "idle"
            reason = "No active corpus documents are present."
        elif stale_documents:
            status = "degraded"
            reason = f"{len(stale_documents)} corpus document(s) have stale or incomplete ingest metadata."
        else:
            status = "active"
            reason = "Corpus ingest metadata is current for all active documents."
        return {
            "schema": "brainstack.corpus_ingest_status.v1",
            "status": status,
            "reason": reason,
            "versions": versions,
            "document_count": document_count,
            "stale_count": len(stale_documents),
            "missing_metadata_count": missing_metadata_count,
            "stale_documents": stale_documents[:20],
            "capabilities": {
                "add": True,
                "update": True,
                "delete": True,
                "reingest": True,
                "idempotency": True,
                "bounded_recall": True,
                "citation_projection": True,
                "semantic_backend": self._corpus_backend is not None,
            },
        }
