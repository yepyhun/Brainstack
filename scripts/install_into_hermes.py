#!/usr/bin/env python3
"""Install Brainstack into a target Hermes checkout.

This installer copies the Brainstack provider payload and applies recognized
config changes. It avoids blind host-code patching; compatibility is verified
by ``brainstack_doctor.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLUGIN = REPO_ROOT / "brainstack"
SOURCE_RTK = REPO_ROOT / "rtk_sidecar.py"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_payload_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and not path.name.endswith(".pyc"):
            files.append(path)
    return files


def _copy_tree(src: Path, dst: Path, dry_run: bool) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    for src_file in _iter_payload_files(src):
        rel = src_file.relative_to(src)
        dst_file = dst / rel
        copied.append({"source": str(src_file.relative_to(REPO_ROOT)), "target": str(dst_file), "sha256": _hash_file(src_file)})
        if not dry_run:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
    return copied


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"Cannot parse YAML config at {path}: {exc}") from exc


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml
    except Exception as exc:
        raise RuntimeError("PyYAML is required to patch Hermes config.yaml") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _default_config_path(target: Path) -> Path:
    bestie = target / "hermes-config" / "bestie" / "config.yaml"
    if bestie.exists():
        return bestie
    return target / "config.yaml"


def _patch_config(config_path: Path, dry_run: bool) -> dict[str, Any]:
    config = _load_yaml(config_path)
    config.setdefault("memory", {})
    if not isinstance(config["memory"], dict):
        raise RuntimeError("config.yaml has non-object `memory` section")
    config["memory"]["provider"] = "brainstack"
    config["memory"]["memory_enabled"] = False
    config["memory"]["user_profile_enabled"] = False
    config.setdefault("plugins", {})
    if not isinstance(config["plugins"], dict):
        raise RuntimeError("config.yaml has non-object `plugins` section")
    brainstack = config["plugins"].setdefault("brainstack", {})
    if not isinstance(brainstack, dict):
        brainstack = {}
        config["plugins"]["brainstack"] = brainstack
    brainstack.setdefault("db_path", "$HERMES_HOME/brainstack/brainstack.db")
    brainstack.setdefault("profile_prompt_limit", 6)
    brainstack.setdefault("profile_match_limit", 4)
    brainstack.setdefault("continuity_recent_limit", 4)
    brainstack.setdefault("continuity_match_limit", 4)
    brainstack.setdefault("transcript_match_limit", 1)
    brainstack.setdefault("transcript_char_budget", 280)
    brainstack.setdefault("graph_match_limit", 6)
    brainstack.setdefault("corpus_match_limit", 4)
    brainstack.setdefault("corpus_char_budget", 700)
    if not dry_run:
        _write_yaml(config_path, config)
    return {
        "config_path": str(config_path),
        "memory_provider": "brainstack",
        "memory_enabled": False,
        "user_profile_enabled": False,
    }


def _write_manifest(target: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path = target / ".brainstack-install-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_docker_start_script(target: Path, dry_run: bool) -> Path:
    script_path = target / "scripts" / "hermes-brainstack-start.sh"
    legacy_path = target / "scripts" / "brainstack-start.sh"
    content = """#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

if [ -f "$REPO_ROOT/docker-compose.bestie.yml" ]; then
  COMPOSE_FILE="$REPO_ROOT/docker-compose.bestie.yml"
else
  COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
fi

SERVICE=""
if grep -q '^  hermes-bestie:' "$COMPOSE_FILE" 2>/dev/null; then
  SERVICE="hermes-bestie"
fi

dc() {
  if [ -n "$SERVICE" ]; then
    docker compose -f "$COMPOSE_FILE" "$@" "$SERVICE"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

ACTION="${1:-start}"

case "$ACTION" in
  start)
    dc up -d
    ;;
  rebuild)
    dc up -d --build
    ;;
  full|full-rebuild)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull "$SERVICE"
      docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull
      docker compose -f "$COMPOSE_FILE" up -d
    fi
    ;;
  stop)
    dc stop
    ;;
  status)
    docker compose -f "$COMPOSE_FILE" ps
    ;;
  logs)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f
    fi
    ;;
  *)
    echo "Usage: $0 [start|rebuild|full|stop|status|logs]" >&2
    exit 1
    ;;
esac
"""
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
        if legacy_path.exists():
            legacy_path.unlink()
    return script_path


def _run_doctor(target: Path, args: argparse.Namespace, planned_install: bool) -> int:
    doctor = REPO_ROOT / "scripts" / "brainstack_doctor.py"
    cmd = [
        sys.executable,
        str(doctor),
        str(target),
        "--config",
        str(args.config or _default_config_path(target)),
        "--runtime",
        args.runtime,
        "--check-docker",
        "--check-desktop-launcher",
    ]
    if planned_install:
        cmd.append("--planned-install")
    if args.compose_file:
        cmd.extend(["--compose-file", str(args.compose_file)])
    if args.desktop_launcher:
        cmd.extend(["--desktop-launcher", str(args.desktop_launcher)])
    proc = subprocess.run(cmd, text=True)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Brainstack into a target Hermes checkout.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--config", type=Path, help="Path to Hermes config.yaml")
    parser.add_argument("--compose-file", type=Path, help="Path to Docker compose file for doctor checks")
    parser.add_argument("--desktop-launcher", type=Path, help="Path to desktop launcher for doctor checks")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument("--enable", action="store_true", help="Patch config.yaml to enable Brainstack and disable builtin memory")
    parser.add_argument("--doctor", action="store_true", help="Run brainstack_doctor after install")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without changing files")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2
    if not SOURCE_PLUGIN.exists():
        print(f"FAIL Brainstack payload missing: {SOURCE_PLUGIN}", file=sys.stderr)
        return 2

    plugin_target = target / "plugins" / "memory" / "brainstack"
    files = _copy_tree(SOURCE_PLUGIN, plugin_target, args.dry_run)
    helper_files: list[dict[str, str]] = []
    if SOURCE_RTK.exists() and (target / "agent").is_dir():
        helper_target = target / "agent" / "rtk_sidecar.py"
        helper_files.append({"source": "rtk_sidecar.py", "target": str(helper_target), "sha256": _hash_file(SOURCE_RTK)})
        if not args.dry_run:
            shutil.copy2(SOURCE_RTK, helper_target)

    generated_files: list[dict[str, str]] = []
    if args.runtime == "docker":
        docker_start = _write_docker_start_script(target, args.dry_run)
        generated_files.append({"source": "generated:hermes-brainstack-start.sh", "target": str(docker_start)})

    config_result = None
    if args.enable:
        config_result = _patch_config(args.config or _default_config_path(target), args.dry_run)

    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "source_repo": str(REPO_ROOT),
        "target_hermes": str(target),
        "runtime_mode": args.runtime,
        "plugin_target": str(plugin_target),
        "files": files,
        "helper_files": helper_files,
        "generated_files": generated_files,
        "config": config_result,
        "secrets_included": False,
    }
    _write_manifest(target, manifest, args.dry_run)

    action = "DRY-RUN" if args.dry_run else "INSTALLED"
    print(f"{action} Brainstack payload files: {len(files)}")
    print(f"{action} helper files: {len(helper_files)}")
    if generated_files:
        print(f"{action} generated files: {len(generated_files)}")
    if config_result:
        print(f"{action} config: {config_result['config_path']}")
    if not args.dry_run:
        print(f"Wrote manifest: {target / '.brainstack-install-manifest.json'}")

    if args.doctor:
        return _run_doctor(target, args, planned_install=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
