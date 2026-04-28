from __future__ import annotations

from ..capture_pipeline import build_capture_plan_from_structured
from ..literal_index import detect_integer_literals, detect_url_literals
from ..memory_write_receipts import (
    CapturePlan,
    build_ack_plan,
    commitment_guard_trace,
    compute_receipt_coverage,
)
from ..transcript import format_turn_content
from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    Dict,
    List,
    Mapping,
    OPERATING_RECORD_CANONICAL_POLICY,
    OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
    Path,
    Sequence,
    _normalize_compact_text,
    build_task_stable_key,
    hashlib,
    json,
    logger,
    summarize_runtime_handoff_dirs,
    validate_output_against_contract,
    utc_now_iso,
)

_RECEIPT_CAPTURE_PROFILE_PREFIXES = ("identity.", "preference.", "reference.")


def _target_slot_from_profile_item(item: Mapping[str, Any]) -> str:
    slot = _normalize_compact_text(item.get("slot"))
    if not slot:
        return ""
    if ":" in slot and "." not in slot:
        slot = slot.replace(":", ".", 1)
    return slot


def _storage_key_from_target_slot(target_slot: str) -> str:
    slot = _normalize_compact_text(target_slot)
    if slot.startswith(_RECEIPT_CAPTURE_PROFILE_PREFIXES):
        return slot.replace(".", ":", 1)
    return ""


def _category_from_target_slot(target_slot: str) -> str:
    prefix = _normalize_compact_text(target_slot).split(".", 1)[0]
    return prefix or "profile"


class ProviderInspectionMixin(ProviderRuntimeBase):
    def _receipt_capture_items_from_tier2(
        self,
        extracted: Mapping[str, Any],
        *,
        source_text: str = "",
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        source_urls = detect_url_literals(source_text)
        source_age_numbers = detect_integer_literals(source_text, min_value=0, max_value=130)
        for index, item in enumerate(list(extracted.get("profile_items") or []), start=1):
            if not isinstance(item, Mapping):
                continue
            target_slot = _target_slot_from_profile_item(item)
            stable_key = _storage_key_from_target_slot(target_slot)
            content = _normalize_compact_text(item.get("content"))
            if target_slot == "reference.repository_url":
                if content not in source_urls and len(source_urls) == 1:
                    content = source_urls[0]
                elif source_urls and content not in source_urls:
                    content = ""
            elif target_slot == "identity.age":
                if content not in source_age_numbers and len(source_age_numbers) == 1:
                    content = source_age_numbers[0]
                elif source_age_numbers and content not in source_age_numbers:
                    content = ""
            if not target_slot or not stable_key or not content:
                continue
            try:
                confidence = float(item.get("confidence", 0.8))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence <= 0:
                continue
            items.append(
                {
                    "target_slot": target_slot,
                    "stable_key": stable_key,
                    "normalized_value": content,
                    "surface_value": content,
                    "source_span_id": f"tier2_profile_item:{index}:{stable_key}",
                    "capture_intent": "explicit_capture",
                    "confidence": confidence,
                    "required_for_full_ack": True,
                }
            )
        return items

    def _validate_explicit_capture_receipts(
        self,
        *,
        user_content: str,
        session_id: str,
    ) -> Dict[str, Any]:
        trace: Dict[str, Any] = {
            "schema": "brainstack.live_explicit_capture_validation.v1",
            "applied": False,
            "status": "not_applicable",
            "reason_code": "NO_USER_CONTENT",
            "capture_plan": None,
            "memory_write_receipts": [],
            "receipt_coverage": None,
            "ack_plan": None,
            "tier2": {
                "ran": False,
                "status": "not_run",
                "profile_item_count": 0,
                "state_count": 0,
                "relation_count": 0,
            },
        }
        user_text = _normalize_compact_text(user_content)
        if not user_text or self._store is None:
            return trace
        if not bool(self._config.get("explicit_capture_validation_enabled", True)):
            trace.update({"reason_code": "EXPLICIT_CAPTURE_VALIDATION_DISABLED", "status": "skipped"})
            return trace
        extractor = getattr(self, "_run_tier2_extractor", None)
        if not callable(extractor):
            trace.update({"reason_code": "TIER2_EXTRACTOR_UNAVAILABLE", "status": "skipped"})
            return trace

        active_session_id = session_id or self._session_id
        turn_number = int(self._turn_counter or 0)
        turn_id = f"{active_session_id}:{turn_number}:final_validation"
        source_event_id = f"{turn_id}:user"
        transcript_row = {
            "id": 0,
            "turn_number": turn_number or 1,
            "kind": "turn",
            "content": format_turn_content(user_text, ""),
            "created_at": utc_now_iso(),
        }
        try:
            extracted = extractor(
                [transcript_row],
                session_id=active_session_id,
                turn_number=turn_number,
                trigger_reason="final_output_validation_explicit_capture",
            )
        except Exception as exc:
            logger.warning("Brainstack explicit capture validation extractor failed: %s", exc)
            trace.update(
                {
                    "applied": True,
                    "status": "failed",
                    "reason_code": "TIER2_EXTRACTOR_FAILED",
                    "error": str(exc),
                }
            )
            return trace
        if not isinstance(extracted, Mapping):
            trace.update(
                {
                    "applied": True,
                    "status": "failed",
                    "reason_code": "TIER2_EXTRACTOR_INVALID_PAYLOAD",
                }
            )
            return trace

        trace["tier2"] = {
            "ran": True,
            "status": "ok",
            "profile_item_count": len(list(extracted.get("profile_items") or [])),
            "state_count": len(list(extracted.get("states") or [])),
            "relation_count": len(list(extracted.get("relations") or [])),
        }

        reconcile = getattr(self, "_reconcile_tier2_payload", None)
        if callable(reconcile):
            try:
                action_counts, writes_performed, operating_promotions = reconcile(
                    session_id=active_session_id,
                    turn_number=turn_number,
                    trigger_reason="final_output_validation_explicit_capture",
                    extracted=dict(extracted),
                    transcript_rows=[transcript_row],
                    consolidation_source={"source_kind": "current_user_turn", "turn_numbers": [turn_number or 1]},
                )
                trace["tier2"].update(
                    {
                        "action_counts": dict(action_counts or {}),
                        "writes_performed": int(writes_performed or 0),
                        "operating_promotions": dict(operating_promotions or {}),
                    }
                )
            except Exception as exc:
                logger.warning("Brainstack explicit capture validation reconcile failed: %s", exc)
                trace["tier2"].update({"reconcile_error": str(exc)})

        capture_items = self._receipt_capture_items_from_tier2(extracted, source_text=user_text)
        if not capture_items:
            trace.update(
                {
                    "applied": True,
                    "status": "no_capture",
                    "reason_code": "NO_RECEIPT_ELIGIBLE_PROFILE_ITEMS",
                }
            )
            return trace

        plan_payload = build_capture_plan_from_structured(
            turn_id=turn_id,
            source_event_id=source_event_id,
            source_role="user",
            items=capture_items,
        )
        plan = CapturePlan.from_proposals(
            turn_id=turn_id,
            source_event_id=source_event_id,
            proposals=plan_payload.get("proposals", []),
            capture_plan_id=str(plan_payload.get("capture_plan_id") or ""),
            plan_status=str(plan_payload.get("plan_status") or "has_proposals"),
        )
        receipts: List[Mapping[str, Any]] = []
        for proposal in plan.proposals:
            capture_item = next(
                (item for item in capture_items if item.get("stable_key") == proposal.stable_key),
                None,
            )
            if not isinstance(capture_item, Mapping):
                continue
            result = self._handle_brainstack_explicit_capture(
                "remember",
                {
                    "shelf": "profile",
                    "stable_key": proposal.stable_key,
                    "category": _category_from_target_slot(proposal.target_slot),
                    "content": proposal.normalized_value,
                    "source_role": "user",
                    "authority_class": "profile",
                    "confidence": float(capture_item.get("confidence") or 0.95),
                    "metadata": {
                        "source_event_id": source_event_id,
                        "source_span_id": proposal.source_span_id,
                        "target_slot": proposal.target_slot,
                        "proposal_id": proposal.proposal_id,
                        "capture_plan_id": plan.capture_plan_id,
                        "capture_intent": str(capture_item.get("capture_intent") or "explicit_capture"),
                        "normalization_method": "tier2_structured_extractor",
                    },
                },
                trusted_operator_origin="brainstack_internal",
            )
            if isinstance(result, Mapping) and isinstance(result.get("memory_write_receipt"), Mapping):
                receipts.append(result["memory_write_receipt"])

        coverage = compute_receipt_coverage(
            plan,
            receipts,
            principal_scope_key=self._principal_scope_key,
            workspace_scope_key=str(getattr(self, "_agent_workspace", "") or ""),
            session_id=self._session_id,
        )
        ack_plan = build_ack_plan(plan, coverage)
        trace.update(
            {
                "applied": True,
                "status": "receipt_coverage_complete" if coverage.get("full_ack_allowed") else "receipt_coverage_incomplete",
                "reason_code": "" if coverage.get("full_ack_allowed") else "INCOMPLETE_RECEIPT_COVERAGE",
                "capture_plan": plan.to_dict(),
                "memory_write_receipts": [dict(receipt) for receipt in receipts],
                "receipt_coverage": dict(coverage),
                "ack_plan": dict(ack_plan),
                "memory_commitment_guard": commitment_guard_trace(
                    capture_plan=plan,
                    coverage=coverage,
                    commitment_claim_present=True,
                )["memory_commitment_guard"],
            }
        )
        return trace

    def _ensure_behavior_authority_ready(self, *, surface: str) -> Dict[str, Any]:
        if not self._store:
            return {
                "surface": surface,
                "repair_attempted": False,
                "repair_report": None,
                "raw_contract_present": False,
                "compiled_policy_present": False,
                "blocked": False,
                "reason": "store_unavailable",
            }

        snapshot_before = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        raw_before = snapshot_before.get("raw_contract") if isinstance(snapshot_before, Mapping) else None
        compiled_before = (
            snapshot_before.get("compiled_policy") if isinstance(snapshot_before, Mapping) else {}
        ) or {}
        raw_before_present = bool(isinstance(raw_before, Mapping) and raw_before.get("present"))

        repair_attempted = raw_before_present and not bool(compiled_before.get("present"))
        repair_report: Dict[str, Any] | None = None
        if repair_attempted:
            repair_report = self._store.repair_behavior_contract_authority(
                principal_scope_key=self._principal_scope_key,
            )

        snapshot_after = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        raw_after = snapshot_after.get("raw_contract") if isinstance(snapshot_after, Mapping) else None
        compiled_after = (
            snapshot_after.get("compiled_policy") if isinstance(snapshot_after, Mapping) else {}
        ) or {}
        raw_after_present = bool(isinstance(raw_after, Mapping) and raw_after.get("present"))
        blocked = raw_after_present and not bool(compiled_after.get("present"))
        result = {
            "surface": surface,
            "repair_attempted": repair_attempted,
            "repair_report": json.loads(json.dumps(repair_report, ensure_ascii=True))
            if isinstance(repair_report, Mapping)
            else None,
            "raw_contract_present": raw_after_present,
            "compiled_policy_present": bool(compiled_after.get("present")),
            "blocked": blocked,
            "reason": (
                "active_behavior_authority_missing_compiled_policy"
                if blocked
                else "repair_converged"
                if repair_attempted
                else "authority_ready"
            ),
            "snapshot": snapshot_after,
        }

        trace = dict(getattr(self, "_last_behavior_policy_trace", None) or {})
        authority_trace = dict(trace.get("authority_bootstrap") or {})
        authority_trace[surface] = {
            "surface": surface,
            "repair_attempted": repair_attempted,
            "repair_report": result["repair_report"],
            "raw_contract_present": raw_after_present,
            "compiled_policy_present": bool(compiled_after.get("present")),
            "blocked": blocked,
            "reason": result["reason"],
        }
        trace["authority_bootstrap"] = authority_trace
        self._last_behavior_policy_trace = trace
        return result

    def behavior_policy_trace(self) -> Dict[str, Any] | None:
        if self._last_behavior_policy_trace is None:
            return None
        return json.loads(json.dumps(self._last_behavior_policy_trace, ensure_ascii=True))

    def behavior_policy_snapshot(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)

    def memory_authority_debug(self) -> Dict[str, Any] | None:
        if self._last_memory_authority_debug is None:
            return None
        return json.loads(json.dumps(self._last_memory_authority_debug, ensure_ascii=True))

    def inspector_proof_snapshot(self) -> Dict[str, Any] | None:
        behavior_snapshot = self.behavior_policy_snapshot()
        memory_debug = self.memory_authority_debug()
        behavior_trace = self.behavior_policy_trace()
        operating_snapshot = self.operating_context_snapshot()
        operating_trace = self.operating_context_trace()
        memory_trace = self.memory_operation_trace()
        graph_trace = self.graph_ingress_trace()
        if not any(
            value is not None
            for value in (
                behavior_snapshot,
                memory_debug,
                behavior_trace,
                operating_snapshot,
                operating_trace,
                memory_trace,
                graph_trace,
            )
        ):
            return None

        canonical_revision = int((memory_debug or {}).get("canonical_generation_revision") or 0)
        compiled_revision = int((memory_debug or {}).get("compiled_policy_source_revision") or 0)
        active_lane_revision = int((memory_debug or {}).get("active_lane_source_revision") or 0)
        read_side_effect_count = int((memory_debug or {}).get("read_side_effect_count") or 0)
        write_receipts_in_packet = bool((memory_debug or {}).get("write_receipts_in_packet"))

        snapshot = {
            "authority": {
                "canonical_generation_revision": canonical_revision,
                "compiled_policy_source_revision": compiled_revision,
                "active_lane_source_revision": active_lane_revision,
                "converged": (
                    canonical_revision > 0
                    and compiled_revision == canonical_revision
                    and active_lane_revision == canonical_revision
                ),
            },
            "read_surface": {
                "read_side_effect_count": read_side_effect_count,
                "write_receipts_in_packet": write_receipts_in_packet,
                "clean": read_side_effect_count == 0 and not write_receipts_in_packet,
            },
            "routing": json.loads(json.dumps(self._last_prefetch_routing or {}, ensure_ascii=True)),
            "channels": json.loads(json.dumps(self._last_prefetch_channels or [], ensure_ascii=True)),
            "behavior_policy_snapshot": behavior_snapshot,
            "behavior_policy_trace": behavior_trace,
            "memory_authority_debug": memory_debug,
            "operating_context_snapshot": operating_snapshot,
            "operating_context_trace": operating_trace,
            "memory_operation_trace": memory_trace,
            "graph_ingress_trace": graph_trace,
            "prefetch_debug": json.loads(json.dumps(self._last_prefetch_debug, ensure_ascii=True))
            if self._last_prefetch_debug is not None
            else None,
            "host_runtime_layers_excluded": list((memory_debug or {}).get("host_runtime_layers_excluded") or []),
        }
        return json.loads(json.dumps(snapshot, ensure_ascii=True))

    def inspector_proof_report(self) -> str | None:
        snapshot = self.inspector_proof_snapshot()
        if snapshot is None:
            return None
        authority = dict(snapshot.get("authority") or {})
        read_surface = dict(snapshot.get("read_surface") or {})
        routing = dict(snapshot.get("routing") or {})
        graph_trace = dict(snapshot.get("graph_ingress_trace") or {})
        lines = [
            "# Brainstack Inspector Proof",
            "",
            "## Authority",
            f"- converged: {authority.get('converged', False)}",
            f"- canonical_generation_revision: {authority.get('canonical_generation_revision', 0)}",
            f"- compiled_policy_source_revision: {authority.get('compiled_policy_source_revision', 0)}",
            f"- active_lane_source_revision: {authority.get('active_lane_source_revision', 0)}",
            "",
            "## Read Surface",
            f"- clean: {read_surface.get('clean', False)}",
            f"- read_side_effect_count: {read_surface.get('read_side_effect_count', 0)}",
            f"- write_receipts_in_packet: {read_surface.get('write_receipts_in_packet', False)}",
            "",
            "## Routing",
            f"- applied_mode: {routing.get('applied_mode', '')}",
            f"- source: {routing.get('source', '')}",
            f"- resolution_status: {routing.get('resolution_status', '')}",
            f"- resolution_error_class: {routing.get('resolution_error_class', '')}",
            "",
            "## Graph Ingress",
            f"- status: {graph_trace.get('status', '')}",
        ]
        return "\n".join(lines)

    def operating_context_snapshot(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.get_operating_context_snapshot(
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
        )

    def live_system_state_snapshot(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.get_live_system_state_snapshot(
            principal_scope_key=self._principal_scope_key,
        )

    def runtime_handoff_snapshot(self) -> Dict[str, Any] | None:
        snapshot = self.operating_context_snapshot()
        if not isinstance(snapshot, Mapping):
            return None
        filesystem_summary: Dict[str, Any] = {}
        if self._hermes_home:
            try:
                filesystem_summary = summarize_runtime_handoff_dirs(Path(self._hermes_home).resolve())
            except Exception:
                logger.warning("Brainstack runtime handoff filesystem summary failed", exc_info=True)
        return {
            "principal_scope_key": str(snapshot.get("principal_scope_key") or "").strip(),
            "canonical_policy": dict(snapshot.get("canonical_policy") or {}),
            "runtime_approval_policy": dict(snapshot.get("runtime_approval_policy") or {}),
            "runtime_handoff_tasks": [dict(item) for item in (snapshot.get("runtime_handoff_tasks") or []) if isinstance(item, Mapping)],
            "runtime_handoff_filesystem": filesystem_summary,
            "session_recovery_contract": dict(snapshot.get("session_recovery_contract") or {}),
            "live_system_state": list(snapshot.get("live_system_state") or []),
            "current_commitments": list(snapshot.get("current_commitments") or []),
            "next_steps": list(snapshot.get("next_steps") or []),
            "open_decisions": list(snapshot.get("open_decisions") or []),
        }

    def canonical_policy_snapshot(self) -> Dict[str, Any] | None:
        snapshot = self.operating_context_snapshot()
        if not isinstance(snapshot, Mapping):
            return None
        return {
            "principal_scope_key": str(snapshot.get("principal_scope_key") or "").strip(),
            "canonical_policy": dict(snapshot.get("canonical_policy") or {}),
            "runtime_read_only": True,
        }

    def operating_context_trace(self) -> Dict[str, Any] | None:
        if self._last_operating_context_trace is None:
            return None
        return json.loads(json.dumps(self._last_operating_context_trace, ensure_ascii=True))

    def upsert_runtime_approval_policy(
        self,
        *,
        domains: Sequence[Mapping[str, Any]],
        default_action: str = "ask_user",
        source: str = "brainstack.runtime_approval_policy",
    ) -> Dict[str, Any] | None:
        normalized_domains: List[Dict[str, Any]] = []
        for raw in domains:
            if not isinstance(raw, Mapping):
                continue
            name = _normalize_compact_text(raw.get("name") or raw.get("domain"))
            if not name:
                continue
            normalized_domains.append(
                {
                    "name": name,
                    "approval_required": bool(raw.get("approval_required")),
                    "default_action": _normalize_compact_text(raw.get("default_action") or raw.get("action")),
                    "risk_class": _normalize_compact_text(raw.get("risk_class")),
                }
            )
        if not normalized_domains:
            return None
        content = "Runtime approval policy: " + ", ".join(
            f"{item['name']}={item['default_action'] or ('ask_user' if item['approval_required'] else 'auto_approved')}"
            for item in normalized_domains
        )
        committed = self._upsert_brainstack_operating_record(
            record_type=OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
            content=content,
            source=source,
            metadata={
                "default_action": _normalize_compact_text(default_action) or "ask_user",
                "domains": normalized_domains,
            },
        )
        if not committed:
            return None
        return {
            "status": "committed",
            "record_type": OPERATING_RECORD_RUNTIME_APPROVAL_POLICY,
            "domain_count": len(normalized_domains),
            "source": source,
        }

    def upsert_canonical_policy_rule(
        self,
        *,
        content: str,
        rule_id: str = "",
        rule_class: str = "user_rule",
        source_authority: str = "explicit_user_rule",
        source: str = "brainstack.canonical_policy",
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        normalized_content = _normalize_compact_text(content)
        if not self._store or not normalized_content:
            return None
        normalized_rule_id = _normalize_compact_text(rule_id) or hashlib.sha256(
            normalized_content.encode("utf-8")
        ).hexdigest()[:16]
        stable_key = "::".join(
            [
                "canonical_policy",
                self._principal_scope_key or "global",
                normalized_rule_id,
            ]
        )
        committed = self._upsert_brainstack_operating_record(
            record_type=OPERATING_RECORD_CANONICAL_POLICY,
            content=normalized_content,
            source=source,
            metadata={
                **dict(metadata or {}),
                "rule_id": normalized_rule_id,
                "rule_class": _normalize_compact_text(rule_class) or "user_rule",
                "source_authority": _normalize_compact_text(source_authority) or "explicit_user_rule",
                "canonical_policy": True,
                "promotion_mode": "explicit_only",
                "runtime_read_only": True,
            },
            stable_key_override=stable_key,
        )
        if not committed:
            return None
        return {
            "status": "committed",
            "record_type": OPERATING_RECORD_CANONICAL_POLICY,
            "rule_id": normalized_rule_id,
            "rule_class": _normalize_compact_text(rule_class) or "user_rule",
            "source": source,
            "runtime_read_only": True,
        }

    def upsert_runtime_handoff_task(
        self,
        *,
        title: str,
        task_id: str = "",
        domain: str = "",
        action: str = "",
        risk_class: str = "",
        approval_required: bool = False,
        due_date: str = "",
        date_scope: str = "none",
        optional: bool = False,
        status: str = "open",
        source: str = "brainstack.runtime_handoff_task",
        metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any] | None:
        if not self._store:
            return None
        normalized_title = _normalize_compact_text(title)
        if not normalized_title:
            return None
        normalized_task_id = _normalize_compact_text(task_id)
        stable_key = normalized_task_id or build_task_stable_key(
            principal_scope_key=self._principal_scope_key,
            item_type="task",
            due_date=str(due_date or "").strip(),
            title=normalized_title,
        )
        task_metadata = dict(self._scoped_metadata(metadata))
        task_metadata.update(
            {
                "runtime_handoff": True,
                "task_id": normalized_task_id or stable_key,
                "domain": _normalize_compact_text(domain),
                "action": _normalize_compact_text(action),
                "risk_class": _normalize_compact_text(risk_class),
                "approval_required": bool(approval_required),
            }
        )
        self._store.upsert_task_item(
            stable_key=stable_key,
            principal_scope_key=self._principal_scope_key,
            item_type="task",
            title=normalized_title,
            due_date=str(due_date or "").strip(),
            date_scope=str(date_scope or "none").strip() or "none",
            optional=optional,
            status=str(status or "open").strip() or "open",
            owner="brainstack.task_memory",
            source=source,
            source_session_id=self._session_id,
            source_turn_number=self._turn_counter,
            metadata=task_metadata,
        )
        return {
            "status": "committed",
            "stable_key": stable_key,
            "task_id": task_metadata.get("task_id"),
            "title": normalized_title,
        }

    def memory_operation_trace(self) -> Dict[str, Any] | None:
        if self._last_memory_operation_trace is None:
            return None
        return json.loads(json.dumps(self._last_memory_operation_trace, ensure_ascii=True))

    def graph_ingress_trace(self) -> Dict[str, Any] | None:
        if self._last_graph_ingress_trace is None:
            return None
        return json.loads(json.dumps(self._last_graph_ingress_trace, ensure_ascii=True))

    def repair_memory_authority(self) -> Dict[str, Any] | None:
        if not self._store:
            return None
        report = self._store.repair_behavior_contract_authority(principal_scope_key=self._principal_scope_key)
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        self._last_memory_authority_debug = {
            "surface": "repair_memory_authority",
            "repair_report": report,
            "behavior_policy_snapshot": snapshot,
            "host_runtime_layers_excluded": [
                "host persona",
                "runtime tools",
                "delivery options",
                "non-Brainstack system prompt layers",
            ],
        }
        trace = dict(self._last_behavior_policy_trace or {})
        trace["repair_memory_authority"] = {
            "surface": "repair_memory_authority",
            "report": dict(report or {}),
            "snapshot": snapshot,
        }
        self._last_behavior_policy_trace = trace
        return json.loads(json.dumps(report, ensure_ascii=True))

    def apply_behavior_policy_correction(self, *, rule_id: str, replacement_text: str) -> Dict[str, Any] | None:
        if not self._store:
            return None
        return self._store.apply_behavior_policy_correction(
            principal_scope_key=self._principal_scope_key,
            rule_id=rule_id,
            replacement_text=replacement_text,
            source="behavior_policy_correction:provider",
        )

    def validate_assistant_output(
        self,
        content: str,
        *,
        user_content: str = "",
        session_id: str = "",
    ) -> Dict[str, Any] | None:
        if not self._store:
            return None
        memory_validation = self._validate_explicit_capture_receipts(
            user_content=user_content,
            session_id=session_id,
        )
        if not self._ordinary_reply_output_validation_enabled:
            trace = dict(self._last_behavior_policy_trace or {})
            trace["final_output_validation"] = {
                "surface": "final_output_validation",
                "applied": False,
                "changed": False,
                "status": "skipped",
                "blocked": False,
                "can_ship": True,
                "block_reason": "",
                "repair_count": 0,
                "remaining_violation_count": 0,
                "contract": {
                    "active": False,
                    "ordinary_reply_validation_enabled": False,
                },
            }
            if memory_validation.get("applied"):
                trace["final_output_validation"]["memory_commitment_validation"] = dict(memory_validation)
            self._last_behavior_policy_trace = trace
            if not memory_validation.get("applied"):
                return None
            coverage = memory_validation.get("receipt_coverage")
            can_ship = True
            if isinstance(coverage, Mapping) and coverage.get("coverage_status") not in {"complete", "not_applicable"}:
                can_ship = False
            return {
                "content": str(content or ""),
                "changed": False,
                "applied": True,
                "status": str(memory_validation.get("status") or "receipt_validation"),
                "blocked": not can_ship,
                "can_ship": can_ship,
                "block_reason": "" if can_ship else "INCOMPLETE_RECEIPT_COVERAGE",
                "memory_commitment_validation": dict(memory_validation),
            }
        authority_state = self._ensure_behavior_authority_ready(surface="final_output_validation")
        if authority_state.get("blocked"):
            result = {
                "content": str(content or ""),
                "changed": False,
                "applied": True,
                "status": "advisory",
                "blocked": False,
                "can_ship": True,
                "block_reason": "",
                "contract": {
                    "active": True,
                    "authority_required": True,
                    "compiled_policy_present": False,
                    "sources": [],
                },
                "enforcement_mode": "ordinary_reply",
                "repairs": [],
                "remaining_violations": [
                    {
                        "kind": "behavior_policy_authority",
                        "violation": "compiled_policy_missing_for_active_authority",
                        "repair": "repair_or_fail_closed",
                        "enforcement": "advisory",
                    }
                ],
            }
            raw_contract = result.get("contract")
            contract: Mapping[str, Any] = raw_contract if isinstance(raw_contract, Mapping) else {}
            trace = dict(self._last_behavior_policy_trace or {})
            trace["final_output_validation"] = {
                "surface": "final_output_validation",
                "applied": True,
                "changed": False,
                "status": "advisory",
                "blocked": False,
                "can_ship": True,
                "block_reason": "",
                "repair_count": 0,
                "remaining_violation_count": 1,
                "contract": dict(contract),
            }
            self._last_behavior_policy_trace = trace
            return result
        compiled_policy_record = self._store.get_compiled_behavior_policy(principal_scope_key=self._principal_scope_key)
        compiled_policy = (
            dict(compiled_policy_record.get("policy") or {})
            if isinstance(compiled_policy_record, dict)
            else None
        )
        result = validate_output_against_contract(
            content=content,
            compiled_policy=compiled_policy,
            enforcement_mode="ordinary_reply",
        )
        raw_contract = result.get("contract")
        contract = raw_contract if isinstance(raw_contract, Mapping) else {}
        repairs = result.get("repairs")
        remaining_violations = result.get("remaining_violations")
        trace = dict(self._last_behavior_policy_trace or {})
        trace["final_output_validation"] = {
            "surface": "final_output_validation",
            "applied": bool(result.get("applied")),
            "changed": bool(result.get("changed")),
            "status": str(result.get("status") or ""),
            "blocked": bool(result.get("blocked")),
            "can_ship": bool(result.get("can_ship", True)),
            "block_reason": str(result.get("block_reason") or ""),
            "repair_count": len(repairs) if isinstance(repairs, Sequence) and not isinstance(repairs, (str, bytes)) else 0,
            "remaining_violation_count": len(remaining_violations)
            if isinstance(remaining_violations, Sequence) and not isinstance(remaining_violations, (str, bytes))
            else 0,
            "contract": dict(contract),
        }
        if memory_validation.get("applied"):
            result["memory_commitment_validation"] = dict(memory_validation)
            trace["final_output_validation"]["memory_commitment_validation"] = dict(memory_validation)
            coverage = memory_validation.get("receipt_coverage")
            if isinstance(coverage, Mapping) and coverage.get("coverage_status") not in {"complete", "not_applicable"}:
                result["blocked"] = True
                result["can_ship"] = False
                result["block_reason"] = "INCOMPLETE_RECEIPT_COVERAGE"
                trace["final_output_validation"]["blocked"] = True
                trace["final_output_validation"]["can_ship"] = False
                trace["final_output_validation"]["block_reason"] = "INCOMPLETE_RECEIPT_COVERAGE"
        self._last_behavior_policy_trace = trace
        return result

    def record_output_validation_delivery(self, result: Mapping[str, Any] | None, *, delivered_content: str) -> None:
        trace = dict(self._last_behavior_policy_trace or {})
        final_trace = dict(trace.get("final_output_validation") or {})
        final_trace.update(
            {
                "delivered": True,
                "delivered_content_changed": str(delivered_content or "") != str(result.get("content") or "")
                if isinstance(result, Mapping)
                else False,
                "delivered_status": str(result.get("status") or "") if isinstance(result, Mapping) else "",
                "delivered_blocked": bool(result.get("blocked")) if isinstance(result, Mapping) else False,
                "delivered_can_ship": bool(result.get("can_ship", True)) if isinstance(result, Mapping) else True,
                "delivered_remaining_violation_count": len(list(result.get("remaining_violations") or []))
                if isinstance(result, Mapping)
                else 0,
            }
        )
        trace["final_output_validation"] = final_trace
        self._last_behavior_policy_trace = trace
