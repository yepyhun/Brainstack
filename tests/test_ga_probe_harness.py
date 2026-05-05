from __future__ import annotations

from brainstack.product_contracts import ProductProbeEnvelope, ProbeOwner, ProbeStatus, Repairability, Severity
from scripts.ga_dashboard import classify_probe_for_dashboard, ga_probe_schema


def test_ga_probe_envelope_required_fields() -> None:
    schema = ga_probe_schema()

    for field in ("probe_id", "phase", "scenario_id", "status", "owner", "repairability", "severity", "reason_code"):
        assert field in schema["required"]


def test_path_proof_required_for_e2e_claims() -> None:
    probe = ProductProbeEnvelope(
        probe_id="x",
        phase="187",
        scenario_id="synthetic_gateway_e2e",
        status=ProbeStatus.PASS,
        owner=ProbeOwner.SOURCE_OF_TRUTH_PARITY,
        repairability=Repairability.NONE,
        severity=Severity.P1,
        reason_code="SYNTHETIC_GATEWAY_E2E_PASS",
        observed={"path_proof_required": True, "path_proof": {"used_gateway_runner": True}},
    )

    classified = classify_probe_for_dashboard(probe)

    assert classified["status"] == "blocked"
    assert classified["reason_code"] == "PATH_PROOF_MISSING"


def test_common_reason_codes_across_gates() -> None:
    schema = ga_probe_schema()

    assert "LIVE_GATE_NOT_RUN" in schema["reason_codes"]
    assert "PATH_PROOF_MISSING" in schema["reason_codes"]
