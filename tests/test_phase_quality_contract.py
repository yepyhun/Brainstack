from __future__ import annotations

from pathlib import Path

from scripts.verify_phase_quality_contract import build_report, evaluate_phase_dir


def _phase(tmp_path: Path, name: str, plan: str, side_issues: str = "") -> Path:
    phase_dir = tmp_path / name
    phase_dir.mkdir()
    number = name.split("-", 1)[0]
    (phase_dir / f"{number}-PLAN.md").write_text(plan.strip() + "\n", encoding="utf-8")
    if side_issues:
        (phase_dir / "SIDE-ISSUES.md").write_text(side_issues.strip() + "\n", encoding="utf-8")
    return phase_dir


def test_incomplete_risky_phase_plan_fails(tmp_path: Path) -> None:
    phase = _phase(
        tmp_path,
        "1-runtime-patch",
        """
# Phase 1: Runtime Patch

## Scope

Patch live Docker memory runtime now.
""",
    )

    result = evaluate_phase_dir(phase)

    assert result["status"] == "fail"
    assert {issue["code"] for issue in result["issues"]} >= {"required_section_missing", "required_concept_missing"}


def test_low_risk_docs_only_phase_is_not_blocked(tmp_path: Path) -> None:
    phase = _phase(
        tmp_path,
        "2-doc-copy",
        """
# Phase 2: Docs Copy

## Scope

Clarify wording in a local planning note.
""",
    )

    result = evaluate_phase_dir(phase)

    assert result["status"] == "pass"
    assert result["risky"] is False


def test_unclassified_side_issue_fails_risky_phase(tmp_path: Path) -> None:
    phase = _phase(
        tmp_path,
        "3-risky-plan",
        """
# Phase 3: Risky Plan

## North Star
Safe wizard runtime memory fix.
## Must Never Happen
Live runtime change without final-state proof.
## Anti-Goals
No broad Hermes patch.
## Scope
Fix the Brainstack wizard runtime memory seam with owner classification, adjacent failure sweep, release parity, rollback, and final-state proof.
## State Transition Contract
| Operation | Pre-state | Allowed post-state | Forbidden post-state |
| --- | --- | --- | --- |
| Wizard patch | Broken | Proven | Unproven |
## Proof Gates
Final-state proof.
## Masterpiece Criteria
Durable owner classification.
## Keep-Out
No Brainstack governor.
""",
        """
# Side Issues

- Found another suspicious runtime symptom.
""",
    )

    result = evaluate_phase_dir(phase)

    assert result["status"] == "fail"
    assert {"code": "side_issue_unclassified"} in result["issues"]


def test_build_report_public_safe_fixture_proof_passes_without_local_plans(tmp_path: Path) -> None:
    report = build_report(plans_root=tmp_path / "missing", require_plans=False)

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["issues"] == []
    assert report["proof"]["incomplete_risky_fixture_failed"] is True
    assert report["proof"]["low_risk_docs_only_allowed"] is True
    assert report["proof"]["side_issue_unclassified_failed"] is True
