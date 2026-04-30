#!/usr/bin/env python3
"""Detect and apply the Brainstack-approved Hermes Gateway patch bundle.

This is an installer boundary shim, not Brainstack runtime governance. The
patch bundle keeps a fresh upstream Hermes checkout aligned with the Gateway
contracts required for the Discord gateway while upstream PRs are pending.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = REPO_ROOT / "patches" / "hermes_gateway"
PATCH_PAYLOAD_DIR = PATCH_DIR / "files"
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
        "capability_preserving_default",
        "DISCORD_DEFAULT_CAPABILITY_PRESERVED",
        "capability_shrunk",
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
    "run_agent.py": (
        "validate_assistant_output_all",
        "validate_assistant_output",
    ),
    "agent/memory_manager.py": (
        "validate_assistant_output_all",
        "validate_assistant_output",
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


def payload_files() -> list[Path]:
    if not PATCH_PAYLOAD_DIR.exists():
        return []
    return [
        path
        for path in sorted(PATCH_PAYLOAD_DIR.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc")
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
    payloads = [
        {
            "path": str(path.relative_to(PATCH_PAYLOAD_DIR)).replace("\\", "/"),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in payload_files()
    ]
    bundle_hash = hashlib.sha256(
        json.dumps(
            {"patches": files, "payloads": payloads},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "schema": PATCH_SCHEMA,
        "patch_dir": str(PATCH_DIR),
        "payload_dir": str(PATCH_PAYLOAD_DIR),
        "bundle_sha256": bundle_hash,
        "patches": files,
        "payloads": payloads,
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


def _git_apply_reverse_check(target: Path, patch: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "-C", str(target), "apply", "--reverse", "--check", str(patch)],
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


def _copy_payload_files(target: Path, *, dry_run: bool) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    for source in payload_files():
        relative = source.relative_to(PATCH_PAYLOAD_DIR)
        destination = target / relative
        source_hash = _sha256(source)
        destination_hash = _sha256(destination) if destination.exists() else None
        if destination_hash == source_hash:
            copied.append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "status": "already_current",
                    "sha256": source_hash,
                }
            )
            continue
        existed = destination.exists()
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        copied.append(
            {
                "path": str(relative).replace("\\", "/"),
                "status": "planned" if dry_run else ("updated" if existed else "created"),
                "sha256": source_hash,
            }
        )
    return copied


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
            "copied_payloads": [],
            "rollback": "none_needed",
        }
    if dry_run:
        with tempfile.TemporaryDirectory(prefix="brainstack-gateway-patch-dry-run-") as tmp:
            probe_target = Path(tmp) / "target"
            shutil.copytree(
                target,
                probe_target,
                ignore=shutil.ignore_patterns(
                    ".git",
                    ".venv",
                    "__pycache__",
                    ".pytest_cache",
                    "node_modules",
                    "runtime",
                    "sessions",
                    "memories",
                ),
            )
            simulated = apply_gateway_patch_bundle(probe_target, dry_run=False)
            simulated["dry_run"] = True
            if simulated["status"] == "gateway_patch_payload_installed":
                simulated["status"] = "gateway_patch_planned"
            simulated["before"] = before
            simulated["rollback"] = "none_written_dry_run"
            return simulated

    if not payload_files():
        raise RuntimeError(f"Hermes Gateway patch payload is empty: {PATCH_PAYLOAD_DIR}")
    copied_payloads = _copy_payload_files(target, dry_run=False)
    after = inspect_gateway_patch_support(target)

    return {
        "schema": "brainstack.hermes_gateway_patch_apply.v1",
        "status": "gateway_patch_payload_installed",
        "dry_run": dry_run,
        "before": before,
        "after": after,
        "apply_checks": [],
        "applied_patches": [],
        "already_applied_patches": [],
        "copied_payloads": copied_payloads,
        "rollback": "git checkout -- <patched files> or reset target checkout before reinstall",
    }
