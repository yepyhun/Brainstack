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
import inspect
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from brainstack.background_task_binding import REQUIRED_BACKGROUND_TASK_BINDINGS  # noqa: E402
from brainstack.config_shape import validate_brainstack_config_shape  # noqa: E402

try:
    from hermes_gateway_patch_support import inspect_gateway_patch_support
except ModuleNotFoundError:  # pytest imports scripts as a namespace package
    from scripts.hermes_gateway_patch_support import inspect_gateway_patch_support


REQUIRED_PLUGIN_FILES = [
    "__init__.py",
    "behavior_policy.py",
    "output_contract.py",
    "operating_context.py",
    "operating_truth.py",
    "operating_loop.py",
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

DOCKER_RUNTIME_DEPENDENCIES = {
    "chromadb": "chromadb",
    "croniter": "croniter",
    "kuzu": "kuzu",
    "openai": "openai",
}


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
    data = _load_yaml(compose_path)
    services = data.get("services") if isinstance(data, dict) else None
    if isinstance(services, dict):
        for name, config in services.items():
            if str(name).startswith("hermes"):
                return str(name)
            if isinstance(config, dict) and str(config.get("container_name") or "").startswith("hermes"):
                return str(name)
        for name, config in services.items():
            if not isinstance(config, dict):
                continue
            raw_command = config.get("command")
            if isinstance(raw_command, list):
                command = " ".join(str(part) for part in raw_command)
            else:
                command = str(raw_command or "")
            if "gateway" in command and "run" in command:
                return str(name)
        for name in services:
            return str(name)
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


def _profile_config_candidates(target: Path, profile: str) -> list[Path]:
    profile_name = str(profile or "").strip()
    if not profile_name or "/" in profile_name or "\\" in profile_name:
        return []

    candidates = [
        target / "hermes-config" / profile_name / "config.yaml",
        target / "profiles" / profile_name / "config.yaml",
    ]
    hermes_home = os.getenv("HERMES_HOME")
    if hermes_home:
        candidates.append(Path(hermes_home).expanduser() / "profiles" / profile_name / "config.yaml")
    candidates.append(Path.home() / ".hermes" / "profiles" / profile_name / "config.yaml")

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        marker = str(candidate.expanduser())
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(candidate.expanduser())
    return unique


def _profile_config_path(target: Path, profile: str) -> Path | None:
    for candidate in _profile_config_candidates(target, profile):
        if candidate.is_file():
            return candidate.resolve()
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


def _has_brainstack_evidence_use_contract(text: str) -> bool:
    return (
        "private recalled memory context is background evidence, not new user input" in text
        and "Do not mention Brainstack blocks" in text
        and "scheduled follow-up exists only when the current evidence includes a native scheduler record" in text
        and "internal task list is not by itself a scheduled job" in text
    )


SKILL_FILE_SIZE_WARN_CHARS = 16_000


def _discover_skill_main_files(target: Path) -> list[Path]:
    roots = [
        target / "skills",
        target.parent / "skills",
    ]
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        roots.append(Path(hermes_home).expanduser() / "skills")

    seen: set[Path] = set()
    files: list[Path] = []
    for root in roots:
        try:
            resolved_root = root.resolve()
        except Exception:
            resolved_root = root
        if resolved_root in seen or not root.exists():
            continue
        seen.add(resolved_root)
        files.extend(path for path in sorted(root.glob("*/SKILL.md")) if path.is_file())
    return files


def _check_skill_policy_surfaces(target: Path, *, planned_install: bool = False) -> list[Check]:
    checks: list[Check] = []
    prompt_builder = _read(target / "agent" / "prompt_builder.py")
    skills_tool = _read(target / "tools" / "skills_tool.py")

    narrowed_prompt_policy = (
        "Load a skill only when it is directly relevant" in prompt_builder
        and "Do not reload the same skill in the same session" in prompt_builder
        and "even partially relevant" not in prompt_builder
    )
    aggressive_prompt_policy = (
        "even partially relevant" in prompt_builder
        or "Err on the side of loading" in prompt_builder
    )
    if narrowed_prompt_policy:
        checks.append(Check("hermes_skill_prompt_policy", "pass", "Hermes skill prompt uses direct-relevance loading policy"))
    elif planned_install and aggressive_prompt_policy:
        checks.append(Check("hermes_skill_prompt_policy", "pass", "Installer will narrow Hermes skill prompt loading policy"))
    elif aggressive_prompt_policy:
        checks.append(Check("hermes_skill_prompt_policy", "warn", "Hermes skill prompt still encourages weak partial-relevance skill loads"))
    else:
        checks.append(Check("hermes_skill_prompt_policy", "pass", "Hermes skill prompt does not show the old partial-relevance overload wording"))

    progressive_view = (
        "DEFAULT_SKILL_VIEW_AUTO_FULL_CHAR_LIMIT" in skills_tool
        and "def _skill_view_content_fields" in skills_tool
        and "already_loaded_in_session" in skills_tool
        and "content_hash" in skills_tool
    )
    if progressive_view:
        checks.append(Check("hermes_skill_view_progressive_disclosure", "pass", "skill_view supports progressive disclosure and unchanged-session metadata"))
    elif planned_install:
        checks.append(Check("hermes_skill_view_progressive_disclosure", "pass", "Installer will add skill_view auto/summary/full progressive disclosure"))
    else:
        checks.append(Check("hermes_skill_view_progressive_disclosure", "warn", "skill_view appears to return full SKILL.md content without cache-aware summary mode"))

    oversized: list[str] = []
    for skill_file in _discover_skill_main_files(target):
        try:
            char_count = len(skill_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if char_count > SKILL_FILE_SIZE_WARN_CHARS:
            try:
                label = str(skill_file.relative_to(skill_file.parents[1]))
            except Exception:
                label = str(skill_file)
            oversized.append(f"{label} ({char_count} chars)")

    if oversized:
        checks.append(
            Check(
                "hermes_skill_file_size_advisory",
                "warn",
                "Large SKILL.md files should be slim core/router files with references loaded only when needed: "
                + ", ".join(oversized[:8]),
            )
        )
    else:
        checks.append(Check("hermes_skill_file_size_advisory", "pass", "No oversized SKILL.md files found in discovered skill roots"))

    return checks


def _check_host_surfaces(target: Path, *, planned_install: bool = False) -> list[Check]:
    checks: list[Check] = []
    memory_provider = _read(target / "agent" / "memory_provider.py")
    memory_manager = _read(target / "agent" / "memory_manager.py")
    installed_brainstack_retrieval = _read(target / "plugins" / "memory" / "brainstack" / "retrieval.py")
    source_brainstack_retrieval = _read(Path(__file__).resolve().parents[1] / "brainstack" / "retrieval.py")
    brainstack_retrieval = installed_brainstack_retrieval or source_brainstack_retrieval
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
    elif _has_brainstack_evidence_use_contract(brainstack_retrieval):
        checks.append(Check("private_recall_wrapper", "pass", "Brainstack provider projection owns private memory evidence-use guidance"))
    else:
        checks.append(Check("private_recall_wrapper", "fail", "No host or Brainstack provider private memory evidence-use contract was detected"))

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

    upstream_interrupted_sync_guard = (
        "def _sync_external_memory_for_turn(" in run_agent
        and "Interrupted turns are skipped entirely (#15218)" in run_agent
        and "if interrupted:\n            return" in run_agent
    )
    legacy_interrupted_sync_guard = (
        "self._memory_manager and final_response and original_user_message and not interrupted" in run_agent
    )
    if upstream_interrupted_sync_guard:
        checks.append(
            Check(
                "interrupted_turn_external_memory_guard",
                "pass",
                "Hermes native seam skips external memory sync for interrupted turns (#15218/#15395)",
            )
        )
    elif legacy_interrupted_sync_guard:
        checks.append(
            Check(
                "interrupted_turn_external_memory_guard",
                "pass",
                "Legacy Brainstack host patch skips external memory sync for interrupted turns",
            )
        )
    else:
        checks.append(
            Check(
                "interrupted_turn_external_memory_guard",
                "fail",
                "run_agent can mirror interrupted turns into external memory providers",
            )
        )

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

    gateway_patch_status = inspect_gateway_patch_support(target)
    status = str(gateway_patch_status.get("status") or "unknown")
    if status == "upstream_gateway_supported":
        checks.append(Check("hermes_gateway_patch_support", "pass", "Hermes Gateway optimization support is present"))
    elif planned_install and status == "gateway_patch_missing":
        checks.append(Check("hermes_gateway_patch_support", "pass", "Installer will apply Hermes Gateway optimization patch bundle"))
    elif status == "gateway_patch_missing":
        checks.append(Check("hermes_gateway_patch_support", "fail", "Hermes Gateway optimization support is missing; run Brainstack installer with gateway patch mode enabled"))
    else:
        missing = ", ".join(gateway_patch_status.get("missing_files") or [])
        checks.append(Check("hermes_gateway_patch_support", "fail", f"Hermes Gateway patch state is partial; missing: {missing}"))

    checks.extend(_check_skill_policy_surfaces(target, planned_install=planned_install))

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
    target: Path | None = None,
) -> list[Check]:
    checks: list[Check] = []
    config: dict[str, Any] = {}
    loaded_from = str(config_path)

    def dependency_import_ok(module_name: str) -> bool | None:
        if runtime == "docker" and compose_path and not planned_install:
            docker_state = _docker_python_can_import(module_name, compose_path)
            if docker_state is True:
                return True
            if _python_can_import(module_name, python_bin) and _dockerfile_declares_runtime_dependency(
                compose_path,
                module_name,
            ):
                return True
            return docker_state
        return _python_can_import(module_name, python_bin)

    def backend_open_checks(*, backend: str, configured_path: str) -> list[Check]:
        return _backend_openability_checks(
            backend=backend,
            configured_path=configured_path,
            config_path=config_path,
            planned_install=planned_install,
            python_bin=python_bin,
            runtime=runtime,
            compose_path=compose_path,
            target=target,
        )

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
    shape_report = validate_brainstack_config_shape(config)
    if shape_report["status"] == "pass":
        checks.append(Check("brainstack_config_shape", "pass", "plugins.brainstack uses the supported flat config shape"))
    else:
        for issue in shape_report["issues"]:
            checks.append(
                Check(
                    "brainstack_config_shape",
                    "fail",
                    (
                        f"{issue['key_path']} is ignored by runtime; "
                        f"use {issue['supported_replacement']} instead"
                    ),
                )
            )
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
            checks.extend(backend_open_checks(backend="kuzu", configured_path=graph_db_path))
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
            checks.extend(backend_open_checks(backend="chroma", configured_path=corpus_db_path))
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
    elif corpus_backend in {"none", "sqlite"}:
        checks.append(
            Check(
                "corpus_backend_target",
                "pass",
                f"plugins.brainstack.corpus_backend is {corpus_backend!r}; semantic corpus backend is explicitly unavailable",
            )
        )
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
    for binding in REQUIRED_BACKGROUND_TASK_BINDINGS:
        slot = binding["hermes_task_slot"]
        task_config = auxiliary.get(slot, {}) if isinstance(auxiliary.get(slot, {}), dict) else {}
        provider = str(task_config.get("provider") or "").strip().lower()
        if provider and provider != "auto":
            checks.append(Check(f"{slot}_provider", "pass", f"auxiliary.{slot}.provider is explicitly configured"))
        elif planned_install:
            checks.append(Check(f"{slot}_provider", "pass", f"auxiliary.{slot}.provider is not explicit yet, but installer will patch it"))
        else:
            checks.append(Check(f"{slot}_provider", "fail", f"auxiliary.{slot}.provider must be explicit for Brainstack background tasks"))

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


def _dockerfile_declares_runtime_dependency(compose_path: Path | None, module_name: str) -> bool:
    if compose_path is None:
        return False
    dockerfile = compose_path.parent / "Dockerfile"
    if not dockerfile.exists():
        return False
    try:
        text = dockerfile.read_text(encoding="utf-8")
    except OSError:
        return False
    dependency = DOCKER_RUNTIME_DEPENDENCIES.get(module_name, module_name)
    return dependency in text


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


def _backend_probe_code(*, backend: str, configured_path: str, default_suffix: str) -> str:
    raw_path = configured_path or f"$HERMES_HOME/brainstack/{default_suffix}"
    if backend == "kuzu":
        open_code = "import kuzu; kuzu.Database(path)"
        skip_missing = True
    elif backend == "chroma":
        open_code = (
            "from brainstack.corpus_backend_chroma import ChromaCorpusBackend\n"
            "    backend = ChromaCorpusBackend(db_path=path)\n"
            "    backend.open()\n"
            "    payload['repair_events'] = getattr(backend, 'repair_events', [])\n"
            "    backend.close()"
        )
        skip_missing = False
    else:
        open_code = "raise RuntimeError('unsupported backend')"
        skip_missing = True
    return (
        "import json, os, sys\n"
        "from pathlib import Path\n"
        f"raw = {raw_path!r}\n"
        "path = os.path.expandvars(raw)\n"
        "exists = Path(path).exists()\n"
        "payload = {'path': path, 'exists': exists, 'openable': None, 'error': '', 'error_class': ''}\n"
        f"skip_missing = {skip_missing!r}\n"
        "if skip_missing and not exists:\n"
        "    print(json.dumps(payload)); sys.exit(0)\n"
        "try:\n"
        f"    {open_code}\n"
        "    payload['exists'] = Path(path).exists()\n"
        "    payload['openable'] = True\n"
        "except Exception as exc:\n"
        "    payload['openable'] = False\n"
        "    payload['error'] = str(exc)\n"
        "    text = str(exc).casefold()\n"
        "    if 'std::bad_alloc' in text or exc.__class__.__name__ == 'MemoryError':\n"
        "        payload['error_class'] = 'backend_open_memory_error'\n"
        "    elif 'chroma default embedding is disabled' in text:\n"
        "        payload['error_class'] = 'backend_embedding_config_missing'\n"
        "    elif 'no module named' in text or exc.__class__.__name__ == 'ModuleNotFoundError':\n"
        "        payload['error_class'] = 'backend_dependency_missing'\n"
        "    else:\n"
        "        payload['error_class'] = exc.__class__.__name__\n"
        "print(json.dumps(payload))\n"
    )


def _is_kuzu_lock_error(*, backend: str, error: str) -> bool:
    if backend != "kuzu":
        return False
    lowered = error.casefold()
    return "could not set lock on file" in lowered or "docs.kuzudb.com/concurrency" in lowered


def _gateway_process_owns_path(path: str) -> bool:
    if not path:
        return False
    commands: list[list[str]] = [
        ["fuser", path],
        ["lsof", "-t", "--", path],
    ]
    pids: set[str] = set()
    for command in commands:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=3)
        except Exception:
            continue
        for token in f"{proc.stdout}\n{proc.stderr}".replace(":", " ").split():
            if token.isdigit():
                pids.add(token)
    for pid in pids:
        try:
            cmdline = Path("/proc", pid, "cmdline").read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        normalized = cmdline.replace("\x00", " ").casefold()
        if "gateway run" in normalized and ("hermes" in normalized or "hermes_cli" in normalized):
            return True
    return False


def _is_expected_active_kuzu_lock(*, backend: str, runtime: str, error: str, path: str) -> bool:
    if not _is_kuzu_lock_error(backend=backend, error=error):
        return False
    if runtime == "docker":
        return True
    return _gateway_process_owns_path(path)


def _run_python_probe(
    code: str,
    *,
    python_bin: Path | None,
    cwd: Path,
    hermes_home: Path,
    target: Path | None = None,
) -> dict[str, Any] | None:
    executable = str(python_bin) if python_bin is not None else sys.executable
    env = os.environ.copy()
    env["HERMES_HOME"] = str(hermes_home)
    if target is not None:
        plugin_memory_path = target / "plugins" / "memory"
        if plugin_memory_path.exists():
            existing_pythonpath = str(env.get("PYTHONPATH") or "")
            parts = [str(plugin_memory_path)]
            if existing_pythonpath:
                parts.append(existing_pythonpath)
            env["PYTHONPATH"] = os.pathsep.join(parts)
    try:
        proc = subprocess.run(
            [executable, "-c", code],
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
        )
    except Exception:
        return None
    raw = proc.stdout.strip().splitlines()[-1:] or [""]
    try:
        payload = json.loads(raw[0])
    except Exception:
        return {"openable": False, "error": (proc.stderr or proc.stdout or "backend probe failed").strip()}
    if proc.returncode != 0 and payload.get("openable") is not True:
        payload.setdefault("error", (proc.stderr or proc.stdout or "backend probe failed").strip())
    return payload if isinstance(payload, dict) else None


def _run_docker_python_probe(
    code: str,
    *,
    compose_path: Path | None,
    service: str | None = None,
) -> dict[str, Any] | None:
    if compose_path is None or not compose_path.exists():
        return None
    resolved_service = service or _default_compose_service(compose_path)
    if not resolved_service:
        return None
    python_commands = [
        "/opt/hermes/.venv/bin/python3",
        "/opt/hermes/.venv/bin/python",
        "python3",
    ]
    probe_user = os.environ.get("BRAINSTACK_DOCKER_PROBE_USER", "hermes").strip()
    container_name = _default_container_name(compose_path, service=resolved_service)
    commands: list[list[str]] = []
    if container_name:
        for python_cmd in python_commands:
            cmd = ["docker", "exec"]
            if probe_user:
                cmd.extend(["--user", probe_user])
            cmd.extend([container_name, python_cmd, "-c", code])
            commands.append(cmd)
    for python_cmd in python_commands:
        cmd = ["docker", "compose", "-f", str(compose_path), "exec", "-T"]
        if probe_user:
            cmd.extend(["--user", probe_user])
        cmd.extend([resolved_service, python_cmd, "-c", code])
        commands.append(cmd)
    for cmd in commands:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        raw = proc.stdout.strip().splitlines()[-1:] or [""]
        try:
            payload = json.loads(raw[0])
        except Exception:
            continue
        return payload if isinstance(payload, dict) else None
    return None


def _backend_openability_checks(
    *,
    backend: str,
    configured_path: str,
    config_path: Path,
    planned_install: bool,
    python_bin: Path | None,
    runtime: str,
    compose_path: Path | None,
    target: Path | None = None,
) -> list[Check]:
    default_suffix = "brainstack.kuzu" if backend == "kuzu" else "brainstack.chroma"
    check_name = "graph_backend_open" if backend == "kuzu" else "corpus_backend_open"
    code = _backend_probe_code(
        backend=backend,
        configured_path=configured_path,
        default_suffix=default_suffix,
    )
    if runtime == "docker" and compose_path and not planned_install:
        payload = _run_docker_python_probe(code, compose_path=compose_path)
    else:
        payload = _run_python_probe(
            code,
            python_bin=python_bin,
            cwd=config_path.parent,
            hermes_home=config_path.parent,
            target=target,
        )
    if payload is None:
        return [Check(check_name, "warn", f"Could not probe {backend} backend openability")]
    path = str(payload.get("path") or configured_path or default_suffix)
    if not bool(payload.get("exists")) and payload.get("openable") is None:
        status = "pass" if planned_install else "warn"
        return [Check(check_name, status, f"{backend} backend path does not exist yet: {path}")]
    if payload.get("openable") is True:
        repair_events = payload.get("repair_events") if isinstance(payload.get("repair_events"), list) else []
        if backend == "chroma" and repair_events:
            return [
                Check(
                    check_name,
                    "pass",
                    f"{backend} backend opened successfully at {path} after quarantining a corrupt derived cache",
                )
            ]
        return [Check(check_name, "pass", f"{backend} backend opens successfully at {path}")]
    error = str(payload.get("error") or "unknown backend open failure")
    error_class = str(payload.get("error_class") or "backend_open_failure")
    if _is_expected_active_kuzu_lock(backend=backend, runtime=runtime, error=error, path=path):
        if runtime == "docker":
            message = (
                f"{backend} backend is locked by the active Docker runtime at {path}; "
                "dependency import and container health must be checked separately"
            )
        else:
            message = (
                f"{backend} backend external probe is blocked by the active runtime owner at {path}; "
                "dependency import and runtime health must be checked separately"
            )
        return [
            Check(
                check_name,
                "warn",
                message,
            )
        ]
    if backend == "chroma" and error_class == "backend_embedding_config_missing":
        return [
            Check(
                check_name,
                "warn",
                f"{backend} backend is configured but unavailable at {path}: embedding config is missing or default embeddings are disabled",
            )
        ]
    return [Check(check_name, "fail", f"{backend} backend exists but cannot be opened at {path}: {error_class}: {error}")]


def _check_compose(compose_path: Path, planned_install: bool) -> list[Check]:
    checks: list[Check] = []
    if not compose_path.exists():
        checks.append(Check("docker_compose", "warn", f"Compose file not found: {compose_path}"))
        return checks
    text = _read(compose_path)
    compact = " ".join(text.replace("[", " ").replace("]", " ").replace(",", " ").split())
    if "gateway" in compact and "run" in compact and "--replace" in compact:
        checks.append(Check("docker_gateway_mode", "pass", "Docker compose starts Hermes Gateway mode"))
    elif planned_install:
        checks.append(Check("docker_gateway_mode", "pass", "Docker compose gateway command will be patched to `gateway run --replace`"))
    else:
        checks.append(Check("docker_gateway_mode", "fail", "Docker compose does not clearly start `gateway run --replace`"))
    if "/opt/data" in text and "HERMES_HOME" in text:
        checks.append(Check("docker_hermes_home", "pass", "Docker compose mounts/configures HERMES_HOME"))
    elif planned_install:
        checks.append(Check("docker_hermes_home", "pass", "Docker HERMES_HOME mapping will be patched by installer"))
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
    if _launcher_points_to_target_start_script(text, target):
        checks.append(Check("desktop_launcher_target", "pass", "Desktop launcher points at this Hermes checkout"))
    elif runtime == "docker":
        checks.append(Check("desktop_launcher_target", "fail", "Desktop launcher points at a different checkout or script"))
    else:
        checks.append(Check("desktop_launcher_target", "warn", "Desktop launcher target is not explicit; manual local start may still be valid"))

    if runtime == "docker":
        if _launcher_points_to_target_start_script(text, target) or "docker compose" in text.lower():
            checks.append(Check("desktop_launcher_mode", "pass", "Desktop launcher uses the Docker Brainstack start path"))
        else:
            checks.append(Check("desktop_launcher_mode", "warn", "Desktop launcher mode is unclear for Docker runtime"))
    else:
        if "docker" in text.lower():
            checks.append(Check("desktop_launcher_mode", "warn", "Launcher text still looks Docker-oriented while doctor is running in local mode"))
        else:
            checks.append(Check("desktop_launcher_mode", "pass", "Local runtime mode does not require Docker launcher checks"))
    return checks


def _launcher_points_to_target_start_script(text: str, target: Path) -> bool:
    target_script = (target / "scripts" / "hermes-brainstack-start.sh").resolve()
    target_str = str(target)
    if target_str in text or str(target / "scripts") in text or str(target_script) in text:
        return True
    for line in text.splitlines():
        if not line.startswith("Exec="):
            continue
        try:
            parts = shlex.split(line.removeprefix("Exec="))
        except ValueError:
            parts = line.removeprefix("Exec=").split()
        for part in parts:
            if not part.endswith("hermes-brainstack-start.sh"):
                continue
            try:
                if Path(part).expanduser().resolve() == target_script:
                    return True
            except OSError:
                continue
    return False


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
    if _has_runtime_ownership_normalization(entrypoint_text):
        checks.append(Check("docker_runtime_ownership_fix", "pass", "Docker entrypoint normalizes runtime ownership before privilege drop"))
    elif planned_install:
        checks.append(Check("docker_runtime_ownership_fix", "pass", "Installer will patch Docker entrypoint ownership normalization"))
    else:
        checks.append(Check("docker_runtime_ownership_fix", "warn", "Docker entrypoint lacks Brainstack runtime ownership normalization"))
    return checks


def _has_runtime_ownership_normalization(entrypoint_text: str) -> bool:
    """Return whether Docker startup owns writable runtime state before running Hermes.

    Older Brainstack installs used a narrow `fix_critical_runtime_ownership`
    patch. Current upstream Hermes already provides the safer donor-owned seam:
    optional UID/GID remap, `$HERMES_HOME` ownership normalization, then `gosu`
    privilege drop. The doctor should accept either shape instead of forcing a
    Brainstack-specific host patch back into core mode.
    """
    text = str(entrypoint_text or "")
    if "fix_critical_runtime_ownership" in text:
        return True
    required_markers = (
        "HERMES_UID",
        "HERMES_GID",
        'chown -R hermes:hermes "$HERMES_HOME"',
        "exec gosu hermes",
    )
    return all(marker in text for marker in required_markers)


def run_doctor(args: argparse.Namespace) -> tuple[int, list[Check]]:
    target = Path(args.target).expanduser().resolve()
    profile = str(getattr(args, "profile", "") or "").strip()
    explicit_config = bool(args.config)
    if explicit_config:
        config_path = Path(args.config).expanduser().resolve()
    elif profile:
        config_path = _profile_config_path(target, profile)
    else:
        config_path = _default_config_path(target)
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
    if profile:
        if explicit_config:
            checks.append(
                Check(
                    "profile_config",
                    "pass",
                    f"--config was provided explicitly; --profile {profile!r} did not override it",
                )
            )
        elif config_path is not None:
            checks.append(
                Check(
                    "profile_config",
                    "pass",
                    f"Resolved profile {profile!r} config: {config_path}",
                )
            )
        else:
            candidates = (
                ", ".join(str(path) for path in _profile_config_candidates(target, profile))
                or "<invalid profile name>"
            )
            checks.append(
                Check(
                    "profile_config",
                    "fail",
                    f"Could not resolve profile {profile!r} config. Checked: {candidates}",
                )
            )
    if python_bin is not None:
        checks.append(Check("python_target", "pass", f"Dependency checks use {python_bin}"))
    else:
        checks.append(Check("python_target", "warn", "No target Python detected; dependency checks fall back to the current interpreter"))
    checks.extend(_check_target_shape(target))
    if "planned_install" in inspect.signature(_check_host_surfaces).parameters:
        checks.extend(_check_host_surfaces(target, planned_install=args.planned_install))
    else:
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
                target=target,
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
    parser.add_argument("--profile", help="Hermes profile name to validate without manually passing --config")
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
