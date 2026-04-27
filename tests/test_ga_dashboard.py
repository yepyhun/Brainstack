from __future__ import annotations

from brainstack.product_contracts import ProductProbeEnvelope, ProbeOwner, ProbeStatus, Repairability, Severity
from scripts.ga_dashboard import build_ga_dashboard


def probe(
    probe_id: str,
    scenario_id: str,
    status: ProbeStatus,
    severity: Severity,
    *,
    owner: ProbeOwner = ProbeOwner.SOURCE_OF_TRUTH_PARITY,
) -> ProductProbeEnvelope:
    return ProductProbeEnvelope(
        probe_id=probe_id,
        phase="187",
        scenario_id=scenario_id,
        status=status,
        owner=owner,
        repairability=Repairability.HUMAN_DECISION_REQUIRED if status != ProbeStatus.PASS else Repairability.NONE,
        severity=severity,
        reason_code="LIVE_GATE_NOT_RUN" if status != ProbeStatus.PASS else "SOURCE_WIZARD_DOCKER_PARITY_PASS",
    )


def green_core_probes() -> list[ProductProbeEnvelope]:
    return [
        probe("source", "source_wizard_docker_parity", ProbeStatus.PASS, Severity.P0),
        probe("synthetic", "synthetic_gateway_e2e", ProbeStatus.PASS, Severity.P1),
        probe("live", "live_gate", ProbeStatus.PASS, Severity.P1),
    ]


def test_ga_dashboard_blocks_open_p0() -> None:
    probes = green_core_probes() + [probe("p0", "capability_shrink", ProbeStatus.FAIL, Severity.P0)]

    dashboard = build_ga_dashboard(probes)

    assert dashboard["ready"] is False
    assert dashboard["counts"]["open_p0"] == 1


def test_ga_dashboard_blocks_open_p1() -> None:
    probes = green_core_probes() + [probe("p1", "live_gate", ProbeStatus.BLOCKED, Severity.P1)]

    dashboard = build_ga_dashboard(probes)

    assert dashboard["ready"] is False
    assert dashboard["counts"]["open_p1"] == 1


def test_ga_dashboard_blocks_inconclusive_p0_p1() -> None:
    probes = green_core_probes() + [probe("inc", "unknown", ProbeStatus.PASS, Severity.P1, owner=ProbeOwner.INCONCLUSIVE)]

    dashboard = build_ga_dashboard(probes)

    assert dashboard["ready"] is False
    assert dashboard["counts"]["inconclusive_p0_p1"] == 1


def test_ga_dashboard_blocks_manual_only_proof() -> None:
    dashboard = build_ga_dashboard(green_core_probes(), manual_only_proof=True)

    assert dashboard["ready"] is False
    assert "MANUAL_ONLY_PROOF" in dashboard["blocking"]


def test_known_limitation_nonblocking_only_when_mitigated() -> None:
    dashboard = build_ga_dashboard(green_core_probes(), known_limitations=[{"id": "web_missing", "mitigation": "diagnostic", "blocks_ga": False}])
    bad = build_ga_dashboard(green_core_probes(), known_limitations=[{"id": "web_missing", "mitigation": "", "blocks_ga": False}])

    assert dashboard["ready"] is True
    assert bad["ready"] is False


def test_dashboard_ready_conditional_blocked_semantics() -> None:
    ready = build_ga_dashboard(green_core_probes())
    blocked = build_ga_dashboard(green_core_probes()[:-1])

    assert ready["verdict"] == "READY"
    assert blocked["verdict"] == "BLOCKED"
