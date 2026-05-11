#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]

RISK_MARKERS = (
    "runtime",
    "live",
    "wizard",
    "release",
    "docker",
    "provider",
    "auth",
    "memory",
    "graph",
    "tier2",
    "proactive",
    "kanban",
    "write",
    "mutation",
    "side effect",
    "side-effect",
)

REQUIRED_RISKY_SECTIONS = (
    "North Star",
    "Must Never Happen",
    "Anti-Goals",
    "Scope",
    "State Transition Contract",
    "Proof Gates",
    "Masterpiece Criteria",
    "Keep-Out",
)

CONCEPT_GROUPS: dict[str, tuple[str, ...]] = {
    "owner_classification": (
        "owner classification",
        "owner class",
        "owner:",
        "owned by",
        "brainstack-owned",
        "hermes-owned",
        "external-owner",
        "external owner",
    ),
    "adjacent_failure_sweep": (
        "adjacent failure",
        "adjacent-risk sweep",
        "similar failure",
        "same failure class",
        "nearby installer seams",
        "nearby",
    ),
    "negative_invariant": (
        "must never happen",
        "negative invariant",
        "forbidden post-state",
        "forbidden state",
    ),
    "final_state_proof": (
        "final-state proof",
        "final state proof",
        "proof gates",
        "agent-facing uat",
        "negative uat",
    ),
    "parity_decision": (
        "parity decision",
        "source/live",
        "release parity",
        "wizard",
        "live parity",
        "source-of-truth",
        "fresh install",
    ),
    "rollback_or_safe_drain": (
        "rollback",
        "reversibility",
        "safe-drain",
        "safe drain",
        "idempotent",
        "revert",
    ),
}

SIDE_ISSUE_CLASSES = (
    "blocks_phase",
    "bonus_phase_next",
    "external_owner",
    "backlog",
    "rejected",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def _has_heading(text: str, heading: str) -> bool:
    pattern = re.compile(rf"^#+\s+{re.escape(heading)}\s*$", re.IGNORECASE | re.MULTILINE)
    return bool(pattern.search(text))


def _is_risky(text: str) -> bool:
    lowered = _norm(text)
    if ("docs-only" in lowered or "docs only" in lowered) and not any(
        marker in lowered
        for marker in (
            "runtime patch",
            "live patch",
            "wizard patch",
            "release gate",
            "memory write",
            "docker install",
        )
    ):
        return False
    return any(marker in lowered for marker in RISK_MARKERS)


def _has_any(text: str, needles: Iterable[str]) -> bool:
    lowered = _norm(text)
    return any(needle.lower() in lowered for needle in needles)


def _phase_number(path: Path) -> str:
    return path.name.split("-", 1)[0]


def _plan_path(phase_dir: Path) -> Path | None:
    number = _phase_number(phase_dir)
    matches = sorted(phase_dir.glob(f"{number}-PLAN.md"))
    return matches[0] if matches else None


def _side_issue_text(phase_dir: Path) -> str:
    path = phase_dir / "SIDE-ISSUES.md"
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _side_issues_classified(side_text: str) -> bool:
    stripped = side_text.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if "no side issues" in lowered or "none" == lowered:
        return True
    return any(cls in lowered for cls in SIDE_ISSUE_CLASSES)


def evaluate_phase_dir(phase_dir: Path) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    plan = _plan_path(phase_dir)
    if plan is None:
        return {
            "phase": _phase_number(phase_dir),
            "status": "fail",
            "risky": None,
            "issues": [{"code": "phase_plan_missing"}],
        }

    text = plan.read_text(encoding="utf-8", errors="replace")
    side_text = _side_issue_text(phase_dir)
    combined = f"{text}\n{side_text}"
    risky = _is_risky(combined)

    if risky:
        for heading in REQUIRED_RISKY_SECTIONS:
            if not _has_heading(text, heading):
                issues.append({"code": "required_section_missing", "section": heading})
        for concept, needles in CONCEPT_GROUPS.items():
            if not _has_any(combined, needles):
                issues.append({"code": "required_concept_missing", "concept": concept})
        if not _side_issues_classified(side_text):
            issues.append({"code": "side_issue_unclassified"})

    return {
        "phase": _phase_number(phase_dir),
        "status": "pass" if not issues else "fail",
        "risky": risky,
        "issues": issues,
    }


def _write_fixture(root: Path, name: str, plan: str, side_issues: str = "") -> Path:
    phase_dir = root / name
    phase_dir.mkdir(parents=True)
    number = name.split("-", 1)[0]
    (phase_dir / f"{number}-PLAN.md").write_text(plan.strip() + "\n", encoding="utf-8")
    if side_issues:
        (phase_dir / "SIDE-ISSUES.md").write_text(side_issues.strip() + "\n", encoding="utf-8")
    return phase_dir


def _fixture_report() -> dict[str, Any]:
    with TemporaryDirectory(prefix="brainstack-phase-quality-") as raw:
        root = Path(raw)
        incomplete = _write_fixture(
            root,
            "901-incomplete-risky-runtime-patch",
            """
# Phase 901: Incomplete Risky Runtime Patch

## Scope

Patch the live runtime wizard because Docker auth broke.
""",
        )
        low_risk = _write_fixture(
            root,
            "902-low-risk-doc-copyedit",
            """
# Phase 902: Low Risk Docs Copyedit

## Scope

Docs-only wording clarification for one README sentence.
""",
        )
        unclassified_side_issue = _write_fixture(
            root,
            "903-risky-with-unclassified-side-issue",
            """
# Phase 903: Risky With Unclassified Side Issue

## North Star
Safe runtime patch.
## Must Never Happen
Live runtime changes without proof.
## Anti-Goals
No broad host patch.
## Scope
Fix a wizard runtime memory issue.
## State Transition Contract
| Operation | Pre-state | Allowed post-state | Forbidden post-state |
| --- | --- | --- | --- |
| Runtime patch | Broken | Proven | Unproven |
## Proof Gates
Final-state proof and release parity.
## Masterpiece Criteria
Owner classification and adjacent failure sweep.
## Keep-Out
No Brainstack governor.
""",
            """
# Side Issues

- Something else looked suspicious.
""",
        )
        results = {
            "incomplete_risky": evaluate_phase_dir(incomplete),
            "low_risk_docs": evaluate_phase_dir(low_risk),
            "unclassified_side_issue": evaluate_phase_dir(unclassified_side_issue),
        }
        return {
            "incomplete_risky_fixture_failed": results["incomplete_risky"]["status"] == "fail",
            "low_risk_docs_only_allowed": results["low_risk_docs"]["status"] == "pass",
            "side_issue_unclassified_failed": results["unclassified_side_issue"]["status"] == "fail",
            "fixture_results": results,
        }


def build_report(
    *,
    plans_root: Path = ROOT / ".planning" / "phases",
    phase_numbers: tuple[str, ...] = ("293", "294", "295", "296", "297"),
    require_plans: bool = False,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    fixture = _fixture_report()
    proof = {
        "incomplete_risky_fixture_failed": fixture["incomplete_risky_fixture_failed"],
        "low_risk_docs_only_allowed": fixture["low_risk_docs_only_allowed"],
        "side_issue_unclassified_failed": fixture["side_issue_unclassified_failed"],
        "public_safe_output": True,
    }
    for key, value in proof.items():
        if value is not True:
            issues.append({"code": "fixture_proof_failed", "proof": key})

    local_phase_results: list[dict[str, Any]] = []
    if plans_root.exists():
        for number in phase_numbers:
            matches = sorted(plans_root.glob(f"{number}-*"))
            if not matches:
                issues.append({"code": "local_phase_missing", "phase": number})
                continue
            result = evaluate_phase_dir(matches[0])
            local_phase_results.append(result)
            if result["status"] != "pass":
                issues.append({"code": "local_phase_quality_failed", "phase": number, "issues": result["issues"]})
    elif require_plans:
        issues.append({"code": "plans_root_missing", "path": str(plans_root)})

    if local_phase_results:
        proof["local_phases_293_297_pass"] = all(item["status"] == "pass" for item in local_phase_results)
        proof["local_phase_count"] = len(local_phase_results)
    else:
        proof["local_phases_293_297_pass"] = None
        proof["local_phase_count"] = 0

    return {
        "schema": "brainstack.phase_quality_contract.v1",
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "issues": issues,
        "proof": proof,
        "phase_numbers": list(phase_numbers),
        "local_phase_results": local_phase_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify risky GSD phase quality gates without publishing .planning.")
    parser.add_argument("--plans-root", type=Path, default=ROOT / ".planning" / "phases")
    parser.add_argument("--phase", action="append", dest="phases", help="Phase number to verify; may be repeated.")
    parser.add_argument("--require-plans", action="store_true", help="Fail if plans root is missing.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = build_report(
        plans_root=args.plans_root,
        phase_numbers=tuple(args.phases or ("293", "294", "295", "296", "297")),
        require_plans=args.require_plans,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
