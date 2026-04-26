from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    Dict,
    _debug_row_snapshot,
    _extract_heading_titles,
    _normalize_compact_text,
    build_consolidation_source,
    build_system_prompt_projection,
    build_turn_ingest_plan,
    build_working_memory_packet,
    continuity_adapter,
    graph_adapter,
    logger,
    time,
)

class PrefetchSyncMixin(ProviderRuntimeBase):
    def _consolidate_recent_work_operating_truth(
        self,
        *,
        session_id: str,
        turn_number: int,
        source: str,
    ) -> Dict[str, Any]:
        if not self._store or not session_id:
            return {"recent_work_promoted": False, "open_decisions_promoted": 0}
        continuity_rows = self._store.recent_continuity(session_id=session_id, limit=12)
        summary_row = next(
            (
                row
                for row in continuity_rows
                if str(row.get("kind") or "").strip() == "tier2_summary"
                and _normalize_compact_text(row.get("content"))
            ),
            None,
        )
        promoted_summary = False
        metadata = {"session_id": session_id, "turn_number": turn_number}
        if isinstance(summary_row, dict):
            summary_metadata = {
                **metadata,
                "consolidation_source": build_consolidation_source([summary_row], source_kind="continuity"),
            }
            promoted_summary = self._promote_recent_work_summary(
                content=str(summary_row.get("content") or ""),
                source=source,
                metadata=summary_metadata,
            )
        decision_rows = [
            str(row.get("content") or "")
            for row in continuity_rows
            if str(row.get("kind") or "").strip() == "decision"
        ]
        promoted_decisions = self._promote_open_decisions(
            decisions=decision_rows,
            source=source,
            metadata=metadata,
        )
        return {
            "recent_work_promoted": promoted_summary,
            "open_decisions_promoted": promoted_decisions,
        }

    def system_prompt_block(self) -> str:
        if not self._store:
            return ""
        self._ensure_behavior_authority_ready(surface="system_prompt_block")
        projection = build_system_prompt_projection(
            self._store,
            profile_limit=self._profile_prompt_limit,
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
            include_behavior_contract=self._system_prompt_behavior_contract_enabled,
        )
        block = str(projection.get("block") or "")
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        trace = dict(self._last_behavior_policy_trace or {})
        contract_title = str(snapshot.get("compiled_policy", {}).get("title") or "")
        trace["system_prompt_block"] = {
            "surface": "system_prompt_block",
            "injected": bool(contract_title and contract_title in block),
            "section_present": bool(projection.get("contract_present")),
            "title_present": bool(contract_title and contract_title in block),
            "snapshot": snapshot,
            "projection": dict(projection),
        }
        self._last_behavior_policy_trace = trace
        operating_snapshot = self._store.get_operating_context_snapshot(
            principal_scope_key=self._principal_scope_key,
            session_id=self._session_id,
        )
        operating_trace = dict(self._last_operating_context_trace or {})
        operating_trace["system_prompt_block"] = {
            "surface": "system_prompt_block",
            "section_present": "# Brainstack Operating Context" in block,
            "live_system_state_present": bool(list(operating_snapshot.get("live_system_state") or [])),
            "active_work_present": bool(str(operating_snapshot.get("active_work_summary") or "").strip()),
            "recent_work_present": bool(str(operating_snapshot.get("recent_work_summary") or "").strip()),
            "open_decisions_present": bool(list(operating_snapshot.get("open_decisions") or [])),
            "snapshot": operating_snapshot,
        }
        self._last_operating_context_trace = operating_trace
        return block

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._store:
            return ""
        authority_state = self._ensure_behavior_authority_ready(surface="prefetch")
        sid = session_id or self._session_id
        style_contract_candidate = self._resolve_style_contract_candidate(
            content=query,
            source="prefetch:style_contract",
            confidence=0.9,
            metadata={"session_id": sid},
            require_explicit_signal=True,
        )
        system_substrate = build_system_prompt_projection(
            self._store,
            profile_limit=self._profile_prompt_limit,
            principal_scope_key=self._principal_scope_key,
            session_id=sid,
            include_behavior_contract=self._system_prompt_behavior_contract_enabled,
        )
        packet = build_working_memory_packet(
            self._store,
            query=query,
            session_id=sid,
            principal_scope_key=self._principal_scope_key,
            timezone_name=self._user_timezone,
            profile_match_limit=self._profile_match_limit,
            continuity_recent_limit=self._continuity_recent_limit,
            continuity_match_limit=self._continuity_match_limit,
            transcript_match_limit=self._transcript_match_limit,
            transcript_char_budget=self._transcript_char_budget,
            evidence_item_budget=self._evidence_item_budget,
            operating_match_limit=self._operating_match_limit,
            graph_limit=self._graph_match_limit,
            corpus_limit=self._corpus_match_limit,
            corpus_char_budget=self._corpus_char_budget,
            route_resolver=self._route_resolver_override,
            system_substrate=system_substrate,
            render_ordinary_contract=self._ordinary_packet_behavior_contract_enabled,
        )
        self._last_prefetch_policy = packet["policy"]
        self._last_prefetch_routing = dict(packet.get("routing") or {})
        self._last_prefetch_channels = [
            dict(channel)
            for channel in list(packet.get("channels") or [])
            if isinstance(channel, dict)
        ]
        if bool(getattr(self, "_capture_candidate_debug", False)) or bool(self._config.get("_capture_candidate_debug")):
            self._last_prefetch_debug = {
                "fused_candidates": [dict(item) for item in list(packet.get("fused_candidates") or [])],
                "selected_rows": {
                    "profile_items": [_debug_row_snapshot(row) for row in list(packet.get("profile_items") or [])],
                    "matched": [_debug_row_snapshot(row) for row in list(packet.get("matched") or [])],
                    "recent": [_debug_row_snapshot(row) for row in list(packet.get("recent") or [])],
                    "transcript_rows": [_debug_row_snapshot(row) for row in list(packet.get("transcript_rows") or [])],
                    "operating_rows": [dict(row) for row in list(packet.get("operating_rows") or [])],
                    "graph_rows": [_debug_row_snapshot(row) for row in list(packet.get("graph_rows") or [])],
                    "corpus_rows": [_debug_row_snapshot(row) for row in list(packet.get("corpus_rows") or [])],
                    "task_rows": [dict(row) for row in list(packet.get("task_rows") or [])],
                },
            }
        else:
            self._last_prefetch_debug = None
        snapshot = self._store.get_behavior_policy_snapshot(principal_scope_key=self._principal_scope_key)
        trace = dict(self._last_behavior_policy_trace or {})
        compiled_policy = packet.get("policy", {}).get("compiled_behavior_policy")
        projection_text = ""
        if isinstance(compiled_policy, dict):
            projection_text = str(compiled_policy.get("projection_text") or "").strip()
        output_block = str(packet.get("block") or "")
        self._set_memory_operation_trace(surface="prefetch_lookup", note="Nominal read surface; no durable writes attempted.")
        trace["prefetch"] = {
            "surface": "prefetch",
            "route_mode": str(packet.get("routing", {}).get("applied_mode") or "fact"),
            "style_contract_activated_before_prefetch": False,
            "task_capture_activated_before_prefetch": False,
            "operating_truth_activated_before_prefetch": False,
            "style_contract_candidate_detected": bool(style_contract_candidate),
            "task_capture_candidate_detected": False,
            "operating_truth_candidate_detected": False,
            "write_receipt_present": False,
            "write_receipt_status": "",
            "read_side_effect_count": 0,
            "compiled_policy_present_in_packet": bool(isinstance(compiled_policy, dict) and projection_text),
            "projection_present_in_block": bool(projection_text and projection_text in output_block),
            "correction_reinforcement_present": False,
            "correction_reinforcement_mode": "",
            "snapshot": snapshot,
        }
        self._last_behavior_policy_trace = trace
        self._last_memory_authority_debug = {
            "surface": "prefetch_debug",
            "session_id": sid,
            "read_side_effect_count": 0,
            "write_receipts_in_packet": False,
            "candidate_writes": {
                "style_contract": bool(style_contract_candidate),
                "task_memory": False,
                "operating_truth": False,
            },
            "candidate_write_modes": {
                "style_contract": str(
                    ((style_contract_candidate or {}).get("metadata") or {}).get("style_contract_write_mode") or ""
                ),
                "task_memory": "",
                "operating_truth": "",
            },
            "behavior_policy_snapshot": snapshot,
            "packet_route_mode": str(packet.get("routing", {}).get("applied_mode") or "fact"),
            "brainstack_packet_sections": _extract_heading_titles(output_block),
            "system_substrate_sections": _extract_heading_titles(str(system_substrate.get("block") or "")),
            "canonical_generation_revision": int((snapshot.get("raw_contract") or {}).get("revision_number") or 0),
            "compiled_policy_source_revision": int((snapshot.get("compiled_policy") or {}).get("source_revision_number") or 0),
            "active_lane_source_revision": int(system_substrate.get("active_lane_source_revision") or 0),
            "authority_bootstrap": {
                "repair_attempted": bool(authority_state.get("repair_attempted")),
                "blocked": bool(authority_state.get("blocked")),
                "reason": str(authority_state.get("reason") or ""),
            },
            "host_runtime_layers_excluded": [
                "host persona",
                "runtime tools",
                "delivery options",
                "non-Brainstack system prompt layers",
            ],
        }
        return output_block

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        event_time: str | None = None,
    ) -> None:
        if not self._store:
            return
        sid = session_id or self._session_id
        now = time.monotonic()
        idle_seconds = None if self._last_turn_monotonic is None else max(0.0, now - self._last_turn_monotonic)
        self._last_turn_monotonic = now
        self._turn_counter += 1
        pending_turns = self._pending_tier2_turns + 1
        continuity_adapter.write_turn_records(
            self._store,
            session_id=sid,
            turn_number=self._turn_counter,
            user_content=user_content,
            assistant_content=assistant_content,
            created_at=event_time,
            metadata=self._scoped_metadata(),
        )
        self._remember_recent_user_message(user_content)
        self._set_memory_operation_trace(
            surface="sync_turn_style_contract_disabled",
            note=(
                "Transcript turns do not create authoritative style contracts. "
                "Explicit style/profile truth must arrive through the native explicit-memory write seam."
            ),
        )
        task_capture = self._infer_task_capture_candidate(content=user_content)
        self._commit_task_capture_candidate(
            capture=task_capture,
            content=user_content,
            source="sync_turn:task_memory",
            metadata={"session_id": sid, "turn_number": self._turn_counter},
        )
        operating_truth_capture = self._infer_operating_truth_candidate(content=user_content)
        self._commit_operating_truth_candidate(
            capture=operating_truth_capture,
            content=user_content,
            source="sync_turn:operating_truth",
            metadata={"session_id": sid, "turn_number": self._turn_counter},
        )
        plan = build_turn_ingest_plan(
            user_content=user_content,
            pending_turns=pending_turns,
            idle_seconds=idle_seconds,
            idle_window_seconds=self._tier2_idle_window_seconds,
            batch_turn_limit=self._tier2_batch_turn_limit,
        )
        with self._tier2_lock:
            self._last_tier2_schedule = plan.tier2_schedule.to_dict()
            self._pending_tier2_turns = plan.tier2_schedule.pending_turns

        if not plan.durable_admission.allowed:
            logger.info(
                "Brainstack durable admission denied in sync_turn: reason=%s matched=%s",
                plan.durable_admission.reason,
                ",".join(plan.durable_admission.matched_rules) or "-",
            )

        if plan.graph_evidence_items:
            try:
                graph_result = graph_adapter.ingest_turn_graph_candidates_with_receipt(
                    self._store,
                    evidence_items=plan.graph_evidence_items,
                    session_id=sid,
                    turn_number=self._turn_counter,
                    source="sync_turn:user",
                    metadata=self._scoped_metadata(),
                )
            except Exception as exc:
                receipt = getattr(exc, "receipt", None)
                self._last_graph_ingress_trace = {
                    "surface": "sync_turn_graph_ingress",
                    "status": "failed",
                    "error": str(exc),
                    "receipt": dict(receipt) if isinstance(receipt, dict) else None,
                }
                raise
            self._last_graph_ingress_trace = {
                "surface": "sync_turn_graph_ingress",
                "status": "committed",
                "receipt": dict(graph_result.get("receipt") or {}),
            }
        else:
            self._last_graph_ingress_trace = {
                "surface": "sync_turn_graph_ingress",
                "status": "skipped_no_typed_graph_evidence",
                "reason": "no explicit producer-aligned graph evidence items",
            }
        if plan.tier2_schedule.should_queue:
            self._queue_tier2_background(session_id=sid, turn_number=self._turn_counter, trigger_reason=plan.tier2_schedule.reason)
