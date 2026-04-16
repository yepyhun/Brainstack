#!/usr/bin/env python3
"""Validate a Brainstack installation inside a Hermes checkout.

The doctor is intentionally explicit and fail-closed. It should tell an
operator whether Brainstack is installed in the Hermes checkout that will
actually run, whether Hermes builtin memory is disabled, and whether the
Docker/desktop launcher is aimed at gateway mode rather than terminal chat.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_PLUGIN_FILES = [
    "__init__.py",
    "plugin.yaml",
    "db.py",
    "corpus_backend.py",
    "corpus_backend_chroma.py",
    "graph_backend.py",
    "graph_backend_kuzu.py",
    "retrieval.py",
    "control_plane.py",
    "graph.py",
    "corpus.py",
    "transcript.py",
    "donors/registry.py",
    "donors/continuity_adapter.py",
    "donors/graph_adapter.py",
    "donors/corpus_adapter.py",
]


@dataclass
class Check:
    name: str
    status: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "message": self.message}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _default_config_path(target: Path) -> Path:
    bestie = target / "hermes-config" / "bestie" / "config.yaml"
    if bestie.exists():
        return bestie
    return target / "config.yaml"


def _default_compose_path(target: Path) -> Path:
    bestie = target / "docker-compose.bestie.yml"
    if bestie.exists():
        return bestie
    return target / "docker-compose.yml"


def _default_desktop_launcher(target: Path) -> Path | None:
    expected = str(target / "scripts" / "hermes-brainstack-start.sh")
    desktop_dir = Path.home() / "Asztal"
    preferred = desktop_dir / "Hermes-Brainstack-Start.desktop"
    if preferred.exists() and expected in _read(preferred):
        return preferred
    for candidate in sorted(desktop_dir.glob("*.desktop")):
        try:
            if expected in _read(candidate):
                return candidate
        except Exception:
            continue
    return preferred if preferred.exists() else None


def _infer_runtime(target: Path, explicit: str, compose_path: Path | None, launcher: Path | None) -> str:
    if explicit != "auto":
        return explicit
    if compose_path and compose_path.exists():
        return "docker"
    if launcher and launcher.exists() and "docker" in _read(launcher).lower():
        return "docker"
    return "local"


def _check_target_shape(target: Path) -> list[Check]:
    checks: list[Check] = []
    required = [
        "run_agent.py",
        "agent/memory_provider.py",
        "agent/memory_manager.py",
        "plugins/memory/__init__.py",
    ]
    missing = [item for item in required if not (target / item).exists()]
    if missing:
        checks.append(Check("target_shape", "fail", f"Missing Hermes files: {', '.join(missing)}"))
    else:
        checks.append(Check("target_shape", "pass", "Target looks like a Hermes checkout"))
    return checks


def _check_host_surfaces(target: Path) -> list[Check]:
    checks: list[Check] = []
    memory_provider = _read(target / "agent" / "memory_provider.py")
    memory_manager = _read(target / "agent" / "memory_manager.py")
    brainstack_mode = _read(target / "agent" / "brainstack_mode.py")
    loader = _read(target / "plugins" / "memory" / "__init__.py")
    run_agent = _read(target / "run_agent.py")
    gateway_run = _read(target / "gateway" / "run.py")
    discord_platform = _read(target / "gateway" / "platforms" / "discord.py")

    required_provider_terms = [
        "class MemoryProvider",
        "def initialize",
        "def prefetch",
        "def sync_turn",
        "def on_pre_compress",
        "def on_session_end",
    ]
    missing_provider = [term for term in required_provider_terms if term not in memory_provider]
    if missing_provider:
        checks.append(Check("provider_interface", "fail", f"Missing provider interface terms: {', '.join(missing_provider)}"))
    else:
        checks.append(Check("provider_interface", "pass", "MemoryProvider surface supports Brainstack lifecycle"))

    required_manager_terms = [
        "class MemoryManager",
        "def add_provider",
        "def prefetch_all",
        "def sync_all",
        "def on_pre_compress",
        "def on_session_end",
    ]
    missing_manager = [term for term in required_manager_terms if term not in memory_manager]
    if missing_manager:
        checks.append(Check("memory_manager_surface", "fail", f"Missing MemoryManager terms: {', '.join(missing_manager)}"))
    else:
        checks.append(Check("memory_manager_surface", "pass", "MemoryManager can load, prefetch, sync, and run lifecycle hooks"))

    if "Apply it silently in your reply." in memory_manager and "unless the user explicitly asks about memory behavior or debugging" in memory_manager:
        checks.append(Check("private_recall_wrapper", "pass", "MemoryManager wraps recalled context as private internal guidance"))
    else:
        checks.append(Check("private_recall_wrapper", "fail", "agent/memory_manager.py still exposes recalled context too weakly"))

    if "load_memory_provider" in loader and "plugins.memory." in loader:
        checks.append(Check("plugin_loader", "pass", "Hermes memory plugin loader is present"))
    else:
        checks.append(Check("plugin_loader", "fail", "Hermes memory plugin loader is missing or incompatible"))

    required_run_terms = [
        "memory.provider",
        "load_memory_provider",
        "prefetch_all",
        "sync_all",
    ]
    missing_run = [term for term in required_run_terms if term not in run_agent]
    if missing_run:
        checks.append(Check("host_runtime_wiring", "fail", f"Missing run_agent wiring terms: {', '.join(missing_run)}"))
    else:
        checks.append(Check("host_runtime_wiring", "pass", "run_agent has external memory provider wiring"))

    if "on_turn_start(" not in run_agent:
        checks.append(Check("turn_start_hook", "warn", "on_turn_start exists in provider API but is not called by this Hermes host; Brainstack can still count turns through sync_turn"))
    else:
        checks.append(Check("turn_start_hook", "pass", "run_agent calls memory provider on_turn_start"))

    if "LEGACY_MEMORY_TOOL_NAMES" in brainstack_mode and "is_brainstack_only_mode" in brainstack_mode:
        checks.append(Check("brainstack_only_helper", "pass", "Brainstack-only host helper is present"))
    else:
        checks.append(Check("brainstack_only_helper", "fail", "agent/brainstack_mode.py is missing or incomplete"))

    if "PERSONAL_MEMORY_FILE_TOOL_NAMES" in brainstack_mode and "side-memory files" in brainstack_mode:
        checks.append(Check("personal_memory_file_boundary", "pass", "Brainstack-only helper blocks Hermes side-memory file detours"))
    else:
        checks.append(Check("personal_memory_file_boundary", "fail", "agent/brainstack_mode.py does not block Hermes side-memory file detours"))

    if "filter_legacy_memory_tool_defs" in run_agent and "LEGACY_MEMORY_TOOL_NAMES" in run_agent:
        checks.append(Check("legacy_tool_surface_gate", "pass", "run_agent strips legacy memory and session_search tools in Brainstack-only mode"))
    else:
        checks.append(Check("legacy_tool_surface_gate", "fail", "run_agent does not gate legacy memory tool surface for Brainstack-only mode"))

    if "Brainstack owns personal memory in this mode." in run_agent:
        checks.append(Check("personal_memory_guidance", "pass", "run_agent injects explicit Brainstack-owned personal memory guidance"))
    else:
        checks.append(Check("personal_memory_guidance", "fail", "run_agent still lacks explicit Brainstack-owned personal memory guidance"))

    if "_async_finalize_session_memory" in gateway_run and "_finalize_brainstack_session_memory" in gateway_run:
        checks.append(Check("gateway_session_boundary_gate", "pass", "gateway routes session boundaries through a Brainstack-aware finalizer"))
    else:
        checks.append(Check("gateway_session_boundary_gate", "fail", "gateway still lacks a Brainstack-aware session boundary finalizer"))

    if "_ensure_background_slash_sync" in discord_platform and "adapter_self._ensure_background_slash_sync()" in discord_platform:
        checks.append(Check("discord_readiness_gate", "pass", "Discord readiness is decoupled from slash command sync"))
    else:
        checks.append(Check("discord_readiness_gate", "fail", "Discord startup still blocks readiness on slash command sync"))

    return checks


def _check_plugin(target: Path, planned_install: bool) -> list[Check]:
    checks: list[Check] = []
    plugin_dir = target / "plugins" / "memory" / "brainstack"
    if not plugin_dir.exists():
        status = "pass" if planned_install else "fail"
        msg = "Brainstack plugin is not present yet, but this is a planned dry-run install" if planned_install else "Brainstack plugin directory is missing"
        checks.append(Check("plugin_present", status, msg))
        return checks

    missing = [item for item in REQUIRED_PLUGIN_FILES if not (plugin_dir / item).exists()]
    if missing:
        checks.append(Check("plugin_files", "fail", f"Missing Brainstack plugin files: {', '.join(missing)}"))
    else:
        checks.append(Check("plugin_files", "pass", "Brainstack plugin payload is present"))

    env = os.environ.copy()
    env.setdefault("HERMES_HOME", str(target / ".brainstack-doctor-home"))
    code = (
        "import sys; "
        f"sys.path.insert(0, {str(target)!r}); "
        "from plugins.memory import load_memory_provider; "
        "p = load_memory_provider('brainstack'); "
        "assert p is not None, 'provider not loaded'; "
        "assert p.name == 'brainstack', p.name; "
        "assert p.is_available(); "
        "print(p.name)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(target),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
    )
    if proc.returncode == 0 and "brainstack" in proc.stdout:
        checks.append(Check("plugin_import", "pass", "Brainstack provider imports and instantiates"))
    else:
        detail = (proc.stderr or proc.stdout or "unknown import failure").strip().splitlines()[-1:]
        checks.append(Check("plugin_import", "fail", f"Brainstack provider import failed: {' '.join(detail)}"))
    return checks


def _check_config(config_path: Path, planned_install: bool) -> list[Check]:
    checks: list[Check] = []
    if not config_path.exists():
        status = "pass" if planned_install else "fail"
        checks.append(Check("config_present", status, f"Config path does not exist: {config_path}"))
        return checks

    config = _load_yaml(config_path)
    memory = config.get("memory", {}) if isinstance(config.get("memory", {}), dict) else {}
    provider = memory.get("provider")
    memory_enabled = memory.get("memory_enabled")
    user_profile_enabled = memory.get("user_profile_enabled")

    if provider == "brainstack":
        checks.append(Check("config_provider", "pass", "memory.provider is brainstack"))
    elif planned_install:
        checks.append(Check("config_provider", "pass", "memory.provider is not brainstack yet, but installer will patch it"))
    else:
        checks.append(Check("config_provider", "fail", f"memory.provider is {provider!r}, expected 'brainstack'"))

    if memory_enabled is False and user_profile_enabled is False:
        checks.append(Check("native_memory_disabled", "pass", "Hermes builtin memory and user profile are disabled"))
    elif planned_install:
        checks.append(Check("native_memory_disabled", "pass", "Builtin memory flags are not both false yet, but installer will patch them"))
    else:
        checks.append(Check("native_memory_disabled", "fail", "memory_enabled and user_profile_enabled must both be false"))

    plugins = config.get("plugins", {}) if isinstance(config.get("plugins", {}), dict) else {}
    if isinstance(plugins.get("brainstack"), dict):
        checks.append(Check("brainstack_plugin_config", "pass", "plugins.brainstack config section exists"))
    elif planned_install:
        checks.append(Check("brainstack_plugin_config", "pass", "plugins.brainstack config will be created by installer"))
    else:
        checks.append(Check("brainstack_plugin_config", "warn", "plugins.brainstack config section is absent; provider will use defaults"))

    brainstack = plugins.get("brainstack", {}) if isinstance(plugins.get("brainstack", {}), dict) else {}
    graph_backend = str(brainstack.get("graph_backend") or "kuzu").strip().lower()
    graph_db_path = str(brainstack.get("graph_db_path") or "").strip()
    corpus_backend = str(brainstack.get("corpus_backend") or "chroma").strip().lower()
    corpus_db_path = str(brainstack.get("corpus_db_path") or "").strip()

    if graph_backend == "kuzu":
        checks.append(Check("graph_backend_target", "pass", "plugins.brainstack.graph_backend targets embedded Kuzu"))
        if graph_db_path:
            checks.append(Check("graph_backend_path", "pass", "plugins.brainstack.graph_db_path is configured"))
        elif planned_install:
            checks.append(Check("graph_backend_path", "pass", "plugins.brainstack.graph_db_path will be added by installer"))
        else:
            checks.append(Check("graph_backend_path", "warn", "plugins.brainstack.graph_db_path is absent; provider defaults will be used"))
        try:
            importlib.import_module("kuzu")
            checks.append(Check("graph_backend_dependency", "pass", "Python kuzu package is importable"))
        except Exception:
            checks.append(Check("graph_backend_dependency", "fail", "Python kuzu package is missing for graph_backend='kuzu'"))
    elif planned_install:
        checks.append(Check("graph_backend_target", "pass", "graph backend is not Kuzu yet, but installer will set it"))
    else:
        checks.append(Check("graph_backend_target", "fail", f"plugins.brainstack.graph_backend is {graph_backend!r}, expected 'kuzu'"))

    if corpus_backend == "chroma":
        checks.append(Check("corpus_backend_target", "pass", "plugins.brainstack.corpus_backend targets embedded Chroma"))
        if corpus_db_path:
            checks.append(Check("corpus_backend_path", "pass", "plugins.brainstack.corpus_db_path is configured"))
        elif planned_install:
            checks.append(Check("corpus_backend_path", "pass", "plugins.brainstack.corpus_db_path will be added by installer"))
        else:
            checks.append(Check("corpus_backend_path", "warn", "plugins.brainstack.corpus_db_path is absent; provider defaults will be used"))
        try:
            importlib.import_module("chromadb")
            checks.append(Check("corpus_backend_dependency", "pass", "Python chromadb package is importable"))
        except Exception:
            checks.append(Check("corpus_backend_dependency", "fail", "Python chromadb package is missing for corpus_backend='chroma'"))
    elif planned_install:
        checks.append(Check("corpus_backend_target", "pass", "corpus backend is not Chroma yet, but installer will set it"))
    else:
        checks.append(Check("corpus_backend_target", "fail", f"plugins.brainstack.corpus_backend is {corpus_backend!r}, expected 'chroma'"))

    return checks


def _check_compose(compose_path: Path, planned_install: bool) -> list[Check]:
    checks: list[Check] = []
    if not compose_path.exists():
        checks.append(Check("docker_compose", "warn", f"Compose file not found: {compose_path}"))
        return checks
    text = _read(compose_path)
    compact = " ".join(text.replace("[", " ").replace("]", " ").replace(",", " ").split())
    if "gateway" in compact and "run" in compact and "--replace" in compact:
        checks.append(Check("docker_gateway_mode", "pass", "Docker compose starts Hermes Gateway mode"))
    else:
        checks.append(Check("docker_gateway_mode", "fail", "Docker compose does not clearly start `gateway run --replace`"))
    if "/opt/data" in text and "HERMES_HOME" in text:
        checks.append(Check("docker_hermes_home", "pass", "Docker compose mounts/configures HERMES_HOME"))
    else:
        checks.append(Check("docker_hermes_home", "warn", "Docker HERMES_HOME mapping is not obvious"))
    if "hermes-gateway-healthcheck.py" in text:
        checks.append(Check("docker_readiness_healthcheck", "pass", "Docker compose uses readiness-aware gateway healthcheck"))
    elif planned_install:
        checks.append(Check("docker_readiness_healthcheck", "pass", "Docker compose healthcheck will be patched to use readiness-aware status"))
    else:
        checks.append(Check("docker_readiness_healthcheck", "fail", "Docker compose still uses a process-only healthcheck"))
    return checks


def _check_desktop_launcher(target: Path, launcher: Path | None, runtime: str) -> list[Check]:
    checks: list[Check] = []
    if not launcher:
        checks.append(Check("desktop_launcher", "warn", f"No {runtime} desktop launcher path provided or discovered"))
        return checks
    if not launcher.exists():
        checks.append(Check("desktop_launcher", "warn", f"Desktop launcher not found: {launcher}"))
        return checks
    text = _read(launcher)
    target_str = str(target)
    if target_str in text or str(target / "scripts") in text:
        checks.append(Check("desktop_launcher_target", "pass", "Desktop launcher points at this Hermes checkout"))
    elif runtime == "docker":
        checks.append(Check("desktop_launcher_target", "fail", "Desktop launcher points at a different checkout or script"))
    else:
        checks.append(Check("desktop_launcher_target", "warn", "Desktop launcher target is not explicit; manual local start may still be valid"))

    if runtime == "docker":
        start_script = str(target / "scripts" / "hermes-brainstack-start.sh")
        if start_script in text or "docker compose" in text.lower():
            checks.append(Check("desktop_launcher_mode", "pass", "Desktop launcher uses the Docker Brainstack start path"))
        else:
            checks.append(Check("desktop_launcher_mode", "warn", "Desktop launcher mode is unclear for Docker runtime"))
    else:
        if "docker" in text.lower():
            checks.append(Check("desktop_launcher_mode", "warn", "Launcher text still looks Docker-oriented while doctor is running in local mode"))
        else:
            checks.append(Check("desktop_launcher_mode", "pass", "Local runtime mode does not require Docker launcher checks"))
    return checks


def _check_docker_helpers(target: Path, planned_install: bool) -> list[Check]:
    checks: list[Check] = []
    healthcheck = target / "scripts" / "hermes-gateway-healthcheck.py"
    if healthcheck.exists():
        checks.append(Check("docker_healthcheck_helper", "pass", "Readiness-aware gateway healthcheck helper exists"))
    elif planned_install:
        checks.append(Check("docker_healthcheck_helper", "pass", "Readiness-aware gateway healthcheck helper will be generated by installer"))
    else:
        checks.append(Check("docker_healthcheck_helper", "fail", "Missing scripts/hermes-gateway-healthcheck.py"))
    return checks


def run_doctor(args: argparse.Namespace) -> tuple[int, list[Check]]:
    target = Path(args.target).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve() if args.config else _default_config_path(target)
    compose_path = Path(args.compose_file).expanduser().resolve() if args.compose_file else _default_compose_path(target)
    launcher = Path(args.desktop_launcher).expanduser().resolve() if args.desktop_launcher else _default_desktop_launcher(target)
    runtime = _infer_runtime(target, args.runtime, compose_path, launcher)

    checks: list[Check] = []
    checks.append(Check("runtime_mode", "pass", f"Doctor running in {runtime} mode"))
    checks.extend(_check_target_shape(target))
    checks.extend(_check_host_surfaces(target))
    checks.extend(_check_plugin(target, planned_install=args.planned_install))
    checks.extend(_check_config(config_path, planned_install=args.planned_install))
    if runtime == "docker" and args.check_docker:
        checks.extend(_check_compose(compose_path, planned_install=args.planned_install))
        checks.extend(_check_docker_helpers(target, planned_install=args.planned_install))
    elif runtime == "local":
        checks.append(Check("docker_gateway_mode", "pass", "Docker gateway checks skipped in local runtime mode"))
        checks.append(Check("docker_hermes_home", "pass", "Docker HERMES_HOME mapping skipped in local runtime mode"))
    if args.check_desktop_launcher:
        checks.extend(_check_desktop_launcher(target, launcher, runtime))

    failures = [check for check in checks if check.status == "fail"]
    return (1 if failures else 0), checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Brainstack installation in a Hermes checkout.")
    parser.add_argument("target", help="Path to the target Hermes checkout")
    parser.add_argument("--config", help="Path to Hermes config.yaml")
    parser.add_argument("--compose-file", help="Path to Docker compose file")
    parser.add_argument("--desktop-launcher", help="Path to desktop launcher")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Runtime mode to validate")
    parser.add_argument("--planned-install", action="store_true", help="Treat missing Brainstack/config changes as planned dry-run actions")
    parser.add_argument("--check-docker", action="store_true", help="Validate Docker compose gateway mode")
    parser.add_argument("--check-desktop-launcher", action="store_true", help="Validate desktop launcher points at the target checkout")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args()

    code, checks = run_doctor(args)
    if args.json:
        print(json.dumps({"ok": code == 0, "checks": [check.to_dict() for check in checks]}, indent=2, ensure_ascii=False))
    else:
        for check in checks:
            marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[check.status]
            print(f"{marker} {check.name}: {check.message}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
