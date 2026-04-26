from __future__ import annotations

from .provider_protocol import ProviderRuntimeBase
from .runtime import (
    Any,
    Dict,
    List,
    build_consolidation_source,
    extract_tier2_candidates,
    hashlib,
    logger,
    reconcile_tier2_candidates,
    threading,
    time,
    utc_now_iso,
)

class Tier2WorkerMixin(ProviderRuntimeBase):
    def shutdown(self) -> None:
        worker_finished = self._wait_for_tier2_worker(timeout=self._tier2_timeout_seconds + 2.0)
        if not worker_finished:
            logger.error("Refusing to reset Brainstack runtime state while the Tier-2 worker is still running.")
            return
        if not self._ensure_explicit_write_barrier_clear(surface="shutdown"):
            return
        if self._store:
            self._store.close()
            self._store = None
        self._reset_session_runtime_state()

    def _record_tier2_batch_result(self, result: Dict[str, Any]) -> None:
        self._last_tier2_batch_result = dict(result)
        self._tier2_batch_history.append(dict(result))
        if len(self._tier2_batch_history) > 256:
            self._tier2_batch_history = self._tier2_batch_history[-256:]
        if self._store is not None:
            try:
                self._store.record_tier2_run_result(result)
            except Exception:
                logger.warning("Brainstack failed to persist Tier-2 run result", exc_info=True)

    def _queue_tier2_background(self, *, session_id: str, turn_number: int, trigger_reason: str) -> None:
        with self._tier2_lock:
            if self._tier2_running:
                self._tier2_followup_requested = True
                return
            self._tier2_running = True
            worker = threading.Thread(
                target=self._tier2_worker_loop,
                kwargs={
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "trigger_reason": trigger_reason,
                },
                name="brainstack-tier2",
                daemon=True,
            )
            self._tier2_thread = worker
            worker.start()

    def _wait_for_tier2_worker(self, *, timeout: float) -> bool:
        current = threading.current_thread()
        worker: threading.Thread | None
        with self._tier2_lock:
            worker = self._tier2_thread
        if not worker or worker is current:
            return True
        worker.join(timeout=max(0.0, timeout))
        if worker.is_alive():
            logger.warning("Brainstack Tier-2 worker did not finish within %.1fs", timeout)
            return False
        return True

    def _tier2_worker_loop(self, *, session_id: str, turn_number: int, trigger_reason: str) -> None:
        current_reason = trigger_reason
        try:
            while True:
                self._run_tier2_batch(session_id=session_id, turn_number=turn_number, trigger_reason=current_reason)
                with self._tier2_lock:
                    should_continue = self._tier2_followup_requested
                    self._tier2_followup_requested = False
                    if not should_continue:
                        self._tier2_running = False
                        self._tier2_thread = None
                        break
                    current_reason = "followup_pending_work"
        except Exception:
            logger.warning("Brainstack Tier-2 worker failed", exc_info=True)
            with self._tier2_lock:
                self._tier2_running = False
                self._tier2_thread = None

    def _run_tier2_batch(self, *, session_id: str, turn_number: int, trigger_reason: str) -> Dict[str, Any]:
        started_monotonic = time.monotonic()
        result: Dict[str, Any] = {
            "run_id": hashlib.sha256(
                f"{session_id}|{turn_number}|{trigger_reason}|{time.time_ns()}".encode("utf-8")
            ).hexdigest()[:24],
            "created_at": utc_now_iso(),
            "session_id": session_id,
            "turn_number": int(turn_number or 0),
            "trigger_reason": trigger_reason,
            "request_status": "started",
            "transcript_turn_numbers": [],
            "transcript_ids": [],
            "transcript_count": 0,
            "json_parse_status": "not_run",
            "parse_context": "",
            "extracted_counts": {},
            "action_counts": {},
            "writes_performed": 0,
            "no_op_reasons": [],
            "error_reason": "",
            "duration_ms": 0,
            "status": "not_run",
        }
        if not self._store:
            result["status"] = "skipped_no_store"
            result["request_status"] = "skipped"
            result["no_op_reasons"] = ["store_unavailable"]
            result["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
            return result
        transcript_rows = [
            row
            for row in reversed(self._store.recent_transcript(session_id=session_id, limit=self._tier2_transcript_limit))
            if str(row.get("kind", "")) == "turn"
        ]
        result["transcript_turn_numbers"] = [int(row.get("turn_number") or 0) for row in transcript_rows]
        result["transcript_ids"] = [int(row["id"]) for row in transcript_rows if row.get("id") is not None]
        result["transcript_count"] = len(transcript_rows)
        consolidation_source = build_consolidation_source(transcript_rows, source_kind="transcript")
        result["consolidation_source"] = dict(consolidation_source)
        if not transcript_rows:
            result["status"] = "skipped_no_transcript"
            result["request_status"] = "skipped"
            result["no_op_reasons"] = ["no_eligible_transcript_turns"]
            result["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
            self._record_tier2_batch_result(result)
            return result
        extractor = self._config.get("_tier2_extractor")
        try:
            if callable(extractor):
                extracted = extractor(
                    transcript_rows,
                    session_id=session_id,
                    turn_number=turn_number,
                    trigger_reason=trigger_reason,
                )
            else:
                extracted = extract_tier2_candidates(
                    transcript_rows,
                    transcript_limit=self._tier2_transcript_limit,
                    timeout_seconds=self._tier2_timeout_seconds,
                    max_tokens=self._tier2_max_tokens,
                )
        except Exception as exc:
            result["status"] = "failed"
            result["request_status"] = "failed"
            result["error_reason"] = str(exc)
            result["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
            self._record_tier2_batch_result(result)
            return result
        if not isinstance(extracted, dict):
            result["status"] = "failed"
            result["request_status"] = "failed"
            result["json_parse_status"] = "invalid_payload"
            result["error_reason"] = "Tier-2 extractor returned a non-dict payload."
            result["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
            self._record_tier2_batch_result(result)
            return result
        result["request_status"] = "ok"
        extracted_meta = extracted.get("_meta") if isinstance(extracted, dict) else {}
        result["json_parse_status"] = str((extracted_meta or {}).get("json_parse_status") or "unknown")
        result["parse_context"] = str((extracted_meta or {}).get("parse_context") or "")
        result["raw_payload_preview"] = str((extracted_meta or {}).get("raw_payload_preview") or "")
        result["raw_payload_tail"] = str((extracted_meta or {}).get("raw_payload_tail") or "")
        result["raw_payload_length"] = int((extracted_meta or {}).get("raw_payload_length") or 0)
        extracted_counts = {
            "profile_items": len(list(extracted.get("profile_items", []) or [])),
            "states": len(list(extracted.get("states", []) or [])),
            "relations": len(list(extracted.get("relations", []) or [])),
            "inferred_relations": len(list(extracted.get("inferred_relations", []) or [])),
            "typed_entities": len(list(extracted.get("typed_entities", []) or [])),
            "temporal_events": len(list(extracted.get("temporal_events", []) or [])),
            "decisions": len(list(extracted.get("decisions", []) or [])),
            "continuity_summary_present": 1 if str(extracted.get("continuity_summary") or "").strip() else 0,
        }
        result["extracted_counts"] = extracted_counts
        if not any(int(value or 0) for value in extracted_counts.values()):
            result["no_op_reasons"].append("extractor_returned_empty_payload")
        temporal_event_samples: List[Dict[str, Any]] = []
        for event in list(extracted.get("temporal_events", []) or [])[:6]:
            if not isinstance(event, dict):
                continue
            temporal_event_samples.append(
                {
                    "turn_number": int(event.get("turn_number") or 0),
                    "content": str(event.get("content") or "").strip(),
                }
            )
        result["temporal_event_samples"] = temporal_event_samples
        typed_entity_samples: List[Dict[str, Any]] = []
        for entity in list(extracted.get("typed_entities", []) or [])[:4]:
            if not isinstance(entity, dict):
                continue
            typed_entity_samples.append(
                {
                    "turn_number": int(entity.get("turn_number") or 0),
                    "name": str(entity.get("name") or "").strip(),
                    "entity_type": str(entity.get("entity_type") or "").strip(),
                    "attributes": dict(entity.get("attributes") or {}),
                }
            )
        result["typed_entity_samples"] = typed_entity_samples
        reconcile_report = reconcile_tier2_candidates(
            self._store,
            session_id=session_id,
            turn_number=turn_number,
            source=f"tier2:{trigger_reason}",
            extracted=extracted,
            metadata=self._scoped_metadata({
                "batch_reason": trigger_reason,
                "transcript_ids": [int(row["id"]) for row in transcript_rows if row.get("id") is not None],
                "consolidation_source": dict(consolidation_source),
            }),
        )
        action_counts: Dict[str, int] = {}
        writes_performed = 0
        for action in reconcile_report.get("actions", []):
            action_name = str(action.get("action") or "UNKNOWN")
            action_counts[action_name] = action_counts.get(action_name, 0) + 1
            if action_name != "NONE" and not action_name.startswith("REJECT_"):
                writes_performed += 1
        operating_promotions = {
            "recent_work_promoted": self._promote_recent_work_summary(
                content=str(extracted.get("continuity_summary") or ""),
                source=f"tier2:{trigger_reason}:recent_work",
                metadata={
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "batch_reason": trigger_reason,
                    "consolidation_source": dict(consolidation_source),
                },
            ),
            "open_decisions_promoted": self._promote_open_decisions(
                decisions=list(extracted.get("decisions", []) or []),
                source=f"tier2:{trigger_reason}:open_decision",
                metadata={
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "batch_reason": trigger_reason,
                    "consolidation_source": dict(consolidation_source),
                },
            ),
        }
        result["action_counts"] = action_counts
        result["writes_performed"] = writes_performed
        result["operating_promotions"] = operating_promotions
        if writes_performed <= 0:
            result["no_op_reasons"].append("no_durable_writes_performed")
        if action_counts and set(action_counts).issubset({"NONE", "REJECT_ASSISTANT_AUTHORED"}):
            result["no_op_reasons"].append("all_candidates_rejected_or_noop")
        result["status"] = "ok"
        result["duration_ms"] = int((time.monotonic() - started_monotonic) * 1000)
        self._record_tier2_batch_result(result)
        return result
