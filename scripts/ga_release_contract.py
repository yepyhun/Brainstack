"""GA release contract verdict helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class GAVerdict(StrEnum):
    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GAReleaseInputs:
    open_p0: int = 0
    open_p1: int = 0
    inconclusive_p0_p1: int = 0
    manual_only_proof: bool = False
    source_wizard_docker_parity: bool = False
    synthetic_gateway_e2e: bool = False
    live_smoke: bool = False
    failure_to_fix_open_repairable_p0_p1: int = 0
    approved_p2_p3_known_limitations: bool = True


def evaluate_ga_verdict(inputs: GAReleaseInputs) -> dict[str, Any]:
    blocking: list[str] = []
    if inputs.open_p0:
        blocking.append("OPEN_P0")
    if inputs.open_p1:
        blocking.append("OPEN_P1")
    if inputs.inconclusive_p0_p1:
        blocking.append("INCONCLUSIVE_P0_P1")
    if inputs.manual_only_proof:
        blocking.append("MANUAL_ONLY_PROOF")
    if not inputs.source_wizard_docker_parity:
        blocking.append("SOURCE_WIZARD_DOCKER_PARITY_MISSING")
    if not inputs.synthetic_gateway_e2e:
        blocking.append("SYNTHETIC_GATEWAY_E2E_MISSING")
    if not inputs.live_smoke:
        blocking.append("LIVE_SMOKE_MISSING")
    if inputs.failure_to_fix_open_repairable_p0_p1:
        blocking.append("OPEN_REPAIRABLE_P0_P1")
    if not inputs.approved_p2_p3_known_limitations:
        blocking.append("UNAPPROVED_KNOWN_LIMITATION")

    verdict = GAVerdict.READY if not blocking else GAVerdict.BLOCKED
    return {
        "schema": "brainstack.ga_release_verdict.v1",
        "verdict": verdict.value,
        "blocking": blocking,
        "ready": verdict is GAVerdict.READY,
        "universal_bug_free_claim": False,
    }


def known_limitation_record(
    *,
    limitation_id: str,
    affected_use_case: str,
    mitigation: str,
    blocks_ga: bool,
    would_block_ga_if: str,
) -> dict[str, Any]:
    return {
        "schema": "brainstack.known_limitation.v1",
        "id": limitation_id,
        "affected_use_case": affected_use_case,
        "mitigation": mitigation,
        "blocks_ga": blocks_ga,
        "would_block_ga_if": would_block_ga_if,
    }
