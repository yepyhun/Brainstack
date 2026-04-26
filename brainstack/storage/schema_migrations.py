from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    BEHAVIOR_POLICY_COMPILER_VERSION,
    BEHAVIOR_POLICY_SCHEMA_VERSION,
    COMMUNICATION_CANONICAL_SLOTS,
    Dict,
    List,
    MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1,
    MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1,
    MIGRATION_COMPILED_BEHAVIOR_POLICY_V1,
    MIGRATION_COMPILED_BEHAVIOR_POLICY_V2,
    MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1,
    MIGRATION_GRAPH_SOURCE_LINEAGE_V1,
    MIGRATION_RECENT_WORK_AUTHORITY_V1,
    MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1,
    MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2,
    MIGRATION_STYLE_CONTRACT_BEHAVIOR_DEMOTION_V1,
    MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1,
    Mapping,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    STYLE_CONTRACT_DOC_KIND,
    STYLE_CONTRACT_SLOT,
    _annotate_principal_scope,
    _behavior_contract_row_to_dict,
    _decode_json_object,
    _is_principal_scoped_profile,
    _locked,
    _merge_record_metadata,
    _principal_scope_key_from_metadata,
    _principal_scope_payload_from_metadata,
    _profile_row_to_dict,
    _profile_storage_key,
    _row_to_dict,
    attach_graph_source_lineage,
    build_style_contract_from_document,
    compile_behavior_policy,
    derive_transcript_identity_profile_items,
    derive_transcript_logistics_typed_entities,
    expand_communication_profile_items,
    initialize_schema,
    json,
    logger,
    mark_migration_applied,
    migration_applied,
    normalize_operating_record_metadata,
    normalize_profile_slot,
    run_compatibility_migrations,
    sqlite3,
    utc_now_iso,
)

class SchemaMigrationMixin(StoreRuntimeBase):
    def _disable_graph_backend(self, *, reason: str) -> None:
        self._graph_backend_error = str(reason or "graph backend disabled")
        backend = self._graph_backend
        self._graph_backend = None
        if backend is None:
            return
        try:
            backend.close()
        except Exception:
            pass

    def _resolve_session_principal_scope(
        self,
        *,
        session_id: str,
    ) -> tuple[str, Dict[str, Any]]:
        session_key = str(session_id or "").strip()
        if not session_key:
            return "", {}
        rows = self.conn.execute(
            """
            SELECT metadata_json
            FROM transcript_entries
            WHERE session_id = ?
            ORDER BY id ASC
            LIMIT 64
            """,
            (session_key,),
        ).fetchall()
        scope_key = ""
        scope_payload: Dict[str, Any] = {}
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            candidate_scope_key = _principal_scope_key_from_metadata(metadata)
            if not candidate_scope_key:
                continue
            if not scope_key:
                scope_key = candidate_scope_key
                scope_payload = _principal_scope_payload_from_metadata(metadata)
                continue
            if candidate_scope_key != scope_key:
                return "", {}
            if not scope_payload:
                scope_payload = _principal_scope_payload_from_metadata(metadata)
        return scope_key, scope_payload

    @_locked
    def _backfill_legacy_principal_scoped_profiles_if_needed(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, source, metadata_json
            FROM profile_items
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()
        migrated = 0
        for row in rows:
            item = _profile_row_to_dict(row)
            stable_key = str(item.get("stable_key") or "").strip()
            category = str(item.get("category") or "").strip()
            if not _is_principal_scoped_profile(stable_key=stable_key, category=category):
                continue
            if str(item.get("principal_scope_key") or "").strip():
                continue
            metadata = dict(item.get("metadata") or {})
            raw_provenance = metadata.get("provenance")
            provenance: Dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
            session_id = str(provenance.get("session_id") or "").strip()
            if not session_id:
                continue
            principal_scope_key, principal_scope = self._resolve_session_principal_scope(session_id=session_id)
            if not principal_scope_key:
                continue
            storage_key = str(item.get("storage_key") or row["stable_key"] or "").strip()
            scoped_storage_key = _profile_storage_key(
                stable_key=stable_key,
                category=category,
                principal_scope_key=principal_scope_key,
            )
            if not scoped_storage_key or scoped_storage_key == storage_key:
                continue
            migrated_metadata = dict(metadata)
            migrated_metadata.setdefault("principal_scope_key", principal_scope_key)
            if principal_scope:
                migrated_metadata.setdefault("principal_scope", dict(principal_scope))
            existing = self.conn.execute(
                "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
                (scoped_storage_key,),
            ).fetchone()
            if existing:
                merged_metadata = _merge_record_metadata(
                    existing["metadata_json"],
                    migrated_metadata,
                    source=str(row["source"] or ""),
                )
                self.conn.execute(
                    "UPDATE profile_items SET metadata_json = ? WHERE id = ?",
                    (
                        json.dumps(merged_metadata, ensure_ascii=True, sort_keys=True),
                        int(existing["id"]),
                    ),
                )
                self.conn.execute(
                    "UPDATE profile_items SET active = 0 WHERE id = ?",
                    (int(row["id"]),),
                )
                self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (int(row["id"]),))
            else:
                merged_metadata = _merge_record_metadata(
                    row["metadata_json"],
                    migrated_metadata,
                    source=str(row["source"] or ""),
                )
                self.conn.execute(
                    "UPDATE profile_items SET stable_key = ?, metadata_json = ? WHERE id = ?",
                    (
                        scoped_storage_key,
                        json.dumps(merged_metadata, ensure_ascii=True, sort_keys=True),
                        int(row["id"]),
                    ),
                )
            migrated += 1
        if migrated:
            self.conn.commit()
            logger.info("Backfilled %s legacy principal-scoped profile rows", migrated)

    @_locked
    def _run_compatibility_migrations_if_needed(self) -> None:
        run_compatibility_migrations(self)

    def _migration_applied(self, name: str) -> bool:
        return migration_applied(self.conn, name)

    def _mark_migration_applied(self, name: str) -> None:
        mark_migration_applied(self.conn, name)

    def _apply_graph_source_lineage_migration_v1(self) -> None:
        migrated = 0
        row_specs = (
            ("graph_states", "state", "source"),
            ("graph_relations", "relation", "source"),
            ("graph_inferred_relations", "inferred_relation", "source"),
            ("graph_conflicts", "state_conflict", "candidate_source"),
        )
        for table_name, graph_kind, source_column in row_specs:
            rows = self.conn.execute(
                f"SELECT id, {source_column} AS source, metadata_json FROM {table_name} ORDER BY id ASC"
            ).fetchall()
            for row in rows:
                existing = _decode_json_object(row["metadata_json"])
                updated = attach_graph_source_lineage(
                    existing,
                    source=str(row["source"] or ""),
                    graph_kind=graph_kind,
                )
                if updated == existing:
                    continue
                self.conn.execute(
                    f"UPDATE {table_name} SET metadata_json = ? WHERE id = ?",
                    (
                        json.dumps(updated, ensure_ascii=True, sort_keys=True),
                        int(row["id"]),
                    ),
                )
                migrated += 1
        self._mark_migration_applied(MIGRATION_GRAPH_SOURCE_LINEAGE_V1)
        self.conn.commit()
        if migrated:
            self._refresh_semantic_evidence_shelf(
                shelf="graph",
                metadata={"migration": MIGRATION_GRAPH_SOURCE_LINEAGE_V1},
            )

    @_locked
    def _apply_recent_work_authority_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, record_type, source, metadata_json
            FROM operating_records
            WHERE record_type = ?
            ORDER BY id ASC
            """,
            (OPERATING_RECORD_RECENT_WORK_SUMMARY,),
        ).fetchall()
        migrated = 0
        for row in rows:
            metadata = normalize_operating_record_metadata(
                record_type=str(row["record_type"] or ""),
                stable_key=str(row["stable_key"] or ""),
                source=str(row["source"] or ""),
                metadata=_decode_json_object(row["metadata_json"]),
            )
            previous = _decode_json_object(row["metadata_json"])
            if metadata == previous:
                continue
            self.conn.execute(
                "UPDATE operating_records SET metadata_json = ?, updated_at = updated_at WHERE id = ?",
                (
                    json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                    int(row["id"]),
                ),
            )
            migrated += 1
        self._mark_migration_applied(MIGRATION_RECENT_WORK_AUTHORITY_V1)
        self.conn.commit()
        if migrated:
            self._refresh_semantic_evidence_shelf(
                shelf="operating",
                principal_scope_key="",
                metadata={"migration": MIGRATION_RECENT_WORK_AUTHORITY_V1},
            )

    @_locked
    def _apply_canonical_communication_rows_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json
            FROM profile_items
            WHERE active = 1
            ORDER BY id ASC
            """
        ).fetchall()
        migrated = 0
        for row in rows:
            item = _profile_row_to_dict(row)
            stable_key = str(item.get("stable_key") or "").strip()
            if not stable_key.startswith("preference:"):
                continue
            if stable_key in COMMUNICATION_CANONICAL_SLOTS:
                continue
            principal_scope_key = str(item.get("principal_scope_key") or "").strip()
            if not principal_scope_key:
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            confidence = float(item.get("confidence") or 0.78)
            expanded = expand_communication_profile_items(
                category="preference",
                content=content,
                slot=stable_key,
                confidence=confidence,
                source="tier2_compat_backfill",
            )
            if not expanded:
                continue
            metadata = dict(item.get("metadata") or {})
            metadata.setdefault("principal_scope_key", principal_scope_key)
            for candidate in expanded:
                self.upsert_profile_item(
                    stable_key=str(candidate["slot"]),
                    category=str(candidate["category"]),
                    content=str(candidate["content"]),
                    source=str(candidate.get("source") or row["source"] or "tier2_compat_backfill"),
                    confidence=float(candidate.get("confidence") or confidence),
                    metadata=metadata,
                )
            self.conn.execute("UPDATE profile_items SET active = 0 WHERE id = ?", (int(row["id"]),))
            self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (int(row["id"]),))
            migrated += 1
        self._mark_migration_applied(MIGRATION_CANONICAL_COMMUNICATION_ROWS_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s legacy communication contract rows", migrated)
        else:
            logger.info("Applied canonical communication compatibility migration with no legacy rows to rewrite")

    @_locked
    def _apply_explicit_identity_backfill_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            if self.get_profile_item(
                stable_key="identity:age",
                principal_scope_key=principal_scope_key,
            ):
                continue
            candidates = derive_transcript_identity_profile_items(
                entries,
                existing_items=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                if str(candidate.get("slot") or "").strip() != "identity:age":
                    continue
                candidate_metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    candidate_metadata["principal_scope"] = principal_scope
                self.upsert_profile_item(
                    stable_key="identity:age",
                    category=str(candidate.get("category") or "identity"),
                    content=str(candidate.get("content") or "").strip(),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    confidence=float(candidate.get("confidence") or 0.88),
                    metadata=candidate_metadata,
                )
                migrated += 1

        self._mark_migration_applied(MIGRATION_EXPLICIT_IDENTITY_BACKFILL_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s explicit identity rows from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied explicit identity compatibility migration with no eligible transcript rows")

    @_locked
    def _apply_stable_logistics_typed_entities_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            candidates = derive_transcript_logistics_typed_entities(
                entries,
                existing_entities=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                candidate_metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    candidate_metadata["principal_scope"] = principal_scope
                if isinstance(candidate.get("temporal"), dict):
                    candidate_metadata["temporal"] = dict(candidate["temporal"])
                actions = self.upsert_typed_entity(
                    entity_name=str(candidate.get("name") or "").strip(),
                    entity_type=str(candidate.get("entity_type") or "").strip(),
                    subject_name=str(candidate.get("subject") or "User").strip() or "User",
                    attributes=dict(candidate.get("attributes") or {}),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    metadata=candidate_metadata,
                )
                if actions:
                    migrated += 1

        self._mark_migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V1)
        self.conn.commit()
        if migrated:
            logger.info("Backfilled %s stable logistics typed entities from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied stable logistics compatibility migration with no eligible transcript rows")

    @_locked
    def _apply_stable_logistics_typed_entities_migration_v2(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, session_id, turn_number, kind, content, source, metadata_json, created_at
            FROM transcript_entries
            ORDER BY id ASC
            """
        ).fetchall()
        scoped_entries: Dict[str, List[Dict[str, Any]]] = {}
        scope_payloads: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _row_to_dict(row)
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            scoped_entries.setdefault(principal_scope_key, []).append(item)
            if principal_scope_key not in scope_payloads:
                payload = _principal_scope_payload_from_metadata(metadata)
                if payload:
                    scope_payloads[principal_scope_key] = payload

        migrated = 0
        for principal_scope_key, entries in scoped_entries.items():
            candidates = derive_transcript_logistics_typed_entities(
                entries,
                existing_entities=[],
                source="tier2_compat_backfill",
            )
            for candidate in candidates:
                candidate_metadata: Dict[str, Any] = {
                    "principal_scope_key": principal_scope_key,
                    "provenance": {
                        "source_ids": [f"migration:{MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2}"],
                        "tier": "migration",
                    },
                }
                principal_scope = scope_payloads.get(principal_scope_key)
                if principal_scope:
                    candidate_metadata["principal_scope"] = principal_scope
                if isinstance(candidate.get("temporal"), dict):
                    candidate_metadata["temporal"] = dict(candidate["temporal"])
                actions = self.upsert_typed_entity(
                    entity_name=str(candidate.get("name") or "").strip(),
                    entity_type=str(candidate.get("entity_type") or "").strip(),
                    subject_name=str(candidate.get("subject") or "User").strip() or "User",
                    attributes=dict(candidate.get("attributes") or {}),
                    source=str(candidate.get("source") or "tier2_compat_backfill"),
                    metadata=candidate_metadata,
                    supersede_existing=True,
                )
                if actions:
                    migrated += 1

        self._mark_migration_applied(MIGRATION_STABLE_LOGISTICS_TYPED_ENTITIES_V2)
        self.conn.commit()
        if migrated:
            logger.info("Repaired %s stable logistics typed entities from principal-scoped transcript history", migrated)
        else:
            logger.info("Applied stable logistics repair migration with no eligible transcript rows")

    @_locked
    def _apply_style_contract_profile_lane_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, title, metadata_json, updated_at, active
            FROM corpus_documents
            WHERE active = 1 AND doc_kind = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (STYLE_CONTRACT_DOC_KIND,),
        ).fetchall()
        grouped: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            principal_scope_key = _principal_scope_key_from_metadata(metadata)
            if not principal_scope_key:
                continue
            grouped.setdefault(principal_scope_key, []).append(row)

        migrated = 0
        retired = 0
        for principal_scope_key, documents in grouped.items():
            active_profile = self.get_profile_item(
                stable_key=STYLE_CONTRACT_SLOT,
                principal_scope_key=principal_scope_key,
            )
            selected_document = documents[0] if documents else None
            if not active_profile and selected_document is not None:
                section_rows = self.conn.execute(
                    """
                    SELECT section_index, heading, content
                    FROM corpus_sections
                    WHERE document_id = ?
                    ORDER BY section_index ASC
                    """,
                    (int(selected_document["id"]),),
                ).fetchall()
                metadata = _decode_json_object(selected_document["metadata_json"])
                principal_scope = _principal_scope_payload_from_metadata(metadata)
                candidate = build_style_contract_from_document(
                    title=selected_document["title"],
                    sections=[dict(section) for section in section_rows],
                    source="tier2_compat_backfill",
                    confidence=0.9,
                )
                if candidate is not None:
                    merged_metadata: Dict[str, Any] = {
                        "principal_scope_key": principal_scope_key,
                        "provenance": {
                            "source_ids": [
                                f"migration:{MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1}",
                                f"corpus_document:{selected_document['stable_key']}",
                            ],
                            "tier": "migration",
                        },
                    }
                    if principal_scope:
                        merged_metadata["principal_scope"] = principal_scope
                    merged_metadata.update(dict(candidate.get("metadata") or {}))
                    self.upsert_profile_item(
                        stable_key=STYLE_CONTRACT_SLOT,
                        category=str(candidate.get("category") or "preference"),
                        content=str(candidate.get("content") or "").strip(),
                        source=str(candidate.get("source") or "tier2_compat_backfill"),
                        confidence=float(candidate.get("confidence") or 0.9),
                        metadata=merged_metadata,
                    )
                    migrated += 1
                    active_profile = self.get_profile_item(
                        stable_key=STYLE_CONTRACT_SLOT,
                        principal_scope_key=principal_scope_key,
                    )
            if not active_profile:
                continue
            for document in documents:
                if not bool(document["active"]):
                    continue
                self.conn.execute(
                    "UPDATE corpus_documents SET active = 0, updated_at = ? WHERE id = ?",
                    (utc_now_iso(), int(document["id"])),
                )
                retired += 1

        self._mark_migration_applied(MIGRATION_STYLE_CONTRACT_PROFILE_LANE_V1)
        self.conn.commit()
        if migrated or retired:
            logger.info(
                "Migrated %s style contracts into canonical profile lane and retired %s corpus documents",
                migrated,
                retired,
            )
        else:
            logger.info("Applied style-contract profile-lane migration with no eligible corpus documents")

    @_locked
    def _apply_behavior_contract_storage_migration_v1(self) -> None:
        self._mark_migration_applied(MIGRATION_BEHAVIOR_CONTRACT_STORAGE_V1)
        self.conn.commit()
        logger.info("Behavior-contract storage migration is disabled; style contracts remain in the profile lane")

    @_locked
    def _apply_style_contract_behavior_demotion_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE stable_key = ?
            ORDER BY principal_scope_key ASC, revision_number DESC, id DESC
            """,
            (STYLE_CONTRACT_SLOT,),
        ).fetchall()
        grouped: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["principal_scope_key"] or "").strip(), []).append(row)

        migrated = 0
        retired = 0
        deleted_policies = 0
        now = utc_now_iso()
        for principal_scope_key, scoped_rows in grouped.items():
            chosen_row: sqlite3.Row | None = None
            for row in scoped_rows:
                if str(row["status"] or "").strip() == BEHAVIOR_CONTRACT_ACTIVE_STATUS:
                    chosen_row = row
                    break
            if chosen_row is None and scoped_rows:
                chosen_row = scoped_rows[0]

            if chosen_row is not None:
                item = _behavior_contract_row_to_dict(chosen_row)
                self.upsert_profile_item(
                    stable_key=STYLE_CONTRACT_SLOT,
                    category=str(item.get("category") or "preference"),
                    content=str(item.get("content") or "").strip(),
                    source=str(item.get("source") or "").strip(),
                    confidence=float(item.get("confidence") or 0.9),
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                    active=True,
                )
                migrated += 1

            for row in scoped_rows:
                if str(row["status"] or "").strip() != BEHAVIOR_CONTRACT_ACTIVE_STATUS:
                    continue
                self.conn.execute(
                    "UPDATE behavior_contracts SET status = ?, updated_at = ? WHERE id = ?",
                    (BEHAVIOR_CONTRACT_SUPERSEDED_STATUS, now, int(row["id"])),
                )
                retired += 1

            deleted_policies += int(
                self.conn.execute(
                    "DELETE FROM compiled_behavior_policies WHERE principal_scope_key = ?",
                    (principal_scope_key,),
                ).rowcount
                or 0
            )

        self._mark_migration_applied(MIGRATION_STYLE_CONTRACT_BEHAVIOR_DEMOTION_V1)
        self.conn.commit()
        logger.info(
            "Demoted %s style-contract behavior authorities into the profile lane, retired %s active behavior contracts, deleted %s compiled policies",
            migrated,
            retired,
            deleted_policies,
        )

    def _upsert_compiled_behavior_policy_record(
        self,
        *,
        principal_scope_key: str,
        compiled_policy: Dict[str, Any],
    ) -> None:
        scope_key = str(principal_scope_key or "").strip()
        if compiled_policy is None:
            return
        now = utc_now_iso()
        self.conn.execute(
            """
            INSERT INTO compiled_behavior_policies (
                principal_scope_key,
                source_storage_key,
                source_contract_hash,
                source_contract_updated_at,
                schema_version,
                compiler_version,
                title,
                policy_json,
                projection_text,
                status,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(principal_scope_key) DO UPDATE SET
                source_storage_key = excluded.source_storage_key,
                source_contract_hash = excluded.source_contract_hash,
                source_contract_updated_at = excluded.source_contract_updated_at,
                schema_version = excluded.schema_version,
                compiler_version = excluded.compiler_version,
                title = excluded.title,
                policy_json = excluded.policy_json,
                projection_text = excluded.projection_text,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                scope_key,
                str(compiled_policy.get("source_storage_key") or "").strip(),
                str(compiled_policy.get("source_contract_hash") or "").strip(),
                str(compiled_policy.get("source_contract_updated_at") or "").strip(),
                int(compiled_policy.get("schema_version") or BEHAVIOR_POLICY_SCHEMA_VERSION),
                str(compiled_policy.get("compiler_version") or BEHAVIOR_POLICY_COMPILER_VERSION),
                str(compiled_policy.get("title") or "").strip(),
                json.dumps(compiled_policy, ensure_ascii=True, sort_keys=True),
                str(compiled_policy.get("projection_text") or "").strip(),
                str(compiled_policy.get("status") or "active").strip() or "active",
                now,
            ),
        )

    def _delete_compiled_behavior_policy_record(self, *, principal_scope_key: str) -> None:
        scope_key = str(principal_scope_key or "").strip()
        if not scope_key:
            return
        self.conn.execute(
            "DELETE FROM compiled_behavior_policies WHERE principal_scope_key = ?",
            (scope_key,),
        )

    def _get_compiled_behavior_policy_row(self, *, principal_scope_key: str) -> sqlite3.Row | None:
        scope_key = str(principal_scope_key or "").strip()
        if not scope_key:
            return None
        return self.conn.execute(
            """
            SELECT principal_scope_key, source_storage_key, source_contract_hash, source_contract_updated_at,
                   schema_version, compiler_version, title, policy_json, projection_text, status, updated_at
            FROM compiled_behavior_policies
            WHERE principal_scope_key = ?
            LIMIT 1
            """,
            (scope_key,),
        ).fetchone()

    def _build_compiled_behavior_policy_from_contract_item(self, item: Mapping[str, Any]) -> Dict[str, Any] | None:
        if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT:
            return None
        return compile_behavior_policy(
            raw_content=str(item.get("content") or ""),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            source_storage_key=str(item.get("storage_key") or ""),
            source_updated_at=str(item.get("updated_at") or ""),
            source_revision_number=int(item.get("revision_number") or 0),
        )

    def _ensure_compiled_behavior_policy_for_contract_item(
        self,
        item: Mapping[str, Any],
    ) -> Dict[str, Any] | None:
        compiled = self._build_compiled_behavior_policy_from_contract_item(item)
        principal_scope_key = str(item.get("principal_scope_key") or "").strip()
        if not compiled:
            self._delete_compiled_behavior_policy_record(principal_scope_key=principal_scope_key)
            return None
        self._upsert_compiled_behavior_policy_record(
            principal_scope_key=principal_scope_key,
            compiled_policy=compiled,
        )
        return compiled

    def _deactivate_style_authority_profile_residue(self, *, principal_scope_key: str) -> int:
        scope_key = str(principal_scope_key or "").strip()
        if not scope_key:
            return 0
        rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE active = 1
            ORDER BY updated_at DESC, id DESC
            """
        ).fetchall()
        updated = 0
        now = utc_now_iso()
        for row in rows:
            item = _profile_row_to_dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=scope_key):
                continue
            logical_key = normalize_profile_slot(str(item.get("stable_key") or ""))
            if (
                logical_key != "preference:communication_rules"
                and logical_key not in COMMUNICATION_CANONICAL_SLOTS
            ):
                continue
            metadata = _merge_record_metadata(
                row["metadata_json"],
                {
                    "repair_action": "deactivated_style_authority_residue",
                    "repair_scope": scope_key,
                    "repair_logical_key": logical_key,
                },
                source="behavior_contract_repair",
            )
            self.conn.execute(
                """
                UPDATE profile_items
                SET active = 0, metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(metadata, ensure_ascii=True, sort_keys=True), now, int(row["id"])),
            )
            self.conn.execute("DELETE FROM profile_fts WHERE rowid = ?", (int(row["id"]),))
            updated += 1
        return updated

    def _rebuild_compiled_behavior_policy_from_behavior_contract_row(self, row: sqlite3.Row) -> bool:
        item = _behavior_contract_row_to_dict(row)
        compiled = self._build_compiled_behavior_policy_from_contract_item(item)
        if not compiled:
            self._delete_compiled_behavior_policy_record(
                principal_scope_key=str(item.get("principal_scope_key") or ""),
            )
            return False
        self._upsert_compiled_behavior_policy_record(
            principal_scope_key=str(item.get("principal_scope_key") or ""),
            compiled_policy=compiled,
        )
        return True

    @_locked
    def _apply_compiled_behavior_policy_migration_v1(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE status = ?
            ORDER BY revision_number DESC, id DESC
            """
            ,
            (BEHAVIOR_CONTRACT_ACTIVE_STATUS,),
        ).fetchall()
        rebuilt = 0
        for row in rows:
            if self._rebuild_compiled_behavior_policy_from_behavior_contract_row(row):
                rebuilt += 1
        self._mark_migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V1)
        self.conn.commit()
        if rebuilt:
            logger.info("Built %s compiled behavior policies from canonical behavior-contract rows", rebuilt)
        else:
            logger.info("Applied compiled behavior policy migration with no eligible behavior-contract rows")

    @_locked
    def _apply_compiled_behavior_policy_migration_v2(self) -> None:
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE status = ?
            ORDER BY revision_number DESC, id DESC
            """
            ,
            (BEHAVIOR_CONTRACT_ACTIVE_STATUS,),
        ).fetchall()
        rebuilt = 0
        for row in rows:
            if self._rebuild_compiled_behavior_policy_from_behavior_contract_row(row):
                rebuilt += 1
        self._mark_migration_applied(MIGRATION_COMPILED_BEHAVIOR_POLICY_V2)
        self.conn.commit()
        if rebuilt:
            logger.info("Rebuilt %s compiled behavior policies for compiler v2", rebuilt)
        else:
            logger.info("Applied compiled behavior policy v2 migration with no eligible style-contract rows")

    def _init_schema(self) -> None:
        initialize_schema(self.conn)
