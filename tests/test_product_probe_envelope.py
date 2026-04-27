from __future__ import annotations

from brainstack.product_contracts import (
    ProbeOwner,
    ProbeStatus,
    ProductProbeEnvelope,
    Repairability,
    Severity,
)


def test_product_probe_envelope_required_fields() -> None:
    probe = ProductProbeEnvelope(
        probe_id="p1",
        phase="179",
        scenario_id="sample",
        status=ProbeStatus.FAIL,
        owner=ProbeOwner.HERMES_TOOL_STATE_GUARD,
        repairability=Repairability.REPAIRABLE_AUTOMATIC,
        severity=Severity.P0,
        reason_code="URL_FINAL_BEFORE_TOOL",
        observed={"final_answer_before_tool": True},
        expected={"final_answer_allowed": False},
        recommended_playbook="TOOL_STATE_FINAL_ANSWER_BLOCK",
    )
    payload = probe.to_dict()

    assert payload["schema"] == "brainstack.product_probe.v1"
    assert payload["owner"] == "hermes_tool_state_guard"
    assert ProductProbeEnvelope.from_dict(payload).failed is True

