from __future__ import annotations

from scripts.verify_enterprise_release_compliance import build_report


def test_enterprise_release_compliance_report_is_public_safe_and_honest() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.enterprise_release_compliance.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["secret_scan"]["status"] == "pass"
    assert isinstance(report["sbom"]["components"], list)
    assert "strict_enterprise_claim_allowed" in report["release_claim_boundary"]
    if report["license_state"]["status"] != "explicit":
        assert "license_decision_required" in report["release_claim_boundary"]["strict_enterprise_blockers"]
