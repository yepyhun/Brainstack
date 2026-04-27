"""GA probe dashboard and failure OS helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from brainstack.product_contracts import (
    ProductProbeEnvelope,
    ProbeStatus,
    Severity,
    build_failure_bundles,
)
from scripts.ga_release_contract import GAReleaseInputs, evaluate_ga_verdict


GA_PROBE_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema",
    "probe_id",
    "phase",
    "scenario_id",
    "status",
    "owner",
    "repairability",
    "severity",
    "reason_code",
)

GA_REASON_CODES: tuple[str, ...] = (
    "SOURCE_WIZARD_DOCKER_PARITY_PASS",
    "SYNTHETIC_GATEWAY_E2E_PASS",
    "LIVE_GATE_NOT_RUN",
    "LIVE_GATE_PASS",
    "MANUAL_ONLY_PROOF",
    "PATH_PROOF_MISSING",
    "KNOWN_LIMITATION_UNMITIGATED",
)


def ga_probe_schema() -> dict[str, Any]:
    return {
        "schema": "brainstack.ga_probe_schema.v1",
        "required": list(GA_PROBE_REQUIRED_FIELDS),
        "reason_codes": list(GA_REASON_CODES),
        "path_proof_required_for": ["synthetic_gateway", "discord_live", "docker_adversarial"],
    }


def probe_has_path_proof(probe: ProductProbeEnvelope) -> bool:
    if not probe.observed.get("path_proof_required"):
        return True
    path_proof = probe.observed.get("path_proof")
    if not isinstance(path_proof, Mapping):
        return False
    return all(
        bool(path_proof.get(key))
        for key in (
            "used_gateway_runner",
            "used_prompt_builder",
            "used_brainstack_packet",
            "used_final_validator",
        )
    )


def classify_probe_for_dashboard(probe: ProductProbeEnvelope) -> dict[str, Any]:
    payload = probe.to_dict()
    payload["path_proof_ok"] = probe_has_path_proof(probe)
    if not payload["path_proof_ok"]:
        payload["status"] = ProbeStatus.BLOCKED.value
        payload["reason_code"] = "PATH_PROOF_MISSING"
    return payload


def build_ga_dashboard(
    probes: Iterable[ProductProbeEnvelope],
    *,
    manual_only_proof: bool = False,
    known_limitations: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    probe_items = list(probes)
    classified = [classify_probe_for_dashboard(probe) for probe in probe_items]
    failures = build_failure_bundles(
        ProductProbeEnvelope.from_dict(item) for item in classified if item["status"] != ProbeStatus.PASS.value
    )
    open_p0 = sum(1 for item in classified if item["severity"] == Severity.P0.value and item["status"] != ProbeStatus.PASS.value)
    open_p1 = sum(1 for item in classified if item["severity"] == Severity.P1.value and item["status"] != ProbeStatus.PASS.value)
    inconclusive = sum(
        1
        for item in classified
        if item["severity"] in {Severity.P0.value, Severity.P1.value} and item["owner"] == "inconclusive"
    )
    source_ok = any(item["scenario_id"] == "source_wizard_docker_parity" and item["status"] == "pass" for item in classified)
    synthetic_ok = any(item["scenario_id"] == "synthetic_gateway_e2e" and item["status"] == "pass" for item in classified)
    live_ok = any(item["scenario_id"] == "live_gate" and item["status"] == "pass" for item in classified)
    approved_known_limits = all(bool(item.get("mitigation")) and not bool(item.get("blocks_ga")) for item in known_limitations)
    verdict = evaluate_ga_verdict(
        GAReleaseInputs(
            open_p0=open_p0,
            open_p1=open_p1,
            inconclusive_p0_p1=inconclusive,
            manual_only_proof=manual_only_proof,
            source_wizard_docker_parity=source_ok,
            synthetic_gateway_e2e=synthetic_ok,
            live_smoke=live_ok,
            approved_p2_p3_known_limitations=approved_known_limits,
        )
    )
    return {
        "schema": "brainstack.ga_readiness_dashboard.v1",
        "verdict": verdict["verdict"],
        "ready": verdict["ready"],
        "blocking": verdict["blocking"],
        "counts": {
            "open_p0": open_p0,
            "open_p1": open_p1,
            "inconclusive_p0_p1": inconclusive,
            "failure_bundle_count": len(failures),
        },
        "manual_only_proof": manual_only_proof,
        "probes": classified,
        "failure_bundles": failures,
        "known_limitations": list(known_limitations),
    }
