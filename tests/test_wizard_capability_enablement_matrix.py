from __future__ import annotations

from brainstack.capability_enablement import build_enablement_plan, capability_matrix
from scripts.verify_wizard_capability_enablement_matrix import build_report


def test_capability_matrix_has_safe_defaults() -> None:
    matrix = capability_matrix()
    kanban = next(item for item in matrix if item["capability"] == "hermes_native_kanban_write_and_workers")
    plan = build_enablement_plan()

    assert plan["status"] == "pass"
    assert plan["side_effectful_tools_enabled_by_default"] is False
    assert kanban["default_action"] == "enable_pending_runtime_proof"
    assert kanban["class"] == "required_proof_workstation"
    assert plan["kanban"]["enabled_by_default"] is True
    assert plan["kanban"]["status"] == "default_enabled_pending_runtime_proof"


def test_wizard_capability_enablement_matrix_report_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["issues"] == []
    assert report["proof"]["default_install_adds_kanban_toolset"] is True
    assert report["proof"]["missing_root_toolsets_preserves_native_default"] is True
    assert report["proof"]["missing_discord_platform_preserves_native_default"] is True
    assert report["proof"]["existing_toolsets_preserved"] is True
    assert report["proof"]["default_kanban_pending_proof_does_not_certify_workers"] is True
    assert report["proof"]["kanban_with_tool_surface_proof_is_runtime_proofed"] is True
