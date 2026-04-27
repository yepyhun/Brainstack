#!/usr/bin/env python3
"""Detect and apply the Brainstack-approved Hermes Gateway patch bundle.

This is an installer boundary shim, not Brainstack runtime governance. The
patch bundle keeps a fresh upstream Hermes checkout aligned with the Gateway
contracts required by Bestie/Discord while upstream PRs are pending.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = REPO_ROOT / "patches" / "hermes_gateway"
PATCH_SCHEMA = "brainstack.hermes_gateway_patch_bundle.v1"

UPSTREAM_TRACKING = [
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16103",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16236",
        "capability": "TurnContract profiles",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16104",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16237",
        "capability": "tool profile snapshots / ToolLoader metadata",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16105",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16238",
        "capability": "context budget / proof-carrying request",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16106",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16239",
        "capability": "first-visible SLO / provider timing",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16107",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16240",
        "capability": "deterministic memory answer renderer",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16108",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16241",
        "capability": "idempotency / stale-response trace helpers",
    },
    {
        "issue": "https://github.com/NousResearch/hermes-agent/issues/16109",
        "pr": "https://github.com/NousResearch/hermes-agent/pull/16242",
        "capability": "heavy bundle / side-effect approval metadata",
    },
]

# Boundary probes only. They detect the presence of upstream-equivalent Gateway
# contracts before applying patches; they are not conversational heuristics.
REQUIRED_GATEWAY_PROBES: dict[str, tuple[str, ...]] = {
    "gateway/turn_contract.py": (
        "hermes.turn_contract.v1",
        "class TurnContract",
        "allowed_tool_profile",
        "forbidden_claims",
    ),
    "gateway/turn_profiles.py": (
        "resolve_turn_profile",
        "conversation_direct",
        "conversation_tools",
        "heavy_work",
    ),
    "gateway/tool_profile_snapshot.py": (
        "hermes.tool_profile_snapshot.v1",
        "class ToolLoaderContract",
        "side_effect_class",
        "heavy_full_debug",
    ),
    "gateway/context_budget.py": (
        "hermes.context_budget.v1",
        "compile_context_budget",
        "minimum_viable_context",
    ),
    "gateway/proof_carrying_request.py": (
        "hermes.proof_carrying_request.v1",
        "request_hash",
        "profile_snapshot_id",
    ),
    "gateway/provider_contract.py": (
        "hermes.provider_contract.v1",
        "first_user_visible_commitment_ms",
        "build_provider_timing_trace",
        "current_assignment_absence",
    ),
    "gateway/memory_answer_renderer.py": (
        "hermes.memory_answer_renderer.v1",
        "render_memory_answer",
        "current_assignment_absence",
    ),
    "gateway/run.py": (
        "resolve_turn_profile",
        "_last_turn_profile_resolution",
    ),
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_files() -> list[Path]:
    return [
        path
        for path in sorted(PATCH_DIR.glob("*.patch"))
        if not path.name.startswith("002-hermes-heartbeat-wake-lane")
    ]


def patch_bundle_manifest() -> dict[str, Any]:
    files = [
        {
            "name": path.name,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in patch_files()
    ]
    bundle_hash = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema": PATCH_SCHEMA,
        "patch_dir": str(PATCH_DIR),
        "bundle_sha256": bundle_hash,
        "patches": files,
        "upstream_tracking": UPSTREAM_TRACKING,
    }


def inspect_gateway_patch_support(target: Path) -> dict[str, Any]:
    missing: list[str] = []
    present: list[str] = []
    file_reports: list[dict[str, Any]] = []
    for relative, markers in REQUIRED_GATEWAY_PROBES.items():
        path = target / relative
        text = _read(path)
        missing_markers = [marker for marker in markers if marker not in text]
        ok = path.exists() and not missing_markers
        if ok:
            present.append(relative)
        else:
            missing.append(relative)
        file_reports.append(
            {
                "path": relative,
                "exists": path.exists(),
                "required_markers": list(markers),
                "missing_markers": missing_markers,
                "status": "pass" if ok else "missing",
            }
        )

    if not missing:
        status = "upstream_gateway_supported"
    elif not present:
        status = "gateway_patch_missing"
    else:
        status = "gateway_patch_partial"

    return {
        "schema": "brainstack.hermes_gateway_patch_status.v1",
        "status": status,
        "present_files": present,
        "missing_files": missing,
        "files": file_reports,
        "patch_bundle": patch_bundle_manifest(),
    }


def _git_apply_check(target: Path, patch: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "-C", str(target), "apply", "--check", str(patch)],
        text=True,
        capture_output=True,
        check=False,
    )
    detail = (proc.stderr or proc.stdout or "").strip()
    return proc.returncode == 0, detail


def _git_apply(target: Path, patch: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(target), "apply", str(patch)],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown git apply error").strip()
        raise RuntimeError(f"Failed to apply {patch.name}: {detail}")


def apply_gateway_patch_bundle(target: Path, *, dry_run: bool) -> dict[str, Any]:
    target = target.expanduser().resolve()
    before = inspect_gateway_patch_support(target)
    if before["status"] == "upstream_gateway_supported":
        return {
            "schema": "brainstack.hermes_gateway_patch_apply.v1",
            "status": "upstream_gateway_supported",
            "dry_run": dry_run,
            "before": before,
            "after": before,
            "applied_patches": [],
            "rollback": "none_needed",
        }
    if before["status"] == "gateway_patch_partial":
        raise RuntimeError(
            "Hermes Gateway patch state is partial; refusing silent patch. "
            f"Missing files: {', '.join(before['missing_files'])}"
        )

    patches = patch_files()
    if not patches:
        raise RuntimeError(f"Hermes Gateway patch bundle is empty: {PATCH_DIR}")

    check_results: list[dict[str, Any]] = []
    for patch in patches:
        ok, detail = _git_apply_check(target, patch)
        check_results.append({"patch": patch.name, "can_apply": ok, "detail": detail})
        if not ok:
            raise RuntimeError(f"Hermes Gateway patch check failed for {patch.name}: {detail}")

    if not dry_run:
        for patch in patches:
            _git_apply(target, patch)

    after = inspect_gateway_patch_support(target) if not dry_run else before
    if not dry_run and after["status"] != "upstream_gateway_supported":
        raise RuntimeError(f"Hermes Gateway patch did not reach supported state: {after['status']}")

    return {
        "schema": "brainstack.hermes_gateway_patch_apply.v1",
        "status": "gateway_patch_planned" if dry_run else "gateway_patch_applied",
        "dry_run": dry_run,
        "before": before,
        "after": after,
        "apply_checks": check_results,
        "applied_patches": [patch.name for patch in patches],
        "rollback": "git checkout -- <patched files> or reset target checkout before reinstall",
    }
