"""Side-effect-free autonomy continuation engine contract.

This module is the universal controller contract for long-running autonomous
work. It does not create tasks, call models, notify users, or mutate runtime
state. It turns event/state evidence into a compact next-action decision that a
Hermes/adapter layer may apply later through its own durable mechanisms.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any


AUTONOMY_CONTINUATION_ENGINE_SCHEMA = "hermes_continuation.engine.v1"
AUTONOMY_RUNTIME_ADAPTER_CONTRACT_SCHEMA = "hermes_continuation.runtime_adapter_contract.v1"

EVENT_KINDS = {
    "task_completed",
    "task_blocked",
    "task_crashed",
    "task_timed_out",
    "blocker_cleared",
    "approval_received",
    "provider_quota_blocked",
    "evolver_signal_observed",
    "frontier_empty",
    "frontier_below_saturation",
}

ACTION_SET = {
    "continue",
    "split",
    "verify",
    "repair",
    "learn",
    "wait",
    "human_needed",
}

HEALTH_VERDICTS = {
    "healthy",
    "degraded",
    "critical",
    "stopped_intentionally",
    "waiting_for_human",
    "waiting_for_signal",
    "insufficient_evidence",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded_score(value: Any, default: float = 0.0) -> float:
    return max(0.0, min(1.0, _float(value, default)))


def _seen_keys(state: Mapping[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key in _list(state.get("seen_idempotency_keys")):
        text = _text(key)
        if text:
            keys.add(text)
    for record in _list(state.get("decision_journal")):
        if isinstance(record, Mapping):
            text = _text(record.get("idempotency_key") or record.get("source_event_id"))
            if text:
                keys.add(text)
    return keys


def _event_idempotency_key(event: Mapping[str, Any], adapter_identity: str) -> str:
    explicit = _text(event.get("idempotency_key"))
    if explicit:
        return explicit
    material = "|".join(
        [
            adapter_identity,
            _text(event.get("source") or event.get("source_id")),
            _text(event.get("event_id") or event.get("id")),
            _text(event.get("task_id")),
            _text(event.get("kind")),
        ]
    )
    return "ace:" + sha256(material.encode("utf-8")).hexdigest()[:24]


def _normalize_forecast(raw: Any) -> list[dict[str, Any]]:
    items = raw if isinstance(raw, list) else _list(_mapping(raw).get("items"))
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(items[:5], start=1):
        if not isinstance(item, Mapping):
            continue
        normalized.append(
            {
                "rank": idx,
                "id": _text(item.get("id")) or f"step-{idx}",
                "summary": _text(item.get("summary") or item.get("title"))[:220],
                "expected_value_next": _bounded_score(item.get("expected_value_next"), 0.0),
                "confidence": _bounded_score(item.get("confidence"), 0.0),
                "independence_score": _bounded_score(item.get("independence_score"), 0.0),
                "requires_verification": _bool(item.get("requires_verification")),
                "stale": _bool(item.get("stale")),
            }
        )
    return normalized


def _forecast_revision_required(event: Mapping[str, Any], forecast: Sequence[Mapping[str, Any]]) -> bool:
    if _bool(event.get("contradicts_forecast")) or _bool(event.get("new_evidence")):
        return True
    kind = _text(event.get("kind"))
    if kind in {"task_completed", "task_blocked", "task_crashed", "task_timed_out", "blocker_cleared"}:
        return True
    return any(_bool(item.get("stale")) for item in forecast)


def _score_summary(scores: Mapping[str, Any]) -> dict[str, float]:
    expected_value = _bounded_score(scores.get("expected_value_next"), 0.0)
    confidence = _bounded_score(scores.get("confidence"), 0.0)
    intervention_risk = _bounded_score(scores.get("intervention_risk"), 0.0)
    repetition_penalty = _bounded_score(scores.get("repetition_penalty"), 0.0)
    autonomy_gain = _bounded_score(scores.get("autonomy_gain"), 0.0)
    progress_delta = _bounded_score(scores.get("progress_delta"), 0.0)
    novelty = _bounded_score(scores.get("novelty"), 0.0)
    independence = _bounded_score(scores.get("independence_score"), 0.0)
    repair_urgency = _bounded_score(scores.get("repair_urgency"), 0.0)
    continue_score = max(
        0.0,
        min(
            1.0,
            (expected_value * confidence)
            + (0.30 * autonomy_gain)
            + (0.25 * progress_delta)
            + (0.15 * novelty)
            - (0.35 * intervention_risk)
            - (0.30 * repetition_penalty),
        ),
    )
    return {
        "expected_value_next": expected_value,
        "confidence": confidence,
        "intervention_risk": intervention_risk,
        "repetition_penalty": repetition_penalty,
        "autonomy_gain": autonomy_gain,
        "progress_delta": progress_delta,
        "novelty": novelty,
        "independence_score": independence,
        "repair_urgency": repair_urgency,
        "continue_score": round(continue_score, 4),
    }


def build_autonomy_continuation_decision(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic next-action decision from continuation evidence."""

    event = _mapping(evidence.get("event"))
    state = _mapping(evidence.get("controller_state") or evidence.get("state"))
    scores = _score_summary(_mapping(evidence.get("scores")))
    safety = _mapping(evidence.get("safety"))
    frontier = _mapping(evidence.get("frontier"))
    review = _mapping(evidence.get("review"))
    artifacts = _mapping(evidence.get("artifacts"))
    evolver = _mapping(evidence.get("evolver_signal"))
    adapter = _mapping(evidence.get("adapter"))

    adapter_identity = _text(adapter.get("identity")) or "universal"
    idempotency_key = _event_idempotency_key(event, adapter_identity)
    reason_codes: list[str] = []
    learning_candidates: list[dict[str, str]] = []
    duplicate = idempotency_key in _seen_keys(state)
    event_kind = _text(event.get("kind"))
    if event_kind and event_kind not in EVENT_KINDS:
        reason_codes.append("UNKNOWN_EVENT_KIND")

    forecast = _normalize_forecast(evidence.get("rolling_next5") or state.get("rolling_next5") or evidence.get("forecast"))
    forecast_revision_required = _forecast_revision_required(event, forecast)
    if forecast_revision_required:
        reason_codes.append("ROLLING_NEXT5_REVIEW_REQUIRED")

    explicit_stop = _bool(state.get("intentional_stop")) or _text(state.get("status")) == "stopped_intentionally"
    no_signal = not event_kind and not forecast and not _bool(frontier.get("actionable_frontier_count"))
    local_repair_available = _bool(safety.get("local_repair_available"))
    external_side_effect = _bool(safety.get("external_side_effect"))
    destructive_action = _bool(safety.get("destructive_action"))
    approval_missing = _bool(safety.get("approval_missing"))
    authority_missing = _bool(safety.get("authority_missing"))
    credential_missing = _bool(safety.get("credential_missing"))
    private_leak = _bool(adapter.get("private_data_present")) or _bool(safety.get("private_adapter_leak"))
    artifact_missing = _bool(artifacts.get("required_missing")) or _bool(event.get("artifact_missing"))
    contradicted = _bool(event.get("contradicted")) or _bool(event.get("previous_step_wrong"))
    worker_crashed = event_kind in {"task_crashed", "task_timed_out"} or _bool(event.get("worker_crashed"))
    quota_blocked = event_kind == "provider_quota_blocked" or _bool(safety.get("provider_quota_blocked"))
    repeated_filler = scores["repetition_penalty"] >= 0.65 or _bool(review.get("filler_loop_detected"))
    risky = scores["intervention_risk"] >= 0.70 or external_side_effect or destructive_action
    low_confidence = scores["confidence"] < 0.55
    high_value = scores["expected_value_next"] >= 0.65
    can_split = (
        scores["independence_score"] >= 0.70
        and high_value
        and scores["confidence"] >= 0.65
        and _int(state.get("current_fanout")) < _int(state.get("max_fanout"), 4)
        and not risky
    )

    decision = "wait"
    verdict = "waiting_for_signal"

    if duplicate:
        decision = "wait"
        verdict = "healthy"
        reason_codes.append("DUPLICATE_EVENT_IGNORED")
    elif explicit_stop:
        decision = "wait"
        verdict = "stopped_intentionally"
        reason_codes.append("INTENTIONAL_STOP_ACTIVE")
    elif private_leak:
        decision = "human_needed"
        verdict = "critical"
        reason_codes.append("PRIVATE_ADAPTER_LEAK")
    elif authority_missing or credential_missing or (approval_missing and (external_side_effect or destructive_action)):
        decision = "human_needed"
        verdict = "waiting_for_human"
        reason_codes.append("MISSING_AUTHORITY_OR_APPROVAL")
    elif local_repair_available and (artifact_missing or contradicted or worker_crashed or repeated_filler):
        decision = "repair"
        verdict = "degraded"
        reason_codes.append("LOCAL_REPAIR_REQUIRED")
    elif contradicted or scores["repair_urgency"] >= 0.65:
        decision = "repair"
        verdict = "degraded"
        reason_codes.append("BACKTRACK_OR_REPAIR_REQUIRED")
    elif artifact_missing:
        decision = "repair"
        verdict = "degraded"
        reason_codes.append("MISSING_REQUIRED_ARTIFACT")
    elif worker_crashed:
        decision = "repair"
        verdict = "degraded"
        reason_codes.append("WORKER_FAILURE_REPAIR_REQUIRED")
    elif quota_blocked:
        decision = "wait"
        verdict = "waiting_for_signal"
        reason_codes.append("PROVIDER_QUOTA_BLOCKED")
    elif _bool(evolver.get("observed")) or event_kind == "evolver_signal_observed":
        decision = "verify"
        verdict = "degraded"
        reason_codes.append("EVOLVER_SIGNAL_REQUIRES_VERIFICATION")
    elif repeated_filler:
        decision = "learn"
        verdict = "degraded"
        reason_codes.append("REPETITION_OR_FILLER_LOOP")
    elif risky or (low_confidence and high_value):
        decision = "verify"
        verdict = "degraded"
        reason_codes.append("VERIFY_BEFORE_ACTION")
    elif can_split:
        decision = "split"
        verdict = "healthy"
        reason_codes.append("INDEPENDENT_HIGH_VALUE_BRANCH")
    elif scores["continue_score"] >= 0.45 and not low_confidence and not no_signal:
        decision = "continue"
        verdict = "healthy"
        reason_codes.append("MEANINGFUL_CONTINUATION")
    elif no_signal:
        decision = "wait"
        verdict = "waiting_for_signal"
        reason_codes.append("NO_SIGNAL_NO_FILLER")
    else:
        decision = "wait"
        verdict = "insufficient_evidence"
        reason_codes.append("INSUFFICIENT_VALUE_OR_CONFIDENCE")

    if decision not in ACTION_SET:
        decision = "wait"
        verdict = "critical"
        reason_codes.append("INVALID_ACTION_NORMALIZED")
    if verdict not in HEALTH_VERDICTS:
        verdict = "critical"
        reason_codes.append("INVALID_VERDICT_NORMALIZED")

    if decision in {"repair", "learn"}:
        learning_candidates.append(
            {
                "kind": "edge_case",
                "reason_code": sorted(set(reason_codes))[0] if reason_codes else "UNKNOWN",
                "suggested_artifact": "skill_patch_or_regression_fixture",
            }
        )

    return {
        "schema": AUTONOMY_CONTINUATION_ENGINE_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "adapter_identity": adapter_identity,
        "event_kind": event_kind or "none",
        "idempotency_key": idempotency_key,
        "duplicate_ignored": duplicate,
        "decision": decision,
        "verdict": verdict,
        "scores": scores,
        "rolling_next5": forecast,
        "forecast_revision_required": forecast_revision_required,
        "review": {
            "cheap_critic_required": True,
            "deep_verifier_required": decision in {"split", "verify", "repair", "human_needed"} or risky or low_confidence,
            "worker_self_final_allowed": decision not in {"split", "verify", "repair", "human_needed"},
        },
        "safety_gates": {
            "external_side_effect": external_side_effect,
            "destructive_action": destructive_action,
            "authority_missing": authority_missing,
            "credential_missing": credential_missing,
            "approval_missing": approval_missing,
            "local_repair_available": local_repair_available,
            "private_adapter_leak": private_leak,
        },
        "learning_candidates": learning_candidates,
        "decision_journal": {
            "idempotency_key": idempotency_key,
            "decision": decision,
            "verdict": verdict,
            "reason_codes": sorted(set(reason_codes)),
            "confidence": scores["confidence"],
            "expected_value_next": scores["expected_value_next"],
            "continue_score": scores["continue_score"],
            "what_would_change_decision": _decision_change_hint(decision),
        },
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": f"autonomy_continuation_{decision}",
    }


def build_autonomy_runtime_adapter_contract(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the side-effect boundary for an autonomy runtime adapter.

    The continuation engine decides. A runtime adapter may apply decisions only
    through explicit Hermes-owned mechanisms and must leave replayable receipts.
    This function is still pure: it validates adapter evidence, it does not run
    the adapter.
    """

    decision = _mapping(evidence.get("decision"))
    adapter = _mapping(evidence.get("adapter"))
    runtime = _mapping(evidence.get("runtime"))
    receipt = _mapping(evidence.get("receipt"))
    cursor = _mapping(evidence.get("cursor"))

    action = _text(decision.get("decision"))
    adapter_identity = _text(adapter.get("identity")) or "universal"
    side_effect_channel = _text(runtime.get("side_effect_channel"))
    applies_side_effect = action in {"continue", "split", "repair", "learn", "verify"} and action != "wait"
    hermes_owned = side_effect_channel in {"none", "", "hermes_kanban", "hermes_cron", "hermes_gateway"}
    receipt_written = _bool(receipt.get("written"))
    cursor_persisted = _bool(cursor.get("persisted"))
    idempotent = _bool(runtime.get("idempotent_applier"))
    failure_as_state = _bool(runtime.get("failure_reported_as_state"))
    private_leak = _bool(adapter.get("private_data_present"))
    direct_evolver_execution = _bool(runtime.get("direct_evolver_execution"))
    direct_domain_execution = _bool(runtime.get("direct_domain_execution"))

    reason_codes: list[str] = []
    if applies_side_effect and not hermes_owned:
        reason_codes.append("SIDE_EFFECT_CHANNEL_NOT_HERMES_OWNED")
    if applies_side_effect and not receipt_written:
        reason_codes.append("MISSING_RESULT_RECEIPT")
    if applies_side_effect and not cursor_persisted:
        reason_codes.append("MISSING_REPLAY_CURSOR")
    if applies_side_effect and not idempotent:
        reason_codes.append("ADAPTER_NOT_IDEMPOTENT")
    if not failure_as_state:
        reason_codes.append("FAILURE_NOT_REPORTED_AS_STATE")
    if private_leak:
        reason_codes.append("PRIVATE_ADAPTER_LEAK")
    if direct_evolver_execution:
        reason_codes.append("DIRECT_EVOLVER_EXECUTION_FORBIDDEN")
    if direct_domain_execution:
        reason_codes.append("DIRECT_DOMAIN_EXECUTION_FORBIDDEN")

    if private_leak or direct_evolver_execution or direct_domain_execution or (
        applies_side_effect and not hermes_owned
    ):
        verdict = "critical"
    elif reason_codes:
        verdict = "degraded"
    else:
        verdict = "healthy"
        reason_codes.append("RUNTIME_ADAPTER_CONTRACT_HEALTHY")

    return {
        "schema": AUTONOMY_RUNTIME_ADAPTER_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "adapter_identity": adapter_identity,
        "decision": action or "none",
        "side_effect_channel": side_effect_channel or "none",
        "applies_side_effect": applies_side_effect,
        "receipt_written": receipt_written,
        "cursor_persisted": cursor_persisted,
        "idempotent_applier": idempotent,
        "failure_reported_as_state": failure_as_state,
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": f"autonomy_runtime_adapter_{verdict}",
    }


def _decision_change_hint(decision: str) -> str:
    if decision == "human_needed":
        return "local authority, credential, approval, or safe confidence becomes available"
    if decision == "wait":
        return "new meaningful event, evidence, or unblocked dependency appears"
    if decision == "verify":
        return "verifier raises confidence or lowers risk"
    if decision == "repair":
        return "missing artifact, contradiction, crash, or wrong step is resolved"
    if decision == "learn":
        return "repetition or failure pattern is converted into a regression or skill update"
    if decision == "split":
        return "branch independence, fanout budget, or value score changes"
    return "new evidence changes expected value, confidence, or risk"
