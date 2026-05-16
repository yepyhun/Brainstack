from __future__ import annotations

from brainstack.scoped_toolset_catalog import (
    build_agent_capability_catalog,
    validate_escalation_request,
)


def test_agent_capability_catalog_exposes_escalation_without_claiming_loss() -> None:
    catalog = build_agent_capability_catalog("read_only_audit")

    assert catalog["profile"] == "read_only_audit"
    assert "file.read" in catalog["current_capabilities"]
    assert "file.write" in catalog["not_available_by_default"]
    assert catalog["escalation"]["allowed"] is True
    assert catalog["capability_shrunk"] is False


def test_escalation_request_is_structured_and_not_for_existing_capability() -> None:
    valid = validate_escalation_request(
        {
            "capability": "file.write",
            "reason": "Need to apply verified patch",
            "risk_class": "medium",
            "fallback_if_denied": "write plan only",
        },
        current_profile="read_only_audit",
    )
    invalid = validate_escalation_request(
        {
            "capability": "file.read",
            "reason": "already available",
            "risk_class": "low",
            "fallback_if_denied": "none",
        },
        current_profile="read_only_audit",
    )

    assert valid["verdict"] == "valid"
    assert invalid["verdict"] == "invalid"
    assert "CAPABILITY_ALREADY_AVAILABLE" in invalid["reason_codes"]

