from __future__ import annotations

from collections import OrderedDict

from .durable_write_guard import guard_and_normalize_durable_truth_metadata
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
    _is_principal_scoped_profile,
    _profile_storage_key,
    _split_profile_storage_key,
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
    style_contract_source_rank,
    utc_now_iso,
)


PROFILE_STYLE_CONTRACT_PROFILE_LANE = "profile_style_contract"
PROFILE_STYLE_CONTRACT_PROJECTION_CACHE_LIMIT = 64
PROFILE_STYLE_CONTRACT_ALLOWED_SOURCE_PREFIXES = (
    "operator_explicit",
    "user_explicit",
    "memory_write:style_contract",
    "prefetch:style_contract",
    "sync_turn:user_style_contract",
)
PROFILE_STYLE_CONTRACT_BLOCKED_SOURCE_ROLES = {"assistant", "system", "tool"}


def _profile_style_contract_has_user_authority(item: Dict[str, Any]) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    source_role = str(metadata.get("source_role") or "").strip().lower()
    if source_role in PROFILE_STYLE_CONTRACT_BLOCKED_SOURCE_ROLES:
        return False
    if source_role == "user":
        return True

    source = str(item.get("source") or "").strip().lower()
    if any(source.startswith(prefix) for prefix in PROFILE_STYLE_CONTRACT_ALLOWED_SOURCE_PREFIXES):
        return True

    provenance = metadata.get("provenance")
    source_ids = provenance.get("source_ids") if isinstance(provenance, dict) else ()
    if isinstance(source_ids, (str, bytes, bytearray)):
        source_ids = (source_ids,)
    if any(
        any(str(source_id).strip().lower().startswith(prefix) for prefix in PROFILE_STYLE_CONTRACT_ALLOWED_SOURCE_PREFIXES)
        for source_id in (source_ids or ())
    ):
        return True

    receipt_id = str(metadata.get("memory_write_receipt_id") or metadata.get("receipt_id") or "").strip().lower()
    return bool(receipt_id and "user" in source and style_contract_source_rank(source) >= 200)


class ProfileStoreMixin(StoreRuntimeBase):
    def _profile_scope_index_values(
        self,
        *,
        storage_key: str,
        category: str,
        metadata: Dict[str, Any] | None,
    ) -> tuple[str, str]:
        logical_key, embedded_scope_key = _split_profile_storage_key(storage_key)
        scope_key = _principal_scope_key_from_metadata(metadata) or embedded_scope_key
        if not _is_principal_scoped_profile(stable_key=logical_key, category=category) and not scope_key:
            scope_key = ""
        return logical_key, scope_key

    def _backfill_profile_scope_index_columns(self) -> int:
        rows = self.conn.execute(
            """
            SELECT id, stable_key, logical_stable_key, principal_scope_key, category, metadata_json
            FROM profile_items
            ORDER BY id ASC
            """
        ).fetchall()
        updated = 0
        for row in rows:
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except (TypeError, ValueError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            logical_key, scope_key = self._profile_scope_index_values(
                storage_key=str(row["stable_key"] or ""),
                category=str(row["category"] or ""),
                metadata=metadata,
            )
            metadata_changed = False
            if scope_key and not str(metadata.get("principal_scope_key") or "").strip():
                metadata = dict(metadata)
                metadata["principal_scope_key"] = scope_key
                metadata_changed = True
            if (
                str(row["logical_stable_key"] or "") == logical_key
                and str(row["principal_scope_key"] or "") == scope_key
                and not metadata_changed
            ):
                continue
            self.conn.execute(
                """
                UPDATE profile_items
                SET logical_stable_key = ?, principal_scope_key = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    logical_key,
                    scope_key,
                    json.dumps(metadata, ensure_ascii=True, sort_keys=True),
                    int(row["id"]),
                ),
            )
            updated += 1
        return updated

    def _profile_lane_projection_cache_store(self) -> OrderedDict[tuple[Any, ...], Dict[str, Any]]:
        cache = getattr(self, "_profile_lane_projection_cache", None)
        if not isinstance(cache, OrderedDict):
            cache = OrderedDict()
            self._profile_lane_projection_cache = cache
        return cache

    def _profile_lane_projection_cache_key(self, item: Dict[str, Any]) -> tuple[Any, ...]:
        raw_content = str(item.get("content") or "")
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest() if raw_content else ""
        rule_count = len(list_style_contract_rules(raw_text=raw_content, metadata=metadata))
        return (
            str(item.get("principal_scope_key") or "").strip(),
            str(item.get("storage_key") or "").strip(),
            source_hash,
            int(item.get("revision_number") or 0),
            str(item.get("updated_at") or "").strip(),
            PROFILE_STYLE_CONTRACT_PROFILE_LANE,
            rule_count,
        )

    def _profile_lane_projection_cache_trace(
        self,
        *,
        status: str,
        key: tuple[Any, ...],
    ) -> Dict[str, Any]:
        cache = self._profile_lane_projection_cache_store()
        return {
            "schema": "brainstack.profile_lane_projection_cache_trace.v1",
            "status": status,
            "cache_durable": False,
            "cache_size": len(cache),
            "cache_limit": PROFILE_STYLE_CONTRACT_PROJECTION_CACHE_LIMIT,
            "principal_scope_key": str(key[0] or ""),
            "source_storage_key": str(key[1] or ""),
            "source_contract_hash": str(key[2] or ""),
            "source_revision_number": int(key[3] or 0),
            "source_updated_at": str(key[4] or ""),
            "source_lane": str(key[5] or ""),
            "source_rule_count": int(key[6] or 0),
        }

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
        logical_stable_key, indexed_principal_scope_key = self._profile_scope_index_values(
            storage_key=storage_key,
            category=category,
            metadata=metadata,
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
        normalized_metadata = guard_and_normalize_durable_truth_metadata(
            shelf="profile",
            source=source,
            metadata=normalized_metadata,
            slot=str(stable_key or "").strip(),
        )
        meta_json = json.dumps(normalized_metadata, ensure_ascii=True, sort_keys=True)

        if existing:
            row_id = int(existing["id"])
            self.conn.execute(
                """
                UPDATE profile_items
                SET logical_stable_key = ?, principal_scope_key = ?, category = ?, content = ?, source = ?, confidence = ?, metadata_json = ?,
                    updated_at = ?, active = ?
                WHERE id = ?
                """,
                (
                    logical_stable_key,
                    indexed_principal_scope_key,
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
                    stable_key, logical_stable_key, principal_scope_key, category, content, source, confidence,
                    metadata_json, first_seen_at, updated_at, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    storage_key,
                    logical_stable_key,
                    indexed_principal_scope_key,
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

    def _profile_style_contract_behavior_projection(
        self,
        *,
        principal_scope_key: str = "",
    ) -> Dict[str, Any] | None:
        scope_key = str(principal_scope_key or "").strip()
        if not scope_key:
            return None
        item = self.get_profile_item(
            stable_key=STYLE_CONTRACT_SLOT,
            principal_scope_key=scope_key,
        )
        if not item or not bool(item.get("active", True)):
            return None
        if str(item.get("stable_key") or "").strip() != STYLE_CONTRACT_SLOT:
            return None
        if not _profile_style_contract_has_user_authority(item):
            return None
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        content = str(item.get("content") or "").strip()
        if style_contract_cleanliness_issues(raw_text=content, metadata=metadata):
            return None
        storage_key = str(item.get("storage_key") or item.get("stable_key") or "").strip()
        updated_at = str(item.get("updated_at") or "").strip()
        return {
            "id": int(item.get("id") or 0),
            "storage_key": storage_key,
            "principal_scope_key": scope_key,
            "stable_key": STYLE_CONTRACT_SLOT,
            "category": str(item.get("category") or "style_contract").strip() or "style_contract",
            "content": content,
            "source": str(item.get("source") or "").strip(),
            "confidence": float(item.get("confidence") or 0.9),
            "metadata": metadata,
            "source_contract_hash": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            "revision_number": 1,
            "parent_revision_id": 0,
            "status": BEHAVIOR_CONTRACT_ACTIVE_STATUS,
            "committed_at": updated_at,
            "updated_at": updated_at,
            "active": True,
            "receipt_id": str(metadata.get("receipt_id") or metadata.get("explicit_capture_receipt_id") or "").strip(),
            "memory_write_receipt_id": str(metadata.get("memory_write_receipt_id") or "").strip(),
            "source_lane": PROFILE_STYLE_CONTRACT_PROFILE_LANE,
            "read_only_projection": True,
        }

    def _compiled_behavior_policy_record_from_profile_projection(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        key = self._profile_lane_projection_cache_key(item)
        cache = self._profile_lane_projection_cache_store()
        if key in cache:
            cached = dict(cache.pop(key))
            cache[key] = cached
            result = dict(cached)
            result["profile_lane_projection_cache"] = self._profile_lane_projection_cache_trace(status="hit", key=key)
            return result
        compiled = compile_behavior_policy(
            raw_content=str(item.get("content") or ""),
            metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else None,
            source_storage_key=str(item.get("storage_key") or ""),
            source_updated_at=str(item.get("updated_at") or ""),
            source_revision_number=int(item.get("revision_number") or 1),
        )
        if compiled is None:
            return None
        result = {
            "principal_scope_key": str(item.get("principal_scope_key") or "").strip(),
            "source_storage_key": str(compiled.get("source_storage_key") or "").strip(),
            "source_contract_hash": str(compiled.get("source_contract_hash") or "").strip(),
            "source_contract_updated_at": str(compiled.get("source_contract_updated_at") or "").strip(),
            "schema_version": int(compiled.get("schema_version") or 0),
            "compiler_version": str(compiled.get("compiler_version") or "").strip(),
            "title": str(compiled.get("title") or "").strip(),
            "policy": compiled,
            "projection_text": str(compiled.get("projection_text") or "").strip(),
            "status": str(compiled.get("status") or "active").strip() or "active",
            "updated_at": str(item.get("updated_at") or "").strip(),
            "source_lane": PROFILE_STYLE_CONTRACT_PROFILE_LANE,
            "read_only_projection": True,
        }
        cache[key] = dict(result)
        while len(cache) > PROFILE_STYLE_CONTRACT_PROJECTION_CACHE_LIMIT:
            cache.popitem(last=False)
        result["profile_lane_projection_cache"] = self._profile_lane_projection_cache_trace(status="miss", key=key)
        return result

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
        if contract and str(contract.get("source_lane") or "").strip() == PROFILE_STYLE_CONTRACT_PROFILE_LANE:
            return self._compiled_behavior_policy_record_from_profile_projection(contract)
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
