"""Read-only durable work-state contract for continuation diagnostics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any


DURABLE_WORK_STATE_CONTRACT_SCHEMA = "brainstack.durable_work_state_contract.v1"

TERMINAL_STATUSES = {"completed", "done"}
BLOCKED_STATUSES = {"blocked", "failed", "crashed", "timed_out", "timeout"}
ACTIVE_STATUSES = {"todo", "ready", "in_progress", "running"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _repair_candidate(work_item_id: str, failure_class: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "brainstack.durable_work_state.repair_candidate.v1",
        "read_only": True,
        "side_effect_free": True,
        "work_item_id": work_item_id,
        "failure_class": failure_class,
        "evidence": dict(evidence),
        "allowed_actions": ["diagnose", "create_repair_task", "request_authority_if_missing"],
        "forbidden_actions": ["auto_ack", "auto_complete", "auto_retry", "auto_reassign"],
        "status": "repair_candidate",
    }


def build_durable_work_state_contract(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Classify durable work state without mutating it."""

    if _bool(evidence.get("explicit_stop")) or _text(evidence.get("state")) == "stopped_intentionally":
        return {
            "schema": DURABLE_WORK_STATE_CONTRACT_SCHEMA,
            "read_only": True,
            "side_effect_free": True,
            "verdict": "stopped_intentionally",
            "reason_codes": ["DURABLE_WORK_STOPPED_INTENTIONALLY"],
            "repair_candidates": [],
            "late_participant_continuable": True,
            "status_counts": {},
            "agent_claim": "durable_work_state_stopped_intentionally",
        }

    work_items = _list_of_mappings(evidence.get("work_items"))
    reason_codes: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    repair_candidates: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    continuable_items = 0

    for item in work_items:
        work_item_id = _text(item.get("id") or item.get("task_id") or item.get("work_item_id")) or "unknown-work-item"
        status = _text(item.get("status") or item.get("lifecycle_state") or item.get("state"))
        status_counts[status or "unknown"] += 1
        authority = _text(item.get("authority") or item.get("authority_state"))
        evidence_refs = _refs(item.get("evidence_refs") or item.get("evidence") or item.get("artifact_refs"))
        handoff = _mapping(item.get("handoff"))
        repair_path = _mapping(item.get("repair")) or bool(item.get("repair_task_id"))

        if authority in {"", "unknown", "missing", "unverified"}:
            blockers.append("unknown_authority")
            reason_codes.append("UNKNOWN_AUTHORITY")
            repair_candidates.append(
                _repair_candidate(work_item_id, "unknown_authority", {"authority": authority or "missing"})
            )

        if status in TERMINAL_STATUSES:
            if _bool(item.get("acknowledged")) and not _bool(item.get("side_effect_durable")):
                blockers.append("ack_before_durability")
                reason_codes.append("ACK_BEFORE_DURABLE_SIDE_EFFECT")
                repair_candidates.append(
                    _repair_candidate(
                        work_item_id,
                        "ack_before_durability",
                        {"status": status, "acknowledged": True, "side_effect_durable": False},
                    )
                )
            if not evidence_refs:
                warnings.append("completed_without_evidence")
                reason_codes.append("COMPLETED_WITHOUT_EVIDENCE")
            if not handoff:
                warnings.append("completed_without_handoff")
                reason_codes.append("COMPLETED_WITHOUT_HANDOFF")
            if evidence_refs and handoff and _bool(item.get("side_effect_durable", True)):
                continuable_items += 1
        elif status in BLOCKED_STATUSES:
            if not repair_path and not handoff:
                warnings.append("blocked_without_repair_path")
                reason_codes.append("BLOCKED_WITHOUT_REPAIR_PATH")
                repair_candidates.append(
                    _repair_candidate(
                        work_item_id,
                        "blocked_without_repair_path",
                        {"status": status, "evidence_refs": evidence_refs[:5]},
                    )
                )
            else:
                continuable_items += 1
        elif status in ACTIVE_STATUSES:
            if evidence_refs or handoff:
                continuable_items += 1
        else:
            warnings.append("unknown_work_status")
            reason_codes.append("UNKNOWN_WORK_STATUS")

    if not work_items:
        verdict = "insufficient_evidence"
        reason_codes.append("DURABLE_WORK_INSUFFICIENT_EVIDENCE")
    elif blockers:
        verdict = "critical"
    elif warnings:
        verdict = "degraded"
    else:
        verdict = "healthy"
        reason_codes.append("DURABLE_WORK_STATE_HEALTHY")

    late_participant_continuable = verdict in {"healthy", "degraded"} and continuable_items > 0
    if not late_participant_continuable and work_items and verdict != "critical":
        warnings.append("late_participant_not_continuable")
        reason_codes.append("LATE_PARTICIPANT_NOT_CONTINUABLE")
        if verdict == "healthy":
            verdict = "degraded"

    return {
        "schema": DURABLE_WORK_STATE_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "verdict": verdict,
        "reason_codes": sorted(set(reason_codes)),
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "repair_candidates": repair_candidates[:20],
        "late_participant_continuable": late_participant_continuable,
        "status_counts": dict(sorted(status_counts.items())),
        "agent_claim": "durable_work_state_healthy" if verdict == "healthy" else f"durable_work_state_{verdict}",
    }


def durable_work_state_summary(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "brainstack.durable_work_state_summary.v1",
        "verdict": _text(contract.get("verdict")),
        "reason_codes": [str(item) for item in contract.get("reason_codes") or [] if str(item)],
        "repair_candidate_count": len(contract.get("repair_candidates") or []),
        "late_participant_continuable": _bool(contract.get("late_participant_continuable")),
    }


__all__ = [
    "DURABLE_WORK_STATE_CONTRACT_SCHEMA",
    "build_durable_work_state_contract",
    "durable_work_state_summary",
]
