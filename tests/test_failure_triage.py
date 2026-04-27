from __future__ import annotations

from brainstack.product_contracts import (
    ProbeOwner,
    ProbeStatus,
    ProductProbeEnvelope,
    Repairability,
    Severity,
    build_failure_bundles,
)


def test_failure_bundle_from_failed_probe() -> None:
    probe = ProductProbeEnvelope(
        probe_id="p",
        phase="177",
        scenario_id="url",
        status=ProbeStatus.FAIL,
        owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
        repairability=Repairability.REPAIRABLE_AUTOMATIC,
        severity=Severity.P0,
        reason_code="URL_FINAL_BEFORE_TOOL",
        recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
    )

    bundles = build_failure_bundles([probe])
    assert bundles[0]["owner_classification"]["primary_owner"] == "hermes_tool_state_guard"
    assert "tests/test_no_final_before_tools.py" in bundles[0]["minimal_retest"]

