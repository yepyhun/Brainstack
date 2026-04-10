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


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Update upstream Hermes and re-apply Brainstack.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument("--pull", action="store_true", help="Run git pull --ff-only in the target Hermes checkout first")
    parser.add_argument("--reinstall", action="store_true", help="Reinstall Brainstack payload and config")
    parser.add_argument("--doctor", action="store_true", help="Run doctor checks")
    parser.add_argument("--docker-rebuild", action="store_true", help="Run docker compose build after install")
    parser.add_argument("--compose-file", type=Path, help="Docker compose file")
    parser.add_argument("--desktop-launcher", type=Path, help="Desktop launcher path")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2

    if args.pull:
        _run(["git", "pull", "--ff-only"], cwd=target)

    if args.reinstall or args.doctor:
        install_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "install_into_hermes.py"),
            str(target),
            "--enable",
            "--runtime",
            args.runtime,
        ]
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
        compose_file = args.compose_file or (target / "docker-compose.bestie.yml")
        _run(["docker", "compose", "-f", str(compose_file), "build", "hermes-bestie"], cwd=target)

    print("Brainstack update workflow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
