from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    Dict,
    List,
    Mapping,
    NATIVE_EXPLICIT_PROFILE_METADATA_KEY,
    NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE,
    Sequence,
    _derive_native_profile_mirror_entries,
    _native_profile_mirror_payload,
    _stable_native_write_id,
    build_compression_hint,
    build_session_message_ingest_plan,
    continuity_adapter,
    corpus_adapter,
    derive_host_trace_id,
    graph_adapter,
    json,
    logger,
)

class IngestLifecycleMixin(ProviderRuntimeBase):
    def ingest_corpus_document(
        self,
        *,
        title: str,
        content: str,
        source: str,
        doc_kind: str = "document",
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("BrainstackStore is not initialized")
        normalized_title = " ".join(str(title).split()).strip()
        normalized_source = " ".join(str(source).split()).strip()
        text = str(content or "")
        if not normalized_title:
            raise ValueError("title is required")
        if not normalized_source:
            raise ValueError("source is required")
        if not text.strip():
            raise ValueError("content is required")

        payload = corpus_adapter.prepare_corpus_payload(
            title=normalized_title,
            content=text,
            source=normalized_source,
            doc_kind=doc_kind,
            metadata=metadata,
            section_max_chars=self._corpus_section_max_chars,
        )
        raw_metadata = dict(metadata or {})
        source_adapter = str(raw_metadata.get("source_adapter") or raw_metadata.get("adapter") or "provider_document").strip()
        source_id = str(raw_metadata.get("source_id") or payload["stable_key"]).strip()
        return self._store.ingest_corpus_source(
            {
                "source_adapter": source_adapter or "provider_document",
                "source_id": source_id or str(payload["stable_key"]),
                "stable_key": payload["stable_key"],
                "title": normalized_title,
                "doc_kind": doc_kind,
                "source_uri": normalized_source,
                "content": text,
                "metadata": self._scoped_metadata(raw_metadata),
                "section_char_limit": self._corpus_section_max_chars,
            }
        )

    def ingest_graph_evidence(
        self,
        *,
        evidence_items: Sequence[Mapping[str, Any] | Any],
        source: str,
        metadata: Dict[str, Any] | None = None,
        session_id: str = "",
        turn_number: int | None = None,
        source_document_id: str = "",
    ) -> Dict[str, Any]:
        if not self._store:
            raise RuntimeError("BrainstackStore is not initialized")
        normalized_source = " ".join(str(source).split()).strip()
        if not normalized_source:
            raise ValueError("source is required")
        target_session_id = str(session_id or self._session_id or "").strip()
        scoped_metadata = self._scoped_metadata(metadata)
        try:
            if turn_number is not None:
                graph_result = graph_adapter.ingest_turn_graph_candidates_with_receipt(
                    self._store,
                    evidence_items=evidence_items,
                    session_id=target_session_id,
                    turn_number=int(turn_number),
                    source=normalized_source,
                    source_document_id=source_document_id,
                    metadata=scoped_metadata,
                )
            else:
                graph_result = graph_adapter.ingest_session_graph_candidates_with_receipt(
                    self._store,
                    evidence_items=evidence_items,
                    session_id=target_session_id,
                    source=normalized_source,
                    source_document_id=source_document_id,
                    metadata=scoped_metadata,
                )
        except Exception as exc:
            receipt = getattr(exc, "receipt", None)
            self._last_graph_ingress_trace = {
                "surface": "explicit_graph_ingress",
                "status": "failed",
                "error": str(exc),
                "receipt": dict(receipt) if isinstance(receipt, dict) else None,
            }
            raise
        self._last_graph_ingress_trace = {
            "surface": "explicit_graph_ingress",
            "status": "committed",
            "receipt": dict(graph_result.get("receipt") or {}),
        }
        self._set_memory_operation_trace(
            surface="explicit_graph_ingress",
            note="Explicit producer-aligned typed graph ingest committed.",
        )
        return json.loads(json.dumps(graph_result, ensure_ascii=True))

    def ingest_multimodal_memory_artifact(
        self,
        *,
        title: str,
        content: str,
        source: str,
        modality: str,
        doc_kind: str = "document",
        metadata: Dict[str, Any] | None = None,
        graph_evidence_items: Sequence[Mapping[str, Any] | Any] | None = None,
        session_id: str = "",
        turn_number: int | None = None,
    ) -> Dict[str, Any]:
        normalized_modality = " ".join(str(modality or "").split()).strip().lower()
        if not normalized_modality:
            raise ValueError("modality is required")
        artifact_metadata = dict(metadata or {})
        artifact_metadata["modality"] = normalized_modality
        corpus_result = self.ingest_corpus_document(
            title=title,
            content=content,
            source=source,
            doc_kind=doc_kind,
            metadata=artifact_metadata,
        )
        source_document_id = f"corpus_document:{str(corpus_result.get('stable_key') or '')}"
        graph_result = None
        if graph_evidence_items:
            graph_result = self.ingest_graph_evidence(
                evidence_items=graph_evidence_items,
                source=f"{source}:graph",
                metadata=artifact_metadata,
                session_id=session_id,
                turn_number=turn_number,
                source_document_id=source_document_id,
            )
        self._set_memory_operation_trace(
            surface="ingest_multimodal_memory_artifact",
            note="Explicit producer-aligned multimodal corpus ingest committed.",
        )
        return {
            "modality": normalized_modality,
            "source_document_id": source_document_id,
            "corpus_document": corpus_result,
            "graph_ingress": graph_result,
        }

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        self._turn_counter = max(self._turn_counter, turn_number - 1)

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        if not self._store:
            return ""
        snapshot_window = continuity_adapter.build_snapshot_source_window(
            messages,
            max_items=self._compression_snapshot_limit,
        )
        summary = continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="pre-compress continuity snapshot",
            kind="compression_snapshot",
            source="on_pre_compress",
            max_items=self._compression_snapshot_limit,
            metadata=self._scoped_metadata(),
        )
        if not summary:
            return ""
        self._store.record_continuity_snapshot_state(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            kind="compression_snapshot",
            message_count=int(snapshot_window.get("captured_message_count") or 0),
            input_message_count=int(snapshot_window.get("input_message_count") or 0),
            digest=str(snapshot_window.get("window_digest") or ""),
        )
        return build_compression_hint(summary)

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._store:
            return
        if not self._ensure_explicit_write_barrier_clear(surface="on_session_end"):
            return
        worker_finished = self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if (
            self._tier2_session_end_flush_enabled
            and worker_finished
            and (self._pending_tier2_turns > 0 or self._tier2_followup_requested)
        ):
            try:
                self._run_tier2_batch(session_id=self._session_id, turn_number=self._turn_counter, trigger_reason="session_end_flush")
            except Exception:
                logger.warning("Brainstack Tier-2 session-end flush failed", exc_info=True)
            finally:
                with self._tier2_lock:
                    self._pending_tier2_turns = 0
                    self._tier2_followup_requested = False
        else:
            with self._tier2_lock:
                self._pending_tier2_turns = 0
                self._tier2_followup_requested = False
        snapshot_window = continuity_adapter.build_snapshot_source_window(messages, max_items=8)
        summary = continuity_adapter.write_snapshot_records(
            self._store,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            messages=messages,
            label="session summary",
            kind="session_summary",
            source="on_session_end",
            max_items=8,
            metadata=self._scoped_metadata(),
        )
        if summary:
            self._store.record_continuity_snapshot_state(
                session_id=self._session_id,
                turn_number=self._turn_counter,
                kind="session_summary",
                message_count=int(snapshot_window.get("captured_message_count") or 0),
                input_message_count=int(snapshot_window.get("input_message_count") or 0),
                digest=str(snapshot_window.get("window_digest") or ""),
            )
        session_end_operating_consolidation = self._consolidate_recent_work_operating_truth(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            source="on_session_end:recent_work_consolidation",
        )
        self._last_operating_context_trace = {
            **dict(self._last_operating_context_trace or {}),
            "session_end_consolidation": session_end_operating_consolidation,
        }
        self._store.finalize_continuity_session_state(
            session_id=self._session_id,
            turn_number=self._turn_counter,
        )
        for message in messages:
            message_content = str(message.get("content", ""))
            plan = build_session_message_ingest_plan(
                role=str(message.get("role", "")),
                content=message_content,
            )
            if not plan.durable_admission.allowed and plan.durable_admission.reason not in {"non_user_role", "empty_fact"}:
                logger.info(
                    "Brainstack durable admission denied in session_end: reason=%s matched=%s",
                    plan.durable_admission.reason,
                    ",".join(plan.durable_admission.matched_rules) or "-",
                )
            if plan.graph_evidence_items:
                try:
                    graph_result = graph_adapter.ingest_session_graph_candidates_with_receipt(
                        self._store,
                        evidence_items=plan.graph_evidence_items,
                        session_id=self._session_id,
                        source="session_end_scan:user",
                        metadata=self._scoped_metadata(),
                    )
                except Exception as exc:
                    receipt = getattr(exc, "receipt", None)
                    self._last_graph_ingress_trace = {
                        "surface": "session_end_graph_ingress",
                        "status": "failed",
                        "error": str(exc),
                        "receipt": dict(receipt) if isinstance(receipt, dict) else None,
                    }
                    raise
                self._last_graph_ingress_trace = {
                    "surface": "session_end_graph_ingress",
                    "status": "committed",
                    "receipt": dict(graph_result.get("receipt") or {}),
                }
            else:
                self._last_graph_ingress_trace = {
                    "surface": "session_end_graph_ingress",
                    "status": "skipped_no_typed_graph_evidence",
                    "reason": "no explicit producer-aligned graph evidence items",
                }

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not self._store or not content or action == "remove":
            return
        store = self._store
        write_metadata = dict(metadata or {})
        write_origin = str(write_metadata.get("write_origin") or "").strip()
        if write_origin == "background_review":
            self._set_memory_operation_trace(
                surface="native_memory_write_reflection_skip",
                note=(
                    "Skipped Brainstack durable mirroring for a reflection-generated built-in memory write "
                    "to avoid treating background review output as ordinary user-established truth."
                ),
            )
            return
        if target == "user":
            native_write_id = _stable_native_write_id(action=action, target=target, content=content)
            host_receipt_id = str(write_metadata.get("host_receipt_id") or "").strip()
            host_receipt_source = "host_receipt" if host_receipt_id else "derived_host_trace"
            if not host_receipt_id:
                host_receipt_id = derive_host_trace_id(
                    action=action,
                    target=target,
                    content=content,
                    metadata=write_metadata,
                )
            mirror_payload = _native_profile_mirror_payload(
                native_write_id=native_write_id,
                action=action,
                target=target,
            )
            self._upsert_style_contract_candidate(
                content=content,
                source="memory_write:style_contract",
                confidence=0.9,
                metadata={
                    "target": target,
                    **write_metadata,
                    NATIVE_EXPLICIT_PROFILE_METADATA_KEY: mirror_payload,
                },
                require_explicit_signal=True,
            )
            mirror_entries = _derive_native_profile_mirror_entries(content)
            if not mirror_entries:
                self._set_memory_operation_trace(
                    surface="native_profile_mirror",
                    note="Native explicit user write produced no bounded Brainstack mirror entries.",
                )
                return
            for index, entry in enumerate(mirror_entries, start=1):
                stable_key = str(entry.get("stable_key") or "").strip()
                if not stable_key:
                    continue
                category = str(entry.get("category") or "native_profile_mirror").strip()
                mirror_metadata = self._scoped_metadata(
                    {
                        "target": target,
                        **write_metadata,
                        NATIVE_EXPLICIT_PROFILE_METADATA_KEY: {
                            **mirror_payload,
                            "mirror_index": index,
                        },
                    }
                )
                source = f"builtin_{action}:native_profile_mirror"
                candidate_content = str(entry.get("content") or "").strip()
                candidate_confidence = float(entry.get("confidence") or 0.95)

                def _commit_profile_item(
                    *,
                    stable_key: str = stable_key,
                    category: str = category,
                    candidate_content: str = candidate_content,
                    source: str = source,
                    candidate_confidence: float = candidate_confidence,
                    mirror_metadata: Dict[str, Any] | None = mirror_metadata,
                ) -> None:
                    store.upsert_profile_item(
                        stable_key=stable_key,
                        category=category,
                        content=candidate_content,
                        source=source,
                        confidence=candidate_confidence,
                        metadata=mirror_metadata,
                    )

                self._commit_explicit_write(
                    owner="brainstack.profile_items",
                    write_class="native_profile_mirror",
                    source=source,
                    target=target,
                    stable_key=stable_key,
                    category=category,
                    content=candidate_content,
                    commit=_commit_profile_item,
                    extra={
                        "native_write_id": native_write_id,
                        "source_generation": native_write_id,
                        "mirrored_from": NATIVE_EXPLICIT_PROFILE_MIRROR_SOURCE,
                        "host_receipt_id": host_receipt_id,
                        "host_receipt_source": host_receipt_source,
                        "host_scope": str(write_metadata.get("principal_scope_key") or self._principal_scope_key),
                        "host_temporal_status": str(write_metadata.get("temporal_status") or ""),
                        "brainstack_temporal_status": str(mirror_metadata.get("temporal_status") or ""),
                    },
                )
            return

        store.add_continuity_event(
            session_id=self._session_id,
            turn_number=self._turn_counter,
            kind="builtin_memory",
            content=content,
            source=f"on_memory_write:{action}:{target}",
            metadata=self._scoped_metadata({"target": target, **write_metadata}),
        )
