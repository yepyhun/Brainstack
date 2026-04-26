from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    ACTIVE_TASK_STATUSES,
    ALL_TASK_STATUSES,
    Any,
    DISABLED_MEMORY_WRITE_TOOLS,
    Dict,
    EXPLICIT_CAPTURE_SCHEMA_VERSION,
    List,
    MAINTENANCE_CLASS_SEMANTIC_INDEX,
    MAINTENANCE_SCHEMA_VERSION,
    Mapping,
    OPERATING_OWNER,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    Path,
    RECENT_WORK_AUTHORITY_CANONICAL,
    RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
    RECENT_WORK_OWNER_USER_PROJECT,
    RECENT_WORK_SOURCE_EXPLICIT,
    RECENT_WORK_SOURCE_MANUAL_MIGRATION,
    TERMINAL_TASK_STATUSES,
    _normalize_compact_text,
    build_commit_metadata,
    build_provider_lifecycle_status,
    build_provider_memory_kernel_doctor,
    build_provider_query_inspect,
    build_tool_schemas,
    explicit_capture_tool_schema,
    handle_brainstack_inspect,
    handle_brainstack_recall,
    handle_brainstack_stats,
    json,
    locate_task_record,
    normalize_maintenance_args,
    normalize_recent_work_metadata,
    receipt_excerpt,
    recent_work_stable_key,
    run_bounded_maintenance,
    runtime_handoff_update_tool_schema,
    trim_text_boundary,
    utc_now_iso,
    validate_explicit_capture_payload,
    workstream_recap_tool_schema,
    write_task_record,
)

class ProviderToolsMixin(ProviderRuntimeBase):
    def _runtime_handoff_update_tool_schema(self) -> Dict[str, Any]:
        return runtime_handoff_update_tool_schema()

    def _workstream_recap_tool_schema(self) -> Dict[str, Any]:
        return workstream_recap_tool_schema(
            owner_user_project=RECENT_WORK_OWNER_USER_PROJECT,
            owner_agent_assignment=RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
            source_explicit=RECENT_WORK_SOURCE_EXPLICIT,
            source_manual_migration=RECENT_WORK_SOURCE_MANUAL_MIGRATION,
        )

    def _explicit_capture_tool_schema(self, *, name: str, operation: str) -> Dict[str, Any]:
        return explicit_capture_tool_schema(
            name=name,
            operation=operation,
            capture_schema_version=EXPLICIT_CAPTURE_SCHEMA_VERSION,
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return build_tool_schemas(
            capture_schema_version=EXPLICIT_CAPTURE_SCHEMA_VERSION,
            maintenance_schema_version=MAINTENANCE_SCHEMA_VERSION,
            maintenance_class_semantic_index=MAINTENANCE_CLASS_SEMANTIC_INDEX,
            owner_user_project=RECENT_WORK_OWNER_USER_PROJECT,
            owner_agent_assignment=RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
            source_explicit=RECENT_WORK_SOURCE_EXPLICIT,
            source_manual_migration=RECENT_WORK_SOURCE_MANUAL_MIGRATION,
            runtime_handoff_update_model_callable=bool(
                self._config.get("runtime_handoff_update_model_callable", False)
            ),
        )

    @staticmethod
    def _trusted_operator_write_origin(kwargs: Mapping[str, Any]) -> str:
        origin = _normalize_compact_text(kwargs.get("trusted_write_origin"))
        if origin in {"host_operator", "manual_migration", "brainstack_internal", "test_operator"}:
            return origin
        return ""

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        trusted_operator_origin = self._trusted_operator_write_origin(kwargs)
        if tool_name == "brainstack_recall":
            return json.dumps(self._handle_brainstack_recall(args), ensure_ascii=False)
        if tool_name == "brainstack_inspect":
            return json.dumps(self._handle_brainstack_inspect(args), ensure_ascii=False)
        if tool_name == "brainstack_stats":
            return json.dumps(self._handle_brainstack_stats(args), ensure_ascii=False)
        if tool_name == "brainstack_remember":
            return json.dumps(
                self._handle_brainstack_explicit_capture(
                    "remember",
                    args,
                    trusted_operator_origin=trusted_operator_origin,
                ),
                ensure_ascii=False,
            )
        if tool_name == "brainstack_supersede":
            return json.dumps(
                self._handle_brainstack_explicit_capture(
                    "supersede",
                    args,
                    trusted_operator_origin=trusted_operator_origin,
                ),
                ensure_ascii=False,
            )
        if tool_name == "brainstack_workstream_recap":
            return json.dumps(
                self._handle_brainstack_workstream_recap(
                    args,
                    trusted_operator_origin=trusted_operator_origin,
                ),
                ensure_ascii=False,
            )
        if tool_name == "brainstack_consolidate":
            return json.dumps(self._handle_brainstack_consolidate(args), ensure_ascii=False)
        if tool_name == "runtime_handoff_update":
            return json.dumps(self._handle_runtime_handoff_update(args, **kwargs), ensure_ascii=False)
        if tool_name in DISABLED_MEMORY_WRITE_TOOLS:
            return json.dumps(
                {
                    "schema": "brainstack.tool_error.v1",
                    "tool_name": tool_name,
                    "error_code": "tool_disabled_pending_contract",
                    "error": "This Brainstack memory operation is disabled until its explicit durable contract lands.",
                    "read_only": False,
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "schema": "brainstack.tool_error.v1",
                "tool_name": tool_name,
                "error_code": "unknown_tool",
                "error": f"Unknown Brainstack tool: {tool_name}",
            },
            ensure_ascii=False,
        )

    def _handle_brainstack_workstream_recap(
        self,
        args: Mapping[str, Any],
        *,
        trusted_operator_origin: str = "",
    ) -> Dict[str, Any]:
        tool_name = "brainstack_workstream_recap"
        if self._store is None:
            return {
                "schema": "brainstack.tool_error.v1",
                "tool_name": tool_name,
                "error_code": "store_unavailable",
                "error": "Brainstack store is not initialized.",
                "read_only": False,
            }
        if not isinstance(args, Mapping):
            return {
                "schema": "brainstack.tool_error.v1",
                "tool_name": tool_name,
                "error_code": "invalid_payload",
                "error": "brainstack_workstream_recap requires an object payload.",
                "read_only": False,
            }

        summary = trim_text_boundary(_normalize_compact_text(args.get("summary")), max_len=280)
        workstream_id = _normalize_compact_text(args.get("workstream_id"))
        source_role = _normalize_compact_text(args.get("source_role")).lower()
        owner_role = _normalize_compact_text(args.get("owner_role")).replace("-", "_")
        source_kind = _normalize_compact_text(args.get("source_kind")).replace("-", "_")
        stable_key = recent_work_stable_key(
            principal_scope_key=self._principal_scope_key,
            workstream_id=workstream_id,
        )
        errors: List[Dict[str, str]] = []
        if not stable_key:
            errors.append({"code": "missing_workstream_id", "message": "workstream_id is required."})
        if not summary:
            errors.append({"code": "missing_summary", "message": "summary is required."})
        if source_role not in {"user", "operator"}:
            errors.append({"code": "invalid_source_role", "message": "source_role must be user or operator."})
        elif source_role == "operator" and not trusted_operator_origin:
            errors.append(
                {
                    "code": "untrusted_operator_source_role",
                    "message": "operator source_role requires a trusted non-model write path.",
                }
            )
        if owner_role not in {RECENT_WORK_OWNER_USER_PROJECT, RECENT_WORK_OWNER_AGENT_ASSIGNMENT}:
            errors.append({"code": "invalid_owner_role", "message": "owner_role must be user_project or agent_assignment."})
        if source_kind not in {RECENT_WORK_SOURCE_EXPLICIT, RECENT_WORK_SOURCE_MANUAL_MIGRATION}:
            errors.append(
                {
                    "code": "invalid_source_kind",
                    "message": "source_kind must be explicit_operating_truth or manual_migration.",
                }
            )
        raw_metadata = args.get("metadata")
        if raw_metadata is not None and not isinstance(raw_metadata, Mapping):
            errors.append({"code": "invalid_metadata", "message": "metadata must be an object when provided."})
        if errors:
            rejection = {
                "schema": "brainstack.workstream_recap_capture.v1",
                "tool_name": tool_name,
                "status": "rejected",
                "read_only": False,
                "errors": errors,
                "principal_scope_key": self._principal_scope_key,
                "session_id": self._session_id,
                "turn_number": int(self._turn_counter),
            }
            self._last_write_receipt = dict(rejection)
            self._set_memory_operation_trace(
                surface="workstream_recap_rejected",
                note="Scoped workstream recap rejected by schema validation.",
            )
            return rejection

        source = _normalize_compact_text(args.get("source")) or f"{tool_name}:operating"
        metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
        metadata.update(
            {
                "workstream_id": workstream_id,
                "owner_role": owner_role,
                "source_kind": source_kind,
                "authority_level": RECENT_WORK_AUTHORITY_CANONICAL,
                "source_role": source_role,
                "write_invoker": "trusted_host" if trusted_operator_origin else "model_tool",
                "trusted_write_origin": trusted_operator_origin,
                "workstream_recap_capture_schema": "brainstack.workstream_recap_capture.v1",
                "current_assignment_authority": False,
            }
        )
        metadata = normalize_recent_work_metadata(
            stable_key=stable_key,
            source=source,
            metadata=metadata,
        )

        def _commit() -> None:
            assert self._store is not None
            self._store.upsert_operating_record(
                stable_key=stable_key,
                principal_scope_key=self._principal_scope_key,
                record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
                content=summary,
                owner=OPERATING_OWNER,
                source=source,
                source_session_id=self._session_id,
                source_turn_number=int(self._turn_counter),
                metadata=self._scoped_metadata(metadata),
            )

        receipt = self._commit_explicit_write(
            owner=OPERATING_OWNER,
            write_class="workstream_recap",
            source=source,
            target="operating",
            stable_key=stable_key,
            category=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content=summary,
            commit=_commit,
            extra={
                "schema": "brainstack.workstream_recap_capture.v1",
                "tool_name": tool_name,
                "read_only": False,
                "workstream_id": str(metadata.get("workstream_id") or ""),
                "owner_role": str(metadata.get("owner_role") or ""),
                "source_kind": str(metadata.get("source_kind") or ""),
                "authority_level": str(metadata.get("authority_level") or ""),
                "write_invoker": "trusted_host" if trusted_operator_origin else "model_tool",
                "trusted_write_origin": trusted_operator_origin,
                "content_excerpt": receipt_excerpt(summary),
            },
        )
        receipt["read_only"] = False
        return receipt

    def _handle_brainstack_explicit_capture(
        self,
        operation: str,
        args: Mapping[str, Any],
        *,
        trusted_operator_origin: str = "",
    ) -> Dict[str, Any]:
        tool_name = f"brainstack_{operation}"
        if self._store is None:
            return {
                "schema": "brainstack.tool_error.v1",
                "tool_name": tool_name,
                "error_code": "store_unavailable",
                "error": "Brainstack store is not initialized.",
                "read_only": False,
            }
        store = self._store
        capture, rejection = validate_explicit_capture_payload(
            args,
            operation=operation,
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
            turn_number=self._turn_counter,
            allow_operator_source_role=bool(trusted_operator_origin),
        )
        if rejection is not None:
            self._last_write_receipt = dict(rejection)
            self._set_memory_operation_trace(
                surface="explicit_capture_rejected",
                note="Explicit durable capture rejected by schema validation.",
            )
            return rejection
        assert capture is not None

        raw_commit_metadata = build_commit_metadata(capture)
        raw_commit_metadata["write_invoker"] = "trusted_host" if trusted_operator_origin else "model_tool"
        raw_commit_metadata["trusted_write_origin"] = trusted_operator_origin
        metadata = self._scoped_metadata(raw_commit_metadata)
        shelf = str(capture.get("shelf") or "")
        stable_key = str(capture.get("stable_key") or "")
        source = f"{tool_name}:{shelf}"
        content = str(capture.get("content") or capture.get("title") or "")

        def _commit() -> None:
            if shelf == "profile":
                store.upsert_profile_item(
                    stable_key=stable_key,
                    category=str(capture.get("category") or ""),
                    content=str(capture.get("content") or ""),
                    source=source,
                    confidence=float(capture.get("confidence") or 0.95),
                    metadata=metadata,
                )
                return
            if shelf == "operating":
                store.upsert_operating_record(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    record_type=str(capture.get("record_type") or ""),
                    content=str(capture.get("content") or ""),
                    owner="brainstack.explicit_capture",
                    source=source,
                    source_session_id=self._session_id,
                    source_turn_number=self._turn_counter,
                    metadata=metadata,
                )
                return
            if shelf == "task":
                store.upsert_task_item(
                    stable_key=stable_key,
                    principal_scope_key=self._principal_scope_key,
                    item_type=str(capture.get("item_type") or "task"),
                    title=str(capture.get("title") or ""),
                    due_date=str(capture.get("due_date") or ""),
                    date_scope=str(capture.get("date_scope") or ""),
                    optional=bool(capture.get("optional", False)),
                    status=str(capture.get("status") or "open"),
                    owner="brainstack.explicit_capture",
                    source=source,
                    source_session_id=self._session_id,
                    source_turn_number=self._turn_counter,
                    metadata=metadata,
                )

        receipt = self._commit_explicit_write(
            owner="brainstack.explicit_capture",
            write_class=f"explicit_{operation}",
            source=source,
            target=shelf,
            stable_key=stable_key,
            category=str(capture.get("category") or capture.get("record_type") or capture.get("item_type") or shelf),
            content=content,
            commit=_commit,
            extra={
                "schema": EXPLICIT_CAPTURE_SCHEMA_VERSION,
                "tool_name": tool_name,
                "operation": operation,
                "shelf": shelf,
                "source_role": str(capture.get("source_role") or ""),
                "write_invoker": "trusted_host" if trusted_operator_origin else "model_tool",
                "trusted_write_origin": trusted_operator_origin,
                "authority_class": str(capture.get("authority_class") or ""),
                "content_excerpt": receipt_excerpt(content),
                "supersedes_stable_key": str(capture.get("supersedes_stable_key") or ""),
                "write_contract_trace": dict(capture.get("write_contract_trace") or {}),
                "host_receipt_id": str(metadata.get("host_receipt_id") or ""),
                "host_receipt_source": "host_receipt" if str(metadata.get("host_receipt_id") or "").strip() else "",
                "host_content_hash": str(metadata.get("host_content_hash") or ""),
                "host_stable_key": str(metadata.get("host_stable_key") or ""),
                "host_scope": str(metadata.get("host_scope") or ""),
                "host_temporal_status": str(metadata.get("host_temporal_status") or ""),
                "brainstack_temporal_status": str(metadata.get("brainstack_temporal_status") or ""),
            },
        )
        receipt["read_only"] = False
        return receipt

    def _handle_brainstack_consolidate(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        if self._store is None:
            return {
                "schema": "brainstack.tool_error.v1",
                "tool_name": "brainstack_consolidate",
                "error_code": "store_unavailable",
                "error": "Brainstack store is not initialized.",
                "read_only": False,
            }
        normalized = normalize_maintenance_args(args)
        receipt = run_bounded_maintenance(
            self._store,
            apply=bool(normalized["apply"]),
            maintenance_class=str(normalized["maintenance_class"]),
            principal_scope_key=self._principal_scope_key,
        )
        receipt["tool_name"] = "brainstack_consolidate"
        receipt["read_only"] = not bool(normalized["apply"])
        self._last_maintenance_receipt = json.loads(json.dumps(receipt, ensure_ascii=True))
        return receipt

    def _handle_brainstack_recall(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        return handle_brainstack_recall(
            args=args,
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
            query_inspect=self.query_inspect,
        )

    def _handle_brainstack_inspect(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        return handle_brainstack_inspect(
            args=args,
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
            query_inspect=self.query_inspect,
        )

    def _handle_brainstack_stats(self, args: Mapping[str, Any]) -> Dict[str, Any]:
        return handle_brainstack_stats(
            args=args,
            principal_scope_key=self._principal_scope_key,
            lifecycle_status=self.lifecycle_status,
            memory_kernel_doctor=self.memory_kernel_doctor,
            last_maintenance_receipt=self._last_maintenance_receipt,
        )

    def lifecycle_status(self) -> Dict[str, Any]:
        return build_provider_lifecycle_status(
            store=self._store,
            tier2_running=self._tier2_running,
            pending_explicit_write_count=self._pending_explicit_write_count,
            session_id=self._session_id,
            principal_scope_key=self._principal_scope_key,
            pending_tier2_turns=self._pending_tier2_turns,
            tool_schemas=self.get_tool_schemas(),
            operator_only_tools=[self._runtime_handoff_update_tool_schema()],
            disabled_memory_write_tools=sorted(DISABLED_MEMORY_WRITE_TOOLS),
            last_maintenance_receipt=self._last_maintenance_receipt,
        )

    def memory_kernel_doctor(self, *, strict: bool = False) -> Dict[str, Any]:
        return build_provider_memory_kernel_doctor(
            store=self._store,
            strict=strict,
            tier2_session_end_flush_enabled=self._tier2_session_end_flush_enabled,
            tier2_running=self._tier2_running,
            pending_tier2_turns=self._pending_tier2_turns,
            last_tier2_schedule=self._last_tier2_schedule,
            last_tier2_batch_result=self._last_tier2_batch_result,
            tier2_batch_history_count=len(self._tier2_batch_history),
        )

    def query_inspect(self, *, query: str, session_id: str | None = None) -> Dict[str, Any]:
        return build_provider_query_inspect(
            store=self._store,
            query=query,
            session_id=session_id or self._session_id,
            principal_scope_key=self._principal_scope_key,
            timezone_name=self._user_timezone,
            route_resolver=self._route_resolver_override,
            profile_match_limit=self._profile_match_limit,
            continuity_recent_limit=self._continuity_recent_limit,
            continuity_match_limit=self._continuity_match_limit,
            transcript_match_limit=self._transcript_match_limit,
            transcript_char_budget=self._transcript_char_budget,
            evidence_item_budget=self._evidence_item_budget,
            graph_limit=self._graph_match_limit,
            corpus_limit=self._corpus_match_limit,
            corpus_char_budget=self._corpus_char_budget,
            operating_match_limit=self._operating_match_limit,
            render_ordinary_contract=self._ordinary_packet_behavior_contract_enabled,
        )

    def _resolve_runtime_handoff_task(self, *, task_id: str) -> Dict[str, Any] | None:
        snapshot = self.runtime_handoff_snapshot() or {}
        for task in snapshot.get("runtime_handoff_tasks") or []:
            if not isinstance(task, Mapping):
                continue
            if _normalize_compact_text(task.get("task_id")) == task_id:
                return dict(task)
        return None

    def _task_defaults_from_record(self, raw: Mapping[str, Any]) -> Dict[str, Any]:
        raw_payload = raw.get("payload")
        payload: Mapping[str, Any] = raw_payload if isinstance(raw_payload, Mapping) else {}
        task_type = _normalize_compact_text(raw.get("type"))
        if task_type == "WIKI_INGEST":
            return {
                "title": f"Wiki ingest: {_normalize_compact_text(payload.get('topic')) or 'Wiki ingest'}",
                "domain": "research",
                "action": _normalize_compact_text(payload.get("action")) or "process_wiki_ingest",
                "risk_class": "low",
                "approval_required": False,
            }
        if task_type == "ALERT":
            severity = _normalize_compact_text(payload.get("severity")) or "medium"
            return {
                "title": f"Alert: {_normalize_compact_text(payload.get('message')) or _normalize_compact_text(payload.get('component')) or 'runtime'}",
                "domain": "infrastructure",
                "action": _normalize_compact_text(payload.get("action")) or "review_alert",
                "risk_class": severity if severity in {"low", "medium", "high"} else "medium",
                "approval_required": severity == "high",
            }
        if task_type == "ROADMAP_ITEM_BLOCKED":
            return {
                "title": _normalize_compact_text(payload.get("task")) or _normalize_compact_text(payload.get("title")) or "Blocked roadmap item",
                "domain": _normalize_compact_text(payload.get("domain")) or "unknown",
                "action": _normalize_compact_text(payload.get("action")) or "awaiting_user_approval",
                "risk_class": "high",
                "approval_required": True,
            }
        domain = _normalize_compact_text(payload.get("domain")) or "unknown"
        risk_class = _normalize_compact_text(payload.get("risk_class") or payload.get("severity"))
        if risk_class not in {"low", "medium", "high"}:
            risk_class = "medium"
        return {
            "title": _normalize_compact_text(payload.get("title") or payload.get("task") or payload.get("message") or payload.get("topic") or task_type or "Runtime handoff task"),
            "domain": domain,
            "action": _normalize_compact_text(payload.get("action")),
            "risk_class": risk_class,
            "approval_required": bool(payload.get("approval_required")) or domain == "unknown",
        }

    def _handle_runtime_handoff_update(self, args: Mapping[str, Any], **kwargs) -> Dict[str, Any]:
        if not self._store:
            return {"error": "BrainstackStore is not initialized"}
        task_id = _normalize_compact_text(args.get("task_id"))
        status = _normalize_compact_text(args.get("status")).lower()
        if not task_id:
            return {"error": "task_id is required"}
        if status not in ALL_TASK_STATUSES:
            return {"error": f"invalid status: {status}"}

        if self._hermes_home:
            hermes_home = Path(self._hermes_home).resolve()
        else:
            from hermes_constants import get_hermes_home

            hermes_home = get_hermes_home().resolve()
        current_path, current_raw = locate_task_record(hermes_home, task_id=task_id)
        current_task = self._resolve_runtime_handoff_task(task_id=task_id) or {}
        defaults = self._task_defaults_from_record(current_raw or {})

        title = _normalize_compact_text(current_task.get("title")) or defaults.get("title") or task_id
        domain = _normalize_compact_text(current_task.get("domain")) or defaults.get("domain") or "unknown"
        action = _normalize_compact_text(current_task.get("action")) or defaults.get("action") or ""
        risk_class = _normalize_compact_text(current_task.get("risk_class")) or defaults.get("risk_class") or "medium"
        approval_required = bool(current_task.get("approval_required")) if current_task else bool(defaults.get("approval_required"))
        result_summary = _normalize_compact_text(args.get("result_summary"))
        note = _normalize_compact_text(args.get("note"))
        artifact_refs = [str(item).strip() for item in (args.get("artifact_refs") or []) if str(item).strip()]
        approved_by = _normalize_compact_text(args.get("approved_by"))
        enforcement_error = ""
        enforcement_message = ""
        if approval_required and status in {"in_progress", "completed"} and not approved_by:
            enforcement_error = "approval_required"
            enforcement_message = "This task requires explicit approval before it can be started or completed."
            status = "blocked"
            if not note:
                note = enforcement_message
        metadata = {
            "runtime_handoff": True,
            "task_id": task_id,
            "domain": domain,
            "action": action,
            "risk_class": risk_class,
            "approval_required": approval_required,
            "result_summary": result_summary,
            "artifact_refs": artifact_refs,
            "note": note,
            "approved_by": approved_by,
            "runtime_writeback": True,
            "runtime_writeback_session_id": str(kwargs.get("session_id") or self._session_id or "").strip(),
        }
        self.upsert_runtime_handoff_task(
            title=title,
            task_id=task_id,
            domain=domain,
            action=action,
            risk_class=risk_class,
            approval_required=approval_required,
            status=status,
            source="runtime.handoff_writeback",
            metadata=metadata,
        )

        if current_raw is not None:
            raw_record: Dict[str, Any] = dict(current_raw)
        else:
            raw_record = {
                "id": task_id,
                "type": "RUNTIME_HANDOFF",
                "created": utc_now_iso(),
                "payload": {
                    "title": title,
                    "domain": domain,
                    "action": action,
                    "risk_class": risk_class,
                    "approval_required": approval_required,
                },
            }
        raw_record["status"] = status
        raw_record["updated_at"] = utc_now_iso()
        if result_summary:
            raw_record["result_summary"] = result_summary
        if note:
            raw_record["note"] = note
        if artifact_refs:
            raw_record["artifact_refs"] = artifact_refs
        if approved_by:
            raw_record["approved_by"] = approved_by
        if status in TERMINAL_TASK_STATUSES:
            raw_record["completed_at"] = utc_now_iso()
        elif status == "blocked":
            raw_record["blocked_at"] = utc_now_iso()
        elif status in ACTIVE_TASK_STATUSES:
            raw_record["active_at"] = utc_now_iso()

        destination = write_task_record(
            hermes_home,
            record=raw_record,
            status=status,
            current_path=current_path,
        )
        return {
            "error": enforcement_error,
            "message": enforcement_message,
            "status": status,
            "task_id": task_id,
            "approval_required": approval_required,
            "approved_by": approved_by,
            "path": str(destination),
            "brainstack_writeback": "committed",
        }
