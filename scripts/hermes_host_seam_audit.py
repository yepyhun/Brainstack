#!/usr/bin/env python3
"""Read-only Hermes host seam audit for Brainstack installer decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.install_into_hermes import (
        HOST_PATCH_INVENTORY,
        _host_patch_policy,
        _memory_manager_forwards_write_metadata,
        _memory_write_signature_accepts_metadata,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from install_into_hermes import (  # type: ignore[no-redef]
        HOST_PATCH_INVENTORY,
        _host_patch_policy,
        _memory_manager_forwards_write_metadata,
        _memory_write_signature_accepts_metadata,
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _has_user_memory_provider_discovery(target: Path) -> bool:
    text = _read(target / "plugins" / "memory" / "__init__.py")
    return all(
        term in text
        for term in (
            "$HERMES_HOME/plugins",
            "_get_user_plugins_dir",
            "_is_memory_provider_dir",
            "find_provider_dir",
        )
    )


def _has_contextual_metadata_threading(target: Path) -> bool:
    text = _read(target / "run_agent.py")
    required = (
        "user_name",
        "chat_id",
        "chat_name",
        "chat_type",
        "thread_id",
        "_init_kwargs",
    )
    return all(term in text for term in required)


def _has_write_origin_metadata(target: Path) -> bool:
    text = _read(target / "run_agent.py")
    return (
        "_build_memory_write_metadata" in text
        and "_memory_write_origin" in text
        and "metadata=self._build_memory_write_metadata" in text
    )


def _has_interrupted_external_sync_guard(target: Path) -> bool:
    text = _read(target / "run_agent.py")
    return (
        "def _sync_external_memory_for_turn(" in text
        and "Interrupted turns are skipped entirely (#15218)" in text
        and "if interrupted:\n            return" in text
    )


def _plugin_dependency_install_available(target: Path) -> bool:
    """Return whether Hermes can install provider-declared runtime deps natively."""

    # Boundary probe only. Avoid importing target Hermes because this script must
    # run against arbitrary source trees without mutating them.
    text = "\n".join(
        _read(path)
        for path in (
            target / "plugins" / "memory" / "__init__.py",
            target / "hermes_cli" / "plugins.py",
            target / "cli.py",
        )
    )
    return "runtime_dependencies" in text or "install_dependencies" in text


def _docker_context_excludes_private_state(target: Path) -> bool:
    text = _read(target / ".dockerignore")
    required = ("hermes-config", "sessions", "auth.json", "brainstack")
    return all(term in text for term in required)


def _memory_provider_metadata(target: Path) -> bool:
    return _memory_write_signature_accepts_metadata(_read(target / "agent" / "memory_provider.py"))


def _memory_manager_metadata(target: Path) -> bool:
    return _memory_manager_forwards_write_metadata(_read(target / "agent" / "memory_manager.py"))


def native_seam_status(target: Path) -> dict[str, dict[str, Any]]:
    return {
        "user_memory_provider_discovery": {
            "status": "pass" if _has_user_memory_provider_discovery(target) else "missing",
            "probe": "plugins/memory/__init__.py scans $HERMES_HOME/plugins/<name>",
        },
        "contextual_metadata_threading": {
            "status": "pass" if _has_contextual_metadata_threading(target) else "missing",
            "probe": "run_agent.py threads user/chat/thread fields into provider init kwargs",
        },
        "memory_provider_write_metadata": {
            "status": "pass" if _memory_provider_metadata(target) else "missing",
            "probe": "agent/memory_provider.py on_memory_write accepts metadata",
        },
        "memory_manager_write_metadata_forwarding": {
            "status": "pass" if _memory_manager_metadata(target) else "missing",
            "probe": "agent/memory_manager.py forwards metadata to opt-in providers",
        },
        "run_agent_write_origin_metadata": {
            "status": "pass" if _has_write_origin_metadata(target) else "missing",
            "probe": "run_agent.py builds and passes structured memory write metadata",
        },
        "interrupted_external_memory_sync_guard": {
            "status": "pass" if _has_interrupted_external_sync_guard(target) else "missing",
            "probe": "run_agent.py skips external memory sync for interrupted turns",
        },
        "plugin_dependency_install": {
            "status": "pass" if _plugin_dependency_install_available(target) else "missing",
            "probe": "Hermes can install plugin-declared runtime deps without Dockerfile patch",
        },
        "docker_private_state_ignore": {
            "status": "pass" if _docker_context_excludes_private_state(target) else "missing",
            "probe": ".dockerignore excludes private runtime state and Brainstack stores",
        },
    }


def _all_pass(status: dict[str, dict[str, Any]], keys: tuple[str, ...]) -> bool:
    return all(status.get(key, {}).get("status") == "pass" for key in keys)


def patch_decision_ledger(target: Path, *, runtime_mode: str = "docker") -> list[dict[str, Any]]:
    status = native_seam_status(target)
    decisions: dict[str, tuple[str, str, tuple[str, ...]]] = {
        "_patch_run_agent": (
            "narrow",
            "latest Hermes natively provides context metadata, write-origin metadata, and interrupted-turn external sync guard; keep compat path only for older hosts",
            (
                "contextual_metadata_threading",
                "run_agent_write_origin_metadata",
                "interrupted_external_memory_sync_guard",
            ),
        ),
        "_patch_memory_provider": (
            "narrow",
            "latest Hermes MemoryProvider accepts optional metadata; keep compat path only for older hosts",
            ("memory_provider_write_metadata",),
        ),
        "_patch_memory_manager_required_seam": (
            "narrow",
            "latest Hermes MemoryManager forwards optional metadata to opt-in providers; keep compat path only for older hosts",
            ("memory_manager_write_metadata_forwarding",),
        ),
        "_patch_dockerfile_backend_dependencies": (
            "keep",
            "native plugin dependency installation is not proven for Brainstack backend deps",
            ("plugin_dependency_install",),
        ),
        "_patch_dockerignore": (
            "keep",
            "native Docker build context does not prove private Brainstack runtime/state exclusion",
            ("docker_private_state_ignore",),
        ),
        "_patch_config": (
            "keep",
            "Brainstack still owns explicit provider activation config for target runtime",
            (),
        ),
    }
    rows: list[dict[str, Any]] = []
    normalized = "docker" if runtime_mode == "docker" else "source"
    for item in HOST_PATCH_INVENTORY:
        if normalized not in tuple(item.get("runtime_modes") or ()):
            continue
        patcher = str(item["patcher"])
        policy = _host_patch_policy(patcher)
        default_decision = "remove" if policy["category"] == "legacy_host_patch" else "keep"
        default_reason = (
            "legacy host patch is not selected by core mode; retain only under explicit legacy mode "
            "until removal proof is recorded"
            if policy["category"] == "legacy_host_patch"
            else "compat hotfix is not selected by core mode; retain only as explicit compat rollback "
            "until upstream-equivalent proof allows deletion"
        )
        decision, reason, probes = decisions.get(
            patcher,
            (
                default_decision,
                default_reason,
                (),
            ),
        )
        rows.append(
            {
                "patcher": patcher,
                "target": item["target"],
                "owner": policy["owner"],
                "category": policy["category"],
                "scope": item["scope"],
                "decision": decision,
                "reason": reason,
                "contract_probes": list(probes),
                "contract_probe_status": {
                    key: status.get(key, {"status": "missing"})
                    for key in probes
                },
                "native_coverage_complete": _all_pass(status, probes) if probes else None,
            }
        )
    return rows


def build_report(target: Path, *, runtime_mode: str = "docker") -> dict[str, Any]:
    return {
        "schema": "brainstack.hermes_host_seam_audit.v1",
        "target": str(target),
        "runtime_mode": runtime_mode,
        "native_seams": native_seam_status(target),
        "patch_decisions": patch_decision_ledger(target, runtime_mode=runtime_mode),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Hermes native seams against Brainstack host patch inventory.")
    parser.add_argument("target", type=Path, help="Hermes source checkout to audit.")
    parser.add_argument("--runtime", choices=("source", "docker"), default="docker")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args()

    report = build_report(args.target.resolve(), runtime_mode=args.runtime)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for name, payload in report["native_seams"].items():
            print(f"{name}: {payload['status']} - {payload['probe']}")
        for row in report["patch_decisions"]:
            print(f"{row['patcher']}: {row['decision']} ({row['category']}) - {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
