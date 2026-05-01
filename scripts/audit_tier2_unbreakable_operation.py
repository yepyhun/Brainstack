#!/usr/bin/env python3
"""Audit Tier2 closure against the unbreakable-operation release gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_tier2_sota_gauntlet import _default_donor_dir, run as run_tier2_gauntlet  # noqa: E402
from scripts.audit_tier2_structural_unbreakability import run_structural_audit  # noqa: E402


REQUIRED_PROOF_FAMILIES = {
    "safety_critical_counters",
    "canonical_event_and_projection_readiness",
    "bloat_and_token_discipline",
    "event_replay_and_projection_rebuild",
    "scope_and_leak_resistance",
    "multi_hop_preservation",
    "hindsight_update_rehearsal",
}
EXACT_DONE_GATE_CLAIM = (
    "MINDE HELYZHETBEN BÁRMILYEN ESETBEN AKÁRHOGY KOMIBNÁLVA BÁRMILYEN "
    "HASZNÁLAT KÖZBEN NEM TÖRHET EL SEMMILYEN ESETBEN SEM SOHA SEHHOGY!"
)
FINITE_PROOF_SOURCES = {"gauntlet", "fixture", "oracle", "metamorphic", "counter"}


def evaluate_unbreakable_operation(packet: Mapping[str, Any]) -> dict[str, Any]:
    blockers = list(packet.get("blockers") or [])
    critical_counters = dict(packet.get("critical_counters") or {})
    proof_families = dict(packet.get("proof_families") or {})
    issues: list[dict[str, Any]] = []

    if packet.get("status") != "pass":
        issues.append({"code": "tier2_gauntlet_status_not_pass", "value": packet.get("status")})
    if blockers:
        issues.append({"code": "tier2_gauntlet_blockers_present", "blockers": blockers})

    nonzero_critical = {
        key: value
        for key, value in critical_counters.items()
        if key != "canonical_event_count" and value != 0
    }
    if nonzero_critical:
        issues.append({"code": "tier2_critical_counters_nonzero", "counters": nonzero_critical})

    missing_families = sorted(REQUIRED_PROOF_FAMILIES - set(proof_families))
    if missing_families:
        issues.append({"code": "tier2_proof_families_missing", "missing": missing_families})
    failed_families = sorted(
        family for family in REQUIRED_PROOF_FAMILIES if proof_families.get(family) is not True
    )
    if failed_families:
        issues.append({"code": "tier2_proof_families_failed", "failed": failed_families})

    canonical_event_count = critical_counters.get("canonical_event_count", 0)
    if not isinstance(canonical_event_count, int) or canonical_event_count <= 0:
        issues.append(
            {"code": "tier2_canonical_events_missing", "canonical_event_count": canonical_event_count}
        )

    proof_equivalence = packet.get("proof_equivalence")
    if not isinstance(proof_equivalence, Mapping):
        issues.append({"code": "proof_equivalence_missing"})
        proof_equivalence = {}
    if proof_equivalence:
        if proof_equivalence.get("claim") != EXACT_DONE_GATE_CLAIM:
            issues.append({"code": "proof_equivalence_claim_mismatch"})
        if proof_equivalence.get("status") != "pass":
            issues.append(
                {"code": "proof_equivalence_status_not_pass", "value": proof_equivalence.get("status")}
            )
        if proof_equivalence.get("machine_proof_same_as_claim") is not True:
            issues.append({"code": "machine_proof_not_equivalent_to_done_gate"})
        if proof_equivalence.get("finite_gauntlet_used_as_universal_proof") is not False:
            issues.append({"code": "finite_gauntlet_used_as_universal_proof"})
        if proof_equivalence.get("release_allowed_used_as_phase_success") is not False:
            issues.append({"code": "release_allowed_used_as_phase_success"})
        proof_source = str(proof_equivalence.get("proof_source") or "").strip()
        if proof_source in FINITE_PROOF_SOURCES:
            issues.append(
                {
                    "code": "finite_proof_source_cannot_prove_universal_claim",
                    "proof_source": proof_source,
                }
            )

    return {
        "schema": "brainstack.tier2_unbreakable_operation_audit.v1",
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "issues": issues,
        "critical_counters": critical_counters,
        "proof_families": {family: proof_families.get(family) for family in sorted(REQUIRED_PROOF_FAMILIES)},
        "proof_equivalence": dict(proof_equivalence),
        "canonical_event_count": canonical_event_count,
    }


def run_audit(
    *,
    phase_dir: Path,
    donor_dir: Path | None = None,
    artifact_prefix: str = "249",
) -> dict[str, Any]:
    packet = run_tier2_gauntlet(
        phase_dir=phase_dir,
        donor_dir=donor_dir or _default_donor_dir(),
        artifact_prefix=artifact_prefix,
    )
    structural = run_structural_audit(root=ROOT, claim=EXACT_DONE_GATE_CLAIM)
    packet = dict(packet)
    packet["proof_equivalence"] = structural["proof_equivalence"]
    result = evaluate_unbreakable_operation(packet)
    result["source_packet_schema"] = packet.get("schema")
    result["structural_proof"] = structural
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-dir", type=Path, required=True)
    parser.add_argument("--donor-dir", type=Path)
    parser.add_argument("--artifact-prefix", default="249")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    result = run_audit(
        phase_dir=args.phase_dir,
        donor_dir=args.donor_dir,
        artifact_prefix=args.artifact_prefix,
    )
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
