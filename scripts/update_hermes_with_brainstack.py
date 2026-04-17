#!/usr/bin/env python3
"""Refresh a Hermes checkout and re-apply Brainstack.

This is a small orchestration wrapper around git pull, the Brainstack
installer, doctor checks, and optional Docker rebuild. It is intentionally
conservative: every external command must succeed or the update stops.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from scripts.install_into_hermes import _default_compose_path, _default_config_path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


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
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2
    config_path = args.config.expanduser().resolve() if args.config else _default_config_path(target)

    if args.pull:
        _run(["git", "pull", "--ff-only"], cwd=target)

    if args.reinstall or args.doctor:
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
        if args.doctor:
            install_cmd.append("--doctor")
        if args.compose_file:
            install_cmd.extend(["--compose-file", str(args.compose_file)])
        if args.desktop_launcher:
            install_cmd.extend(["--desktop-launcher", str(args.desktop_launcher)])
        _run(install_cmd)

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
