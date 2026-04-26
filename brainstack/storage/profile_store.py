from __future__ import annotations

from .store_protocol import StoreRuntimeBase
from .store_runtime import (
    Any,
    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
    Dict,
    STYLE_CONTRACT_SLOT,
    _annotate_principal_scope,
    _behavior_contract_row_to_dict,
    _behavior_contract_storage_key,
    _compiled_behavior_policy_row_to_dict,
    _cursor_lastrowid,
    _enrich_record_metadata_with_literals,
    _locked,
    _merge_record_metadata,
    _principal_scope_key_from_metadata,
    _profile_storage_key,
    _scoped_row_priority,
    _should_preserve_existing_style_contract,
    apply_style_contract_rule_correction,
    build_behavior_policy_snapshot,
    build_live_system_state_snapshot,
    build_operating_context_snapshot,
    compile_behavior_policy,
    hashlib,
    json,
    list_style_contract_rules,
    sqlite3,
    style_contract_cleanliness_issues,
    utc_now_iso,
)

class ProfileStoreMixin(StoreRuntimeBase):
    def _get_active_behavior_contract_row(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        principal_scope_key: str = "",
    ) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT id, storage_key, principal_scope_key, stable_key, category, content, source, confidence,
                   metadata_json, source_contract_hash, revision_number, parent_revision_id, status,
                   committed_at, updated_at
            FROM behavior_contracts
            WHERE principal_scope_key = ? AND stable_key = ? AND status = ?
            ORDER BY revision_number DESC, id DESC
            LIMIT 1
            """,
            (
                str(principal_scope_key or "").strip(),
                str(stable_key or "").strip() or STYLE_CONTRACT_SLOT,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS,
            ),
        ).fetchone()

    @_locked
    def upsert_behavior_contract(
        self,
        *,
        stable_key: str = STYLE_CONTRACT_SLOT,
        category: str,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None = None,
        active: bool = True,
    ) -> int:
        now = utc_now_iso()
        principal_scope_key = _principal_scope_key_from_metadata(metadata)
        logical_key = str(stable_key or "").strip() or STYLE_CONTRACT_SLOT
        existing = self._get_active_behavior_contract_row(
            stable_key=logical_key,
            principal_scope_key=principal_scope_key,
        )
        if existing is None and principal_scope_key:
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
                    logical_key,
                    BEHAVIOR_CONTRACT_ACTIVE_STATUS,
                ),
            ).fetchall()
            fallback_existing: sqlite3.Row | None = None
            fallback_priority: tuple[int, float, str, int] | None = None
            for candidate_row in candidate_rows:
                item = _behavior_contract_row_to_dict(candidate_row)
                if not _annotate_principal_scope(item, principal_scope_key=principal_scope_key):
                    continue
                priority = _scoped_row_priority(item, principal_scope_key=principal_scope_key)
                if priority[0] <= 0:
                    continue
                if fallback_priority is None or priority > fallback_priority:
                    fallback_existing = candidate_row
                    fallback_priority = priority
            existing = fallback_existing
        normalized_metadata = _merge_record_metadata(
            existing["metadata_json"] if existing else None,
            _enrich_record_metadata_with_literals(metadata, text=content),
            source=source,
        )
        if existing and str(existing["content"] or "").strip() == str(content or "").strip():
            existing_item = _behavior_contract_row_to_dict(existing)
            self._ensure_compiled_behavior_policy_for_contract_item(existing_item)
            return int(existing["id"])
        if (
            existing
            and _should_preserve_existing_style_contract(
                existing_source=existing["source"],
                incoming_source=source,
                existing_content=existing["content"],
                existing_metadata=existing["metadata_json"],
                incoming_content=content,
                incoming_metadata=normalized_metadata,
            )
            and str(existing["content"] or "").strip() != str(content or "").strip()
        ):
            return int(existing["id"])
        metadata_json = json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True)
        if existing:
            existing_item = _behavior_contract_row_to_dict(existing)
            if (
                str(existing_item.get("content") or "").strip() == str(content or "").strip()
                and str(existing_item.get("source") or "").strip() == str(source or "").strip()
                and json.dumps(existing_item.get("metadata") or {}, ensure_ascii=True, sort_keys=True) == metadata_json
                and float(existing_item.get("confidence") or 0.0) == float(confidence)
                and bool(existing_item.get("active", False)) == bool(active)
            ):
                self._ensure_compiled_behavior_policy_for_contract_item(existing_item)
                return int(existing_item["id"])
            parent_revision_id = int(existing_item["id"])
            revision_number = int(existing_item.get("revision_number") or 0) + 1
        else:
            parent_revision_id = 0
            revision_number = 1
        storage_key = _behavior_contract_storage_key(
            stable_key=logical_key,
            principal_scope_key=principal_scope_key,
            revision_number=revision_number,
        )
        compiled = None
        if active:
            compiled = compile_behavior_policy(
                raw_content=content,
                metadata=normalized_metadata,
                source_storage_key=storage_key,
                source_updated_at=now,
                source_revision_number=revision_number,
            )
            if compiled is None:
                raise ValueError("Behavior contract commit failed because compiled behavior policy could not be built")
        if existing:
            self.conn.execute(
                """
                UPDATE behavior_contracts
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
                    now,
                    int(existing["id"]),
                ),
            )
        cur = self.conn.execute(
            """
            INSERT INTO behavior_contracts (
                storage_key,
                principal_scope_key,
                stable_key,
                category,
                content,
                source,
                confidence,
                metadata_json,
                source_contract_hash,
                revision_number,
                parent_revision_id,
                status,
                committed_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                storage_key,
                str(principal_scope_key or "").strip(),
                logical_key,
                category,
                content,
                source,
                confidence,
                metadata_json,
                hashlib.sha256(str(content or "").encode("utf-8")).hexdigest() if str(content or "") else "",
                revision_number,
                parent_revision_id,
                BEHAVIOR_CONTRACT_ACTIVE_STATUS if active else BEHAVIOR_CONTRACT_SUPERSEDED_STATUS,
                now,
                now,
            ),
        )
        row_id = _cursor_lastrowid(cur)
        if compiled is not None:
            self._upsert_compiled_behavior_policy_record(
                principal_scope_key=principal_scope_key,
                compiled_policy=compiled,
            )
        self.conn.commit()
        return row_id

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
        principal_scope_key = _principal_scope_key_from_metadata(metadata)
        storage_key = _profile_storage_key(
            stable_key=stable_key,
            category=category,
            principal_scope_key=principal_scope_key,
        )
        existing = self.conn.execute(
            "SELECT id, content, source, metadata_json FROM profile_items WHERE stable_key = ?",
            (storage_key,),
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
                    storage_key,
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
            row_id = _cursor_lastrowid(cur)

        self.conn.execute(
            "INSERT INTO profile_fts(rowid, content, category, stable_key) VALUES (?, ?, ?, ?)",
            (row_id, content, category, stable_key),
        )
        self.conn.commit()
        self._refresh_semantic_evidence_shelf(
            shelf="profile",
            principal_scope_key=principal_scope_key,
            metadata=normalized_metadata,
        )
        return row_id

    @_locked
    def get_compiled_behavior_policy(self, *, principal_scope_key: str = "") -> Dict[str, Any] | None:
        requested_scope_key = str(principal_scope_key or "").strip()
        contract = self.get_behavior_contract(principal_scope_key=requested_scope_key)
        if contract and style_contract_cleanliness_issues(
            raw_text=str(contract.get("content") or ""),
            metadata=contract.get("metadata") if isinstance(contract.get("metadata"), dict) else None,
        ):
            polluted_scope_key = str(contract.get("principal_scope_key") or "").strip() or requested_scope_key
            self._delete_compiled_behavior_policy_record(principal_scope_key=polluted_scope_key)
            self.conn.commit()
            return None
        row = self._get_compiled_behavior_policy_row(principal_scope_key=requested_scope_key)
        if row:
            compiled_item = _compiled_behavior_policy_row_to_dict(row)
            raw_hash = hashlib.sha256(str(contract.get("content") or "").encode("utf-8")).hexdigest() if contract else ""
            if contract and (
                str(compiled_item.get("source_contract_hash") or "").strip() != raw_hash
                or str(compiled_item.get("source_storage_key") or "").strip() != str(contract.get("storage_key") or "").strip()
            ):
                refreshed = self._ensure_compiled_behavior_policy_for_contract_item(contract)
                self.conn.commit()
                refreshed_row = (
                    self._get_compiled_behavior_policy_row(principal_scope_key=requested_scope_key) if refreshed else None
                )
                return _compiled_behavior_policy_row_to_dict(refreshed_row) if refreshed_row is not None else None
            return compiled_item
        if not requested_scope_key:
            return None
        if not contract:
            return None
        fallback_scope_key = str(contract.get("principal_scope_key") or "").strip()
        refreshed = self._ensure_compiled_behavior_policy_for_contract_item(contract)
        if refreshed:
            self.conn.commit()
            scope_key = fallback_scope_key or requested_scope_key
            rebuilt_row = self._get_compiled_behavior_policy_row(principal_scope_key=scope_key)
            return _compiled_behavior_policy_row_to_dict(rebuilt_row) if rebuilt_row else None
        if not fallback_scope_key or fallback_scope_key == requested_scope_key:
            return None
        fallback_row = self._get_compiled_behavior_policy_row(principal_scope_key=fallback_scope_key)
        return _compiled_behavior_policy_row_to_dict(fallback_row) if fallback_row else None

    @_locked
    def get_behavior_policy_snapshot(self, *, principal_scope_key: str = "") -> Dict[str, Any]:
        raw_contract = self.get_behavior_contract(principal_scope_key=principal_scope_key)
        compiled_policy = self.get_compiled_behavior_policy(principal_scope_key=principal_scope_key)
        snapshot = build_behavior_policy_snapshot(
            raw_contract_row=raw_contract,
            compiled_policy_record=compiled_policy,
        )
        snapshot["principal_scope_key"] = str(principal_scope_key or "").strip()
        return snapshot

    @_locked
    def get_operating_context_snapshot(
        self,
        *,
        principal_scope_key: str = "",
        session_id: str = "",
        stable_profile_limit: int = 4,
        continuity_limit: int = 12,
        decision_limit: int = 4,
    ) -> Dict[str, Any]:
        scope_key = str(principal_scope_key or "").strip()
        sid = str(session_id or "").strip()
        compiled_policy = self.get_compiled_behavior_policy(principal_scope_key=scope_key)
        profile_items = self.list_profile_items(
            limit=max(12, stable_profile_limit * 4),
            principal_scope_key=scope_key,
        )
        operating_rows = self.list_operating_records(
            principal_scope_key=scope_key,
            limit=16,
        )
        task_rows = self.list_task_items(
            principal_scope_key=scope_key,
            statuses=("open", "pending", "blocked", "in_progress"),
            limit=12,
        )
        continuity_rows = (
            self.recent_principal_continuity(
                principal_scope_key=scope_key,
                session_id=sid,
                kinds=("tier2_summary", "decision", "session_summary"),
                limit=max(continuity_limit, decision_limit * 2),
            )
            if scope_key
            else (self.recent_continuity(session_id=sid, limit=max(continuity_limit, decision_limit * 2)) if sid else [])
        )
        lifecycle_state = self.get_continuity_lifecycle_state(session_id=sid) if sid else None
        return build_operating_context_snapshot(
            principal_scope_key=scope_key,
            compiled_behavior_policy_record=compiled_policy,
            profile_items=profile_items,
            operating_rows=operating_rows,
            task_rows=task_rows,
            continuity_rows=continuity_rows,
            lifecycle_state=lifecycle_state,
            stable_profile_limit=stable_profile_limit,
            decision_limit=decision_limit,
        )

    @_locked
    def get_live_system_state_snapshot(
        self,
        *,
        principal_scope_key: str = "",
        limit: int = 8,
    ) -> Dict[str, Any]:
        return build_live_system_state_snapshot(
            principal_scope_key=str(principal_scope_key or "").strip(),
            limit=limit,
        )

    @_locked
    def apply_behavior_policy_correction(
        self,
        *,
        principal_scope_key: str = "",
        rule_id: str,
        replacement_text: Any,
        source: str = "behavior_policy_correction",
    ) -> Dict[str, Any] | None:
        raw_contract = self.get_behavior_contract(principal_scope_key=principal_scope_key)
        if raw_contract is None:
            return None
        corrected = apply_style_contract_rule_correction(
            raw_text=raw_contract.get("content"),
            rule_id=rule_id,
            replacement_text=replacement_text,
            metadata=raw_contract.get("metadata"),
        )
        if corrected is None:
            return None
        metadata = dict(raw_contract.get("metadata") or {})
        metadata["style_contract_title"] = corrected["title"]
        metadata["style_contract_sections"] = corrected["sections"]
        if corrected["summary"]:
            metadata["style_contract_summary"] = corrected["summary"]
        else:
            metadata.pop("style_contract_summary", None)
        metadata["last_behavior_policy_correction"] = {
            "rule_id": corrected["updated_rule_id"],
            "source": str(source or "").strip() or "behavior_policy_correction",
            "rule_count": len(list_style_contract_rules(raw_text=corrected["content"], metadata=metadata)),
            "content_hash": hashlib.sha256(str(corrected["content"]).encode("utf-8")).hexdigest(),
        }
        self.upsert_behavior_contract(
            stable_key=STYLE_CONTRACT_SLOT,
            category=str(raw_contract.get("category") or "preference"),
            content=str(corrected["content"]),
            source=str(source or "").strip() or "behavior_policy_correction",
            confidence=float(raw_contract.get("confidence") or 0.9),
            metadata=metadata,
        )
        return self.get_behavior_policy_snapshot(principal_scope_key=principal_scope_key)
