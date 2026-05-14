from __future__ import annotations

from hermes_continuation.capability import (
    validate_capability_assignment,
    validate_completion_proof,
)


def test_unknown_assignee_is_not_runnable() -> None:
    verdict = validate_capability_assignment(
        {
            "capabilities": [
                {"profile_id": "default", "exists": True, "capability_tags": ["research"]},
            ],
            "work_requirement": {
                "assignee": "worker",
                "required_capabilities": ["research"],
                "work_type": "evidence_review",
            },
        }
    )

    assert verdict["verdict"] == "critical"
    assert verdict["runnable"] is False
    assert "UNKNOWN_ASSIGNEE" in verdict["reason_codes"]


def test_capability_mismatch_is_not_runnable() -> None:
    verdict = validate_capability_assignment(
        {
            "capabilities": [
                {"profile_id": "reviewer", "exists": True, "capability_tags": ["review"]},
            ],
            "work_requirement": {
                "assignee": "reviewer",
                "required_capabilities": ["research"],
                "work_type": "evidence_research",
            },
        }
    )

    assert verdict["verdict"] == "critical"
    assert verdict["runnable"] is False
    assert "CAPABILITY_MISMATCH" in verdict["reason_codes"]


def test_valid_capability_assignment_is_runnable() -> None:
    verdict = validate_capability_assignment(
        {
            "capabilities": [
                {
                    "profile_id": "reviewer",
                    "exists": True,
                    "capability_tags": ["review", "research"],
                    "source": "fixture",
                },
            ],
            "work_requirement": {
                "assignee": "reviewer",
                "required_capabilities": ["review"],
                "work_type": "evidence_review",
            },
        }
    )

    assert verdict["verdict"] == "healthy"
    assert verdict["runnable"] is True
    assert verdict["reason_codes"] == ["CAPABILITY_ASSIGNMENT_VALID"]


def test_empty_done_proof_is_not_material_progress() -> None:
    proof = validate_completion_proof({"status": "done"})

    assert proof["verdict"] == "critical"
    assert proof["is_material_progress"] is False
    assert proof["proof_strength"] == "none"
    assert "COMPLETION_PROOF_MISSING" in proof["reason_codes"]


def test_failed_result_with_blocker_is_recovery_evidence_not_done() -> None:
    proof = validate_completion_proof(
        {
            "status": "failed",
            "error_or_blocker": "missing credentials",
            "evidence_refs": ["log:failure"],
        }
    )

    assert proof["verdict"] == "degraded"
    assert proof["is_material_progress"] is False
    assert proof["recovery_evidence"] is True
    assert "BLOCKED_RESULT_RECOVERY_EVIDENCE" in proof["reason_codes"]


def test_done_with_artifact_evidence_and_verdict_is_material_progress() -> None:
    proof = validate_completion_proof(
        {
            "status": "done",
            "artifact_refs": ["artifact:summary.json"],
            "evidence_refs": ["receipt:1"],
            "verdict": "accepted",
            "postcondition": "frontier_created",
            "proof_strength": "sufficient",
        }
    )

    assert proof["verdict"] == "healthy"
    assert proof["is_material_progress"] is True
    assert proof["proof_strength"] == "sufficient"
    assert proof["reason_codes"] == ["COMPLETION_PROOF_SUFFICIENT"]

