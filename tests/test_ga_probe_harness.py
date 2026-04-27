from __future__ import annotations

import json
from pathlib import Path

from brainstack.product_contracts import ProductProbeEnvelope, ProbeOwner, ProbeStatus, Repairability, Severity
from scripts.ga_dashboard import classify_probe_for_dashboard, ga_probe_schema


ROOT = Path(__file__).resolve().parents[1]


def test_ga_probe_envelope_required_fields() -> None:
    schema = ga_probe_schema()

    for field in ("probe_id", "phase", "scenario_id", "status", "owner", "repairability", "severity", "reason_code"):
        assert field in schema["required"]


def test_failure_bundle_includes_owner_playbook_retests() -> None:
    text = (ROOT / "GA_FAILURE_PLAYBOOKS.yaml").read_text(encoding="utf-8")

    assert "LIVE_GATE_EXECUTION_REQUIRED" in text
    assert "forbidden_fixes" in text
    assert "minimal_tests" in text
    assert "blast_radius_tests" in text


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


def test_affected_retest_map_is_machine_readable() -> None:
    payload = json.loads((ROOT / "GA_AFFECTED_RETEST_MAP.json").read_text(encoding="utf-8"))

    assert payload["schema"] == "brainstack.ga_affected_retest_map.v1"
    assert "scripts/ga_dashboard.py" in payload
