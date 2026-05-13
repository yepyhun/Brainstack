#!/usr/bin/env python3
"""Refresh a Hermes checkout and re-apply Brainstack.

This is a small orchestration wrapper around git pull, the Brainstack
installer, doctor checks, and optional Docker rebuild. It is intentionally
conservative: every external command must succeed or the update stops.
"""

from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.install_into_hermes import _default_compose_path, _default_config_path  # noqa: E402

PRESERVED_HERMES_RUNTIME_OVERRIDE_KEYS: tuple[str, ...] = (
    "compression",
    "discord",
    "proactive_mode",
    "proactive_kill_switch",
)


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    import yaml  # type: ignore[import-untyped]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(data), default_flow_style=False, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )


def _snapshot_runtime_overrides(
    config_path: Path,
    *,
    keys: tuple[str, ...] = PRESERVED_HERMES_RUNTIME_OVERRIDE_KEYS,
) -> dict[str, Any]:
    data = _load_yaml(config_path)
    return {key: copy.deepcopy(data[key]) for key in keys if key in data}


def _restore_runtime_overrides(
    config_path: Path,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    if not snapshot:
        return {"status": "skipped", "restored_keys": []}
    data = _load_yaml(config_path)
    restored_keys: list[str] = []
    for key, value in snapshot.items():
        if data.get(key) != value:
            data[str(key)] = copy.deepcopy(value)
            restored_keys.append(str(key))
    if restored_keys:
        _write_yaml(config_path, data)
    return {"status": "restored" if restored_keys else "unchanged", "restored_keys": sorted(restored_keys)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Update upstream Hermes and re-apply Brainstack.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--config", type=Path, help="Path to target Hermes agent config.yaml")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument("--python", type=Path, help="Target Hermes Python interpreter for dependency install and doctor checks")
    parser.add_argument("--pull", action="store_true", help="Run git pull --ff-only in the target Hermes checkout first")
    parser.add_argument("--reinstall", action="store_true", help="Reinstall Brainstack payload and config")
    parser.add_argument("--doctor", action="store_true", help="Run doctor checks")
    parser.add_argument("--skip-deps", action="store_true", help="Skip installing missing backend dependencies into the target Hermes Python")
    parser.add_argument("--docker-rebuild", action="store_true", help="Run docker compose build after install")
    parser.add_argument("--compose-file", type=Path, help="Docker compose file")
    parser.add_argument("--compose-service", help="Optional compose service name for targeted rebuilds")
    parser.add_argument("--desktop-launcher", type=Path, help="Desktop launcher path")
    parser.add_argument(
        "--no-preserve-runtime-overrides",
        action="store_true",
        help="Do not restore Hermes runtime overrides such as compression, discord, and proactive mode after update/install",
    )
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2
    config_path = args.config.expanduser().resolve() if args.config else _default_config_path(target)
    if config_path is None:
        print("FAIL could not resolve target Hermes config.yaml; pass --config explicitly", file=sys.stderr)
        return 2

    runtime_override_snapshot: dict[str, Any] = {}
    if not args.no_preserve_runtime_overrides:
        runtime_override_snapshot = _snapshot_runtime_overrides(config_path)

    def restore_runtime_overrides(stage: str) -> None:
        if args.no_preserve_runtime_overrides:
            return
        result = _restore_runtime_overrides(config_path, runtime_override_snapshot)
        if result["restored_keys"]:
            print(f"Preserved Hermes runtime overrides after {stage}: {', '.join(result['restored_keys'])}")

    if args.pull:
        _run(["git", "pull", "--ff-only"], cwd=target)
        restore_runtime_overrides("git pull")

    if args.reinstall:
        install_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "install_into_hermes.py"),
            str(target),
            "--enable",
            "--config",
            str(config_path),
            "--runtime",
            args.runtime,
        ]
        if args.python:
            install_cmd.extend(["--python", str(args.python)])
        if args.skip_deps:
            install_cmd.append("--skip-deps")
        if args.compose_file:
            install_cmd.extend(["--compose-file", str(args.compose_file)])
        if args.desktop_launcher:
            install_cmd.extend(["--desktop-launcher", str(args.desktop_launcher)])
        _run(install_cmd)
        restore_runtime_overrides("Brainstack reinstall")

    if args.doctor:
        doctor_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "brainstack_doctor.py"),
            str(target),
            "--config",
            str(config_path),
            "--runtime",
            args.runtime,
        ]
        if args.python:
            doctor_cmd.extend(["--python", str(args.python)])
        if args.compose_file:
            doctor_cmd.extend(["--compose-file", str(args.compose_file)])
        if args.desktop_launcher:
            doctor_cmd.extend(["--desktop-launcher", str(args.desktop_launcher)])
        _run(doctor_cmd)

    if args.docker_rebuild:
        if args.runtime == "local":
            print("FAIL --docker-rebuild cannot be used with --runtime local", file=sys.stderr)
            return 2
        compose_file = args.compose_file.expanduser().resolve() if args.compose_file else _default_compose_path(target, config_path)
        rebuild_cmd = ["docker", "compose", "-f", str(compose_file), "build"]
        if args.compose_service:
            rebuild_cmd.append(args.compose_service)
        _run(rebuild_cmd, cwd=target)

    print("Brainstack update workflow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
