from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    OPERATING_OWNER,
    OPERATING_RECORD_CANONICAL_POLICY,
    OPERATING_RECORD_OPEN_DECISION,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    Sequence,
    _normalize_compact_text,
    apply_style_contract_patch,
    build_explicit_truth_parity,
    build_operating_stable_key,
    build_style_contract_from_text,
    build_task_stable_key,
    has_explicit_style_authority_signal,
    hashlib,
    list_style_contract_rules,
    logger,
    looks_like_style_contract_fragment,
    looks_like_style_contract_teaching,
    normalize_recent_work_metadata,
    parse_operating_capture,
    parse_task_capture,
    recent_work_stable_key,
    should_promote_open_decision,
    trim_text_boundary,
)

class ExplicitCaptureMixin(ProviderRuntimeBase):
    def _commit_explicit_write(
        self,
        *,
        owner: str,
        write_class: str,
        source: str,
        target: str,
        stable_key: str,
        category: str,
        content: str,
        commit: Callable[[], None],
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        receipt = {
            "receipt_id": self._next_write_receipt_id(),
            "status": "pending",
            "owner": owner,
            "write_class": write_class,
            "target": target,
            "stable_key": stable_key,
            "category": category,
            "source": source,
            "session_id": self._session_id,
            "turn_number": int(self._turn_counter),
            "principal_scope_key": self._principal_scope_key,
            "content_hash": hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()
            if str(content or "")
            else "",
        }
        if isinstance(extra, dict):
            receipt.update(extra)
        parity_common = {
            "source_role": str(receipt.get("source_role") or ""),
            "stable_key": stable_key,
            "principal_scope_key": self._principal_scope_key,
            "content": content,
            "brainstack_projection_receipt_id": str(receipt.get("receipt_id") or ""),
            "host_receipt_id": str(receipt.get("host_receipt_id") or ""),
            "host_receipt_source": str(receipt.get("host_receipt_source") or ""),
            "host_content_hash": str(receipt.get("host_content_hash") or ""),
            "host_stable_key": str(receipt.get("host_stable_key") or ""),
            "host_scope": str(receipt.get("host_scope") or ""),
            "host_temporal_status": str(receipt.get("host_temporal_status") or ""),
            "brainstack_temporal_status": str(receipt.get("brainstack_temporal_status") or ""),
            "authority_class": str(receipt.get("authority_class") or ""),
        }
        receipt["explicit_truth_parity"] = build_explicit_truth_parity(
            projection_status="pending",
            **parity_common,
        )

        self._pending_explicit_write_count += 1
        self._last_write_receipt = dict(receipt)
        self._set_memory_operation_trace(surface="explicit_write_pending")
        try:
            commit()
        except Exception as exc:
            failed = dict(receipt)
            failed["status"] = "failed"
            failed["error"] = str(exc)
            failed["explicit_truth_parity"] = build_explicit_truth_parity(
                projection_status="failed",
                error=str(exc),
                **parity_common,
            )
            self._last_write_receipt = failed
            self._set_memory_operation_trace(surface="explicit_write_failed", note=str(exc))
            raise
        finally:
            self._pending_explicit_write_count = max(0, self._pending_explicit_write_count - 1)

        committed = dict(receipt)
        committed["status"] = "committed"
        committed_parity = build_explicit_truth_parity(
            projection_status="committed",
            **parity_common,
        )
        committed["explicit_truth_parity"] = committed_parity
        if self._store is not None:
            self._store.annotate_explicit_truth_parity(
                target=target,
                stable_key=stable_key,
                category=category,
                principal_scope_key=self._principal_scope_key,
                parity=committed_parity,
            )
        self._last_write_receipt = committed
        self._set_memory_operation_trace(surface="explicit_write_committed")
        return committed

    def _ensure_explicit_write_barrier_clear(self, *, surface: str) -> bool:
        clear = self._pending_explicit_write_count == 0
        note = "" if clear else "Explicit durable write is still pending; refusing teardown."
        self._set_memory_operation_trace(surface=surface, note=note)
        if not clear:
            logger.error(note)
        return clear

    def _render_memory_operation_receipt_block(self, receipt: Dict[str, Any] | None) -> str:
        if not isinstance(receipt, dict):
            return ""
        if str(receipt.get("status") or "").strip() != "committed":
            return ""
        lines = [
            f"Committed durable write for this session: {receipt.get('write_class', 'write')}.",
            f"Owner: {receipt.get('owner', 'brainstack')}.",
            "This is committed evidence, not a plan or an optimistic promise.",
        ]
        source = str(receipt.get("source") or "").strip()
        if source:
            lines.append(f"Write source: {source}.")
        item_count = int(receipt.get("item_count") or 0)
        if item_count > 0:
            lines.append(f"Committed items: {item_count}.")
        due_date = str(receipt.get("due_date") or "").strip()
        if due_date:
            lines.append(f"Due date: {due_date}.")
        return "## Brainstack Memory Operation Receipt\n" + "\n".join(f"- {line}" for line in lines)

    def _upsert_style_contract_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float = 0.9,
        metadata: Dict[str, Any] | None = None,
        require_explicit_signal: bool = False,
    ) -> Dict[str, Any] | None:
        store = self._store
        if store is None or not content:
            return None
        style_contract = self._resolve_style_contract_candidate(
            content=content,
            source=source,
            confidence=confidence,
            metadata=metadata,
            require_explicit_signal=require_explicit_signal,
        )
        self._remember_recent_user_message(content)
        if style_contract is None:
            return None

        def commit() -> None:
            store.upsert_profile_item(
                stable_key=style_contract["slot"],
                category=style_contract["category"],
                content=style_contract["content"],
                source=style_contract["source"],
                confidence=float(style_contract["confidence"]),
                metadata=style_contract["metadata"],
            )

        receipt = self._commit_explicit_write(
            owner="brainstack.profile_archive",
            write_class="style_contract",
            source=str(style_contract["source"]),
            target="user",
            stable_key=str(style_contract["slot"]),
            category=str(style_contract["category"]),
            content=str(style_contract["content"]),
            commit=commit,
            extra={
                "rule_count": int(style_contract.get("metadata", {}).get("style_contract_rule_count") or 0),
                "fragment_count": int(style_contract.get("metadata", {}).get("style_contract_fragment_count") or 1),
                "write_mode": str(style_contract.get("metadata", {}).get("style_contract_write_mode") or ""),
                "patch_rule_count": int(
                    style_contract.get("metadata", {}).get("last_style_contract_patch", {}).get("patch_rule_count") or 0
                ),
            },
        )
        profile_row = store.get_profile_item(
            stable_key=str(style_contract["slot"]),
            principal_scope_key=self._principal_scope_key,
        )
        receipt["profile_lane_active"] = bool(profile_row)
        receipt["profile_storage_key"] = str(profile_row.get("stable_key") or "") if profile_row else ""
        receipt["compiled_policy_active"] = False
        receipt["compiled_policy_status"] = ""
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="style_contract_upsert")
        return receipt

    def _remember_recent_user_message(self, content: str) -> None:
        text = str(content or "").strip()
        if not text:
            return
        if self._recent_user_messages and self._recent_user_messages[-1] == text:
            return
        self._recent_user_messages.append(text)
        if len(self._recent_user_messages) > 4:
            self._recent_user_messages = self._recent_user_messages[-4:]

    def _iter_style_contract_candidate_texts(self, content: str) -> List[tuple[str, int]]:
        text = str(content or "").strip()
        if not text:
            return []
        prior_fragments = [
            fragment
            for fragment in self._recent_user_messages
            if (
                str(fragment or "").strip()
                and str(fragment or "").strip() != text
                and looks_like_style_contract_fragment(fragment)
            )
        ]
        candidates: List[tuple[str, int]] = []
        seen: set[str] = set()

        def _add(raw_text: str, fragment_count: int) -> None:
            normalized = str(raw_text or "").strip()
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append((normalized, fragment_count))

        _add(text, 1)
        if "\n" not in text or not looks_like_style_contract_fragment(text):
            return candidates
        for fragment_count in range(1, min(len(prior_fragments), 2) + 1):
            _add("\n".join([*prior_fragments[-fragment_count:], text]), fragment_count + 1)
        return candidates

    def _resolve_style_contract_candidate(
        self,
        *,
        content: str,
        source: str,
        confidence: float,
        metadata: Dict[str, Any] | None,
        require_explicit_signal: bool,
    ) -> Dict[str, Any] | None:
        scoped_metadata = self._scoped_metadata(metadata)
        raw_contract = self._store.get_behavior_contract(principal_scope_key=self._principal_scope_key) if self._store else None
        direct_text = str(content or "").strip()
        direct_text_has_explicit_authority = bool(
            direct_text and has_explicit_style_authority_signal(direct_text)
        )
        allow_fragment_merge = not (
            require_explicit_signal
            and direct_text
            and looks_like_style_contract_teaching(direct_text)
            and direct_text_has_explicit_authority
        )
        best_candidate: Dict[str, Any] | None = None
        best_score: tuple[int, int, int] | None = None
        for raw_text, fragment_count in self._iter_style_contract_candidate_texts(content):
            if fragment_count > 1 and not allow_fragment_merge:
                continue
            if require_explicit_signal and not looks_like_style_contract_teaching(raw_text):
                continue
            candidate = build_style_contract_from_text(
                raw_text=raw_text,
                source=source,
                confidence=confidence,
                metadata={
                    **scoped_metadata,
                    "style_contract_fragment_count": fragment_count,
                },
            )
            if candidate is None:
                continue
            rule_count = int(
                candidate.get("metadata", {}).get("style_contract_rule_count")
                or len(list_style_contract_rules(raw_text=raw_text, metadata=candidate.get("metadata")))
            )
            score = (rule_count, -fragment_count, -len(str(candidate.get("content") or "")))
            if best_score is None or score > best_score:
                best_candidate = candidate
                best_score = score
        if best_candidate is not None:
            best_candidate.setdefault("metadata", {})
            best_candidate["metadata"]["style_contract_write_mode"] = "replace" if raw_contract else "create"
            return best_candidate

        if not self._store or raw_contract is None:
            return None

        patch_source = source.replace(":style_contract", ":style_contract_patch")
        scoped_metadata = self._scoped_metadata(metadata)
        corrected = apply_style_contract_patch(
            raw_text=raw_contract.get("content"),
            patch_text=content,
            metadata=raw_contract.get("metadata"),
        )
        if corrected is None:
            return None
        merged_metadata = {
            **dict(raw_contract.get("metadata") or {}),
            **scoped_metadata,
            "memory_class": "style_contract",
            "style_contract_title": corrected["title"],
            "style_contract_sections": corrected["sections"],
            "style_contract_rule_count": len(
                list_style_contract_rules(raw_text=corrected["content"], metadata={"style_contract_sections": corrected["sections"]})
            ),
            "style_contract_fragment_count": 1,
            "style_contract_write_mode": "patch",
            "last_style_contract_patch": {
                "updated_rule_ids": list(corrected.get("updated_rule_ids") or []),
                "patch_rule_count": int(corrected.get("patch_rule_count") or 0),
                "source": patch_source,
            },
        }
        return {
            "category": str(raw_contract.get("category") or "preference"),
            "slot": str(raw_contract.get("stable_key") or "preference:style_contract"),
            "content": str(corrected["content"]),
            "confidence": float(raw_contract.get("confidence") or confidence or 0.9),
            "source": patch_source,
            "metadata": merged_metadata,
        }

    def _infer_task_capture_candidate(
        self,
        *,
        content: str,
    ) -> Dict[str, Any] | None:
        if not content:
            return None
        capture = parse_task_capture(content, timezone_name=self._user_timezone)
        if capture is None:
            return None

        items = list(capture.get("items") or [])
        if not items:
            return None
        return capture

    def _commit_task_capture_candidate(
        self,
        *,
        capture: Dict[str, Any] | None,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        store = self._store
        if store is None or not content or not isinstance(capture, dict):
            return None
        items = list(capture.get("items") or [])
        if not items:
            return None
        item_type = str(capture.get("item_type") or "task").strip() or "task"
        due_date = str(capture.get("due_date") or "").strip()
        date_scope = str(capture.get("date_scope") or "").strip()
        batch_stable_key = build_task_stable_key(
            principal_scope_key=self._principal_scope_key,
            item_type=item_type,
            due_date=due_date,
            title=" | ".join(str(item.get("title") or "").strip() for item in items),
        )

        def commit() -> None:
            scoped_metadata = self._scoped_metadata(metadata)
            input_excerpt = trim_text_boundary(_normalize_compact_text(content), max_len=220)
            write_metadata = dict(scoped_metadata)
            if input_excerpt:
                write_metadata["input_excerpt"] = input_excerpt
            for item in items:
                title = str(item.get("title") or "").strip()
                item_due_date = str(item.get("due_date") or due_date).strip()
                item_date_scope = str(item.get("date_scope") or date_scope).strip()
                raw_item_metadata = item.get("metadata")
                item_metadata: Mapping[str, Any] = raw_item_metadata if isinstance(raw_item_metadata, Mapping) else {}
                combined_metadata = dict(write_metadata)
                if item_metadata:
                    combined_metadata.update(dict(item_metadata))
                stable_key = build_task_stable_key(
                    principal_scope_key=self._principal_scope_key,
                    item_type=str(item.get("item_type") or item_type).strip() or item_type,
                    due_date=item_due_date,
                    title=title,
                )
                store.upsert_task_item(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    item_type=str(item.get("item_type") or item_type).strip() or item_type,
                    title=title,
                    due_date=item_due_date,
                    date_scope=item_date_scope,
                    optional=bool(item.get("optional")),
                    status=str(item.get("status") or "open").strip() or "open",
                    owner="brainstack.task_memory",
                    source=source,
                    source_session_id=str((metadata or {}).get("session_id") or self._session_id or "").strip(),
                    source_turn_number=int((metadata or {}).get("turn_number") or self._turn_counter or 0),
                    metadata=combined_metadata,
                )

        receipt = self._commit_explicit_write(
            owner="brainstack.task_memory",
            write_class="task_memory",
            source=source,
            target="user",
            stable_key=batch_stable_key,
            category=item_type,
            content=content,
            commit=commit,
            extra={
                "item_count": len(items),
                "due_date": due_date,
                "date_scope": date_scope,
                "items": [
                    {
                        "title": str(item.get("title") or "").strip(),
                        "optional": bool(item.get("optional")),
                        "due_date": str(item.get("due_date") or due_date).strip(),
                    }
                    for item in items
                ],
            },
        )
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="task_capture_upsert")
        return receipt

    def _upsert_task_capture_candidate(
        self,
        *,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        capture = self._infer_task_capture_candidate(content=content)
        return self._commit_task_capture_candidate(
            capture=capture,
            content=content,
            source=source,
            metadata=metadata,
        )

    def _infer_operating_truth_candidate(
        self,
        *,
        content: str,
    ) -> Dict[str, Any] | None:
        if not content:
            return None
        capture = parse_operating_capture(content, timezone_name=self._user_timezone)
        if capture is None:
            return None

        items = list(capture.get("items") or [])
        if not items:
            return None
        return capture

    def _commit_operating_truth_candidate(
        self,
        *,
        capture: Dict[str, Any] | None,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        store = self._store
        if store is None or not content or not isinstance(capture, dict):
            return None
        items = list(capture.get("items") or [])
        if not items:
            return None

        batch_stable_key = "::".join(
            [
                "operating_truth_batch",
                self._principal_scope_key or "global",
                str((metadata or {}).get("session_id") or self._session_id or "").strip() or "session",
                str((metadata or {}).get("turn_number") or self._turn_counter or 0),
            ]
        )

        def commit() -> None:
            scoped_metadata = self._scoped_metadata(metadata)
            input_excerpt = trim_text_boundary(_normalize_compact_text(content), max_len=220)
            write_metadata = dict(scoped_metadata)
            if input_excerpt:
                write_metadata["input_excerpt"] = input_excerpt
            for item in items:
                record_type = str(item.get("record_type") or "").strip()
                content_text = str(item.get("content") or "").strip()
                if not record_type or not content_text:
                    continue
                raw_item_metadata = item.get("metadata")
                item_metadata: Mapping[str, Any] = raw_item_metadata if isinstance(raw_item_metadata, Mapping) else {}
                combined_metadata = dict(write_metadata)
                if item_metadata:
                    combined_metadata.update(dict(item_metadata))
                explicit_rule_id = _normalize_compact_text(combined_metadata.get("rule_id"))
                if record_type == OPERATING_RECORD_CANONICAL_POLICY and explicit_rule_id:
                    stable_key = "::".join(
                        [
                            "canonical_policy",
                            self._principal_scope_key or "global",
                            explicit_rule_id,
                        ]
                    )
                elif record_type == OPERATING_RECORD_RECENT_WORK_SUMMARY:
                    stable_key = recent_work_stable_key(
                        principal_scope_key=self._principal_scope_key,
                        workstream_id=str(combined_metadata.get("workstream_id") or ""),
                    ) or build_operating_stable_key(
                        principal_scope_key=self._principal_scope_key,
                        record_type=record_type,
                        content=content_text,
                    )
                else:
                    stable_key = build_operating_stable_key(
                        principal_scope_key=self._principal_scope_key,
                        record_type=record_type,
                        content=content_text,
                    )
                store.upsert_operating_record(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    record_type=record_type,
                    content=content_text,
                    owner=OPERATING_OWNER,
                    source=source,
                    source_session_id=str((metadata or {}).get("session_id") or self._session_id or "").strip(),
                    source_turn_number=int((metadata or {}).get("turn_number") or self._turn_counter or 0),
                    metadata=combined_metadata,
                )

        receipt = self._commit_explicit_write(
            owner=OPERATING_OWNER,
            write_class="operating_truth",
            source=source,
            target="user",
            stable_key=batch_stable_key,
            category="operating_truth",
            content=content,
            commit=commit,
            extra={
                "item_count": len(items),
                "record_types": [str(item.get("record_type") or "").strip() for item in items],
                "items": [dict(item) for item in items],
            },
        )
        self._last_write_receipt = receipt
        self._set_memory_operation_trace(surface="operating_truth_upsert")
        return receipt

    def _upsert_operating_truth_candidate(
        self,
        *,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        capture = self._infer_operating_truth_candidate(content=content)
        return self._commit_operating_truth_candidate(
            capture=capture,
            content=content,
            source=source,
            metadata=metadata,
        )

    def _upsert_brainstack_operating_record(
        self,
        *,
        record_type: str,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
        stable_key_override: str = "",
    ) -> bool:
        if not self._store:
            return False
        normalized_content = _normalize_compact_text(content)
        if not normalized_content:
            return False
        stable_key = _normalize_compact_text(stable_key_override) or build_operating_stable_key(
            principal_scope_key=self._principal_scope_key,
            record_type=record_type,
            content=normalized_content,
        )
        scoped_metadata = self._scoped_metadata(metadata)
        self._store.upsert_operating_record(
            stable_key=stable_key,
            principal_scope_key=self._principal_scope_key,
            record_type=record_type,
            content=normalized_content,
            owner=OPERATING_OWNER,
            source=source,
            source_session_id=str((metadata or {}).get("session_id") or self._session_id or "").strip(),
            source_turn_number=int((metadata or {}).get("turn_number") or self._turn_counter or 0),
            metadata=scoped_metadata,
        )
        return True

    def _promote_recent_work_summary(
        self,
        *,
        content: str,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        compact_summary = trim_text_boundary(_normalize_compact_text(content), max_len=280)
        if not compact_summary:
            return False
        recent_work_metadata = normalize_recent_work_metadata(
            stable_key="",
            source=source,
            metadata=dict(metadata or {}),
        )
        stable_key_override = recent_work_stable_key(
            principal_scope_key=self._principal_scope_key,
            workstream_id=str(recent_work_metadata.get("workstream_id") or ""),
        )
        return self._upsert_brainstack_operating_record(
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content=compact_summary,
            source=source,
            metadata=recent_work_metadata,
            stable_key_override=stable_key_override,
        )

    def _promote_open_decisions(
        self,
        *,
        decisions: Sequence[str] | None,
        source: str,
        metadata: Dict[str, Any] | None = None,
    ) -> int:
        if not should_promote_open_decision(source=source, metadata=metadata):
            self._set_memory_operation_trace(
                surface="operating_open_decision_rejected",
                note="Background/Tier-2/session-derived open decisions are supporting evidence, not operating authority.",
            )
            return 0
        promoted = 0
        for decision in decisions or ():
            normalized_decision = trim_text_boundary(_normalize_compact_text(decision), max_len=220)
            if not normalized_decision:
                continue
            if self._upsert_brainstack_operating_record(
                record_type=OPERATING_RECORD_OPEN_DECISION,
                content=normalized_decision,
                source=source,
                metadata=metadata,
            ):
                promoted += 1
        return promoted
