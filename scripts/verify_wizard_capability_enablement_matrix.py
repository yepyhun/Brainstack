#!/usr/bin/env python3
"""Verify Brainstack wizard capability defaults are explicit and safe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.capability_enablement import (  # noqa: E402
    ENABLE_PENDING_RUNTIME_PROOF,
    ENABLE_AND_VERIFY,
    EXPLICIT_OPT_IN_REQUIRED,
    OPTIONAL_SIDE_EFFECTFUL_HERMES_NATIVE,
    build_enablement_plan,
    capability_matrix,
    summarize_enablement_plan,
)
from scripts import install_into_hermes  # noqa: E402


REPORT_SCHEMA = "brainstack.wizard_capability_enablement_matrix.v1"


def _target(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = root / "hermes"
    target.mkdir()
    return target


def _config(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    config = root / "config.yaml"
    config.write_text("toolsets:\n  - hermes-cli\nplatform_toolsets:\n  discord:\n    - memory\n", encoding="utf-8")
    return config


def _default_install_manifest(root: Path) -> dict[str, Any]:
    _target(root / "default")
    config = _config(root / "default")
    result = install_into_hermes._patch_config(config, dry_run=False, embedding_runtime="none")
    plan = build_enablement_plan()
    data = install_into_hermes._load_yaml(config)
    return {
        "patch_result": result,
        "config": data,
        "capability_summary": summarize_enablement_plan(plan),
    }


def _empty_config_install_manifest(root: Path) -> dict[str, Any]:
    _target(root / "empty")
    config = root / "empty" / "config.yaml"
    config.write_text("{}", encoding="utf-8")
    result = install_into_hermes._patch_config(config, dry_run=False, embedding_runtime="none")
    data = install_into_hermes._load_yaml(config)
    return {"patch_result": result, "config": data}


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-capability-matrix-") as tmpdir:
        root = Path(tmpdir)
        default_manifest = _default_install_manifest(root)
        empty_manifest = _empty_config_install_manifest(root)
    matrix = capability_matrix()
    default_plan = build_enablement_plan()
    proofed_kanban = build_enablement_plan(
        enable_kanban_workstation=True,
        kanban_tool_surface_proof="tool_surface_exposed",
    )
    config = default_manifest["config"]
    root_toolsets = [str(item) for item in config.get("toolsets") or []]
    platform_toolsets = [
        str(item)
        for item in (config.get("platform_toolsets") or {}).get("discord", [])
    ]
    empty_discord_toolsets = [
        str(item)
        for item in (empty_manifest["config"].get("platform_toolsets") or {}).get("discord", [])
    ]
    empty_root_toolsets = [str(item) for item in empty_manifest["config"].get("toolsets") or []]
    side_effectful = [
        item for item in matrix if item["class"] == OPTIONAL_SIDE_EFFECTFUL_HERMES_NATIVE
    ]
    proof = {
        "matrix_has_required_fields": all(
            all(key in item for key in ("capability", "owner", "class", "default_action", "config_seam", "proof_command", "side_effect_risk"))
            for item in matrix
        ),
        "required_capabilities_enable_and_verify": all(
            item["default_action"] in {ENABLE_AND_VERIFY, ENABLE_PENDING_RUNTIME_PROOF}
            for item in matrix
            if item["class"].startswith("required_")
        ),
        "side_effectful_default_not_enabled": default_plan.get("side_effectful_tools_enabled_by_default") is False
        and all(item["default_action"] == EXPLICIT_OPT_IN_REQUIRED for item in side_effectful),
        "default_install_adds_kanban_toolset": "kanban" in root_toolsets
        and "kanban" in platform_toolsets,
        "missing_root_toolsets_preserves_native_default": "kanban" in empty_root_toolsets
        and "hermes-cli" in empty_root_toolsets
        and empty_manifest["patch_result"]["kanban_toolset_hygiene"]["root_default_toolset_preserved"] is True,
        "missing_discord_platform_preserves_native_default": "kanban" in empty_discord_toolsets
        and "hermes-discord" in empty_discord_toolsets
        and empty_manifest["patch_result"]["kanban_toolset_hygiene"]["discord_default_toolset_preserved"] is True,
        "existing_toolsets_preserved": "hermes-cli" in root_toolsets and "memory" in platform_toolsets,
        "default_kanban_pending_proof_does_not_certify_workers": default_plan["status"] == "pass"
        and default_plan["kanban"]["enabled_by_default"] is True
        and default_plan["kanban"]["status"] == "default_enabled_pending_runtime_proof",
        "kanban_with_tool_surface_proof_is_runtime_proofed": proofed_kanban["status"] == "pass"
        and proofed_kanban["kanban"]["status"] == "default_enabled_runtime_proofed"
        and proofed_kanban["side_effectful_tools_enabled_by_default"] is False,
        "optional_failures_not_health_failures": default_plan["optional_failures_are_health_failures"] is False,
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "issues": issues,
        "proof": proof,
        "capability_count": len(matrix),
        "default_summary": summarize_enablement_plan(default_plan),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify wizard capability enablement matrix.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
