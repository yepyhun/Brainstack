"""Read-only operating-loop health contracts for proactive/Kanban workflows.

These helpers classify runtime evidence. They do not schedule, dispatch,
notify, repair, reassign, or mutate Kanban/workstream state.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from .workstream_controller import classify_cadence_job


OPERATING_LOOP_VERDICT_SCHEMA = "brainstack.operating_loop.verdict.v1"
KANBAN_RECOVERY_CANDIDATE_SCHEMA = "brainstack.kanban.recovery_candidate.v1"
SCHEDULER_LANE_HEALTH_SCHEMA = "brainstack.scheduler_lane_health.v1"
COMPRESSION_FAILURE_GUARD_SCHEMA = "brainstack.hermes_auxiliary_compression_guard.v1"
FRONTIER_CONTINUATION_CONTRACT_SCHEMA = "brainstack.frontier_continuation.contract.v1"

OPERATING_LOOP_VERDICTS = (
    "healthy",
    "degraded",
    "critical",
    "stopped_intentionally",
    "insufficient_evidence",
)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _record_event_keys(records: list[Mapping[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        for field in ("event_id", "source_event_id", "terminal_event_id", "idempotency_key"):
            value = _text(record.get(field))
            if value:
                keys.add(value)
    return keys


def build_frontier_continuation_contract(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify whether frontier continuation is event-first or cadence-primary.

    This contract is intentionally read-only. It does not create tasks, trigger
    schedulers, notify users, or mutate Kanban state. It only makes the control
    shape inspectable so agents cannot call a cadence-primary loop healthy.
    """

    controller = _mapping(evidence.get("controller"))
    allocator = _mapping(evidence.get("allocator") or controller.get("allocator"))
    terminal_events = _list_of_mappings(evidence.get("terminal_events"))
    continuation_records = _list_of_mappings(evidence.get("continuation_records"))
    seen_continuations = _record_event_keys(continuation_records)
    explicit_stop = _bool(evidence.get("explicit_stop")) or _text(evidence.get("state")) == "stopped_intentionally"

    event_bridge_enabled = _bool(controller.get("event_bridge_enabled")) or _bool(evidence.get("event_bridge_enabled"))
    event_bridge_stale = _bool(controller.get("event_bridge_stale")) or _bool(evidence.get("event_bridge_stale"))
    watchdog_enabled = _bool(controller.get("watchdog_enabled")) or _bool(evidence.get("watchdog_enabled"))
    allocator_exists = bool(allocator)
    allocator_fixed = _bool(allocator.get("fixed_schedule", allocator_exists))
    allocator_creates_work = _bool(allocator.get("creates_work")) or _bool(controller.get("allocator_creates_work"))
    allocator_reads_events = _bool(allocator.get("reads_events")) or _bool(controller.get("allocator_reads_events"))
    allocator_watchdog_only = _bool(allocator.get("watchdog_only")) or _text(allocator.get("kind")) in {
        "watchdog",
        "recovery",
        "heartbeat",
    }

    if event_bridge_enabled and not event_bridge_stale and (watchdog_enabled or allocator_watchdog_only):
        controller_mode = "event_plus_watchdog"
    elif event_bridge_enabled and not event_bridge_stale:
        controller_mode = "event_driven"
    elif event_bridge_enabled and event_bridge_stale:
        controller_mode = "event_bridge_stale"
    elif allocator_creates_work and allocator_fixed and not allocator_reads_events:
        controller_mode = "cadence_primary"
    elif watchdog_enabled or allocator_watchdog_only:
        controller_mode = "watchdog_only"
    elif not (controller or allocator or terminal_events or continuation_records):
        controller_mode = "insufficient_evidence"
    else:
        controller_mode = "missing"

    terminal_kinds = {
        "task_completed",
        "completed",
        "done",
        "blocked",
        "crashed",
        "failed",
        "timed_out",
        "timeout",
    }
    allowed_decisions = {
        "next_frontier_created",
        "wait_for_parent_or_dependency",
        "human_gate",
        "intentional_stop",
        "recovery_candidate",
        "wait",
        "stop",
        "ask",
        "kanban_handoff",
    }
    continuation_gaps: list[dict[str, Any]] = []
    for event in terminal_events:
        event_kind = _text(event.get("kind"))
        if event_kind not in terminal_kinds:
            continue
        event_id = _text(event.get("event_id") or event.get("id") or event.get("idempotency_key"))
        decision = _text(event.get("continuation_decision") or event.get("decision"))
        has_continuation = (
            _bool(event.get("has_continuation"))
            or decision in allowed_decisions
            or (event_id and event_id in seen_continuations)
        )
        if not has_continuation and not explicit_stop:
            continuation_gaps.append(
                {
                    "event_id": event_id or "unknown-event",
                    "task_id": _text(event.get("task_id")) or "unknown-task",
                    "kind": event_kind,
                    "reason_code": "terminal_event_without_continuation",
                }
            )

    reason_codes: list[str] = []
    if continuation_gaps:
        reason_codes.append("FRONTIER_CONTINUATION_GAP")
    if controller_mode == "cadence_primary":
        reason_codes.append("FRONTIER_CADENCE_PRIMARY_ALLOCATOR")
    elif controller_mode == "event_bridge_stale":
        reason_codes.append("FRONTIER_EVENT_BRIDGE_STALE")
    elif controller_mode == "watchdog_only":
        reason_codes.append("FRONTIER_WATCHDOG_ONLY")
    elif controller_mode == "missing":
        reason_codes.append("FRONTIER_CONTROLLER_MISSING")
    elif controller_mode == "insufficient_evidence":
        reason_codes.append("FRONTIER_CONTINUATION_INSUFFICIENT_EVIDENCE")

    if explicit_stop:
        verdict = "stopped_intentionally"
        reason_codes.append("FRONTIER_STOPPED_INTENTIONALLY")
    elif continuation_gaps:
        verdict = "critical"
    elif controller_mode in {"cadence_primary", "event_bridge_stale", "missing", "watchdog_only"}:
        verdict = "degraded"
    elif controller_mode == "insufficient_evidence":
        verdict = "insufficient_evidence"
    else:
        verdict = "healthy"
        reason_codes.append("FRONTIER_CONTINUATION_HEALTHY")

    return {
        "schema": FRONTIER_CONTINUATION_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "controller_mode": controller_mode,
        "event_bridge_enabled": event_bridge_enabled,
        "event_bridge_stale": event_bridge_stale,
        "cadence_primary_allocator": controller_mode == "cadence_primary",
        "continuation_gap_count": len(continuation_gaps),
        "terminal_events_without_continuation": continuation_gaps[:20],
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": (
            "frontier_continuation_event_driven"
            if verdict == "healthy"
            else f"frontier_continuation_{verdict}"
        ),
    }


def _freshness_state(evidence: Mapping[str, Any], *, default_stale_after_seconds: int) -> str:
    if _bool(evidence.get("explicit_stop")) or _bool(evidence.get("human_gate")):
        return "intentional_stop"
    if _bool(evidence.get("stale")):
        return "stale"
    age = _safe_int(evidence.get("last_run_age_seconds"), -1)
    stale_after = _safe_int(evidence.get("stale_after_seconds"), default_stale_after_seconds)
    if age >= 0 and stale_after > 0 and age > stale_after:
        return "stale"
    if age >= 0:
        return "fresh"
    if _bool(evidence.get("fresh")):
        return "fresh"
    if _text(evidence.get("status")) in {"ok", "pass", "healthy", "running", "ready"}:
        return "fresh"
    return "unknown"


def build_operating_loop_verdict(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify whether the full operating loop is healthy.

    Expected evidence is intentionally generic and public-safe. Callers may pass
    partial evidence; the result will be `insufficient_evidence` instead of a
    false green verdict.
    """

    kanban = _mapping(evidence.get("kanban_runtime_snapshot"))
    scheduler = _mapping(evidence.get("scheduler_lane_health"))
    continuation = _mapping(evidence.get("frontier_continuation"))
    signal_bus = _mapping(evidence.get("signal_bus"))
    executor = _mapping(evidence.get("executor"))
    builder = _mapping(evidence.get("builder"))
    next_action = _mapping(evidence.get("next_action"))

    intentional_stop = (
        _bool(evidence.get("explicit_stop"))
        or _bool(next_action.get("explicit_stop"))
        or _bool(next_action.get("human_gate"))
        or _text(evidence.get("state")) == "stopped_intentionally"
    )

    reason_codes: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []

    kanban_state = _text(kanban.get("dispatcher_state"))
    ready_count = _safe_int(kanban.get("ready_task_count"), 0)
    running_count = _safe_int(kanban.get("running_worker_count"), 0)
    blocked_count = _safe_int(kanban.get("blocked_task_count"), 0)
    unknown_assignee_count = _safe_int(kanban.get("blocked_unknown_assignee_count"), 0)
    recent_failures = [str(item) for item in kanban.get("recent_failure_event_kinds") or [] if str(item)]
    wait_reasons = {
        _text(item.get("reason_code"))
        for item in _list_of_mappings(kanban.get("wait_reasons"))
        if _text(item.get("reason_code"))
    }

    if unknown_assignee_count:
        blockers.append("blocked_unknown_assignee")
        reason_codes.append("KANBAN_UNKNOWN_ASSIGNEE_BLOCKER")
    if recent_failures:
        warnings.append("recent_kanban_failures")
        reason_codes.append("KANBAN_RECENT_FAILURE_EVENTS")
    if blocked_count:
        warnings.append("blocked_kanban_tasks")
        reason_codes.append("KANBAN_BLOCKED_TASKS_PRESENT")
    kanban_required = (
        _bool(evidence.get("kanban_required"))
        or _bool(next_action.get("requires_kanban"))
        or ready_count > 0
        or running_count > 0
        or unknown_assignee_count > 0
    )
    if kanban_state == "blocked_ready_tasks" and not intentional_stop:
        blockers.append("kanban_blocked_ready_tasks")
    elif kanban_state == "unavailable" and kanban_required and not intentional_stop:
        blockers.append("kanban_unavailable")
    if "blocked_unknown_assignee" in wait_reasons and "blocked_unknown_assignee" not in blockers:
        blockers.append("blocked_unknown_assignee")

    signal_state = _freshness_state(signal_bus, default_stale_after_seconds=600)
    executor_state = _freshness_state(executor, default_stale_after_seconds=600)
    builder_state = _freshness_state(builder, default_stale_after_seconds=900)
    scheduler_verdict = _text(scheduler.get("verdict"))
    scheduler_reasons = [str(item) for item in scheduler.get("reason_codes") or [] if str(item)]
    if scheduler_verdict in {"critical", "degraded"}:
        blockers.append("scheduler_lane_unhealthy" if scheduler_verdict == "critical" else "scheduler_lane_degraded")
        reason_codes.extend(scheduler_reasons or [f"SCHEDULER_{scheduler_verdict.upper()}"])

    continuation_verdict = _text(continuation.get("verdict"))
    continuation_reasons = [str(item) for item in continuation.get("reason_codes") or [] if str(item)]
    if continuation_verdict == "critical":
        blockers.append("frontier_continuation_critical")
        reason_codes.extend(continuation_reasons or ["FRONTIER_CONTINUATION_CRITICAL"])
    elif continuation_verdict == "degraded":
        blockers.append("frontier_continuation_degraded")
        reason_codes.extend(continuation_reasons or ["FRONTIER_CONTINUATION_DEGRADED"])

    split_brain = (
        builder_state == "fresh"
        and (signal_state == "stale" or executor_state == "stale" or kanban_state in {"blocked_ready_tasks", "unavailable"})
        and not intentional_stop
    )
    if split_brain:
        blockers.append("split_brain_activity")
        reason_codes.append("SPLIT_BRAIN_ACTIVITY")

    has_frontier = (
        running_count > 0
        or ready_count > 0
        or kanban_state in {"workers_running", "ready_waiting", "blocked_ready_tasks"}
        or _bool(next_action.get("exists"))
    )
    has_any_evidence = any(
        bool(item)
        for item in (
            kanban,
            scheduler,
            continuation,
            signal_bus,
            executor,
            builder,
            next_action,
            evidence.get("state"),
        )
    )

    if intentional_stop:
        verdict = "stopped_intentionally"
        reason_codes.append("OPERATING_LOOP_STOPPED_INTENTIONALLY")
    elif not has_any_evidence:
        verdict = "insufficient_evidence"
        reason_codes.append("OPERATING_LOOP_INSUFFICIENT_EVIDENCE")
    elif split_brain or "kanban_blocked_ready_tasks" in blockers or scheduler_verdict == "critical":
        verdict = "critical"
    elif blockers or warnings:
        verdict = "degraded"
    elif has_frontier and signal_state in {"fresh", "unknown"} and executor_state in {"fresh", "unknown"}:
        verdict = "healthy"
        reason_codes.append("OPERATING_LOOP_HEALTHY")
    else:
        verdict = "insufficient_evidence"
        reason_codes.append("OPERATING_LOOP_INSUFFICIENT_EVIDENCE")

    return {
        "schema": OPERATING_LOOP_VERDICT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "reason_codes": sorted(set(reason_codes)),
        "split_brain_detected": split_brain,
        "has_frontier": has_frontier,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "lane_freshness": {
            "signal_bus": signal_state,
            "executor": executor_state,
            "builder": builder_state,
        },
        "frontier_continuation": {
            "verdict": continuation_verdict,
            "controller_mode": _text(continuation.get("controller_mode")),
            "continuation_gap_count": _safe_int(continuation.get("continuation_gap_count"), 0),
        }
        if continuation
        else {},
        "agent_claim": (
            "operating_loop_whole_loop_healthy"
            if verdict == "healthy"
            else f"operating_loop_{verdict}"
        ),
    }


def build_kanban_recovery_candidates(
    snapshot: Mapping[str, Any],
    *,
    now_ts: int | None = None,
    stale_running_after_seconds: int = 900,
) -> list[dict[str, Any]]:
    """Return read-only recovery candidates for broken Kanban frontier states."""

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(task_id: str, failure_class: str, *, evidence: Mapping[str, Any], allowed: Iterable[str], forbidden: Iterable[str], approval: bool = True, owner: str = "hermes_kanban") -> None:
        key = (task_id, failure_class)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            {
                "schema": KANBAN_RECOVERY_CANDIDATE_SCHEMA,
                "read_only": True,
                "side_effect_free": True,
                "task_id": task_id,
                "failure_class": failure_class,
                "evidence": dict(evidence),
                "allowed_actions": sorted(set(allowed)),
                "forbidden_actions": sorted(set(forbidden)),
                "requires_human_approval": approval,
                "suggested_owner": owner,
                "status": "recovery_candidate",
            }
        )

    for item in _list_of_mappings(snapshot.get("wait_reasons")):
        reason = _text(item.get("reason_code"))
        task_id = _text(item.get("task_id")) or "unknown-task"
        if reason == "blocked_unknown_assignee":
            add(
                task_id,
                "unknown_assignee",
                evidence={"assignee": _text(item.get("assignee")), "status": _text(item.get("status"))},
                allowed=("operator_reassign_or_block", "open_upstream_or_board_issue"),
                forbidden=("auto_reassign_default", "auto_complete", "auto_retry"),
            )
        elif reason == "waiting_for_parent_promotion_or_recompute":
            add(
                task_id,
                "parent_or_fan_in_wait",
                evidence={"status": _text(item.get("status")), "assignee": _text(item.get("assignee"))},
                allowed=("inspect_parent_state", "create_explicit_followup_if_parent_done"),
                forbidden=("pretend_completed", "auto_promote_without_parent_proof"),
                approval=False,
            )

    if snapshot.get("recent_failure_event_kinds"):
        add(
            "board",
            "recent_failure_wave",
            evidence={"recent_failure_event_kinds": list(snapshot.get("recent_failure_event_kinds") or [])[:8]},
            allowed=("inspect_failed_runs", "open_recovery_queue_item"),
            forbidden=("retry_storm", "clear_failures_without_final_state_proof"),
        )

    now = now_ts if now_ts is not None else _safe_int(snapshot.get("now_ts"), 0)
    for item in _list_of_mappings(snapshot.get("running_tasks")):
        task_id = _text(item.get("task_id")) or "unknown-running-task"
        age = _safe_int(item.get("running_age_seconds"), -1)
        if age < 0 and now > 0:
            started = _safe_int(item.get("started_at"), 0)
            if started > 0:
                age = max(0, now - started)
        if age >= stale_running_after_seconds:
            add(
                task_id,
                "stale_running_worker",
                evidence={"assignee": _text(item.get("assignee")), "running_age_seconds": age},
                allowed=("inspect_worker_log", "operator_reclaim_or_retry_with_budget"),
                forbidden=("silent_healthy", "unbounded_retry"),
            )

    return candidates


def recovery_summary(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(_text(item.get("failure_class")) for item in candidates)
    return {
        "read_only": True,
        "candidate_count": len(candidates),
        "failure_class_counts": dict(sorted(counts.items())),
        "status": "recovery_candidates_present" if candidates else "no_recovery_candidates",
    }


def build_scheduler_lane_health(
    jobs: list[Mapping[str, Any]],
    *,
    default_stale_after_seconds: int = 600,
) -> dict[str, Any]:
    """Classify scheduled job lanes and detect starvation risk."""

    job_reports: list[dict[str, Any]] = []
    lane_states: dict[str, str] = {}
    reason_codes: list[str] = []
    heavy_active = False
    critical_lane_stale = False

    for job in jobs:
        classification = classify_cadence_job(job)
        lane = _text(job.get("lane")) or str(classification.get("job_class") or "unknown")
        age = _safe_int(job.get("last_run_age_seconds"), -1)
        stale_after = _safe_int(job.get("stale_after_seconds"), default_stale_after_seconds)
        running_duration = _safe_int(job.get("running_duration_seconds"), 0)
        max_runtime = _safe_int(job.get("max_runtime_seconds"), stale_after)
        missed_runs = _safe_int(job.get("missed_run_count"), 0)
        state = "unknown"
        if _bool(job.get("disabled")):
            state = "disabled"
        elif _bool(job.get("intentional_stop")):
            state = "stopped_intentionally"
        elif age >= 0 and stale_after > 0 and age > stale_after:
            state = "stale"
        elif running_duration and max_runtime and running_duration > max_runtime:
            state = "over_runtime"
        elif missed_runs > 0:
            state = "missed_runs"
        elif age >= 0 or _text(job.get("status")) in {"ok", "pass", "running"}:
            state = "fresh"

        if lane in {"heartbeat", "recovery", "status_projection"} and state in {"stale", "missed_runs", "over_runtime"}:
            critical_lane_stale = True
        if classification.get("job_class") == "controller_substitute" and state in {"fresh", "over_runtime", "missed_runs"}:
            heavy_active = True
        if state in {"stale", "over_runtime", "missed_runs"}:
            reason_codes.append(f"{lane.upper()}_{state.upper()}")

        lane_states[lane] = state
        job_reports.append(
            {
                "job_id": str(classification.get("job_id") or ""),
                "lane": lane,
                "job_class": str(classification.get("job_class") or ""),
                "migration_target": str(classification.get("migration_target") or ""),
                "state": state,
                "last_run_age_seconds": age,
                "running_duration_seconds": running_duration,
                "missed_run_count": missed_runs,
            }
        )

    starvation_risk = heavy_active and critical_lane_stale
    if starvation_risk:
        reason_codes.append("SCHEDULER_STARVATION_RISK")

    if not jobs:
        verdict = "insufficient_evidence"
        reason_codes.append("SCHEDULER_INSUFFICIENT_EVIDENCE")
    elif starvation_risk:
        verdict = "critical"
    elif critical_lane_stale:
        verdict = "degraded"
    elif any(item["state"] in {"stale", "over_runtime", "missed_runs"} for item in job_reports):
        verdict = "degraded"
    else:
        verdict = "healthy"
        reason_codes.append("SCHEDULER_LANES_HEALTHY")

    return {
        "schema": SCHEDULER_LANE_HEALTH_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "starvation_risk": starvation_risk,
        "reason_codes": sorted(set(reason_codes)),
        "lane_states": lane_states,
        "jobs": job_reports[:20],
    }


def build_compression_failure_guard(events: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Classify public-safe auxiliary compression failure evidence."""

    active_sessions: set[str] = set()
    timeout_sessions: set[str] = set()
    bad_fd_sessions: set[str] = set()
    huge_context_seen = False
    for event in events:
        message = _text(event.get("message"))
        session = _text(event.get("session_id")) or _text(event.get("session")) or "unknown"
        if "Preflight compression" in message:
            active_sessions.add(session)
            if "~" in message and "tokens" in message:
                huge_context_seen = True
        if "Responses stream exceeded" in message or "total timeout" in message:
            timeout_sessions.add(session)
        if "Bad file descriptor" in message or "[Errno 9]" in message:
            bad_fd_sessions.add(session)

    overlapping_compression = len(active_sessions) >= 2
    stream_poisoning_suspected = bool(timeout_sessions and bad_fd_sessions and overlapping_compression)
    issues: list[str] = []
    if stream_poisoning_suspected:
        issues.append("auxiliary_stream_lifecycle_poisoning_suspected")
    elif bad_fd_sessions:
        issues.append("bad_file_descriptor_seen_without_full_overlap_proof")
    if huge_context_seen and (timeout_sessions or bad_fd_sessions):
        issues.append("context_pressure_triggered_compression_failure")

    return {
        "schema": COMPRESSION_FAILURE_GUARD_SCHEMA,
        "read_only": True,
        "public_safe": True,
        "owner": "hermes_auxiliary_runtime" if issues else "none",
        "status": "fail" if issues else "pass",
        "issues": sorted(set(issues)),
        "proof": {
            "overlapping_compression_detected": overlapping_compression,
            "timeout_detected": bool(timeout_sessions),
            "bad_file_descriptor_detected": bool(bad_fd_sessions),
            "stream_poisoning_suspected": stream_poisoning_suspected,
            "huge_context_pressure_seen": huge_context_seen,
        },
        "recommended_owner_action": (
            "Hermes should avoid closing a shared auxiliary client/transport while another stream can still be active."
            if issues
            else ""
        ),
    }
