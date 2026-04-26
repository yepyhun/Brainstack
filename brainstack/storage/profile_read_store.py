from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_QUARANTINED_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    Dict,
    Iterable,
    List,
    PROFILE_SCOPE_DELIMITER,
    STYLE_CONTRACT_SLOT,
    _annotate_principal_scope,
    _attach_keyword_scores,
    _behavior_contract_row_to_dict,
    _decode_json_object,
    _is_principal_scoped_profile,
    _locked,
    _profile_row_to_dict,
    _profile_storage_key,
    _row_to_dict,
    _scoped_row_priority,
    apply_retrieval_telemetry,
    build_fts_query,
    json,
    profile_priority_adjustment,
    record_is_effective_at,
    sqlite3,
    style_contract_cleanliness_issues,
    utc_now_iso,
)

class ProfileReadStoreMixin(StoreRuntimeBase):
    @_locked
    def list_profile_items(
        self,
        *,
        limit: int,
        categories: Iterable[str] | None = None,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        params: list[Any] = []
        fetch_limit = max(limit * 4, 16) if principal_scope_key else limit
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
        params.append(fetch_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        parsed_by_key: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            item = _profile_row_to_dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            logical_key = str(item.get("stable_key") or "").strip() or str(item.get("storage_key") or "")
            existing = parsed_by_key.get(logical_key)
            if existing is None or _scoped_row_priority(item, principal_scope_key=principal_scope_key) > _scoped_row_priority(
                existing,
                principal_scope_key=principal_scope_key,
            ):
                parsed_by_key[logical_key] = item
        parsed = sorted(
            parsed_by_key.values(),
            key=lambda item: _scoped_row_priority(item, principal_scope_key=principal_scope_key),
            reverse=True,
        )
        return parsed[:limit]

    @_locked
    def list_current_graph_states(
        self,
        *,
        limit: int,
        subjects: Iterable[str] | None = None,
        attributes: Iterable[str] | None = None,
        principal_scope_key: str = "",
    ) -> List[Dict[str, Any]]:
        params: list[Any] = []
        fetch_limit = max(limit * 4, 16) if principal_scope_key else limit
        sql = """
            SELECT
                gs.id AS row_id,
                'state' AS row_type,
                e.canonical_name AS subject,
                gs.attribute AS predicate,
                gs.value_text AS object_value,
                gs.source,
                gs.metadata_json,
                gs.valid_from AS created_at,
                gs.valid_from,
                gs.valid_to,
                gs.is_current
            FROM graph_states gs
            JOIN graph_entities e ON e.id = gs.entity_id
            WHERE gs.is_current = 1
        """
        if subjects:
            normalized_subjects = [" ".join(str(value or "").strip().lower().split()) for value in subjects if str(value or "").strip()]
            if normalized_subjects:
                sql += f" AND lower(e.canonical_name) IN ({','.join('?' for _ in normalized_subjects)})"
                params.extend(normalized_subjects)
        if attributes:
            normalized_attributes = [" ".join(str(value or "").strip().lower().split()) for value in attributes if str(value or "").strip()]
            if normalized_attributes:
                sql += f" AND lower(gs.attribute) IN ({','.join('?' for _ in normalized_attributes)})"
                params.extend(normalized_attributes)
        sql += " ORDER BY gs.valid_from DESC, gs.id DESC LIMIT ?"
        params.append(fetch_limit)
        rows = self.conn.execute(sql, tuple(params)).fetchall()
        parsed: List[Dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            if not record_is_effective_at(item):
                continue
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            parsed.append(item)
        return parsed[:limit]

    @_locked
    def get_profile_item(self, *, stable_key: str, principal_scope_key: str = "") -> Dict[str, Any] | None:
        storage_key = _profile_storage_key(
            stable_key=stable_key,
            principal_scope_key=principal_scope_key,
        )
        row = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE stable_key = ?
            LIMIT 1
            """,
            (storage_key,),
        ).fetchone()
        if row:
            return _profile_row_to_dict(row)
        if not principal_scope_key or not _is_principal_scoped_profile(stable_key=stable_key):
            return None
        like_pattern = f"{str(stable_key or '').strip()}{PROFILE_SCOPE_DELIMITER}%"
        candidate_rows = self.conn.execute(
            """
            SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at, active
            FROM profile_items
            WHERE active = 1 AND stable_key LIKE ?
            ORDER BY confidence DESC, updated_at DESC, id DESC
            LIMIT 16
            """,
            (like_pattern,),
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for candidate_row in candidate_rows:
            item = _profile_row_to_dict(candidate_row)
            if _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: _scoped_row_priority(item, principal_scope_key=principal_scope_key),
            reverse=True,
        )
        return candidates[0]

    @_locked
    def get_behavior_contract(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        principal_scope_key: str = "",
    ) -> Dict[str, Any] | None:
        requested_scope_key = str(principal_scope_key or "").strip()
        row = self._get_active_behavior_contract_row(
            stable_key=stable_key,
            principal_scope_key=requested_scope_key,
        )
        if row:
            return _behavior_contract_row_to_dict(row)
        if not requested_scope_key:
            return None
        candidate_rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE stable_key = ? AND status = ?
            ORDER BY committed_at DESC, revision_number DESC, id DESC
            LIMIT 16
            """,
            (
                str(stable_key or "").strip() or STYLE_CONTRACT_SLOT,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS,
            ),
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for candidate_row in candidate_rows:
            item = _behavior_contract_row_to_dict(candidate_row)
            if _annotate_principal_scope(item, principal_scope_key=requested_scope_key):
                candidates.append(item)
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: _scoped_row_priority(item, principal_scope_key=requested_scope_key),
            reverse=True,
        )
        return candidates[0]

    @_locked
    def repair_behavior_contract_authority(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        principal_scope_key: str = "",
    ) -> Dict[str, Any]:
        requested_scope_key = str(principal_scope_key or "").strip()
        logical_key = str(stable_key or "").strip() or STYLE_CONTRACT_SLOT
        rows = self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE stable_key = ?
            ORDER BY revision_number DESC, id DESC
            LIMIT 32
            """,
            (logical_key,),
        ).fetchall()
        candidates: List[Dict[str, Any]] = []
        for row in rows:
            item = _behavior_contract_row_to_dict(row)
            if requested_scope_key and not _annotate_principal_scope(item, principal_scope_key=requested_scope_key):
                continue
            candidates.append(item)

        report: Dict[str, Any] = {
            "surface": "behavior_contract_repair",
            "requested_scope_key": requested_scope_key,
            "stable_key": logical_key,
            "candidate_count": len(candidates),
            "quarantined_ids": [],
            "superseded_ids": [],
            "reactivated_id": 0,
            "compiled_policy_rebuilt": False,
            "compiled_policy_deleted": False,
            "deactivated_profile_residue_count": 0,
        }
        if not candidates:
            return report

        clean_candidates = [
            item
            for item in candidates
            if not style_contract_cleanliness_issues(
                raw_text=str(item.get("content") or ""),
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            )
        ]
        chosen = clean_candidates[0] if clean_candidates else None
        now = utc_now_iso()

        for item in candidates:
            row_id = int(item.get("id") or 0)
            if row_id <= 0 or str(item.get("status") or "").strip() != BEHAVIOR_CONTRACT_ACTIVE_STATUS:
                continue
            is_dirty = bool(
                style_contract_cleanliness_issues(
                    raw_text=str(item.get("content") or ""),
                    metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
                )
            )
            if chosen and row_id == int(chosen.get("id") or 0) and not is_dirty:
                continue
            next_status = BEHAVIOR_CONTRACT_QUARANTINED_STATUS if is_dirty else BEHAVIOR_CONTRACT_SUPERSEDED_STATUS
            self.conn.execute(
                "UPDATE behavior_contracts SET status = ?, updated_at = ? WHERE id = ?",
                (next_status, now, row_id),
            )
            key = "quarantined_ids" if next_status == BEHAVIOR_CONTRACT_QUARANTINED_STATUS else "superseded_ids"
            report[key].append(row_id)

        active_scope_key = requested_scope_key
        if chosen:
            active_scope_key = str(chosen.get("principal_scope_key") or "").strip() or requested_scope_key
            if str(chosen.get("status") or "").strip() != BEHAVIOR_CONTRACT_ACTIVE_STATUS:
                self.conn.execute(
                    "UPDATE behavior_contracts SET status = ?, updated_at = ? WHERE id = ?",
                    (BEHAVIOR_CONTRACT_ACTIVE_STATUS, now, int(chosen["id"])),
                )
                report["reactivated_id"] = int(chosen["id"])
            rebuilt = self._ensure_compiled_behavior_policy_for_contract_item(chosen)
            report["compiled_policy_rebuilt"] = bool(rebuilt)
            if not rebuilt:
                report["compiled_policy_deleted"] = True
            report["active_generation_revision"] = int(chosen.get("revision_number") or 0)
            report["active_generation_storage_key"] = str(chosen.get("storage_key") or "")
        else:
            self._delete_compiled_behavior_policy_record(principal_scope_key=active_scope_key)
            report["compiled_policy_deleted"] = True
            report["active_generation_revision"] = 0
            report["active_generation_storage_key"] = ""

        if active_scope_key:
            report["deactivated_profile_residue_count"] = self._deactivate_style_authority_profile_residue(
                principal_scope_key=active_scope_key
            )
        self.conn.commit()
        return report

    @_locked
    def purge_style_contract_behavior_residue(self) -> Dict[str, Any]:
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
        if not rows:
            deleted_policies = int(
                self.conn.execute("DELETE FROM compiled_behavior_policies WHERE source_storage_key LIKE ?", (f"{STYLE_CONTRACT_SLOT}%",)).rowcount
                or 0
            )
            if deleted_policies:
                self.conn.commit()
            return {
                "migrated_to_profile_lane": 0,
                "deleted_behavior_contract_rows": 0,
                "deleted_compiled_policies": deleted_policies,
                "principal_scope_keys": [],
            }

        grouped: Dict[str, List[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["principal_scope_key"] or "").strip(), []).append(row)

        migrated = 0
        deleted_behavior_rows = 0
        deleted_compiled_policies = 0
        principal_scope_keys: List[str] = []
        for principal_scope_key, scoped_rows in grouped.items():
            if principal_scope_key and principal_scope_key not in principal_scope_keys:
                principal_scope_keys.append(principal_scope_key)
            chosen_row = scoped_rows[0]
            for row in scoped_rows:
                if str(row["status"] or "").strip() == BEHAVIOR_CONTRACT_ACTIVE_STATUS:
                    chosen_row = row
                    break
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
            deleted_behavior_rows += int(
                self.conn.execute(
                    "DELETE FROM behavior_contracts WHERE principal_scope_key = ? AND stable_key = ?",
                    (principal_scope_key, STYLE_CONTRACT_SLOT),
                ).rowcount
                or 0
            )
            deleted_compiled_policies += int(
                self.conn.execute(
                    "DELETE FROM compiled_behavior_policies WHERE principal_scope_key = ?",
                    (principal_scope_key,),
                ).rowcount
                or 0
            )

        self.conn.commit()
        return {
            "migrated_to_profile_lane": migrated,
            "deleted_behavior_contract_rows": deleted_behavior_rows,
            "deleted_compiled_policies": deleted_compiled_policies,
            "principal_scope_keys": principal_scope_keys,
        }

    @_locked
    def record_profile_retrievals(self, *, rows: Iterable[Dict[str, Any]]) -> int:
        updated = 0
        now = utc_now_iso()
        for row in rows:
            logical_stable_key = str(row.get("stable_key") or "").strip()
            storage_key = str(row.get("storage_key") or "").strip()
            if not storage_key:
                storage_key = _profile_storage_key(
                    stable_key=logical_stable_key,
                    category=str(row.get("category") or ""),
                    principal_scope_key=str(row.get("principal_scope_key") or ""),
                )
            if not storage_key:
                continue
            existing = self.conn.execute(
                "SELECT id, metadata_json FROM profile_items WHERE stable_key = ?",
                (storage_key,),
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
    def search_profile(
        self,
        *,
        query: str,
        limit: int,
        principal_scope_key: str = "",
        target_slots: Iterable[str] | None = None,
        excluded_slots: Iterable[str] | None = None,
    ) -> List[Dict[str, Any]]:
        fts_query = build_fts_query(query)
        rows: List[sqlite3.Row]
        candidate_limit = max(limit * 8, 16)
        targeted: List[Dict[str, Any]] = []
        seen_storage_keys: set[str] = set()
        excluded = {str(slot or "").strip() for slot in (excluded_slots or ()) if str(slot or "").strip()}
        for stable_key in target_slots or ():
            normalized_key = str(stable_key or "").strip()
            if not normalized_key:
                continue
            item = self.get_profile_item(
                stable_key=normalized_key,
                principal_scope_key=principal_scope_key,
            )
            if not item or not bool(item.get("active", True)):
                continue
            storage_key = str(item.get("storage_key") or "")
            if storage_key and storage_key in seen_storage_keys:
                continue
            seen_storage_keys.add(storage_key)
            item["keyword_score"] = 2.0
            item["retrieval_source"] = "profile.slot_target"
            item["match_mode"] = "slot"
            item["_direct_slot_match"] = True
            targeted.append(item)
        if not fts_query:
            rows = self.conn.execute(
                """
                SELECT id, stable_key, category, content, source, confidence, metadata_json, updated_at
                FROM profile_items
                WHERE active = 1
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (candidate_limit,),
            ).fetchall()
        else:
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
                    (fts_query, candidate_limit),
                ).fetchall()
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
                    (like, candidate_limit),
                ).fetchall()

        scored: List[Dict[str, Any]] = []
        scored.extend(targeted)
        for row in _attach_keyword_scores(_profile_row_to_dict(item) for item in rows):
            item = dict(row)
            if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                continue
            if str(item.get("stable_key") or "").strip() in excluded:
                continue
            storage_key = str(item.get("storage_key") or "")
            if storage_key and storage_key in seen_storage_keys:
                continue
            item["retrieval_source"] = "profile.keyword"
            item["match_mode"] = "keyword"
            item["_direct_slot_match"] = False
            scored.append(item)

        scored.sort(
            key=lambda item: (
                1 if bool(item.get("_direct_slot_match")) else 0,
                float(item.get("keyword_score") or 0.0),
                profile_priority_adjustment(item),
                float(item.get("confidence") or 0.0),
                str(item.get("updated_at") or ""),
                int(item.get("id") or 0),
            ),
            reverse=True,
        )
        return scored[:limit]
