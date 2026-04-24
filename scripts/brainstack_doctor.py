#!/usr/bin/env python3
"""Validate a Brainstack installation inside a Hermes checkout.

The doctor is intentionally explicit and fail-closed. It should tell an
operator whether Brainstack is installed in the Hermes checkout that will
actually run, whether Hermes native builtin memory and user profile remain
enabled alongside Brainstack, and whether the Docker/desktop launcher is aimed
at gateway mode rather than terminal chat.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_PLUGIN_FILES = [
    "__init__.py",
    "behavior_policy.py",
    "output_contract.py",
    "operating_context.py",
    "operating_truth.py",
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


def _default_compose_service(compose_path: Path) -> str | None:
    text = _read(compose_path)
    in_services = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped == "services:":
            in_services = True
            continue
        if in_services:
            if not stripped:
                continue
            if not raw_line.startswith("  "):
                break
            if raw_line.startswith("  ") and not raw_line.startswith("    ") and stripped.endswith(":"):
                return stripped[:-1]
    return None


def _default_container_name(compose_path: Path, *, service: str | None = None) -> str | None:
    text = _read(compose_path)
    resolved_service = service or _default_compose_service(compose_path)
    if not resolved_service:
        return None
    in_service = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if raw_line.startswith("  ") and not raw_line.startswith("    ") and stripped == f"{resolved_service}:":
            in_service = True
            continue
        if in_service:
            if not stripped:
                continue
            if not raw_line.startswith("    "):
                break
            if stripped.startswith("container_name:"):
                return stripped.split(":", 1)[1].strip().strip("'\"")
    return None


def _load_docker_runtime_yaml(compose_path: Path, *, service: str | None = None, container_path: str = "/opt/data/config.yaml") -> dict[str, Any]:
    resolved_service = service or _default_compose_service(compose_path)
    if not resolved_service:
        return {}
    try:
        proc = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(compose_path),
                "exec",
                "-T",
                resolved_service,
                "python3",
                "-c",
                (
                    "from pathlib import Path; "
                    f"path = Path({container_path!r}); "
                    "print(path.read_text(encoding='utf-8')) if path.exists() else None"
                ),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except Exception:
        return {}

    if proc.returncode != 0 or not proc.stdout.strip():
        return {}

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(proc.stdout) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _discover_agent_configs(target: Path) -> list[Path]:
    candidates: list[Path] = []
    root_config = target / "config.yaml"
    if root_config.exists():
        candidates.append(root_config)
    hermes_config_root = target / "hermes-config"
    if hermes_config_root.exists():
        for config_path in sorted(hermes_config_root.glob("*/config.yaml")):
            if config_path.is_file():
                candidates.append(config_path)
    return candidates


def _default_config_path(target: Path) -> Path | None:
    candidates = _discover_agent_configs(target)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _default_compose_path(target: Path, config_path: Path | None = None) -> Path | None:
    candidates: list[Path] = []
    root_compose = target / "docker-compose.yml"
    if root_compose.exists():
        candidates.append(root_compose)
    for compose_path in sorted(target.glob("docker-compose*.yml")):
        if compose_path.exists() and compose_path not in candidates:
            candidates.append(compose_path)

    if config_path:
        try:
            rel = config_path.relative_to(target / "hermes-config")
        except ValueError:
            rel = None
        if rel and len(rel.parts) >= 2:
            agent_compose = target / f"docker-compose.{rel.parts[0]}.yml"
            if agent_compose.exists():
                return agent_compose
        if root_compose.exists():
            return root_compose

    if len(candidates) == 1:
        return candidates[0]
    return None


def _default_target_python(target: Path) -> Path | None:
    candidates = [
        target / ".venv" / "bin" / "python",
        target / "venv" / "bin" / "python",
        target / ".venv" / "Scripts" / "python.exe",
        target / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


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


def _has_private_recall_wrapper(memory_manager: str) -> bool:
    legacy_private_instruction = (
        "Apply it silently in your reply." in memory_manager
        and "unless the user explicitly asks about memory behavior or debugging" in memory_manager
    )
    fenced_context_wrapper = (
        "<memory-context>" in memory_manager
        and "NOT new user input" in memory_manager
        and "sanitize_context" in memory_manager
    )
    return legacy_private_instruction or fenced_context_wrapper


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

    if _has_private_recall_wrapper(memory_manager):
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

    if (
        "def is_brainstack_only_mode" in brainstack_mode
        and "return False" in brainstack_mode
        and "return list(tool_defs or [])" in brainstack_mode
    ):
        checks.append(Check("brainstack_only_helper", "pass", "Legacy host helper is present only as a no-op compatibility shim"))
    elif "LEGACY_MEMORY_TOOL_NAMES" in brainstack_mode and "is_brainstack_only_mode" in brainstack_mode:
        checks.append(Check("brainstack_only_helper", "warn", "Legacy Brainstack-only host helper is still present; phase-52 installs no longer require it"))
    else:
        checks.append(Check("brainstack_only_helper", "pass", "No Brainstack-only host helper is required for native-seam mode"))

    if "apply_brainstack_output_validation(" in run_agent:
        checks.append(Check("final_output_validation", "warn", "run_agent still routes final answers through a Brainstack-specific output gate"))
    else:
        checks.append(Check("final_output_validation", "pass", "No Brainstack-specific host reply gate detected"))

    if "self._memory_manager.on_memory_write(" in run_agent:
        checks.append(Check("native_profile_write_bridge", "pass", "run_agent bridges Hermes native explicit writes into external memory providers"))
    else:
        checks.append(Check("native_profile_write_bridge", "fail", "run_agent does not bridge Hermes native explicit writes into external memory providers"))

    if "filter_legacy_memory_tool_defs" in run_agent and "LEGACY_MEMORY_TOOL_NAMES" in run_agent:
        checks.append(Check("legacy_tool_surface_gate", "warn", "Legacy Brainstack-only tool gating is still present in run_agent"))
    else:
        checks.append(Check("legacy_tool_surface_gate", "pass", "No Brainstack-only legacy tool gate is required"))

    if "Brainstack owns personal memory in this mode." in run_agent:
        checks.append(Check("personal_memory_guidance", "warn", "run_agent still contains Brainstack-only personal-memory guidance"))
    else:
        checks.append(Check("personal_memory_guidance", "pass", "run_agent is not injecting Brainstack-only personal-memory guidance"))

    legacy_brainstack_boundary = "_async_finalize_session_memory" in gateway_run and "_finalize_brainstack_session_memory" in gateway_run
    upstream_boundary = (
        "on_session_finalize" in gateway_run
        and "session:end" in gateway_run
        and "self._memory_manager.on_session_end(" in run_agent
    )
    if legacy_brainstack_boundary:
        checks.append(Check("gateway_session_boundary_gate", "pass", "gateway routes session boundaries through a Brainstack-aware finalizer"))
    elif upstream_boundary:
        checks.append(Check("gateway_session_boundary_gate", "pass", "gateway and run_agent use upstream session-finalize and provider on_session_end hooks; no Brainstack-specific finalizer is required"))
    else:
        checks.append(Check("gateway_session_boundary_gate", "warn", "Gateway session boundaries do not show either the legacy Brainstack finalizer or the upstream provider-finalize path"))

    legacy_ready_flow = "_ensure_background_slash_sync" in discord_platform and "adapter_self._ensure_background_slash_sync()" in discord_platform
    modern_ready_flow = (
        "self._post_connect_task: Optional[asyncio.Task] = None" in discord_platform
        and "async def _run_post_connect_initialization(self) -> None:" in discord_platform
        and "adapter_self._ready_event.set()" in discord_platform
        and "adapter_self._post_connect_task = asyncio.create_task(" in discord_platform
    )
    if legacy_ready_flow or modern_ready_flow:
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
        "assert hasattr(p, 'behavior_policy_snapshot'); "
        "assert hasattr(p, 'behavior_policy_trace'); "
        "assert hasattr(p, 'memory_operation_trace'); "
        "assert hasattr(p, 'operating_context_snapshot'); "
        "assert hasattr(p, 'operating_context_trace'); "
        "assert hasattr(p, 'apply_behavior_policy_correction'); "
        "assert hasattr(p, 'validate_assistant_output'); "
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


def _check_config(
    config_path: Path,
    planned_install: bool,
    *,
    python_bin: Path | None,
    runtime: str,
    compose_path: Path | None,
) -> list[Check]:
    checks: list[Check] = []
    config: dict[str, Any] = {}
    loaded_from = str(config_path)

    def dependency_import_ok(module_name: str) -> bool | None:
        if runtime == "docker" and compose_path and not planned_install:
            return _docker_python_can_import(module_name, compose_path)
        return _python_can_import(module_name, python_bin)

    def runtime_db_hygiene_checks() -> list[Check]:
        runtime_root = config_path.parent
        db_path = runtime_root / "brainstack" / "brainstack.db"
        if not db_path.exists():
            status = "pass" if planned_install else "warn"
            return [
                Check(
                    "runtime_brainstack_db_present",
                    status,
                    f"Runtime Brainstack DB is not present yet at {db_path}",
                )
            ]

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
        except Exception as exc:
            status = "pass" if planned_install else "fail"
            return [
                Check(
                    "runtime_brainstack_db_present",
                    status,
                    f"Runtime Brainstack DB is not readable at {db_path}: {exc}",
                )
            ]

        try:
            checks_out = [
                Check("runtime_brainstack_db_present", "pass", f"Runtime Brainstack DB is readable at {db_path}")
            ]
            interrupt_hits = int(
                conn.execute(
                    """
                    SELECT count(*)
                    FROM transcript_entries
                    WHERE content LIKE '%Assistant: Operation interrupted:%'
                       OR content LIKE '%Assistant: Session reset.%'
                    """
                ).fetchone()[0]
            )
            if interrupt_hits == 0:
                checks_out.append(
                    Check("runtime_transcript_hygiene", "pass", "Runtime transcript store has no internal assistant status residue")
                )
            else:
                checks_out.append(
                    Check(
                        "runtime_transcript_hygiene",
                        "fail",
                        f"Runtime transcript store contains {interrupt_hits} internal assistant status rows",
                    )
                )

            style_contract_rows = int(
                conn.execute(
                    "SELECT count(*) FROM behavior_contracts WHERE stable_key = ?",
                    ("preference:style_contract",),
                ).fetchone()[0]
            )
            if style_contract_rows == 0:
                checks_out.append(
                    Check("runtime_style_contract_behavior_residue", "pass", "No style-contract behavior rows remain in runtime DB")
                )
            else:
                checks_out.append(
                    Check(
                        "runtime_style_contract_behavior_residue",
                        "fail",
                        f"Runtime DB still contains {style_contract_rows} style-contract behavior rows",
                    )
                )

            compiled_policy_rows = int(
                conn.execute("SELECT count(*) FROM compiled_behavior_policies").fetchone()[0]
            )
            if compiled_policy_rows == 0:
                checks_out.append(
                    Check("runtime_compiled_behavior_policies", "pass", "No compiled behavior policies remain in runtime DB")
                )
            else:
                checks_out.append(
                    Check(
                        "runtime_compiled_behavior_policies",
                        "fail",
                        f"Runtime DB still contains {compiled_policy_rows} compiled behavior policies",
                    )
                )
            return checks_out
        except sqlite3.Error as exc:
            status = "pass" if planned_install else "fail"
            return [
                Check(
                    "runtime_brainstack_db_present",
                    status,
                    f"Runtime Brainstack DB query failed at {db_path}: {exc}",
                )
            ]
        finally:
            conn.close()

    if config_path.exists():
        config = _load_yaml(config_path)
    elif runtime == "docker" and compose_path and compose_path.exists():
        config = _load_docker_runtime_yaml(compose_path)
        if config:
            loaded_from = "docker runtime /opt/data/config.yaml"

    if not config:
        status = "pass" if planned_install else "fail"
        checks.append(Check("config_present", status, f"Config path is not readable: {config_path}"))
        return checks

    checks.append(Check("config_present", "pass", f"Config loaded from {loaded_from}"))
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

    if memory_enabled is True and user_profile_enabled is True:
        checks.append(Check("native_memory_enabled", "pass", "Hermes builtin memory and user profile are enabled"))
    elif planned_install:
        checks.append(Check("native_memory_enabled", "pass", "Builtin memory flags are not both true yet, but installer will patch them"))
    else:
        checks.append(Check("native_memory_enabled", "fail", "memory_enabled and user_profile_enabled must both be true"))

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
        dependency_state = dependency_import_ok("kuzu")
        if dependency_state is True:
            checks.append(Check("graph_backend_dependency", "pass", "Python kuzu package is importable"))
        elif dependency_state is None:
            checks.append(
                Check(
                    "graph_backend_dependency",
                    "warn",
                    "Could not verify Python kuzu package importability from this exec surface because Docker API access is unavailable",
                )
            )
        elif planned_install:
            checks.append(Check("graph_backend_dependency", "pass", "Python kuzu package is not present yet, but installer will add it"))
        else:
            checks.append(Check("graph_backend_dependency", "fail", "Python kuzu package is missing for graph_backend='kuzu' in the active runtime"))
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
        dependency_state = dependency_import_ok("chromadb")
        if dependency_state is True:
            checks.append(Check("corpus_backend_dependency", "pass", "Python chromadb package is importable"))
        elif dependency_state is None:
            checks.append(
                Check(
                    "corpus_backend_dependency",
                    "warn",
                    "Could not verify Python chromadb package importability from this exec surface because Docker API access is unavailable",
                )
            )
        elif planned_install:
            checks.append(Check("corpus_backend_dependency", "pass", "Python chromadb package is not present yet, but installer will add it"))
        else:
            checks.append(Check("corpus_backend_dependency", "fail", "Python chromadb package is missing for corpus_backend='chroma' in the active runtime"))
    elif planned_install:
        checks.append(Check("corpus_backend_target", "pass", "corpus backend is not Chroma yet, but installer will set it"))
    else:
        checks.append(Check("corpus_backend_target", "fail", f"plugins.brainstack.corpus_backend is {corpus_backend!r}, expected 'chroma'"))

    dependency_state = dependency_import_ok("openai")
    if dependency_state is True:
        checks.append(Check("route_hint_dependency", "pass", "Python openai package is importable for Brainstack route-hint LLM calls"))
    elif dependency_state is None:
        checks.append(
            Check(
                "route_hint_dependency",
                "warn",
                "Could not verify Python openai package importability from this exec surface because Docker API access is unavailable",
            )
        )
    elif planned_install:
        checks.append(Check("route_hint_dependency", "pass", "Python openai package is not present yet, but installer will add it"))
    else:
        checks.append(Check("route_hint_dependency", "fail", "Python openai package is missing for Brainstack route-hint LLM calls in the active runtime"))

    dependency_state = dependency_import_ok("croniter")
    if dependency_state is True:
        checks.append(Check("cron_dependency", "pass", "Python croniter package is importable for cron-expression scheduling"))
    elif dependency_state is None:
        checks.append(
            Check(
                "cron_dependency",
                "warn",
                "Could not verify Python croniter package importability from this exec surface because Docker API access is unavailable",
            )
        )
    elif planned_install:
        checks.append(Check("cron_dependency", "pass", "Python croniter package is not present yet, but installer will add it"))
    else:
        checks.append(Check("cron_dependency", "fail", "Python croniter package is missing for cron-expression scheduling in the active runtime"))

    auxiliary = config.get("auxiliary", {}) if isinstance(config.get("auxiliary", {}), dict) else {}
    flush_memories = auxiliary.get("flush_memories", {}) if isinstance(auxiliary.get("flush_memories", {}), dict) else {}
    flush_provider = str(flush_memories.get("provider") or "").strip().lower()
    if flush_provider == "main":
        checks.append(Check("flush_memories_provider", "pass", "auxiliary.flush_memories.provider uses the main agent provider"))
    elif planned_install:
        checks.append(Check("flush_memories_provider", "pass", "auxiliary.flush_memories.provider is not 'main' yet, but installer will patch it"))
    else:
        checks.append(Check("flush_memories_provider", "fail", "auxiliary.flush_memories.provider must be 'main' for reliable Brainstack Tier-2 writes"))

    checks.extend(runtime_db_hygiene_checks())
    return checks


def _python_can_import(module_name: str, python_bin: Path | None) -> bool:
    if python_bin is None:
        try:
            importlib.import_module(module_name)
            return True
        except Exception:
            return False
    try:
        proc = subprocess.run(
            [
                str(python_bin),
                "-c",
                (
                    "import importlib.util, sys; "
                    f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
                ),
            ],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _docker_python_can_import(module_name: str, compose_path: Path | None, *, service: str | None = None) -> bool | None:
    if compose_path is None or not compose_path.exists():
        return False
    resolved_service = service or _default_compose_service(compose_path)
    if not resolved_service:
        return False
    probe = (
        "import importlib.util, sys; "
        f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
    )
    python_commands = [
        "/opt/hermes/.venv/bin/python3",
        "/opt/hermes/.venv/bin/python",
        "python3",
    ]
    container_name = _default_container_name(compose_path, service=resolved_service)
    commands: list[list[str]] = []
    if container_name:
        for python_cmd in python_commands:
            commands.append(["docker", "exec", container_name, python_cmd, "-c", probe])
    for python_cmd in python_commands:
        commands.append(
            [
                "docker",
                "compose",
                "-f",
                str(compose_path),
                "exec",
                "-T",
                resolved_service,
                python_cmd,
                "-c",
                probe,
            ]
        )
    docker_api_unavailable = False
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if proc.returncode == 0:
                return True
            stderr = f"{proc.stderr}\n{proc.stdout}".casefold()
            if (
                "permission denied while trying to connect to the docker api" in stderr
                or "cannot connect to the docker daemon" in stderr
                or "error while dialing dial unix /var/run/docker.sock" in stderr
            ):
                docker_api_unavailable = True
        except Exception:
            continue
    if docker_api_unavailable:
        return None
    return False


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
    if "HERMES_UID" in text and "HERMES_GID" in text:
        checks.append(Check("docker_runtime_identity", "pass", "Docker compose maps Hermes runtime identity to host-configurable UID/GID"))
    elif planned_install:
        checks.append(Check("docker_runtime_identity", "pass", "Docker compose runtime identity mapping will be patched by installer"))
    else:
        checks.append(Check("docker_runtime_identity", "warn", "Docker compose lacks explicit Hermes UID/GID mapping"))
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
    dockerignore = target / ".dockerignore"
    dockerignore_text = _read(dockerignore)
    if "hermes-config/" in dockerignore_text and "runtime/" in dockerignore_text:
        checks.append(Check("dockerignore_runtime_excludes", "pass", "Docker build context excludes runtime state"))
    elif planned_install:
        checks.append(Check("dockerignore_runtime_excludes", "pass", "Installer will patch .dockerignore to exclude runtime state"))
    else:
        checks.append(Check("dockerignore_runtime_excludes", "warn", "Runtime state is still visible to Docker build context"))
    entrypoint = target / "docker" / "entrypoint.sh"
    entrypoint_text = _read(entrypoint)
    if "fix_critical_runtime_ownership" in entrypoint_text:
        checks.append(Check("docker_runtime_ownership_fix", "pass", "Docker entrypoint normalizes critical runtime ownership"))
    elif planned_install:
        checks.append(Check("docker_runtime_ownership_fix", "pass", "Installer will patch Docker entrypoint ownership normalization"))
    else:
        checks.append(Check("docker_runtime_ownership_fix", "warn", "Docker entrypoint lacks Brainstack runtime ownership normalization"))
    return checks


def run_doctor(args: argparse.Namespace) -> tuple[int, list[Check]]:
    target = Path(args.target).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve() if args.config else _default_config_path(target)
    compose_path: Path | None = None
    if args.compose_file:
        compose_path = Path(args.compose_file).expanduser().resolve()
    elif args.runtime != "local":
        try:
            compose_path = _default_compose_path(target, config_path)
        except RuntimeError:
            compose_path = None
    launcher = Path(args.desktop_launcher).expanduser().resolve() if args.desktop_launcher else _default_desktop_launcher(target)
    python_bin = Path(args.python).expanduser() if args.python else _default_target_python(target)
    runtime = _infer_runtime(target, args.runtime, compose_path, launcher)

    checks: list[Check] = []
    checks.append(Check("runtime_mode", "pass", f"Doctor running in {runtime} mode"))
    if python_bin is not None:
        checks.append(Check("python_target", "pass", f"Dependency checks use {python_bin}"))
    else:
        checks.append(Check("python_target", "warn", "No target Python detected; dependency checks fall back to the current interpreter"))
    checks.extend(_check_target_shape(target))
    checks.extend(_check_host_surfaces(target))
    checks.extend(_check_plugin(target, planned_install=args.planned_install))
    if config_path is None:
        checks.append(Check("config_path", "fail", "Could not uniquely resolve a Hermes agent config; pass --config explicitly"))
    else:
        checks.append(Check("config_path", "pass", f"Using config path: {config_path}"))
        checks.extend(
            _check_config(
                config_path,
                planned_install=args.planned_install,
                python_bin=python_bin,
                runtime=runtime,
                compose_path=compose_path,
            )
        )
    if runtime == "docker" and args.check_docker:
        if compose_path is None:
            checks.append(Check("docker_compose", "fail", "Could not uniquely resolve a Docker compose file; pass --compose-file explicitly"))
        else:
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
    parser.add_argument("--python", help="Target Hermes Python interpreter for dependency checks")
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
