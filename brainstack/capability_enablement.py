"""Wizard capability enablement policy for Brainstack/Hermes integration."""

from __future__ import annotations

from typing import Any, Mapping


CAPABILITY_MATRIX_SCHEMA = "brainstack.capability_enablement_matrix.v1"

REQUIRED_SAFE_CORE = "required_safe_core"
REQUIRED_PROOF_WORKSTATION = "required_proof_workstation"
OPTIONAL_SIDE_EFFECTFUL_HERMES_NATIVE = "optional_side_effectful_hermes_native"
EXTERNAL_OWNER = "external_owner"

ENABLE_AND_VERIFY = "enable_and_verify"
DETECT_AND_REPORT = "detect_and_report"
EXPLICIT_OPT_IN_REQUIRED = "explicit_opt_in_required"


CAPABILITY_MATRIX: tuple[dict[str, Any], ...] = (
    {
        "capability": "brainstack_memory_provider",
        "owner": "brainstack",
        "class": REQUIRED_SAFE_CORE,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "plugins.brainstack.memory_provider",
        "proof_command": "brainstack_stats(strict=True)",
        "side_effect_risk": "none",
    },
    {
        "capability": "profile_user_memory",
        "owner": "brainstack",
        "class": REQUIRED_SAFE_CORE,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "plugins.brainstack.profile_scope",
        "proof_command": "brainstack_recall + behavior-card proof",
        "side_effect_risk": "none",
    },
    {
        "capability": "bounded_session_search_runtime",
        "owner": "brainstack_installer_or_wizard",
        "class": REQUIRED_PROOF_WORKSTATION,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "auxiliary.session_search.total_timeout",
        "proof_command": "session_search deadline/status proof",
        "side_effect_risk": "read_only",
    },
    {
        "capability": "hermes_proactive_extension_status_and_pulse",
        "owner": "brainstack_extension",
        "class": REQUIRED_PROOF_WORKSTATION,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "extensions.hermes_proactive + proactive_mode",
        "proof_command": "brainstack_proactive_status",
        "side_effect_risk": "wake_surface_only",
    },
    {
        "capability": "terminal_workstation_contract",
        "owner": "brainstack_installer_or_wizard",
        "class": REQUIRED_PROOF_WORKSTATION,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "docker.compose TERMINAL_CWD/PATH/workspace mount",
        "proof_command": "fresh installer workstation verifier",
        "side_effect_risk": "none",
    },
    {
        "capability": "local_embedding_runtime",
        "owner": "brainstack_installer_or_wizard",
        "class": REQUIRED_SAFE_CORE,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "embedding_runtime",
        "proof_command": "backend health + corpus availability status",
        "side_effect_risk": "local_service_when_selected",
    },
    {
        "capability": "tier2_background_memory_runtime",
        "owner": "brainstack",
        "class": REQUIRED_SAFE_CORE,
        "default_action": ENABLE_AND_VERIFY,
        "config_seam": "plugins.brainstack.tier2_runtime",
        "proof_command": "runtime_spine_capability_parity",
        "side_effect_risk": "memory_candidate_generation_only",
    },
    {
        "capability": "hermes_native_kanban_write_and_workers",
        "owner": "hermes_kanban",
        "class": OPTIONAL_SIDE_EFFECTFUL_HERMES_NATIVE,
        "default_action": EXPLICIT_OPT_IN_REQUIRED,
        "config_seam": "Hermes profile/toolsets kanban",
        "proof_command": "kanban_capability_evidence_ladder",
        "side_effect_risk": "creates_routes_or_executes_work",
    },
)


def capability_matrix() -> list[dict[str, Any]]:
    return [dict(item) for item in CAPABILITY_MATRIX]


def build_enablement_plan(
    *,
    enable_kanban_workstation: bool = False,
    kanban_tool_surface_proof: str = "",
) -> dict[str, Any]:
    matrix = capability_matrix()
    optional_failures: list[dict[str, str]] = []
    enabled_by_default = [
        item["capability"]
        for item in matrix
        if item["default_action"] == ENABLE_AND_VERIFY
    ]
    side_effectful_enabled_by_default = [
        item["capability"]
        for item in matrix
        if item["class"] == OPTIONAL_SIDE_EFFECTFUL_HERMES_NATIVE
        and item["default_action"] == ENABLE_AND_VERIFY
    ]
    kanban = next(item for item in matrix if item["capability"] == "hermes_native_kanban_write_and_workers")
    kanban_status = {
        "capability": kanban["capability"],
        "default_action": kanban["default_action"],
        "enabled_by_default": False,
        "operator_opt_in_requested": bool(enable_kanban_workstation),
        "tool_surface_proof": str(kanban_tool_surface_proof or "none"),
        "status": "not_requested",
    }
    if enable_kanban_workstation:
        if kanban_tool_surface_proof not in {
            "tool_surface_exposed",
            "board_write_certified",
            "worker_lifecycle_certified",
        }:
            kanban_status["status"] = "blocked_missing_tool_surface_proof"
            optional_failures.append(
                {
                    "capability": kanban["capability"],
                    "reason_code": "KANBAN_OPT_IN_REQUIRES_TOOL_SURFACE_PROOF",
                }
            )
        else:
            kanban_status["status"] = "opt_in_ready_for_operator_config"
    return {
        "schema": CAPABILITY_MATRIX_SCHEMA,
        "matrix": matrix,
        "enabled_by_default": enabled_by_default,
        "side_effectful_tools_enabled_by_default": bool(side_effectful_enabled_by_default),
        "side_effectful_default_violations": side_effectful_enabled_by_default,
        "kanban": kanban_status,
        "optional_failures_are_health_failures": False,
        "optional_failures": optional_failures,
        "status": "fail" if side_effectful_enabled_by_default or optional_failures else "pass",
    }


def summarize_enablement_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    kanban = plan.get("kanban") if isinstance(plan.get("kanban"), Mapping) else {}
    return {
        "schema": "brainstack.capability_enablement_summary.v1",
        "status": str(plan.get("status") or "unknown"),
        "required_enabled_count": len(plan.get("enabled_by_default") or []),
        "side_effectful_tools_enabled_by_default": bool(plan.get("side_effectful_tools_enabled_by_default")),
        "kanban_default_action": str(kanban.get("default_action") or ""),
        "kanban_status": str(kanban.get("status") or ""),
        "optional_failures_are_health_failures": bool(plan.get("optional_failures_are_health_failures")),
    }
