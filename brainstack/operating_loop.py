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


def _external_work_state_summary(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Compact an optional extension-provided work-state verdict.

    Brainstack does not calculate continuation/work-state authority. Optional
    runtime extensions may pass a verdict into this health contract; the memory
    kernel only surfaces a bounded summary.
    """

    repair_candidates = contract.get("repair_candidates")
    reason_codes = [str(item) for item in contract.get("reason_codes") or [] if str(item)]
    return {
        "schema": "brainstack.external_work_state_summary.v1",
        "verdict": _text(contract.get("verdict")),
        "reason_code": reason_codes[0] if reason_codes else "",
        "reason_count": len(reason_codes),
        "repair_candidate_count": len(repair_candidates) if isinstance(repair_candidates, list) else 0,
        "agent_claim": _text(contract.get("agent_claim")),
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
    durable_work_state = _mapping(evidence.get("durable_work_state"))
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

    durable_work_verdict = _text(durable_work_state.get("verdict"))
    durable_work_reasons = [
        str(item) for item in durable_work_state.get("reason_codes") or [] if str(item)
    ]
    if durable_work_verdict == "critical":
        blockers.append("durable_work_state_critical")
        reason_codes.extend(durable_work_reasons or ["DURABLE_WORK_STATE_CRITICAL"])
    elif durable_work_verdict == "degraded":
        blockers.append("durable_work_state_degraded")
        reason_codes.extend(durable_work_reasons or ["DURABLE_WORK_STATE_DEGRADED"])

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
            durable_work_state,
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
    elif (
        split_brain
        or "kanban_blocked_ready_tasks" in blockers
        or "frontier_continuation_critical" in blockers
        or "durable_work_state_critical" in blockers
        or scheduler_verdict == "critical"
    ):
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
            "token_policy": _text(continuation.get("token_policy")),
            "continuation_gap_count": _safe_int(continuation.get("continuation_gap_count"), 0),
        }
        if continuation
        else {},
        "durable_work_state": _external_work_state_summary(durable_work_state)
        if durable_work_state
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
