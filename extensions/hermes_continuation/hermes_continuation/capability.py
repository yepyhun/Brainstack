"""Continuation capability and completion-proof contracts.

These contracts are intentionally side-effect-free. They validate whether a
work item can be assigned to a known capable worker and whether a reported
result is strong enough to advance continuation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CAPABILITY_CONTRACT_SCHEMA = "hermes_continuation.capability_contract.v1"
COMPLETION_PROOF_CONTRACT_SCHEMA = "hermes_continuation.completion_proof_contract.v1"

PROOF_STRENGTHS = {"none": 0, "weak": 1, "sufficient": 2, "verified": 3}
RECOVERY_STATUSES = {"failed", "blocked", "crashed", "timed_out", "timeout", "rejected"}
DONE_STATUSES = {"done", "completed", "success"}


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


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _refs(value: Any) -> list[str]:
    if not isinstance(value, list | tuple | set):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _tags(value: Any) -> set[str]:
    return {item.lower() for item in _refs(value)}


def _worker_id(worker: Mapping[str, Any]) -> str:
    return _text(worker.get("worker_id") or worker.get("profile_id") or worker.get("id"))


def _proof_strength(value: Any, *, has_any_proof: bool) -> str:
    explicit = _text(value).lower()
    if explicit in PROOF_STRENGTHS:
        return explicit
    return "weak" if has_any_proof else "none"


def validate_capability_assignment(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Validate whether a work requirement can be assigned to a worker/profile."""

    requirement = _mapping(evidence.get("work_requirement") or evidence.get("requirement"))
    assignee = _text(
        requirement.get("assignee")
        or requirement.get("worker_id")
        or requirement.get("profile_id")
        or evidence.get("assignee")
    )
    required_capabilities = _tags(requirement.get("required_capabilities"))
    capabilities = _items(evidence.get("capabilities") or evidence.get("workers") or evidence.get("profiles"))
    workers_by_id = {_worker_id(worker): worker for worker in capabilities if _worker_id(worker)}
    worker = workers_by_id.get(assignee)

    reason_codes: list[str] = []
    missing_capabilities: list[str] = []
    runnable = False
    source = "unknown"

    if _bool(evidence.get("private_payload_present")) or _bool(requirement.get("private_payload_present")):
        reason_codes.append("PRIVATE_PAYLOAD_PRESENT")
        verdict = "critical"
    elif not assignee or worker is None or not _bool(worker.get("exists", True)):
        reason_codes.append("UNKNOWN_ASSIGNEE")
        verdict = "critical"
    else:
        source = _text(worker.get("source")) or "capability_evidence"
        available = _tags(worker.get("capability_tags") or worker.get("capabilities"))
        missing_capabilities = sorted(required_capabilities - available)
        if missing_capabilities:
            reason_codes.append("CAPABILITY_MISMATCH")
            verdict = "critical"
        elif _bool(requirement.get("needs_human_approval")):
            reason_codes.append("HUMAN_APPROVAL_REQUIRED")
            verdict = "degraded"
        else:
            reason_codes.append("CAPABILITY_ASSIGNMENT_VALID")
            verdict = "healthy"
            runnable = True

    return {
        "schema": CAPABILITY_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": "PRIVATE_PAYLOAD_PRESENT" not in reason_codes,
        "verdict": verdict,
        "runnable": runnable,
        "assignee": assignee or "unknown",
        "required_capabilities": sorted(required_capabilities),
        "missing_capabilities": missing_capabilities,
        "capability_source": source,
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": f"capability_assignment_{verdict}",
    }


def validate_completion_proof(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate whether a worker result can count as continuation progress."""

    status = _text(result.get("status") or result.get("state")).lower()
    artifact_refs = _refs(result.get("artifact_refs") or result.get("artifacts"))
    evidence_refs = _refs(result.get("evidence_refs") or result.get("evidence"))
    result_verdict = _text(result.get("verdict") or result.get("decision"))
    postcondition = _text(result.get("postcondition"))
    blocker = _text(result.get("error_or_blocker") or result.get("blocker") or result.get("error"))
    has_any_proof = bool(artifact_refs or evidence_refs or result_verdict or postcondition or blocker)
    strength = _proof_strength(result.get("proof_strength"), has_any_proof=has_any_proof)

    reason_codes: list[str] = []
    is_material_progress = False
    recovery_evidence = False
    public_safe = not _bool(result.get("private_payload_present"))

    if not public_safe:
        reason_codes.append("PRIVATE_PAYLOAD_PRESENT")
        verdict = "critical"
    elif status in DONE_STATUSES:
        sufficient = (
            bool(artifact_refs)
            and bool(evidence_refs)
            and bool(result_verdict)
            and bool(postcondition)
            and PROOF_STRENGTHS[strength] >= PROOF_STRENGTHS["sufficient"]
        )
        if sufficient:
            verdict = "healthy"
            is_material_progress = True
            reason_codes.append("COMPLETION_PROOF_SUFFICIENT")
        else:
            verdict = "critical"
            reason_codes.append("COMPLETION_PROOF_MISSING" if strength == "none" else "WEAK_COMPLETION_PROOF")
    elif status in RECOVERY_STATUSES:
        verdict = "degraded"
        recovery_evidence = bool(blocker or evidence_refs or artifact_refs)
        reason_codes.append(
            "BLOCKED_RESULT_RECOVERY_EVIDENCE" if recovery_evidence else "BLOCKED_RESULT_MISSING_RECOVERY_EVIDENCE"
        )
    elif status in {"partial", "in_progress", "running"}:
        verdict = "degraded"
        reason_codes.append("PARTIAL_RESULT_NOT_MATERIAL_PROGRESS")
    else:
        verdict = "critical"
        reason_codes.append("UNKNOWN_COMPLETION_STATUS")

    return {
        "schema": COMPLETION_PROOF_CONTRACT_SCHEMA,
        "read_only": True,
        "side_effect_free": True,
        "public_safe": public_safe,
        "verdict": verdict,
        "status": status or "unknown",
        "proof_strength": strength,
        "artifact_refs": artifact_refs[:10],
        "evidence_refs": evidence_refs[:10],
        "result_verdict": result_verdict,
        "postcondition": postcondition,
        "is_material_progress": is_material_progress,
        "recovery_evidence": recovery_evidence,
        "reason_codes": sorted(set(reason_codes)),
        "agent_claim": f"completion_proof_{verdict}",
    }


__all__ = [
    "CAPABILITY_CONTRACT_SCHEMA",
    "COMPLETION_PROOF_CONTRACT_SCHEMA",
    "validate_capability_assignment",
    "validate_completion_proof",
]

