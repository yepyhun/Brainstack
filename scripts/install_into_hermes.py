#!/usr/bin/env python3
"""Install Brainstack into a target Hermes checkout.

This installer copies the Brainstack provider payload and applies recognized
config changes. It avoids blind host-code patching; compatibility is verified
by ``brainstack_doctor.py``. Hermes-native explicit truth capture, addressing
precedence, explicit rule-pack fidelity, and ordinary-turn compliance remain
upstream Hermes seams rather than Brainstack installer responsibilities.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PLUGIN = REPO_ROOT / "brainstack"
SOURCE_HOST_PAYLOAD = REPO_ROOT / "host_payload"
BACKEND_DEPENDENCIES = {
    "kuzu": "kuzu",
    "chromadb": "chromadb",
    "openai": "openai",
    "croniter": "croniter",
}

HOST_PATCH_MODE_CATEGORIES: dict[str, set[str]] = {
    "core": {"required_seam", "core_hygiene"},
    "compat": {"required_seam", "core_hygiene", "compat_hotfix"},
    "legacy": {"required_seam", "core_hygiene", "compat_hotfix", "legacy_host_patch"},
}

HOST_PATCH_POLICIES: dict[str, dict[str, str]] = {
    "_patch_run_agent": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes exposes structured write-origin metadata and interrupted-turn sync suppression natively.",
    },
    "_patch_memory_provider": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes MemoryProvider.on_memory_write accepts optional metadata natively.",
    },
    "_patch_memory_manager_required_seam": {
        "category": "compat_hotfix",
        "owner": "host-seam",
        "removal_condition": "Hermes MemoryManager forwards optional write metadata natively.",
    },
    "_patch_dockerfile_backend_dependencies": {
        "category": "required_seam",
        "owner": "build-seam",
        "removal_condition": "Hermes supports plugin-declared runtime dependency installation.",
    },
    "_patch_dockerignore": {
        "category": "core_hygiene",
        "owner": "source-hygiene",
        "removal_condition": "Upstream Docker build context already excludes private runtime state.",
    },
    "_patch_config": {
        "category": "core_hygiene",
        "owner": "runtime-config",
        "removal_condition": "Hermes provides a first-class provider activation config writer.",
    },
    "_patch_auxiliary_client": {
        "category": "compat_hotfix",
        "owner": "host-provider-hotfix",
        "removal_condition": "Hermes auxiliary task resolver natively supports provider=main model inheritance.",
    },
    "_patch_credential_pool": {
        "category": "compat_hotfix",
        "owner": "host-provider-hotfix",
        "removal_condition": "Hermes credential pool natively rejects stale Nous agent keys at selection time.",
    },
    "_patch_credential_pool_tests": {
        "category": "compat_hotfix",
        "owner": "host-provider-hotfix-test",
        "removal_condition": "Upstream Hermes tests cover stale Nous agent-key rejection.",
    },
    "_patch_compose_healthcheck": {
        "category": "compat_hotfix",
        "owner": "private-runtime",
        "removal_condition": "Runtime deployment provides an explicit readiness healthcheck outside source patching.",
    },
    "_patch_compose_runtime_identity": {
        "category": "compat_hotfix",
        "owner": "private-runtime",
        "removal_condition": "Runtime deployment provides UID/GID mapping outside source patching.",
    },
    "_patch_prompt_builder": {
        "category": "legacy_host_patch",
        "owner": "host-prompt-legacy",
        "removal_condition": "Brainstack provider projection renders the evidence-use contract.",
    },
    "_patch_memory_manager": {
        "category": "legacy_host_patch",
        "owner": "host-memory-legacy",
        "removal_condition": "Brainstack provider projection renders private memory-context guidance.",
    },
    "_patch_cron_jobs": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler",
        "removal_condition": "Scheduler correctness is handled by upstream Hermes or explicit private runtime tooling.",
    },
    "_patch_cron_scheduler": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler",
        "removal_condition": "Scheduler delivery/fail-closed behavior is handled by upstream Hermes.",
    },
    "_patch_cron_scheduler_tests": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler-test",
        "removal_condition": "Scheduler compatibility patches are no longer applied by Brainstack installer.",
    },
    "_patch_cron_tests": {
        "category": "legacy_host_patch",
        "owner": "host-scheduler-test",
        "removal_condition": "Scheduler compatibility patches are no longer applied by Brainstack installer.",
    },
    "_patch_gateway_run": {
        "category": "legacy_host_patch",
        "owner": "host-gateway",
        "removal_condition": "Gateway lifecycle/status behavior is handled by upstream Hermes.",
    },
    "_patch_docker_entrypoint": {
        "category": "legacy_host_patch",
        "owner": "host-docker-runtime",
        "removal_condition": "Upstream Docker entrypoint owns UID/GID and runtime ownership normalization.",
    },
}

PRIVATE_RUNTIME_DENYLIST: tuple[str, ...] = (
    ".planning",
    ".planning/**",
    "hermes-config",
    "hermes-config/**",
    "runtime",
    "runtime/**",
    "docker-compose.*.yml",
    "scripts/desktop",
    "scripts/desktop/**",
    "*.desktop",
    "sessions",
    "sessions/**",
    "memories",
    "memories/**",
    "cron",
    "cron/**",
    "auth.json",
    "**/auth.json",
    "auth.lock",
    "**/auth.lock",
    ".env",
    "**/.env",
    "gateway_state.json",
    "**/gateway_state.json",
    "gateway.pid",
    "**/gateway.pid",
    "state.db",
    "state.db-*",
    "**/state.db",
    "**/state.db-*",
    "brainstack/*.db",
    "brainstack/*.db-*",
    "**/brainstack/*.db",
    "**/brainstack/*.db-*",
)

SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"oauth[_-]?token|agent[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{20,}"
)

HOST_PATCH_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "patcher": "_patch_run_agent",
        "target": "run_agent.py",
        "scope": "host-runtime-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Brainstack session-finalize wiring, transcript hygiene, and deterministic memory sync hooks.",
        "why": "Needed until Hermes exposes a stable memory-finalization seam for Brainstack.",
    },
    {
        "patcher": "_patch_prompt_builder",
        "target": "agent/prompt_builder.py",
        "scope": "prompt-projection-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Inject Brainstack-owned truth and memory guidance into the host prompt assembly path.",
        "why": "Brainstack still needs a thin prompt projection seam instead of a parallel prompt stack.",
    },
    {
        "patcher": "_patch_cron_jobs",
        "target": "cron/jobs.py",
        "scope": "cron-correctness-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Fail-closed job state and one-shot scheduling correctness for Brainstack-integrated reminder truth.",
        "why": "Prevents scheduler-state illusions that would contaminate Brainstack recall and user-facing truth.",
    },
    {
        "patcher": "_patch_cron_scheduler",
        "target": "cron/scheduler.py",
        "scope": "cron-delivery-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Delivery fail-closed behavior, bounded cron execution, and Brainstack-safe reminder semantics.",
        "why": "Keeps reminder truth aligned with actual scheduler delivery instead of memory-only claims.",
    },
    {
        "patcher": "_patch_cron_scheduler_tests",
        "target": "tests/cron/test_scheduler.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Align cron scheduler regression tests with the narrowed discord tool disable set and resolved runtime credential-pool contract.",
        "why": "Installer-applied cron scheduler behavior must ship with explicit regression coverage to prevent drift across Hermes updates.",
    },
    {
        "patcher": "_patch_cron_tests",
        "target": "tests/cron/test_jobs.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Extends host cron tests to cover the Brainstack-owned delivery/truth contract.",
        "why": "Installer-applied host behavior must ship with explicit regression coverage.",
    },
    {
        "patcher": "_patch_auxiliary_client",
        "target": "agent/auxiliary_client.py",
        "scope": "auxiliary-routing-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Expose Brainstack auxiliary task routing and provider control without forking the host client stack.",
        "why": "Brainstack structured-understanding and flush paths need stable auxiliary task plumbing.",
    },
    {
        "patcher": "_patch_credential_pool",
        "target": "agent/credential_pool.py",
        "scope": "provider-auth-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Prevent stale Nous agent-key entries from being selected by the host credential pool during live runtime execution.",
        "why": "Without this, cron and other runtime paths can randomly fall onto expired Nous entries and appear logged out despite valid credentials.",
    },
    {
        "patcher": "_patch_credential_pool_tests",
        "target": "tests/agent/test_credential_pool.py",
        "scope": "verification-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Add regression coverage for skipping stale Nous credential-pool entries and keep time-sensitive fixtures valid.",
        "why": "The credential-pool seam is host-owned runtime behavior and must keep an explicit, reproducible test contract.",
    },
    {
        "patcher": "_patch_memory_provider",
        "target": "agent/memory_provider.py",
        "scope": "memory-provider-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Add Brainstack-specific write-origin and provider bridge wiring.",
        "why": "Preserves provenance/trust boundaries between host memory events and Brainstack durable state.",
    },
    {
        "patcher": "_patch_memory_manager_required_seam",
        "target": "agent/memory_manager.py",
        "scope": "memory-write-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Forward optional write-origin metadata from Hermes memory manager to external memory providers.",
        "why": "Brainstack must distinguish reflection/background writes from user-established truth without heuristic inference.",
    },
    {
        "patcher": "_patch_memory_manager",
        "target": "agent/memory_manager.py",
        "scope": "legacy-memory-projection-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Legacy host-side private recalled-memory wording mutation.",
        "why": "Superseded by Brainstack-owned evidence-use projection; retained only for legacy emergency installs.",
    },
    {
        "patcher": "_patch_gateway_run",
        "target": "gateway/run.py",
        "scope": "gateway-lifecycle-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Brainstack lifecycle hooks that must execute at gateway runtime boundaries.",
        "why": "Avoids a parallel runtime while keeping Brainstack synchronized with the single Hermes gateway.",
    },
    {
        "patcher": "_patch_config",
        "target": "hermes-config/<agent>/config.yaml",
        "scope": "runtime-config-seam",
        "runtime_modes": ("source", "docker"),
        "purpose": "Enable Brainstack provider and task-specific auxiliary/runtime configuration.",
        "why": "The live runtime needs explicit config ownership separate from copied plugin payload files.",
    },
    {
        "patcher": "_patch_compose_healthcheck",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Install Brainstack-aware gateway healthcheck behavior for Docker runtime verification.",
        "why": "Docker installs need explicit health semantics to validate the integrated runtime, not just the container process.",
    },
    {
        "patcher": "_patch_compose_runtime_identity",
        "target": "docker-compose*.yml",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Align runtime UID/GID and mounted state paths with the generated Brainstack Docker flow.",
        "why": "Prevents permission drift and runtime ownership breakage in containerized installs.",
    },
    {
        "patcher": "_patch_dockerignore",
        "target": ".dockerignore",
        "scope": "docker-build-seam",
        "runtime_modes": ("docker",),
        "purpose": "Ensure required Brainstack payload and runtime assets are available in Docker builds.",
        "why": "Without this, Docker rebuilds can silently omit install-critical files.",
    },
    {
        "patcher": "_patch_dockerfile_backend_dependencies",
        "target": "Dockerfile",
        "scope": "docker-build-seam",
        "runtime_modes": ("docker",),
        "purpose": "Install Brainstack backend dependencies inside the runtime image.",
        "why": "The plugin payload alone is insufficient; the container image must contain its runtime deps.",
    },
    {
        "patcher": "_patch_docker_entrypoint",
        "target": "docker/entrypoint.sh",
        "scope": "docker-runtime-seam",
        "runtime_modes": ("docker",),
        "purpose": "Preserve Brainstack runtime startup invariants in Docker mode.",
        "why": "Keeps the container startup path aligned with the installed Brainstack-integrated runtime.",
    },
)


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


def _normalize_rel_path(value: str | Path) -> str:
    rendered = str(value).replace("\\", "/").strip()
    while rendered.startswith("./"):
        rendered = rendered[2:]
    return rendered.strip("/")


def _is_private_runtime_path(value: str | Path) -> bool:
    normalized = _normalize_rel_path(value)
    if not normalized:
        return False
    return any(
        normalized == pattern.rstrip("/").replace("/**", "")
        or fnmatch.fnmatch(normalized, pattern)
        for pattern in PRIVATE_RUNTIME_DENYLIST
    )


def _assert_no_private_payload_files(files: list[dict[str, str]]) -> None:
    private_sources = [
        item["source"]
        for item in files
        if _is_private_runtime_path(item.get("source", ""))
    ]
    if private_sources:
        raise RuntimeError(
            "Refusing to include private runtime files in Brainstack payload: "
            + ", ".join(sorted(private_sources)[:12])
        )


def _path_may_contain_text(path: Path) -> bool:
    return path.suffix.lower() in {
        "",
        ".cfg",
        ".conf",
        ".json",
        ".md",
        ".py",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }


def _scan_tracked_secret_like_assignments(repo_root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repo_root,
            text=False,
            capture_output=True,
            check=True,
        )
    except Exception:
        return []
    findings: list[str] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        path = repo_root / rel
        if not path.is_file() or not _path_may_contain_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SECRET_ASSIGNMENT_RE.search(text):
            findings.append(rel)
    return findings


def _check_release_hygiene(repo_root: Path) -> dict[str, Any]:
    tracked: list[str] = []
    staged: list[str] = []
    for cmd, output in (
        (["git", "ls-files", "-z"], tracked),
        (["git", "diff", "--cached", "--name-only", "-z"], staged),
    ):
        proc = subprocess.run(cmd, cwd=repo_root, text=False, capture_output=True, check=True)
        output.extend(
            raw.decode("utf-8", errors="replace")
            for raw in proc.stdout.split(b"\0")
            if raw
        )
    private_tracked = [path for path in tracked if _is_private_runtime_path(path)]
    private_staged = [path for path in staged if _is_private_runtime_path(path)]
    secret_like = _scan_tracked_secret_like_assignments(repo_root)
    status = "pass" if not private_tracked and not private_staged and not secret_like else "fail"
    return {
        "schema": "brainstack.release_hygiene.v1",
        "status": status,
        "private_tracked": private_tracked,
        "private_staged": private_staged,
        "secret_like_tracked": secret_like,
    }


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


def _python_can_import(python_bin: Path, module_name: str) -> bool:
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


def _ensure_backend_dependencies(
    python_bin: Path | None,
    *,
    dry_run: bool,
    skip_deps: bool,
) -> dict[str, Any]:
    if skip_deps:
        return {"status": "skipped", "reason": "skip_deps"}
    if python_bin is None:
        return {"status": "skipped", "reason": "no_target_python"}

    missing = [dist for module, dist in BACKEND_DEPENDENCIES.items() if not _python_can_import(python_bin, module)]
    if not missing:
        return {"status": "already_satisfied", "python": str(python_bin), "packages": []}
    if dry_run:
        return {"status": "planned", "python": str(python_bin), "packages": missing}

    attempts: list[tuple[str, list[str]]] = [
        ("pip", [str(python_bin), "-m", "pip", "install", *missing]),
    ]
    uv_bin = shutil.which("uv")
    if uv_bin:
        attempts.append(("uv", [uv_bin, "pip", "install", "--python", str(python_bin), *missing]))

    failures: list[str] = []
    for label, cmd in attempts:
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.returncode == 0:
            return {"status": "installed", "python": str(python_bin), "packages": missing, "installer": label}
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        failures.append(f"{label}: {stderr or stdout or 'unknown error'}")

    raise RuntimeError(
        f"Dependency install failed for {' '.join(missing)} using {python_bin}; "
        + " | ".join(failures)
    )


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


def _copy_file(src: Path, dst: Path, dry_run: bool) -> dict[str, str]:
    copied = {
        "source": str(src.relative_to(REPO_ROOT)),
        "target": str(dst),
        "sha256": _hash_file(src),
    }
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return copied


def _host_patch_policy(patcher: str) -> dict[str, str]:
    return dict(
        HOST_PATCH_POLICIES.get(
            patcher,
            {
                "category": "legacy_host_patch",
                "owner": "unclassified",
                "removal_condition": "Classify this host patch before enabling it by default.",
            },
        )
    )


def _host_patch_selected(patcher: str, host_patch_mode: str) -> bool:
    policy = _host_patch_policy(patcher)
    allowed = HOST_PATCH_MODE_CATEGORIES[host_patch_mode]
    return policy["category"] in allowed


def _selected_host_patch_inventory(runtime_mode: str, host_patch_mode: str = "core") -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    normalized = "docker" if runtime_mode == "docker" else "source"
    for item in HOST_PATCH_INVENTORY:
        runtime_modes = tuple(item.get("runtime_modes") or ())
        if normalized in runtime_modes:
            patcher = str(item["patcher"])
            policy = _host_patch_policy(patcher)
            selected.append(
                {
                    "patcher": patcher,
                    "target": item["target"],
                    "scope": item["scope"],
                    "runtime_modes": list(runtime_modes),
                    "purpose": item["purpose"],
                    "why": item["why"],
                    "category": policy["category"],
                    "owner": policy["owner"],
                    "removal_condition": policy["removal_condition"],
                    "selected": _host_patch_selected(patcher, host_patch_mode),
                    "host_patch_mode": host_patch_mode,
                }
            )
    return selected


def _run_host_patch(
    patcher: str,
    target_path: Path,
    dry_run: bool,
    *,
    host_patch_mode: str,
) -> list[str]:
    if not _host_patch_selected(patcher, host_patch_mode):
        return []
    patch_func = globals().get(patcher)
    if not callable(patch_func):
        raise RuntimeError(f"Unknown host patcher: {patcher}")
    return list(patch_func(target_path, dry_run))


def _replace_once(text: str, old: str, new: str, *, label: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"Installer patch anchor missing for {label} in {path}")
    return text.replace(old, new, 1)


def _replace_once_any(
    text: str,
    replacements: list[tuple[str, str]],
    *,
    label: str,
    path: Path,
) -> str:
    for old, new in replacements:
        if old in text:
            return text.replace(old, new, 1)
    raise RuntimeError(f"Installer patch anchor missing for {label} in {path}")


def _memory_write_signature_accepts_metadata(text: str) -> bool:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "on_memory_write":
            arg_names = {arg.arg for arg in [*node.args.args, *node.args.kwonlyargs]}
            return "metadata" in arg_names
    return False


def _memory_manager_forwards_write_metadata(text: str) -> bool:
    if not _memory_write_signature_accepts_metadata(text):
        return False
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "on_memory_write":
            continue
        if any(keyword.arg == "metadata" for keyword in node.keywords):
            return True
        if len(node.args) >= 4:
            return True
    return False


def _patch_memory_manager_required_seam(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if _memory_manager_forwards_write_metadata(text):
        return []

    metadata_signature = "def on_memory_write(self, action: str, target: str, content: str, metadata: dict | None = None) -> None:"
    if metadata_signature not in text:
        old_signature = "def on_memory_write(self, action: str, target: str, content: str) -> None:"
        new_signature = "def on_memory_write(self, action: str, target: str, content: str, metadata: dict | None = None) -> None:"
        text = _replace_once(
            text,
            old_signature,
            new_signature,
            label="memory_manager memory-write metadata signature",
            path=path,
        )
        applied.append("memory_manager:memory_write_metadata_signature")

    metadata_bridge = (
        "                if metadata:\n"
        "                    try:\n"
        "                        provider.on_memory_write(action, target, content, metadata=metadata)\n"
        "                    except TypeError:\n"
        "                        provider.on_memory_write(action, target, content)\n"
        "                else:\n"
        "                    provider.on_memory_write(action, target, content)\n"
    )
    if metadata_bridge not in text:
        old_call = "                provider.on_memory_write(action, target, content)\n"
        text = _replace_once(
            text,
            old_call,
            metadata_bridge,
            label="memory_manager memory-write metadata bridge",
            path=path,
        )
        applied.append("memory_manager:memory_write_metadata_bridge")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_memory_manager(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_note = (
        '        "[System note: The following is recalled memory context, "\n'
        '        "NOT new user input. Treat as informational background data.]\\n\\n"\n'
    )
    new_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging. "\n'
        '        "Use recalled details as supporting memory context, and when recalled items disagree, prefer the strongest committed or non-conflicted recalled record instead of blending them.]\\n\\n"\n'
    )
    current_private_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging.]\\n\\n"\n'
    )
    authoritative_private_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging. "\n'
        '        "When recalled memory provides a specific, non-conflicted factual user detail or committed owner-backed record such as a name, number, date, or task record, treat it as authoritative over assistant suggestions or generic prior knowledge unless another recalled fact in this memory block conflicts with it.]\\n\\n"\n'
    )
    if new_note not in text:
        text = _replace_once_any(
            text,
            [
                (old_note, new_note),
                (current_private_note, new_note),
                (authoritative_private_note, new_note),
            ],
            label="memory_manager private recall note",
            path=path,
        )
        applied.append("memory_manager:private_recall_note")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")

    applied.extend(_patch_memory_manager_required_seam(path, dry_run))
    return applied


def _patch_memory_provider(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if _memory_write_signature_accepts_metadata(text):
        return []

    metadata_doc = "    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:\n"
    if metadata_doc not in text:
        old_signature = "    def on_memory_write(self, action: str, target: str, content: str) -> None:\n"
        new_signature = "    def on_memory_write(self, action: str, target: str, content: str, metadata: dict[str, Any] | None = None) -> None:\n"
        text = _replace_once(
            text,
            old_signature,
            new_signature,
            label="memory_provider memory-write metadata signature",
            path=path,
        )
        applied.append("memory_provider:memory_write_metadata_signature")

    if "metadata: optional write-origin or trust metadata" not in text:
        old_doc = (
            "        action: 'add', 'replace', or 'remove'\n"
            "        target: 'memory' or 'user'\n"
            "        content: the entry content\n"
            "\n"
            "        Use to mirror built-in memory writes to your backend.\n"
        )
        new_doc = (
            "        action: 'add', 'replace', or 'remove'\n"
            "        target: 'memory' or 'user'\n"
            "        content: the entry content\n"
            "        metadata: optional write-origin or trust metadata\n"
            "\n"
            "        Use to mirror built-in memory writes to your backend.\n"
        )
        text = _replace_once(
            text,
            old_doc,
            new_doc,
            label="memory_provider memory-write metadata doc",
            path=path,
        )
        applied.append("memory_provider:memory_write_metadata_doc")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_prompt_builder(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    scheduler_guidance = (
        '    "without acting are not acceptable.\\n"\n'
        '    "If you claim that a reminder, cron job, or scheduled follow-up exists, that claim must be grounded in a real native scheduler record or a successful cronjob tool result from this run. A memory entry, todo note, or generic internal task list is not a scheduled job. Do not inspect OS-level cron or systemd timers as a substitute for Hermes scheduler state. If the cronjob tool is unavailable or the scheduler call fails, say that scheduling is unavailable or failed."\n'
        ")\n"
    )
    old_tail = (
        '    "without acting are not acceptable."\n'
        ")\n"
    )
    weaker_tail = (
        '    "without acting are not acceptable.\\n"\n'
        '    "If you claim that a reminder, cron job, or scheduled follow-up exists, that claim must be grounded in a real native scheduler record or a successful cronjob tool result from this run. Memory alone is not a scheduled job. If scheduling fails or you did not verify the job exists, say so plainly."\n'
        ")\n"
    )
    if "generic internal task list is not a scheduled job" not in text and weaker_tail in text:
        text = _replace_once(
            text,
            weaker_tail,
            scheduler_guidance,
            label="prompt_builder stronger scheduler truth guidance",
            path=path,
        )
        applied.append("prompt_builder:stronger_scheduler_truth_guidance")
    elif "generic internal task list is not a scheduled job" not in text and old_tail in text:
        text = _replace_once(
            text,
            old_tail,
            scheduler_guidance,
            label="prompt_builder scheduler truth guidance",
            path=path,
        )
        applied.append("prompt_builder:scheduler_truth_guidance")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_jobs(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    helper_anchor = "ONESHOT_GRACE_SECONDS = 120\n\n\n"
    helper_block = (
        "ONESHOT_GRACE_SECONDS = 120\n\n\n"
        "def _request_active_job_cancel(job_id: str, reason: str) -> None:\n"
        "    \"\"\"Best-effort interrupt for an in-flight cron job running in this process.\"\"\"\n"
        "    try:\n"
        "        from cron.scheduler import request_cancel  # Lazy import avoids module cycle at import time\n"
        "        request_cancel(job_id, reason)\n"
        "    except Exception:\n"
        "        pass\n\n\n"
        "def _request_scheduler_wake(reason: str) -> None:\n"
        "    \"\"\"Best-effort wake-up hint for the in-process cron ticker.\"\"\"\n"
        "    try:\n"
        "        from cron.scheduler import request_tick_wake  # Lazy import avoids module cycle at import time\n"
        "        request_tick_wake(reason)\n"
        "    except Exception:\n"
        "        pass\n\n\n"
    )
    if "def _request_scheduler_wake(reason: str) -> None:" not in text and helper_anchor in text:
        text = _replace_once(
            text,
            helper_anchor,
            helper_block,
            label="cron.jobs wake/cancel helpers",
            path=path,
        )
        applied.append("cron_jobs:wake_cancel_helpers")

    old_block = (
        "    # Default delivery to origin if available, otherwise local\n"
        "    if deliver is None:\n"
        "        deliver = \"origin\" if origin else \"local\"\n"
        "\n"
        "    job_id = uuid.uuid4().hex[:12]\n"
        "    now = _hermes_now().isoformat()\n"
    )
    new_block = (
        "    # Default delivery to origin if available, otherwise local\n"
        "    if deliver is None:\n"
        "        deliver = \"origin\" if origin else \"local\"\n"
        "\n"
        "    next_run_at = compute_next_run(parsed_schedule)\n"
        "    if parsed_schedule[\"kind\"] == \"once\" and next_run_at is None:\n"
        "        raise ValueError(\"Requested one-shot schedule is already in the past.\")\n"
        "\n"
        "    job_id = uuid.uuid4().hex[:12]\n"
        "    now = _hermes_now().isoformat()\n"
    )
    if "Requested one-shot schedule is already in the past." not in text and old_block in text:
        text = _replace_once(text, old_block, new_block, label="cron.jobs past one-shot rejection", path=path)
        applied.append("cron_jobs:reject_past_oneshot")

    old_next_run = '        "next_run_at": compute_next_run(parsed_schedule),\n'
    new_next_run = '        "next_run_at": next_run_at,\n'
    if old_next_run in text and new_next_run not in text:
        text = _replace_once(text, old_next_run, new_next_run, label="cron.jobs cached next_run_at", path=path)
        applied.append("cron_jobs:reuse_next_run_at")

    old_create_save = (
        "    jobs = load_jobs()\n"
        "    jobs.append(job)\n"
        "    save_jobs(jobs)\n"
        "\n"
        "    return job\n"
    )
    new_create_save = (
        "    jobs = load_jobs()\n"
        "    jobs.append(job)\n"
        "    save_jobs(jobs)\n"
        "    _request_scheduler_wake(f\"cron job created: {job_id}\")\n"
        "\n"
        "    return job\n"
    )
    if "_request_scheduler_wake(f\"cron job created: {job_id}\")" not in text and old_create_save in text:
        text = _replace_once(text, old_create_save, new_create_save, label="cron.jobs wake after create", path=path)
        applied.append("cron_jobs:wake_after_create")

    old_update_intro = (
        "        updated = _apply_skill_fields({**job, **updates})\n"
        "        schedule_changed = \"schedule\" in updates\n"
        "\n"
        "        if \"skills\" in updates or \"skill\" in updates:\n"
    )
    new_update_intro = (
        "        updated = _apply_skill_fields({**job, **updates})\n"
        "        schedule_changed = \"schedule\" in updates\n"
        "        update_keys = set(updates)\n"
        "        should_cancel_active = bool(\n"
        "            update_keys.intersection(\n"
        "                {\n"
        "                    \"schedule\",\n"
        "                    \"enabled\",\n"
        "                    \"state\",\n"
        "                    \"next_run_at\",\n"
        "                    \"prompt\",\n"
        "                    \"skill\",\n"
        "                    \"skills\",\n"
        "                    \"script\",\n"
        "                    \"model\",\n"
        "                    \"provider\",\n"
        "                    \"base_url\",\n"
        "                    \"deliver\",\n"
        "                    \"origin\",\n"
        "                }\n"
        "            )\n"
        "        )\n"
        "        should_wake_scheduler = bool(\n"
        "            update_keys.intersection({\"schedule\", \"enabled\", \"state\", \"next_run_at\"})\n"
        "        )\n"
        "\n"
        "        if \"skills\" in updates or \"skill\" in updates:\n"
    )
    if "should_wake_scheduler = bool(" not in text and old_update_intro in text:
        text = _replace_once(text, old_update_intro, new_update_intro, label="cron.jobs update control flags", path=path)
        applied.append("cron_jobs:update_control_flags")

    old_update_save = (
        "        jobs[i] = updated\n"
        "        save_jobs(jobs)\n"
        "        return _apply_skill_fields(jobs[i])\n"
    )
    new_update_save = (
        "        jobs[i] = updated\n"
        "        save_jobs(jobs)\n"
        "        if should_cancel_active:\n"
        "            _request_active_job_cancel(job_id, \"Cron job updated while running\")\n"
        "        if should_wake_scheduler:\n"
        "            _request_scheduler_wake(f\"cron job updated: {job_id}\")\n"
        "        return _apply_skill_fields(jobs[i])\n"
    )
    if "Cron job updated while running" not in text and old_update_save in text:
        text = _replace_once(text, old_update_save, new_update_save, label="cron.jobs update wake/cancel", path=path)
        applied.append("cron_jobs:update_wake_cancel")

    old_remove = (
        "    if len(jobs) < original_len:\n"
        "        save_jobs(jobs)\n"
        "        return True\n"
    )
    new_remove = (
        "    if len(jobs) < original_len:\n"
        "        save_jobs(jobs)\n"
        "        _request_active_job_cancel(job_id, \"Cron job removed\")\n"
        "        _request_scheduler_wake(f\"cron job removed: {job_id}\")\n"
        "        return True\n"
    )
    if "_request_scheduler_wake(f\"cron job removed: {job_id}\")" not in text and old_remove in text:
        text = _replace_once(text, old_remove, new_remove, label="cron.jobs remove wake/cancel", path=path)
        applied.append("cron_jobs:remove_wake_cancel")

    old_delivery_status = (
        '            job["last_status"] = "ok" if success else "error"\n'
        '            job["last_error"] = error if not success else None\n'
        '            # Track delivery failures separately — cleared on successful delivery\n'
        '            job["last_delivery_error"] = delivery_error\n'
    )
    new_delivery_status = (
        '            delivery_failed = bool(delivery_error)\n'
        '            job["last_status"] = "error" if (not success or delivery_failed) else "ok"\n'
        '            job["last_error"] = error if error else (delivery_error if delivery_failed else None)\n'
        '            job["last_delivery_error"] = delivery_error\n'
    )
    if 'job["last_status"] = "error" if (not success or delivery_failed) else "ok"' not in text and old_delivery_status in text:
        text = _replace_once(text, old_delivery_status, new_delivery_status, label="cron.jobs fail_closed_delivery_status", path=path)
        applied.append("cron_jobs:fail_closed_delivery_status")

    seconds_helper_anchor = "def save_job_output(job_id: str, output: str):\n"
    seconds_helper_block = (
        "def seconds_until_next_run(max_wait: float = 60.0) -> float:\n"
        "    \"\"\"Return seconds until the next due job, bounded by ``max_wait``.\"\"\"\n"
        "    now = _hermes_now()\n"
        "    soonest = max_wait\n"
        "\n"
        "    for job in [_apply_skill_fields(j) for j in copy.deepcopy(load_jobs())]:\n"
        "        if not job.get(\"enabled\", True):\n"
        "            continue\n"
        "\n"
        "        next_run = job.get(\"next_run_at\")\n"
        "        if not next_run:\n"
        "            next_run = _recoverable_oneshot_run_at(\n"
        "                job.get(\"schedule\", {}),\n"
        "                now,\n"
        "                last_run_at=job.get(\"last_run_at\"),\n"
        "            )\n"
        "        if not next_run:\n"
        "            continue\n"
        "\n"
        "        try:\n"
        "            next_dt = _ensure_aware(datetime.fromisoformat(next_run))\n"
        "        except Exception:\n"
        "            continue\n"
        "\n"
        "        delay = (next_dt - now).total_seconds()\n"
        "        if delay <= 0:\n"
        "            return 0.0\n"
        "        if delay < soonest:\n"
        "            soonest = delay\n"
        "\n"
        "    return max(0.0, min(max_wait, soonest))\n\n\n"
        "def save_job_output(job_id: str, output: str):\n"
    )
    if "def seconds_until_next_run(max_wait: float = 60.0) -> float:" not in text and seconds_helper_anchor in text:
        text = _replace_once(text, seconds_helper_anchor, seconds_helper_block, label="cron.jobs next-run delay helper", path=path)
        applied.append("cron_jobs:seconds_until_next_run")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_scheduler(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    import_anchor = "from cron.jobs import get_due_jobs, mark_job_run, save_job_output, advance_next_run\n"
    import_block = (
        "from cron.jobs import get_due_jobs, mark_job_run, save_job_output, advance_next_run\n\n"
        "_ACTIVE_JOBS_LOCK = threading.Lock()\n"
        "_ACTIVE_JOBS: dict[str, dict] = {}\n"
        "_TICK_WAKE_EVENT = threading.Event()\n\n\n"
        "def _set_active_job_field(job_id: str, **updates) -> None:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.setdefault(\n"
        "            job_id,\n"
        "            {\n"
        "                \"agent\": None,\n"
        "                \"future\": None,\n"
        "                \"cancel_requested\": False,\n"
        "                \"cancel_reason\": None,\n"
        "            },\n"
        "        )\n"
        "        entry.update(updates)\n\n\n"
        "def _clear_active_job(job_id: str) -> None:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        _ACTIVE_JOBS.pop(job_id, None)\n\n\n"
        "def _is_cancel_requested(job_id: str) -> tuple[bool, Optional[str]]:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.get(job_id) or {}\n"
        "        return bool(entry.get(\"cancel_requested\")), entry.get(\"cancel_reason\")\n\n\n"
        "def request_cancel(job_id: str, reason: str = \"Cron job cancelled\") -> bool:\n"
        "    with _ACTIVE_JOBS_LOCK:\n"
        "        entry = _ACTIVE_JOBS.get(job_id)\n"
        "        if not entry:\n"
        "            return False\n"
        "        entry[\"cancel_requested\"] = True\n"
        "        entry[\"cancel_reason\"] = reason\n"
        "        agent = entry.get(\"agent\")\n"
        "        future = entry.get(\"future\")\n\n"
        "    if agent is not None and hasattr(agent, \"interrupt\"):\n"
        "        try:\n"
        "            agent.interrupt(reason)\n"
        "        except Exception:\n"
        "            pass\n"
        "    if future is not None:\n"
        "        try:\n"
        "            future.cancel()\n"
        "        except Exception:\n"
        "            pass\n"
        "    return True\n\n\n"
        "def request_tick_wake(reason: Optional[str] = None) -> None:\n"
        "    if reason:\n"
        "        logger.debug(\"Cron scheduler wake requested: %s\", reason)\n"
        "    _TICK_WAKE_EVENT.set()\n\n\n"
        "def wait_for_tick_wake(stop_event: threading.Event, timeout: float) -> None:\n"
        "    if timeout <= 0:\n"
        "        return\n"
        "    if stop_event.is_set():\n"
        "        return\n"
        "    _TICK_WAKE_EVENT.wait(timeout=timeout)\n"
        "    _TICK_WAKE_EVENT.clear()\n"
    )
    if "def request_tick_wake(reason: Optional[str] = None) -> None:" not in text and import_anchor in text:
        text = _replace_once(text, import_anchor, import_block, label="cron.scheduler active job registry", path=path)
        applied.append("cron_scheduler:active_job_registry")

    old_live_adapter = (
        "        runtime_adapter = (adapters or {}).get(platform)\n"
        "        delivered = False\n"
        "        if runtime_adapter is not None and loop is not None and getattr(loop, \"is_running\", lambda: False)():\n"
    )
    new_live_adapter = (
        "        runtime_adapter = (adapters or {}).get(platform)\n"
        "        gateway_delivery_mode = adapters is not None and loop is not None\n"
        "        delivered = False\n"
        "        live_adapter_error = None\n"
        "        if runtime_adapter is not None and loop is not None and getattr(loop, \"is_running\", lambda: False)():\n"
    )
    if "live_adapter_error = None" not in text and old_live_adapter in text:
        text = _replace_once(text, old_live_adapter, new_live_adapter, label="cron.scheduler gateway delivery mode", path=path)
        applied.append("cron_scheduler:gateway_delivery_mode")

    old_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify"],\n'
    new_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify", "discord"],\n'
    if old_disabled in text and new_disabled not in text:
        text = _replace_once(text, old_disabled, new_disabled, label="cron.scheduler disable discord admin tool", path=path)
    legacy_disabled = '            disabled_toolsets=["cronjob", "messaging", "clarify", "hermes-discord"],\n'
    if legacy_disabled in text:
        text = _replace_once(text, legacy_disabled, new_disabled, label="cron.scheduler replace over-broad hermes-discord disable", path=path)
        applied.append("cron_scheduler:disable_hermes_discord")

    old_pool_block = (
        "        fallback_model = _cfg.get(\"fallback_providers\") or _cfg.get(\"fallback_model\") or None\n"
        "        credential_pool = None\n"
        "        runtime_provider = str(runtime.get(\"provider\") or \"\").strip().lower()\n"
        "        if runtime_provider:\n"
        "            try:\n"
        "                from agent.credential_pool import load_pool\n"
        "                pool = load_pool(runtime_provider)\n"
        "                if pool.has_credentials():\n"
        "                    credential_pool = pool\n"
        "                    logger.info(\n"
        "                        \"Job '%s': loaded credential pool for provider %s with %d entries\",\n"
        "                        job_id,\n"
        "                        runtime_provider,\n"
        "                        len(pool.entries()),\n"
        "                    )\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Job '%s': failed to load credential pool for %s: %s\", job_id, runtime_provider, e)\n"
    )
    new_pool_block = (
        "        fallback_model = _cfg.get(\"fallback_providers\") or _cfg.get(\"fallback_model\") or None\n"
        "        credential_pool = runtime.get(\"credential_pool\")\n"
        "        runtime_provider = str(runtime.get(\"provider\") or \"\").strip().lower()\n"
        "        if credential_pool is not None:\n"
        "            try:\n"
        "                if credential_pool.has_credentials():\n"
        "                    logger.info(\n"
        "                        \"Job '%s': using resolved credential pool for provider %s with %d entries\",\n"
        "                        job_id,\n"
        "                        runtime_provider,\n"
        "                        len(credential_pool.entries()),\n"
        "                    )\n"
        "                else:\n"
        "                    credential_pool = None\n"
        "            except Exception as e:\n"
        "                logger.debug(\n"
        "                    \"Job '%s': resolved credential pool unusable for %s: %s\",\n"
        "                    job_id,\n"
        "                    runtime_provider,\n"
        "                    e,\n"
        "                )\n"
        "                credential_pool = None\n"
    )
    if old_pool_block in text and new_pool_block not in text:
        text = _replace_once(text, old_pool_block, new_pool_block, label="cron.scheduler resolved credential pool", path=path)
        applied.append("cron_scheduler:resolved_credential_pool")

    old_ctx = (
        "    _ctx_tokens = set_session_vars(\n"
        "        platform=origin[\"platform\"] if origin else \"\",\n"
        "        chat_id=str(origin[\"chat_id\"]) if origin else \"\",\n"
        "        chat_name=origin.get(\"chat_name\", \"\") if origin else \"\",\n"
        "    )\n"
    )
    new_ctx = old_ctx + "    _set_active_job_field(job_id)\n"
    if "_set_active_job_field(job_id)" not in text and old_ctx in text:
        text = _replace_once(text, old_ctx, new_ctx, label="cron.scheduler mark active job", path=path)
        applied.append("cron_scheduler:mark_active_job")

    old_future = "        _cron_future = _cron_pool.submit(_cron_context.run, agent.run_conversation, prompt)\n"
    new_future = (
        "        _cron_future = _cron_pool.submit(_cron_context.run, agent.run_conversation, prompt)\n"
        "        _set_active_job_field(job_id, agent=agent, future=_cron_future)\n"
    )
    if "_set_active_job_field(job_id, agent=agent, future=_cron_future)" not in text and old_future in text:
        text = _replace_once(text, old_future, new_future, label="cron.scheduler track cron future", path=path)
        applied.append("cron_scheduler:track_future")

    old_wait_loop = (
        "                while True:\n"
        "                    done, _ = concurrent.futures.wait(\n"
        "                        {_cron_future}, timeout=_POLL_INTERVAL,\n"
        "                    )\n"
    )
    new_wait_loop = (
        "                while True:\n"
        "                    _cancelled, _cancel_reason = _is_cancel_requested(job_id)\n"
        "                    if _cancelled:\n"
        "                        if hasattr(agent, \"interrupt\"):\n"
        "                            try:\n"
        "                                agent.interrupt(_cancel_reason or \"Cron job cancelled\")\n"
        "                            except Exception:\n"
        "                                pass\n"
        "                        raise RuntimeError(_cancel_reason or \"Cron job cancelled\")\n"
        "                    done, _ = concurrent.futures.wait(\n"
        "                        {_cron_future}, timeout=_POLL_INTERVAL,\n"
        "                    )\n"
    )
    if "_cancelled, _cancel_reason = _is_cancel_requested(job_id)" not in text and old_wait_loop in text:
        text = _replace_once(text, old_wait_loop, new_wait_loop, label="cron.scheduler cancel while waiting", path=path)
        applied.append("cron_scheduler:cancel_while_waiting")

    old_final_response = '        final_response = result.get("final_response", "") or ""\n'
    new_final_response = (
        "        _cancelled, _cancel_reason = _is_cancel_requested(job_id)\n"
        "        if _cancelled:\n"
        "            raise RuntimeError(_cancel_reason or \"Cron job cancelled\")\n\n"
        '        final_response = result.get("final_response", "") or ""\n'
    )
    if "_cancelled, _cancel_reason = _is_cancel_requested(job_id)" in text:
        pass
    elif old_final_response in text:
        text = _replace_once(text, old_final_response, new_final_response, label="cron.scheduler cancel before final response", path=path)
        applied.append("cron_scheduler:cancel_before_final_response")

    old_run_finally = (
        "    finally:\n"
        "        # Clean up ContextVar session/delivery state for this job.\n"
        "        clear_session_vars(_ctx_tokens)\n"
    )
    new_run_finally = (
        "    finally:\n"
        "        _clear_active_job(job_id)\n"
        "        # Clean up ContextVar session/delivery state for this job.\n"
        "        clear_session_vars(_ctx_tokens)\n"
    )
    if "_clear_active_job(job_id)" not in text and old_run_finally in text:
        text = _replace_once(text, old_run_finally, new_run_finally, label="cron.scheduler clear active job", path=path)
        applied.append("cron_scheduler:clear_active_job")

    old_live_send_fail = (
        "                        msg = f\"live adapter send to {platform_name}:{chat_id} failed: {err}\"\n"
        "                        logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                        delivery_errors.append(msg)\n"
        "                        adapter_ok = False\n"
    )
    new_live_send_fail = (
        "                        msg = f\"live adapter send to {platform_name}:{chat_id} failed: {err}\"\n"
        "                        logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                        live_adapter_error = msg\n"
        "                        adapter_ok = False\n"
    )
    if old_live_send_fail in text and new_live_send_fail not in text:
        text = _replace_once(text, old_live_send_fail, new_live_send_fail, label="cron.scheduler retain live send error for fallback", path=path)
        applied.append("cron_scheduler:live_send_error_buffer")

    old_live_send_success = (
        "                # Send extracted media files as native attachments via the live adapter\n"
        "                if adapter_ok and media_files:\n"
        "                    _send_media_via_adapter(runtime_adapter, chat_id, media_files, send_metadata, loop, job)\n"
        "\n"
        "                if adapter_ok:\n"
        "                    logger.info(\"Job '%s': delivered to %s:%s via live adapter\", job[\"id\"], platform_name, chat_id)\n"
        "                    delivered = True\n"
        "                else:\n"
        "                    continue\n"
        "            except Exception as e:\n"
        "                msg = f\"live adapter delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_live_send_success = (
        "                # Send extracted media files as native attachments via the live adapter\n"
        "                if adapter_ok and media_files:\n"
        "                    _send_media_via_adapter(runtime_adapter, chat_id, media_files, send_metadata, loop, job)\n"
        "\n"
        "                if adapter_ok:\n"
        "                    logger.info(\"Job '%s': delivered to %s:%s via live adapter\", job[\"id\"], platform_name, chat_id)\n"
        "                    delivered = True\n"
        "            except Exception as e:\n"
        "                msg = f\"live adapter delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                live_adapter_error = msg\n"
    )
    if old_live_send_success in text and new_live_send_success not in text:
        text = _replace_once(text, old_live_send_success, new_live_send_success, label="cron.scheduler fallback after live adapter failure", path=path)
        applied.append("cron_scheduler:live_delivery_fallback")

    old_platform_disabled = (
        "            if not pconfig or not pconfig.enabled:\n"
        "                msg = f\"platform '{platform_name}' not configured/enabled\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_platform_disabled = (
        "            if not pconfig or not pconfig.enabled:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"platform '{platform_name}' not configured/enabled\"\n"
        "                logger.warning(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    if "if live_adapter_error:\n                    delivery_errors.append(live_adapter_error)" not in text and old_platform_disabled in text:
        text = _replace_once(text, old_platform_disabled, new_platform_disabled, label="cron.scheduler preserve live adapter error when fallback unavailable", path=path)
        applied.append("cron_scheduler:preserve_live_error_on_disabled_platform")

    old_standalone = (
        "            # Standalone path: run the async send in a fresh event loop (safe from any thread)\n"
        "            coro = _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files)\n"
        "            try:\n"
        "                result = asyncio.run(coro)\n"
        "            except RuntimeError:\n"
        "                # asyncio.run() checks for a running loop before awaiting the coroutine;\n"
        "                # when it raises, the original coro was never started — close it to\n"
        "                # prevent \"coroutine was never awaited\" RuntimeWarning, then retry in a\n"
        "                # fresh thread that has no running loop.\n"
        "                coro.close()\n"
        "                import concurrent.futures\n"
        "                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:\n"
        "                    future = pool.submit(asyncio.run, _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files))\n"
        "                    result = future.result(timeout=30)\n"
        "            except Exception as e:\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_standalone = (
        "            # Standalone path: always run in a bounded worker thread so a hung\n"
        "            # network send cannot wedge the scheduler tick.\n"
        "            import concurrent.futures\n"
        "            _standalone_timeout = int(float(os.getenv(\"HERMES_CRON_DELIVERY_TIMEOUT\", \"30\")))\n"
        "            _pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)\n"
        "            try:\n"
        "                future = _pool.submit(\n"
        "                    asyncio.run,\n"
        "                    _send_to_platform(\n"
        "                        platform,\n"
        "                        pconfig,\n"
        "                        chat_id,\n"
        "                        cleaned_delivery_content,\n"
        "                        thread_id=thread_id,\n"
        "                        media_files=media_files,\n"
        "                    ),\n"
        "                )\n"
        "                result = future.result(timeout=_standalone_timeout)\n"
        "            except concurrent.futures.TimeoutError:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} timed out after {_standalone_timeout}s\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
        "                continue\n"
        "            except Exception as e:\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery to {platform_name}:{chat_id} failed: {e}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
        "                continue\n"
        "            finally:\n"
        "                _pool.shutdown(wait=False, cancel_futures=True)\n"
    )
    if "HERMES_CRON_DELIVERY_TIMEOUT" not in text and old_standalone in text:
        text = _replace_once(text, old_standalone, new_standalone, label="cron.scheduler bounded standalone delivery", path=path)
        applied.append("cron_scheduler:bounded_standalone_delivery")

    old_result_error = (
        "            if result and result.get(\"error\"):\n"
        "                msg = f\"delivery error: {result['error']}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    new_result_error = (
        "            if result and result.get(\"error\"):\n"
        "                if live_adapter_error:\n"
        "                    delivery_errors.append(live_adapter_error)\n"
        "                msg = f\"delivery error: {result['error']}\"\n"
        "                logger.error(\"Job '%s': %s\", job[\"id\"], msg)\n"
        "                delivery_errors.append(msg)\n"
        "                continue\n"
    )
    if "if live_adapter_error:\n                    delivery_errors.append(live_adapter_error)" not in text[text.find("if result and result.get(\"error\")") - 120:text.find("if result and result.get(\"error\")") + 240] and old_result_error in text:
        text = _replace_once(text, old_result_error, new_result_error, label="cron.scheduler retain live adapter error on fallback error", path=path)
        applied.append("cron_scheduler:retain_live_error_on_fallback_error")

    old_mark = '                mark_job_run(job["id"], success, error, delivery_error=delivery_error)\n'
    new_mark = (
        '                mark_job_run(job["id"], success, error, delivery_error=delivery_error)\n'
        '                logger.info(\n'
        '                    "Job \'%s\': finalized success=%s delivery_error=%s",\n'
        '                    job["id"],\n'
        '                    success,\n'
        '                    delivery_error,\n'
        '                )\n'
    )
    if 'logger.info(\n                    "Job \'%s\': finalized success=%s delivery_error=%s"' not in text and old_mark in text:
        text = _replace_once(text, old_mark, new_mark, label="cron.scheduler finalized logging", path=path)
        applied.append("cron_scheduler:finalized_logging")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_expectation = (
        '        assert updated["last_status"] == "ok"\n'
        '        assert updated["last_error"] is None\n'
        "        assert updated[\"last_delivery_error\"] == \"platform 'telegram' not configured\"\n"
    )
    new_expectation = (
        '        assert updated["last_status"] == "error"\n'
        "        assert updated[\"last_error\"] == \"platform 'telegram' not configured\"\n"
        "        assert updated[\"last_delivery_error\"] == \"platform 'telegram' not configured\"\n"
    )
    if old_expectation in text and new_expectation not in text:
        text = _replace_once(
            text,
            old_expectation,
            new_expectation,
            label="cron tests fail_closed_delivery_expectation",
            path=path,
        )
        applied.append("cron_tests:fail_closed_delivery_expectation")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_cron_scheduler_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_disabled_expectation = '        assert "hermes-discord" in (kwargs["disabled_toolsets"] or [])\n'
    new_disabled_expectation = '        assert "discord" in (kwargs["disabled_toolsets"] or [])\n'
    if old_disabled_expectation in text and new_disabled_expectation not in text:
        text = _replace_once(
            text,
            old_disabled_expectation,
            new_disabled_expectation,
            label="cron scheduler tests narrow discord disabled toolset expectation",
            path=path,
        )
        applied.append("cron_scheduler_tests:disable_discord_expectation")

    old_pool_test = (
        "        assert kwargs[\"credential_pool\"] is pool\n"
        "        mock_load_pool.assert_called_once_with(\"nous\")\n"
    )
    new_pool_test = (
        "        assert kwargs[\"credential_pool\"] is pool\n"
        "        mock_load_pool.assert_not_called()\n"
    )
    if old_pool_test in text and new_pool_test not in text:
        text = _replace_once(
            text,
            old_pool_test,
            new_pool_test,
            label="cron scheduler tests resolved credential pool expectation",
            path=path,
        )
        applied.append("cron_scheduler_tests:resolved_credential_pool")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_credential_pool(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_available_block = (
        "            if refresh and self._entry_needs_refresh(entry):\n"
        "                refreshed = self._refresh_entry(entry, force=False)\n"
        "                if refreshed is None:\n"
        "                    continue\n"
        "                entry = refreshed\n"
        "            available.append(entry)\n"
    )
    new_available_block = (
        "            if refresh and self._entry_needs_refresh(entry):\n"
        "                refreshed = self._refresh_entry(entry, force=False)\n"
        "                if refreshed is None:\n"
        "                    continue\n"
        "                entry = refreshed\n"
        "            if self.provider == \"nous\":\n"
        "                nous_state = {\n"
        "                    \"agent_key\": entry.agent_key,\n"
        "                    \"agent_key_expires_at\": entry.agent_key_expires_at,\n"
        "                }\n"
        "                if not auth_mod._agent_key_is_usable(\n"
        "                    nous_state,\n"
        "                    DEFAULT_AGENT_KEY_MIN_TTL_SECONDS,\n"
        "                ):\n"
        "                    continue\n"
        "            available.append(entry)\n"
    )
    if old_available_block in text and new_available_block not in text:
        text = _replace_once(
            text,
            old_available_block,
            new_available_block,
            label="credential pool skip stale nous agent keys",
            path=path,
        )
        applied.append("credential_pool:skip_stale_nous_entries")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_credential_pool_tests(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old_fixture_dates = [
        ("                    \"expires_at\": \"2026-03-24T12:00:00+00:00\",\n", "                    \"expires_at\": \"2027-03-24T12:00:00+00:00\",\n"),
        ("                    \"agent_key_expires_at\": \"2026-03-24T13:30:00+00:00\",\n", "                    \"agent_key_expires_at\": \"2027-03-24T13:30:00+00:00\",\n"),
    ]
    fixture_patched = False
    for old_line, new_line in old_fixture_dates:
        if old_line in text:
            text = text.replace(old_line, new_line)
            fixture_patched = True
    if fixture_patched:
        applied.append("credential_pool_tests:refresh_nous_fixture_dates")

    marker = "def test_singleton_seed_does_not_clobber_manual_oauth_entry"
    new_test = (
        "\n\ndef test_select_skips_stale_nous_agent_keys(tmp_path, monkeypatch):\n"
        "    monkeypatch.setenv(\"HERMES_HOME\", str(tmp_path / \"hermes\"))\n"
        "    _write_auth_store(\n"
        "        tmp_path,\n"
        "        {\n"
        "            \"version\": 1,\n"
        "            \"credential_pool\": {\n"
        "                \"nous\": [\n"
        "                    {\n"
        "                        \"id\": \"stale\",\n"
        "                        \"label\": \"stale-manual\",\n"
        "                        \"auth_type\": \"oauth\",\n"
        "                        \"priority\": 0,\n"
        "                        \"source\": \"manual:device_code\",\n"
        "                        \"access_token\": \"portal-token-stale\",\n"
        "                        \"refresh_token\": \"refresh-stale\",\n"
        "                        \"agent_key\": \"agent-key-stale\",\n"
        "                        \"agent_key_expires_at\": \"2026-04-11T19:06:29.675Z\",\n"
        "                        \"inference_base_url\": \"https://inference-api.nousresearch.com/v1\",\n"
        "                    },\n"
        "                    {\n"
        "                        \"id\": \"fresh\",\n"
        "                        \"label\": \"fresh-device\",\n"
        "                        \"auth_type\": \"oauth\",\n"
        "                        \"priority\": 1,\n"
        "                        \"source\": \"device_code\",\n"
        "                        \"access_token\": \"portal-token-fresh\",\n"
        "                        \"refresh_token\": \"refresh-fresh\",\n"
        "                        \"agent_key\": \"agent-key-fresh\",\n"
        "                        \"agent_key_expires_at\": \"2026-04-24T00:04:33.001Z\",\n"
        "                        \"inference_base_url\": \"https://inference-api.nousresearch.com/v1\",\n"
        "                    },\n"
        "                ]\n"
        "            },\n"
        "        },\n"
        "    )\n"
        "\n"
        "    from agent.credential_pool import load_pool\n"
        "\n"
        "    pool = load_pool(\"nous\")\n"
        "    entry = pool.select()\n"
        "\n"
        "    assert entry is not None\n"
        "    assert entry.id == \"fresh\"\n"
    )
    if "def test_select_skips_stale_nous_agent_keys" not in text and marker in text:
        text = text.replace(marker, new_test + "\n\n" + marker)
        applied.append("credential_pool_tests:skip_stale_nous_entries")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_run_agent(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    deterministic_index_impl = (
        "    def _compile_user_profile_index(self) -> None:\n"
        "        if not self._memory_store or not self._user_profile_enabled:\n"
        "            return\n"
        "        entries = [str(entry).strip() for entry in getattr(self._memory_store, \"user_entries\", []) if str(entry).strip()]\n"
        "        if not entries:\n"
        "            try:\n"
        "                self._memory_store.save_user_profile_index({})\n"
        "            except Exception:\n"
        "                pass\n"
        "            return\n"
        "        normalized = self._memory_store._derive_user_profile_index_from_entries(entries)\n"
        "        try:\n"
        "            self._memory_store.save_user_profile_index(\n"
        "                {\n"
        "                    \"preferred_user_name\": str(normalized.get(\"preferred_user_name\") or \"\").strip(),\n"
        "                    \"assistant_name\": str(normalized.get(\"assistant_name\") or \"\").strip(),\n"
        "                }\n"
        "            )\n"
        "        except Exception:\n"
        "            pass\n"
    )
    old_compile = (
        "    def _compile_user_profile_index(self) -> None:\n"
        "        if not self._memory_store or not self._user_profile_enabled:\n"
        "            return\n"
        "        entries = [str(entry).strip() for entry in getattr(self._memory_store, \"user_entries\", []) if str(entry).strip()]\n"
        "        if not entries:\n"
        "            try:\n"
        "                self._memory_store.save_user_profile_index({})\n"
        "            except Exception:\n"
        "                pass\n"
        "            return\n"
        "        messages = [\n"
        "            {\n"
        "                \"role\": \"system\",\n"
        "                \"content\": (\n"
        "                    \"You compile a tiny reusable index from explicit user-taught profile truth. \"\n"
        "                    \"Return JSON only with keys preferred_user_name and assistant_name. \"\n"
        "                    \"Fill a key only when the explicit entries make it clearly usable later. \"\n"
        "                    \"For preferred_user_name, return the direct reusable address form that should be used to address \"\n"
        "                    \"the user in later replies, not an inflected sentence fragment. If a stored entry already uses a \"\n"
        "                    \"canonical naming label but its value is still a sentence fragment or grammatically inflected \"\n"
        "                    \"variant, repair it to the shortest reusable standalone name or address form. Do not return \"\n"
        "                    \"surrounding teaching words, quoted clauses, or case-marked variants when a direct reusable form \"\n"
        "                    \"is recoverable from the explicit entry. \"\n"
        "                    \"For assistant_name, return the assistant's own name only if explicit user-taught truth makes it clear. \"\n"
        "                    \"Do not infer age, language, style, or any other fields. \"\n"
        "                    \"If unclear, return empty strings.\"\n"
        "                ),\n"
        "            },\n"
        "            {\"role\": \"user\", \"content\": json.dumps({\"entries\": entries}, ensure_ascii=False)},\n"
        "        ]\n"
        "        try:\n"
        "            from agent.auxiliary_client import get_text_auxiliary_client, _get_task_timeout\n"
        "\n"
        "            aux_client, aux_model = get_text_auxiliary_client(\"user_profile_index\")\n"
        "            request_client = aux_client or self._ensure_primary_openai_client(reason=\"user_profile_index\")\n"
        "            request_model = aux_model or self.model\n"
        "            response = self._side_chat_completion(\n"
        "                reason=\"user_profile_index\",\n"
        "                client=request_client,\n"
        "                timeout=_get_task_timeout(\"user_profile_index\"),\n"
        "                model=request_model,\n"
        "                messages=messages,\n"
        "                temperature=0,\n"
        "                **self._max_tokens_param(512),\n"
        "            )\n"
        "            content = \"\"\n"
        "            if hasattr(response, \"choices\") and response.choices:\n"
        "                content = str(getattr(response.choices[0].message, \"content\", \"\") or \"\")\n"
        "            payload = self._extract_json_object(content)\n"
        "            normalized = {\n"
        "                \"preferred_user_name\": str(payload.get(\"preferred_user_name\") or \"\").strip(),\n"
        "                \"assistant_name\": str(payload.get(\"assistant_name\") or \"\").strip(),\n"
        "            }\n"
        "            # Fail closed: do not erase an existing compiled index when the\n"
        "            # model returns nothing usable for an otherwise populated profile.\n"
        "            if not any(normalized.values()):\n"
        "                return\n"
        "            self._memory_store.save_user_profile_index(normalized)\n"
        "        except Exception:\n"
        "            pass\n"
    )
    if (
        "self._memory_store._derive_user_profile_index_from_entries(entries)" not in text
        and old_compile in text
    ):
        text = _replace_once(text, old_compile, deterministic_index_impl, label="run_agent deterministic user-profile index", path=path)
        applied.append("run_agent:deterministic_user_profile_index")

    upstream_interrupted_sync_guard = (
        "def _sync_external_memory_for_turn(" in text
        and "Interrupted turns are skipped entirely (#15218)" in text
        and "if interrupted:\n            return" in text
    )
    sync_guard = "if self._memory_manager and final_response and original_user_message and not interrupted:"
    if not upstream_interrupted_sync_guard and sync_guard not in text:
        old_sync = (
            "        if self._memory_manager and final_response and original_user_message:\n"
            "            try:\n"
            "                self._memory_manager.sync_all(original_user_message, final_response)\n"
            "                self._memory_manager.queue_prefetch_all(original_user_message)\n"
            "            except Exception:\n"
            "                pass\n"
        )
        new_sync = (
            "        if self._memory_manager and final_response and original_user_message and not interrupted:\n"
            "            try:\n"
            "                self._memory_manager.sync_all(original_user_message, final_response)\n"
            "                self._memory_manager.queue_prefetch_all(original_user_message)\n"
            "            except Exception:\n"
            "                pass\n"
        )
        text = _replace_once(text, old_sync, new_sync, label="run_agent interrupted transcript hygiene", path=path)
        applied.append("run_agent:skip_interrupted_transcript_sync")

    background_origin = '                    review_agent._brainstack_memory_write_origin = "background_review"\n'
    native_background_origin = 'review_agent._memory_write_origin = "background_review"'
    if background_origin not in text and native_background_origin not in text:
        old_review_setup = (
            "                    review_agent._memory_store = self._memory_store\n"
            "                    review_agent._memory_enabled = self._memory_enabled\n"
            "                    review_agent._user_profile_enabled = self._user_profile_enabled\n"
            "                    review_agent._memory_nudge_interval = 0\n"
            "                    review_agent._skill_nudge_interval = 0\n"
        )
        new_review_setup = (
            "                    review_agent._memory_store = self._memory_store\n"
            "                    review_agent._memory_enabled = self._memory_enabled\n"
            "                    review_agent._user_profile_enabled = self._user_profile_enabled\n"
            "                    review_agent._brainstack_memory_write_origin = \"background_review\"\n"
            "                    review_agent._memory_nudge_interval = 0\n"
            "                    review_agent._skill_nudge_interval = 0\n"
        )
        text = _replace_once(
            text,
            old_review_setup,
            new_review_setup,
            label="run_agent background-review write origin tag",
            path=path,
        )
        applied.append("run_agent:background_review_write_origin")

    metadata_bridge_impl = (
        "                    memory_write_metadata = None\n"
        "                    write_origin = str(getattr(self, \"_brainstack_memory_write_origin\", \"\") or \"\").strip()\n"
        "                    if write_origin:\n"
        "                        memory_write_metadata = {\"write_origin\": write_origin}\n"
        "                    self._memory_manager.on_memory_write(\n"
        "                        function_args.get(\"action\", \"\"),\n"
        "                        target,\n"
        "                        function_args.get(\"content\", \"\"),\n"
        "                        metadata=memory_write_metadata,\n"
        "                    )\n"
    )
    if metadata_bridge_impl not in text:
        old_bridge = (
            "                    self._memory_manager.on_memory_write(\n"
            "                        function_args.get(\"action\", \"\"),\n"
            "                        target,\n"
            "                        function_args.get(\"content\", \"\"),\n"
            "                    )\n"
        )
        text = text.replace(old_bridge, metadata_bridge_impl, 2)
        if metadata_bridge_impl in text:
            applied.append("run_agent:memory_write_metadata_bridge")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _canonicalize_runtime_user_profile(config_path: Path, dry_run: bool) -> dict[str, Any]:
    runtime_root = config_path.parent
    user_path = runtime_root / "memories" / "USER.md"
    index_path = runtime_root / "memories" / "USER_PROFILE_INDEX.json"
    if not user_path.exists():
        return {"status": "skipped", "reason": "user_profile_missing", "path": str(user_path)}

    raw = user_path.read_text(encoding="utf-8")
    delimiter = "\n§\n"
    entries = [entry.strip() for entry in raw.split(delimiter) if entry.strip()]
    if not entries:
        return {"status": "no_entries", "path": str(user_path)}

    legacy_name_re = re.compile(r"^User's Discord name is (?P<handle>.+?) but should be addressed as (?P<name>.+)$")
    legacy_address_re = re.compile(r"^Address user as (?P<name>.+), not (?P<handle>.+)$")

    def _rehydrate_rule_pack(text: str) -> str:
        prefix = "Communication rules:"
        if not text.startswith(prefix):
            return text
        body = text[len(prefix):].strip()
        normalized_body = body.replace("\\n", "\n").strip()
        if not normalized_body:
            return text
        if "\n" in normalized_body:
            return prefix + "\n" + normalized_body
        body = normalized_body
        matches = list(re.finditer(r"(?<!\S)\d+\.\s", body))
        if len(matches) < 2:
            return text
        parts: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            part = body[start:end].strip()
            if part:
                parts.append(part)
        if len(parts) < 2:
            return text
        return prefix + "\n" + "\n".join(parts)

    rewritten: list[str] = []
    preferred_user_name = ""
    assistant_name = ""
    discord_handle = ""
    changed = False

    for entry in entries:
        text = str(entry).strip()
        if not text:
            continue
        if text.startswith("Preferred user name:"):
            preferred_user_name = text.partition(":")[2].strip()
            continue
        if text.startswith("Assistant name:"):
            assistant_name = text.partition(":")[2].strip()
            continue
        if text.startswith("Discord handle:"):
            discord_handle = text.partition(":")[2].strip()
            continue

        match = legacy_name_re.match(text)
        if match:
            preferred_user_name = preferred_user_name or match.group("name").strip()
            discord_handle = discord_handle or match.group("handle").strip()
            changed = True
            continue

        match = legacy_address_re.match(text)
        if match:
            preferred_user_name = preferred_user_name or match.group("name").strip()
            discord_handle = discord_handle or match.group("handle").strip()
            changed = True
            continue

        canonical = _rehydrate_rule_pack(text)
        if canonical != text:
            changed = True
        rewritten.append(canonical)

    canonical_entries: list[str] = []
    seen: set[str] = set()

    def _append(entry: str) -> None:
        normalized = str(entry).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        canonical_entries.append(normalized)

    if preferred_user_name:
        _append(f"Preferred user name: {preferred_user_name}")
    if assistant_name:
        _append(f"Assistant name: {assistant_name}")
    if discord_handle:
        _append(f"Discord handle: {discord_handle}")
    for entry in rewritten:
        _append(entry)

    serialized = delimiter.join(canonical_entries)
    current_index = {}
    if index_path.exists():
        try:
            current_index = json.loads(index_path.read_text(encoding="utf-8").strip() or "{}")
            if not isinstance(current_index, dict):
                current_index = {}
        except (OSError, json.JSONDecodeError):
            current_index = {}
    new_index = {
        "preferred_user_name": preferred_user_name,
        "assistant_name": assistant_name,
    }
    if canonical_entries != entries:
        changed = True
    if current_index != new_index:
        changed = True

    if changed and not dry_run:
        user_path.write_text(serialized, encoding="utf-8")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(new_index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    return {
        "status": "updated" if changed else "already_canonical",
        "path": str(user_path),
        "index_path": str(index_path),
        "entry_count": len(canonical_entries),
        "preferred_user_name": preferred_user_name,
        "assistant_name": assistant_name,
        "discord_handle": discord_handle,
    }


def _canonicalize_runtime_brainstack_db(
    target: Path,
    config_path: Path,
    *,
    python_bin: Path | None,
    dry_run: bool,
) -> dict[str, Any]:
    runtime_root = config_path.parent
    db_path = runtime_root / "brainstack" / "brainstack.db"
    if not db_path.exists():
        return {"status": "skipped", "reason": "brainstack_db_missing", "path": str(db_path)}
    if dry_run:
        return {"status": "planned", "path": str(db_path)}

    python_exec = str(python_bin or sys.executable)
    script = f"""
import json
import sys
sys.path.insert(0, {str(target)!r})
from plugins.memory.brainstack.db import BrainstackStore

store = BrainstackStore({str(db_path)!r})
store.open()
conn = store.conn
before = {{
    "style_contract_behavior_rows": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ?",
        ("preference:style_contract",),
    ).fetchone()[0],
    "compiled_behavior_policies": conn.execute(
        "select count(*) from compiled_behavior_policies"
    ).fetchone()[0],
    "interrupt_transcript_hits": conn.execute(
        "select count(*) from transcript_entries where content like '%Assistant: Operation interrupted:%' or content like '%Assistant: Session reset.%'"
    ).fetchone()[0],
}}
transcript_scrub = store.scrub_transcript_hygiene_residue()
behavior_residue = store.purge_style_contract_behavior_residue()
result = {{
    "before": before,
    "transcript_scrub": transcript_scrub,
    "behavior_residue": behavior_residue,
    "style_contract_behavior_rows": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ?",
        ("preference:style_contract",),
    ).fetchone()[0],
    "active_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "active"),
    ).fetchone()[0],
    "superseded_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "superseded"),
    ).fetchone()[0],
    "quarantined_behavior_contracts": conn.execute(
        "select count(*) from behavior_contracts where stable_key = ? and status = ?",
        ("preference:style_contract", "quarantined"),
    ).fetchone()[0],
    "compiled_behavior_policies": conn.execute(
        "select count(*) from compiled_behavior_policies"
    ).fetchone()[0],
    "interrupt_transcript_hits": conn.execute(
        "select count(*) from transcript_entries where content like '%Assistant: Operation interrupted:%' or content like '%Assistant: Session reset.%'"
    ).fetchone()[0],
    "style_contract_profile_items": conn.execute(
        "select count(*) from profile_items where stable_key like 'preference:style_contract%'"
    ).fetchone()[0],
    "applied_migrations": [
        row[0]
        for row in conn.execute(
            "select name from applied_migrations where name like 'style_contract%' or name like 'behavior%' order by name"
        ).fetchall()
    ],
}}
store.close()
print(json.dumps(result, ensure_ascii=False))
"""
    proc = subprocess.run([python_exec, "-c", script], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Brainstack DB canonicalization failed for "
            f"{db_path}: {proc.stderr.strip() or proc.stdout.strip() or 'unknown error'}"
        )
    payload = json.loads(proc.stdout.strip() or "{}")
    payload["status"] = "updated"
    payload["path"] = str(db_path)
    return payload


def _patch_gateway_run(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    hooks_anchor = "    # -- Setup skill availability ----------------------------------------\n\n    def _has_setup_skill(self) -> bool:\n"
    hooks_inject = (
        "    def _maintenance_agent_toolsets(self) -> list[str]:\n"
        "        return [\"memory\"]\n"
        "\n"
        "    def _derive_gateway_runtime_state(self) -> str:\n"
        "        if self.adapters:\n"
        "            return \"degraded\" if self._failed_platforms else \"running\"\n"
        "        if self._failed_platforms:\n"
        "            return \"reconnecting\"\n"
        "        if self._running:\n"
        "            return \"idle\"\n"
        "        return \"starting\"\n"
        "\n"
        "    def _write_gateway_runtime_status(\n"
        "        self,\n"
        "        *,\n"
        "        gateway_state: str | None = None,\n"
        "        exit_reason: str | None = None,\n"
        "        platform: str | None = None,\n"
        "        platform_state: str | None = None,\n"
        "        error_code: str | None = None,\n"
        "        error_message: str | None = None,\n"
        "    ) -> None:\n"
        "        try:\n"
        "            from gateway.status import write_runtime_status\n"
        "\n"
        "            write_runtime_status(\n"
        "                gateway_state=gateway_state if gateway_state is not None else self._derive_gateway_runtime_state(),\n"
        "                exit_reason=exit_reason,\n"
        "                platform=platform,\n"
        "                platform_state=platform_state,\n"
        "                error_code=error_code,\n"
        "                error_message=error_message,\n"
        "            )\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "    def _finalize_session_memory_sync(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        del session_key\n"
        "        self._flush_memories_for_session(session_id)\n"
        "\n"
        "    async def _async_finalize_session_memory(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        loop = asyncio.get_event_loop()\n"
        "        await loop.run_in_executor(\n"
        "            None,\n"
        "            self._finalize_session_memory_sync,\n"
        "            session_key,\n"
        "            session_id,\n"
        "        )\n"
        "\n"
        + hooks_anchor
    )
    if "def _maintenance_agent_toolsets(self) -> list[str]:" not in text:
        text = _replace_once(text, hooks_anchor, hooks_inject, label="gateway helper block", path=path)
        applied.append("gateway:add_boundary_helpers")

    replacements = [
        (
            "        try:\n            from gateway.status import write_runtime_status\n            write_runtime_status(gateway_state=\"starting\", exit_reason=None)\n        except Exception:\n            pass\n",
            "        self._write_gateway_runtime_status(gateway_state=\"starting\", exit_reason=None)\n",
            "gateway:startup_status",
        ),
        (
            "                                    enabled_toolsets=[\"memory\"],\n",
            "                                    enabled_toolsets=self._maintenance_agent_toolsets(),\n",
            "gateway:hygiene_toolsets",
        ),
        (
            "                enabled_toolsets=[\"memory\"],\n",
            "                enabled_toolsets=self._maintenance_agent_toolsets(),\n",
            "gateway:compress_toolsets",
        ),
        (
            "                        await self._async_flush_memories(entry.session_id)\n",
            "                        await self._async_finalize_session_memory(key, entry.session_id)\n",
            "gateway:expiry_finalize",
        ),
        (
            "                _flush_task = asyncio.create_task(\n                    self._async_flush_memories(old_entry.session_id)\n                )\n",
            "                _flush_task = asyncio.create_task(\n                    self._async_finalize_session_memory(session_key, old_entry.session_id)\n                )\n",
            "gateway:reset_finalize",
        ),
        (
            "            _flush_task = asyncio.create_task(\n                self._async_flush_memories(current_entry.session_id)\n            )\n",
            "            _flush_task = asyncio.create_task(\n                self._async_finalize_session_memory(session_key, current_entry.session_id)\n            )\n",
            "gateway:resume_finalize",
        ),
        (
            "                        logger.debug(\n                            \"Memory flush completed for session %s\",\n",
            "                        self._evict_cached_agent(key)\n                        logger.debug(\n                            \"Memory flush completed for session %s\",\n",
            "gateway:evict_cached_expiry",
        ),
        (
            "            logger.info(\"Connecting to %s...\", platform.value)\n            try:\n",
            "            logger.info(\"Connecting to %s...\", platform.value)\n            self._write_gateway_runtime_status(\n                gateway_state=\"starting\",\n                exit_reason=None,\n                platform=platform.value,\n                platform_state=\"connecting\",\n                error_code=None,\n                error_message=None,\n            )\n            try:\n",
            "gateway:connect_starting_status",
        ),
        (
            "                    connected_count += 1\n                    logger.info(\"✓ %s connected\", platform.value)\n",
            "                    connected_count += 1\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"starting\",\n                        exit_reason=None,\n                        platform=platform.value,\n                        platform_state=\"connected\",\n                        error_code=None,\n                        error_message=None,\n                    )\n                    logger.info(\"✓ %s connected\", platform.value)\n",
            "gateway:connect_success_status",
        ),
        (
            "                    if adapter.has_fatal_error:\n                        target = (\n",
            "                    if adapter.has_fatal_error:\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"starting\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"retrying\" if adapter.fatal_error_retryable else \"failed\",\n                            error_code=adapter.fatal_error_code,\n                            error_message=adapter.fatal_error_message,\n                        )\n                        target = (\n",
            "gateway:connect_fatal_status",
        ),
        (
            "                    else:\n                        startup_retryable_errors.append(\n",
            "                    else:\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"starting\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"retrying\",\n                            error_code=\"connect_failed\",\n                            error_message=\"failed to connect\",\n                        )\n                        startup_retryable_errors.append(\n",
            "gateway:connect_retry_status",
        ),
        (
            "            except Exception as e:\n                logger.error(\"✗ %s error: %s\", platform.value, e)\n                startup_retryable_errors.append(f\"{platform.value}: {e}\")\n",
            "            except Exception as e:\n                logger.error(\"✗ %s error: %s\", platform.value, e)\n                self._write_gateway_runtime_status(\n                    gateway_state=\"starting\",\n                    exit_reason=None,\n                    platform=platform.value,\n                    platform_state=\"retrying\",\n                    error_code=\"connect_exception\",\n                    error_message=str(e),\n                )\n                startup_retryable_errors.append(f\"{platform.value}: {e}\")\n",
            "gateway:connect_exception_status",
        ),
        (
            "        self._running = True\n        try:\n            from gateway.status import write_runtime_status\n            write_runtime_status(gateway_state=\"running\", exit_reason=None)\n        except Exception:\n            pass\n",
            "        self._running = True\n        self._write_gateway_runtime_status(\n            gateway_state=\"degraded\" if self._failed_platforms else \"running\",\n            exit_reason=None,\n        )\n",
            "gateway:running_status",
        ),
        (
            "                logger.info(\n                    \"%s queued for background reconnection\",\n                    adapter.platform.value,\n                )\n\n        if not self.adapters and not self._failed_platforms:\n",
            "                logger.info(\n                    \"%s queued for background reconnection\",\n                    adapter.platform.value,\n                )\n\n        self._write_gateway_runtime_status(\n            platform=adapter.platform.value,\n            platform_state=\"retrying\" if adapter.fatal_error_retryable else \"failed\",\n            error_code=adapter.fatal_error_code,\n            error_message=adapter.fatal_error_message,\n        )\n\n        if not self.adapters and not self._failed_platforms:\n",
            "gateway:fatal_status",
        ),
        (
            "        if not self.adapters and not self._failed_platforms:\n            self._exit_reason = adapter.fatal_error_message or \"All messaging adapters disconnected\"\n",
            "        if not self.adapters and not self._failed_platforms:\n            self._exit_reason = adapter.fatal_error_message or \"All messaging adapters disconnected\"\n            self._write_gateway_runtime_status(\n                gateway_state=\"startup_failed\",\n                exit_reason=self._exit_reason,\n                platform=adapter.platform.value,\n                platform_state=\"failed\",\n                error_code=adapter.fatal_error_code,\n                error_message=adapter.fatal_error_message,\n            )\n",
            "gateway:fatal_exit_status",
        ),
        (
            "                logger.info(\n                    \"Reconnecting %s (attempt %d/%d)...\",\n                    platform.value, attempt, _MAX_ATTEMPTS,\n                )\n\n                try:\n",
            "                logger.info(\n                    \"Reconnecting %s (attempt %d/%d)...\",\n                    platform.value, attempt, _MAX_ATTEMPTS,\n                )\n                self._write_gateway_runtime_status(\n                    gateway_state=\"reconnecting\" if not self.adapters else \"degraded\",\n                    exit_reason=None,\n                    platform=platform.value,\n                    platform_state=\"retrying\",\n                    error_code=None,\n                    error_message=None,\n                )\n\n                try:\n",
            "gateway:reconnect_attempt_status",
        ),
        (
            "                        self.delivery_router.adapters = self.adapters\n                        del self._failed_platforms[platform]\n                        logger.info(\"✓ %s reconnected successfully\", platform.value)\n",
            "                        self.delivery_router.adapters = self.adapters\n                        del self._failed_platforms[platform]\n                        self._write_gateway_runtime_status(\n                            gateway_state=\"degraded\" if self._failed_platforms else \"running\",\n                            exit_reason=None,\n                            platform=platform.value,\n                            platform_state=\"connected\",\n                            error_code=None,\n                            error_message=None,\n                        )\n                        logger.info(\"✓ %s reconnected successfully\", platform.value)\n",
            "gateway:reconnect_success_status",
        ),
        (
            "                            logger.warning(\n                                \"Reconnect %s: non-retryable error (%s), removing from retry queue\",\n                                platform.value, adapter.fatal_error_message,\n                            )\n                            del self._failed_platforms[platform]\n",
            "                            logger.warning(\n                                \"Reconnect %s: non-retryable error (%s), removing from retry queue\",\n                                platform.value, adapter.fatal_error_message,\n                            )\n                            del self._failed_platforms[platform]\n                            self._write_gateway_runtime_status(\n                                gateway_state=\"degraded\" if self.adapters else \"startup_failed\",\n                                exit_reason=None if self.adapters else adapter.fatal_error_message,\n                                platform=platform.value,\n                                platform_state=\"failed\",\n                                error_code=adapter.fatal_error_code,\n                                error_message=adapter.fatal_error_message,\n                            )\n",
            "gateway:reconnect_nonretryable_status",
        ),
        (
            "                            backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                            info[\"attempts\"] = attempt\n                            info[\"next_retry\"] = time.monotonic() + backoff\n                            logger.info(\n                                \"Reconnect %s failed, next retry in %ds\",\n                                platform.value, backoff,\n                            )\n",
            "                            backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                            info[\"attempts\"] = attempt\n                            info[\"next_retry\"] = time.monotonic() + backoff\n                            self._write_gateway_runtime_status(\n                                gateway_state=\"degraded\" if self.adapters else \"reconnecting\",\n                                exit_reason=None,\n                                platform=platform.value,\n                                platform_state=\"retrying\",\n                                error_code=adapter.fatal_error_code or \"reconnect_failed\",\n                                error_message=adapter.fatal_error_message or f\"next retry in {backoff}s\",\n                            )\n                            logger.info(\n                                \"Reconnect %s failed, next retry in %ds\",\n                                platform.value, backoff,\n                            )\n",
            "gateway:reconnect_retry_status",
        ),
        (
            "                    backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                    info[\"attempts\"] = attempt\n                    info[\"next_retry\"] = time.monotonic() + backoff\n                    logger.warning(\n                        \"Reconnect %s error: %s, next retry in %ds\",\n                        platform.value, e, backoff,\n                    )\n",
            "                    backoff = min(30 * (2 ** (attempt - 1)), _BACKOFF_CAP)\n                    info[\"attempts\"] = attempt\n                    info[\"next_retry\"] = time.monotonic() + backoff\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"degraded\" if self.adapters else \"reconnecting\",\n                        exit_reason=None,\n                        platform=platform.value,\n                        platform_state=\"retrying\",\n                        error_code=\"reconnect_exception\",\n                        error_message=str(e),\n                    )\n                    logger.warning(\n                        \"Reconnect %s error: %s, next retry in %ds\",\n                        platform.value, e, backoff,\n                    )\n",
            "gateway:reconnect_exception_status",
        ),
        (
            "                    logger.warning(\n                        \"Giving up reconnecting %s after %d attempts\",\n                        platform.value, info[\"attempts\"],\n                    )\n                    del self._failed_platforms[platform]\n                    continue\n",
            "                    logger.warning(\n                        \"Giving up reconnecting %s after %d attempts\",\n                        platform.value, info[\"attempts\"],\n                    )\n                    del self._failed_platforms[platform]\n                    self._write_gateway_runtime_status(\n                        gateway_state=\"degraded\" if self.adapters else \"startup_failed\",\n                        exit_reason=None if self.adapters else f\"{platform.value}: reconnect attempts exhausted\",\n                        platform=platform.value,\n                        platform_state=\"failed\",\n                        error_code=\"reconnect_exhausted\",\n                        error_message=f\"reconnect attempts exhausted after {info['attempts']} tries\",\n                    )\n                    continue\n",
            "gateway:reconnect_exhausted_status",
        ),
        (
            '            header = "Session reset."\n',
            '            header = "Fresh session started."\n',
            "gateway:clean_reset_header",
        ),
    ]
    for old, new, label in replacements:
        if new not in text and old in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    old_cron_ticker = (
        "def _start_cron_ticker(stop_event: threading.Event, adapters=None, loop=None, interval: int = 60):\n"
        "    \"\"\"\n"
        "    Background thread that ticks the cron scheduler at a regular interval.\n"
        "    \n"
        "    Runs inside the gateway process so cronjobs fire automatically without\n"
        "    needing a separate `hermes cron daemon` or system cron entry.\n"
        "\n"
        "    When ``adapters`` and ``loop`` are provided, passes them through to the\n"
        "    cron delivery path so live adapters can be used for E2EE rooms.\n"
        "\n"
        "    Also refreshes the channel directory every 5 minutes and prunes the\n"
        "    image/audio/document cache once per hour.\n"
        "    \"\"\"\n"
        "    from cron.scheduler import tick as cron_tick\n"
        "    from gateway.platforms.base import cleanup_image_cache, cleanup_document_cache\n"
        "\n"
        "    IMAGE_CACHE_EVERY = 60   # ticks — once per hour at default 60s interval\n"
        "    CHANNEL_DIR_EVERY = 5    # ticks — every 5 minutes\n"
        "\n"
        "    logger.info(\"Cron ticker started (interval=%ds)\", interval)\n"
        "    tick_count = 0\n"
        "    while not stop_event.is_set():\n"
        "        try:\n"
        "            cron_tick(verbose=False, adapters=adapters, loop=loop)\n"
        "        except Exception as e:\n"
        "            logger.debug(\"Cron tick error: %s\", e)\n"
        "\n"
        "        tick_count += 1\n"
        "\n"
        "        if tick_count % CHANNEL_DIR_EVERY == 0 and adapters:\n"
        "            try:\n"
        "                from gateway.channel_directory import build_channel_directory\n"
        "                build_channel_directory(adapters)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Channel directory refresh error: %s\", e)\n"
        "\n"
        "        if tick_count % IMAGE_CACHE_EVERY == 0:\n"
        "            try:\n"
        "                removed = cleanup_image_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Image cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Image cache cleanup error: %s\", e)\n"
        "            try:\n"
        "                removed = cleanup_document_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Document cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Document cache cleanup error: %s\", e)\n"
        "\n"
        "        stop_event.wait(timeout=interval)\n"
        "    logger.info(\"Cron ticker stopped\")\n"
    )
    new_cron_ticker = (
        "def _start_cron_ticker(stop_event: threading.Event, adapters=None, loop=None, interval: int = 60):\n"
        "    \"\"\"\n"
        "    Background thread that ticks the cron scheduler at a regular interval.\n"
        "    \n"
        "    Runs inside the gateway process so cronjobs fire automatically without\n"
        "    needing a separate `hermes cron daemon` or system cron entry.\n"
        "\n"
        "    When ``adapters`` and ``loop`` are provided, passes them through to the\n"
        "    cron delivery path so live adapters can be used for E2EE rooms.\n"
        "\n"
        "    Also refreshes the channel directory every 5 minutes and prunes the\n"
        "    image/audio/document cache once per hour.\n"
        "    \"\"\"\n"
        "    from cron.jobs import seconds_until_next_run\n"
        "    from cron.scheduler import tick as cron_tick, wait_for_tick_wake\n"
        "    from gateway.platforms.base import cleanup_image_cache, cleanup_document_cache\n"
        "\n"
        "    IMAGE_CACHE_INTERVAL = 60 * 60\n"
        "    CHANNEL_DIR_INTERVAL = 5 * 60\n"
        "\n"
        "    logger.info(\"Cron ticker started (interval=%ds)\", interval)\n"
        "    last_channel_refresh = time.monotonic()\n"
        "    last_cache_cleanup = time.monotonic()\n"
        "    while not stop_event.is_set():\n"
        "        try:\n"
        "            cron_tick(verbose=False, adapters=adapters, loop=loop)\n"
        "        except Exception as e:\n"
        "            logger.debug(\"Cron tick error: %s\", e)\n"
        "\n"
        "        now_mono = time.monotonic()\n"
        "\n"
        "        if adapters and (now_mono - last_channel_refresh) >= CHANNEL_DIR_INTERVAL:\n"
        "            try:\n"
        "                from gateway.channel_directory import build_channel_directory\n"
        "                build_channel_directory(adapters)\n"
        "                last_channel_refresh = now_mono\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Channel directory refresh error: %s\", e)\n"
        "\n"
        "        if (now_mono - last_cache_cleanup) >= IMAGE_CACHE_INTERVAL:\n"
        "            try:\n"
        "                removed = cleanup_image_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Image cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Image cache cleanup error: %s\", e)\n"
        "            try:\n"
        "                removed = cleanup_document_cache(max_age_hours=24)\n"
        "                if removed:\n"
        "                    logger.info(\"Document cache cleanup: removed %d stale file(s)\", removed)\n"
        "            except Exception as e:\n"
        "                logger.debug(\"Document cache cleanup error: %s\", e)\n"
        "            last_cache_cleanup = now_mono\n"
        "\n"
        "        wait_timeout = seconds_until_next_run(max_wait=float(interval))\n"
        "        wait_for_tick_wake(stop_event, timeout=wait_timeout)\n"
        "    logger.info(\"Cron ticker stopped\")\n"
    )
    if "from cron.jobs import seconds_until_next_run" not in text and old_cron_ticker in text:
        text = _replace_once(text, old_cron_ticker, new_cron_ticker, label="gateway:cron_wake_aware_ticker", path=path)
        applied.append("gateway:cron_wake_aware_ticker")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_auxiliary_client(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    old = "    resolved_model = model or cfg_model\n"
    new = (
        "    resolved_model = model or cfg_model\n"
        "    # Brainstack relies on auxiliary.flush_memories.provider: main meaning\n"
        "    # the task should inherit the agent's actual active model, not the\n"
        "    # provider default auxiliary model. Without this, a Nous-backed main\n"
        "    # provider can silently drift to a missing Gemini auxiliary default\n"
        "    # and durable Tier-2 writes fail at runtime.\n"
        "    if not resolved_model:\n"
        "        explicit_provider = str(provider or cfg_provider or \"\").strip().lower()\n"
        "        if explicit_provider == \"main\":\n"
        "            resolved_model = _read_main_model() or None\n"
    )
    if "explicit_provider == \"main\"" not in text:
        text = _replace_once(
            text,
            old,
            new,
            label="auxiliary_client main model inheritance",
            path=path,
        )
        applied.append("auxiliary_client:inherit_main_model")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        raise RuntimeError(f"Cannot parse YAML config at {path}: {exc}") from exc


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception as exc:
        raise RuntimeError("PyYAML is required to patch Hermes config.yaml") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True), encoding="utf-8")


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


def _default_config_path(target: Path) -> Path:
    candidates = _discover_agent_configs(target)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            "No Hermes agent config found. Create or select an agent first, then rerun the installer with "
            "--config <path/to/config.yaml> if needed."
        )
    rendered = ", ".join(str(path.relative_to(target)) for path in candidates)
    raise RuntimeError(
        "Multiple Hermes agent configs found. Pass --config explicitly so Brainstack installs into the right agent: "
        f"{rendered}"
    )


def _default_compose_path(target: Path, config_path: Path | None = None) -> Path:
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
            agent_name = rel.parts[0]
            agent_compose = target / f"docker-compose.{agent_name}.yml"
            if agent_compose.exists():
                return agent_compose
        if root_compose.exists():
            return root_compose

    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            "No Docker compose file found for this Hermes checkout. Pass --compose-file explicitly if you use Docker."
        )
    rendered = ", ".join(str(path.relative_to(target)) for path in candidates)
    raise RuntimeError(
        "Multiple Docker compose files found. Pass --compose-file explicitly so Brainstack patches the right runtime: "
        f"{rendered}"
    )


def _docker_runtime_home_dir(target: Path, config_path: Path) -> Path:
    try:
        rel = config_path.relative_to(target / "hermes-config")
    except ValueError as exc:
        raise RuntimeError(
            "Docker runtime requires an agent home like hermes-config/<agent>/config.yaml. "
            "Root-level config.yaml is fine for local mode, but Docker needs a dedicated agent directory."
        ) from exc
    if len(rel.parts) < 2:
        raise RuntimeError(
            "Docker runtime requires an agent home like hermes-config/<agent>/config.yaml."
        )
    return target / "hermes-config" / rel.parts[0]


def _sanitize_compose_slug(name: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return cleaned or "brainstack"


def _generated_compose_path(target: Path, config_path: Path) -> Path:
    runtime_home = _docker_runtime_home_dir(target, config_path)
    return target / f"docker-compose.{_sanitize_compose_slug(runtime_home.name)}.yml"


def _patch_config(config_path: Path, dry_run: bool) -> dict[str, Any]:
    config = _load_yaml(config_path)
    config.setdefault("memory", {})
    if not isinstance(config["memory"], dict):
        raise RuntimeError("config.yaml has non-object `memory` section")
    config["memory"]["provider"] = "brainstack"
    config["memory"]["memory_enabled"] = True
    config["memory"]["user_profile_enabled"] = True
    config.setdefault("plugins", {})
    if not isinstance(config["plugins"], dict):
        raise RuntimeError("config.yaml has non-object `plugins` section")
    brainstack = config["plugins"].setdefault("brainstack", {})
    if not isinstance(brainstack, dict):
        brainstack = {}
        config["plugins"]["brainstack"] = brainstack
    brainstack.setdefault("db_path", "$HERMES_HOME/brainstack/brainstack.db")
    brainstack.setdefault("graph_backend", "kuzu")
    brainstack.setdefault("graph_db_path", "$HERMES_HOME/brainstack/brainstack.kuzu")
    brainstack.setdefault("corpus_backend", "chroma")
    brainstack.setdefault("corpus_db_path", "$HERMES_HOME/brainstack/brainstack.chroma")
    brainstack.setdefault("profile_prompt_limit", 6)
    brainstack.setdefault("profile_match_limit", 4)
    brainstack.setdefault("continuity_recent_limit", 4)
    brainstack.setdefault("continuity_match_limit", 4)
    brainstack.setdefault("transcript_match_limit", 1)
    brainstack.setdefault("transcript_char_budget", 280)
    brainstack.setdefault("graph_match_limit", 6)
    brainstack.setdefault("corpus_match_limit", 4)
    brainstack.setdefault("corpus_char_budget", 700)
    config.setdefault("auxiliary", {})
    if not isinstance(config["auxiliary"], dict):
        raise RuntimeError("config.yaml has non-object `auxiliary` section")
    flush_memories = config["auxiliary"].setdefault("flush_memories", {})
    if not isinstance(flush_memories, dict):
        flush_memories = {}
        config["auxiliary"]["flush_memories"] = flush_memories
    flush_provider = str(flush_memories.get("provider") or "").strip().lower()
    if not flush_provider or flush_provider == "auto":
        flush_memories["provider"] = "main"
    config.setdefault("agent", {})
    if not isinstance(config["agent"], dict):
        raise RuntimeError("config.yaml has non-object `agent` section")
    agent = config["agent"]

    def _normalized_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    gateway_timeout = _normalized_int(agent.get("gateway_timeout"))
    gateway_timeout_warning = _normalized_int(agent.get("gateway_timeout_warning"))
    if gateway_timeout in {None, 1800}:
        agent["gateway_timeout"] = 120
    if gateway_timeout_warning in {None, 900}:
        agent["gateway_timeout_warning"] = 30
    if not dry_run:
        _write_yaml(config_path, config)
    return {
        "config_path": str(config_path),
        "memory_provider": "brainstack",
        "memory_enabled": True,
        "user_profile_enabled": True,
        "flush_memories_provider": str(flush_memories.get("provider") or ""),
        "gateway_timeout": agent.get("gateway_timeout"),
        "gateway_timeout_warning": agent.get("gateway_timeout_warning"),
    }


def _write_manifest(target: Path, manifest: dict[str, Any], dry_run: bool) -> None:
    if dry_run:
        return
    path = target / ".brainstack-install-manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _relative_to_target_or_absolute(target: Path, path: Path) -> str:
    try:
        return str(path.relative_to(target))
    except ValueError:
        return str(path)


def _write_docker_start_script(target: Path, config_path: Path, compose_path: Path, dry_run: bool) -> Path:
    script_path = target / "scripts" / "hermes-brainstack-start.sh"
    legacy_path = target / "scripts" / "brainstack-start.sh"
    config_ref = _relative_to_target_or_absolute(target, config_path)
    compose_ref = _relative_to_target_or_absolute(target, compose_path)
    content = """#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

CONFIG_FILE="${HERMES_CONFIG_FILE:-$REPO_ROOT/__CONFIG_REF__}"
COMPOSE_FILE="${HERMES_COMPOSE_FILE:-$REPO_ROOT/__COMPOSE_REF__}"
HERMES_HOME_DEFAULT=$(dirname -- "$CONFIG_FILE")
HERMES_HOME_DIR="${HERMES_HOME_DIR:-$HERMES_HOME_DEFAULT}"
HERMES_UID="${HERMES_UID:-$(id -u)}"
HERMES_GID="${HERMES_GID:-$(id -g)}"
export HERMES_UID HERMES_GID

SERVICE="${HERMES_DOCKER_SERVICE:-}"
if [ -z "$SERVICE" ] && [ -f "$COMPOSE_FILE" ]; then
  SERVICE=$(awk '/^[[:space:]]{2}[A-Za-z0-9_.-]+:$/ {gsub(":","",$1); print $1; exit}' "$COMPOSE_FILE")
fi

dc() {
  if [ -n "$SERVICE" ]; then
    docker compose -f "$COMPOSE_FILE" "$@" "$SERVICE"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

ACTION="${1:-start}"
HEALTHCHECK="$REPO_ROOT/scripts/hermes-gateway-healthcheck.py"

wait_for_ready() {
  if [ ! -f "$HEALTHCHECK" ]; then
    return 0
  fi
  i=0
  while [ "$i" -lt 45 ]; do
    if HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" --quiet; then
      HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK"
      return 0
    fi
    i=$((i + 1))
    sleep 2
  done
  HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" || true
  return 1
}

show_status() {
  docker compose -f "$COMPOSE_FILE" ps
  if [ -f "$HEALTHCHECK" ]; then
    HERMES_HOME="$HERMES_HOME_DIR" python3 "$HEALTHCHECK" || true
  fi
}

confirm_destructive_reset() {
  echo "======================================"
  echo "WARNING: DELETE EVERY MEMORY"
  echo "======================================"
  echo "Ez torolni fogja:"
  echo "- Brainstack adatbazist"
  echo "- session replay fajlokat"
  echo "- state.db tartalmat"
  echo "- memories cache-t"
  echo "======================================"
  printf "Ird be pontosan hogy DELETE: "
  read -r CONFIRM
  if [ "$CONFIRM" != "DELETE" ]; then
    echo "Megszakitva."
    exit 1
  fi
}

purge_runtime_state() {
  CLEANUP_SERVICE="$SERVICE"
  if [ -z "$CLEANUP_SERVICE" ]; then
    echo "Nincs egyertelmuen detektalhato compose service. Add meg HERMES_DOCKER_SERVICE kornyezeti valtozokent."
    exit 1
  fi
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh "$CLEANUP_SERVICE" -lc '
    rm -f \
      /opt/data/gateway_state.json \
      /opt/data/gateway.pid \
      /opt/data/channel_directory.json \
      /opt/data/discord_threads.json \
      /opt/data/.skills_prompt_snapshot.json \
      /opt/data/state.db \
      /opt/data/state.db-shm \
      /opt/data/state.db-wal \
      /opt/data/brainstack/brainstack.db \
      /opt/data/brainstack/brainstack.db-shm \
      /opt/data/brainstack/brainstack.db-wal
    rm -rf /opt/data/sessions /opt/data/memories
    mkdir -p /opt/data/sessions /opt/data/memories /opt/data/brainstack
  '
}

case "$ACTION" in
  start)
    dc up -d
    wait_for_ready
    ;;
  rebuild)
    dc up -d --build
    wait_for_ready
    ;;
  full|full-rebuild)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull "$SERVICE"
      docker compose -f "$COMPOSE_FILE" up -d "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" build --no-cache --pull
      docker compose -f "$COMPOSE_FILE" up -d
    fi
    wait_for_ready
    ;;
  stop)
    dc stop
    ;;
  purge|clear-memory|clear-state)
    confirm_destructive_reset
    dc stop || true
    purge_runtime_state
    ;;
  reset)
    confirm_destructive_reset
    dc stop || true
    purge_runtime_state
    dc up -d
    wait_for_ready
    ;;
  status)
    show_status
    ;;
  logs)
    if [ -n "$SERVICE" ]; then
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f "$SERVICE"
    else
      docker compose -f "$COMPOSE_FILE" logs --tail 200 -f
    fi
    ;;
  *)
    echo "Usage: $0 [start|rebuild|full|stop|purge|reset|status|logs]" >&2
    exit 1
    ;;
esac
"""
    content = content.replace("__CONFIG_REF__", config_ref).replace("__COMPOSE_REF__", compose_ref)
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
        if legacy_path.exists():
            legacy_path.unlink()
    return script_path


def _write_docker_compose_file(target: Path, config_path: Path, compose_path: Path, dry_run: bool) -> Path:
    runtime_home = _docker_runtime_home_dir(target, config_path)
    runtime_ref = _relative_to_target_or_absolute(target, runtime_home)
    workspace_ref = "runtime/workspace"
    service_slug = _sanitize_compose_slug(runtime_home.name)
    content = f"""name: hermes-{service_slug}

services:
  hermes-{service_slug}:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: hermes-{service_slug}
    working_dir: /opt/data
    restart: unless-stopped
    network_mode: host
    command: ["gateway", "run", "--replace"]
    environment:
      HERMES_HOME: /opt/data
      HERMES_ENABLE_PROJECT_PLUGINS: "true"
      HERMES_UID: "${{HERMES_UID:-1000}}"
      HERMES_GID: "${{HERMES_GID:-1000}}"
    volumes:
      - ./{runtime_ref}:/opt/data
      - ./{workspace_ref}:/workspace
    healthcheck:
      test: ["CMD", "python3", "/opt/hermes/scripts/hermes-gateway-healthcheck.py", "--quiet"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
"""
    if not dry_run:
        compose_path.parent.mkdir(parents=True, exist_ok=True)
        compose_path.write_text(content, encoding="utf-8")
    return compose_path


def _patch_compose_runtime_identity(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    if 'HERMES_UID:' in text and 'HERMES_GID:' in text:
        return applied
    anchors = [
        '      HERMES_ENABLE_PROJECT_PLUGINS: "true"\n',
        "      HERMES_ENABLE_PROJECT_PLUGINS: 'true'\n",
    ]
    inject = (
        '      HERMES_ENABLE_PROJECT_PLUGINS: "true"\n'
        '      HERMES_UID: "${HERMES_UID:-1000}"\n'
        '      HERMES_GID: "${HERMES_GID:-1000}"\n'
    )
    for anchor in anchors:
        if anchor in text:
            text = text.replace(anchor, inject, 1)
            applied.append("compose:runtime_identity_mapping")
            break
    if not applied:
        raise RuntimeError(f"Installer patch anchor missing for compose runtime identity in {path}")
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_dockerignore(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if "hermes-config/\nruntime/\n" in text:
        return []
    block = (
        "# Runtime data mounted into the container at /opt/data or /workspace.\n"
        "# These must stay out of the image build context:\n"
        "# - they are not needed for image construction\n"
        "# - they may have restrictive ownership from the running container user\n"
        "# - including them can break rebuilds on host-side permission checks\n"
        "hermes-config/\n"
        "runtime/\n\n"
    )
    anchor = "*.md\n"
    if anchor not in text:
        raise RuntimeError(f"Installer patch anchor missing for dockerignore in {path}")
    text = text.replace(anchor, block + anchor, 1)
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["dockerignore:exclude_runtime_state"]


def _patch_dockerfile_backend_dependencies(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    backend_packages = " ".join(sorted(set(BACKEND_DEPENDENCIES.values())))
    install_line = f'uv pip install --no-cache-dir {backend_packages}'
    if install_line in text:
        return []
    current_backend_line = "uv pip install --no-cache-dir chromadb kuzu"
    upgraded_backend_line = "uv pip install --no-cache-dir chromadb croniter kuzu"
    if current_backend_line in text and upgraded_backend_line not in text:
        text = text.replace(current_backend_line, upgraded_backend_line, 1)
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        return ["dockerfile:install_runtime_dependencies"]
    if (
        "uv pip install --no-cache-dir -r /tmp/requirements.txt" in text
        and upgraded_backend_line in text
    ):
        # Newer Hermes Dockerfiles already install core requirements from the
        # lock export and keep runtime extras that Brainstack depends on in a
        # dedicated backend layer, so no further patch is needed.
        return []
    anchor = '    uv pip install --no-cache-dir -e ".[all]"\n'
    if anchor not in text:
        raise RuntimeError(f"Installer patch anchor missing for docker backend deps in {path}")
    replacement = anchor + f"RUN {install_line}\n"
    text = text.replace(anchor, replacement, 1)
    if not dry_run:
        path.write_text(text, encoding="utf-8")
    return ["dockerfile:install_backend_dependencies"]


def _patch_docker_entrypoint(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    ownership_block = """fix_critical_runtime_ownership() {
    target_uid=$(id -u hermes)
    target_gid=$(id -g hermes)
    for path in \\
        "$HERMES_HOME/.env" \\
        "$HERMES_HOME/config.yaml" \\
        "$HERMES_HOME/auth.json" \\
        "$HERMES_HOME/auth.lock" \\
        "$HERMES_HOME/gateway_state.json" \\
        "$HERMES_HOME/gateway.pid" \\
        "$HERMES_HOME/state.db" \\
        "$HERMES_HOME/state.db-shm" \\
        "$HERMES_HOME/state.db-wal" \\
        "$HERMES_HOME/brainstack" \\
        "$HERMES_HOME/sessions" \\
        "$HERMES_HOME/memories"
    do
        [ -e "$path" ] || continue
        owner_uid=$(stat -c %u "$path" 2>/dev/null || echo "")
        owner_gid=$(stat -c %g "$path" 2>/dev/null || echo "")
        if [ "$owner_uid" != "$target_uid" ] || [ "$owner_gid" != "$target_gid" ]; then
            chown -R hermes:hermes "$path" 2>/dev/null || \\
                echo "Warning: failed to normalize ownership for $path"
        fi
    done
}

"""
    if "fix_critical_runtime_ownership()" not in text:
        anchor = 'INSTALL_DIR="/opt/hermes"\n\n'
        if anchor not in text:
            raise RuntimeError(f"Installer patch anchor missing for docker entrypoint function in {path}")
        text = text.replace(anchor, anchor + ownership_block, 1)
        applied.append("docker_entrypoint:normalize_runtime_ownership_function")

    if "\n    fix_critical_runtime_ownership\n" not in text:
        anchor = (
            '        chown -R hermes:hermes "$HERMES_HOME" 2>/dev/null || \\\n'
            '            echo "Warning: chown failed (rootless container?) — continuing anyway"\n'
            "    fi\n\n"
        )
        inject = anchor + (
            "    # Rebuild/login flows can leave a few critical files owned by root even\n"
            "    # when the top-level volume already belongs to hermes. Normalize the\n"
            "    # small runtime-critical surface before we drop privileges so the gateway\n"
            "    # never boots with an unreadable auth/config state.\n"
            "    fix_critical_runtime_ownership\n\n"
        )
        if anchor not in text:
            raise RuntimeError(f"Installer patch anchor missing for docker entrypoint call in {path}")
        text = text.replace(anchor, inject, 1)
        applied.append("docker_entrypoint:normalize_runtime_ownership_call")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _write_docker_healthcheck_script(target: Path, dry_run: bool) -> Path:
    script_path = target / "scripts" / "hermes-gateway-healthcheck.py"
    content = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _status_path() -> Path:
    hermes_home = Path(os.getenv("HERMES_HOME", "/opt/data"))
    return hermes_home / "gateway_state.json"


def _load_status() -> dict:
    path = _status_path()
    if not path.exists():
        raise RuntimeError(f"missing status file: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid status json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("status payload is not an object")
    return payload


def _evaluate(payload: dict) -> tuple[bool, str]:
    gateway_state = str(payload.get("gateway_state") or "unknown")
    exit_reason = payload.get("exit_reason")
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}

    connected = []
    platform_states = {}
    for name, info in platforms.items():
        if not isinstance(info, dict):
            continue
        state = str(info.get("state") or "unknown")
        platform_states[name] = state
        if state == "connected":
            connected.append(name)

    if gateway_state in {"running", "degraded"} and connected:
        return True, f"{gateway_state}; connected={','.join(sorted(connected))}"

    details = [f"gateway_state={gateway_state}"]
    if exit_reason:
        details.append(f"exit_reason={exit_reason}")
    if platform_states:
        details.append(
            "platforms=" + ",".join(f"{name}:{state}" for name, state in sorted(platform_states.items()))
        )
    else:
        details.append("platforms=none")
    return False, "; ".join(details)


def main() -> int:
    parser = argparse.ArgumentParser(description="Readiness-aware Hermes gateway healthcheck")
    parser.add_argument("--quiet", action="store_true", help="Only use exit code")
    args = parser.parse_args()

    try:
        payload = _load_status()
        ok, message = _evaluate(payload)
    except Exception as exc:
        if not args.quiet:
            print(f"gateway healthcheck failed: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        stream = sys.stdout if ok else sys.stderr
        print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
"""
    if not dry_run:
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
    return script_path


def _patch_compose_healthcheck(path: Path, dry_run: bool) -> list[str]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    old = '      test: ["CMD-SHELL", "tr \'\\\\000\' \' \' </proc/1/cmdline | grep -q \'hermes gateway run --replace\' || exit 1"]\n'
    new = '      test: ["CMD", "python3", "/opt/hermes/scripts/hermes-gateway-healthcheck.py", "--quiet"]\n'
    if new not in text and old in text:
        text = text.replace(old, new, 1)
        applied.append("compose:readiness_healthcheck")
    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _run_doctor(
    target: Path,
    args: argparse.Namespace,
    planned_install: bool,
    *,
    config_path: Path,
    compose_path: Path | None,
) -> int:
    doctor_path = REPO_ROOT / "scripts" / "brainstack_doctor.py"
    spec = importlib.util.spec_from_file_location("brainstack_doctor_runtime", doctor_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load doctor module from {doctor_path}")
    doctor_mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = doctor_mod
    spec.loader.exec_module(doctor_mod)

    doctor_args = argparse.Namespace(
        target=str(target),
        config=str(config_path),
        compose_file=str(compose_path) if compose_path else None,
        desktop_launcher=str(args.desktop_launcher) if args.desktop_launcher else None,
        python=str(args.python or _default_target_python(target)) if (args.python or _default_target_python(target)) else None,
        runtime=args.runtime,
        planned_install=planned_install,
        check_docker=args.runtime != "local",
        check_desktop_launcher=True,
        json=False,
    )
    code, checks = doctor_mod.run_doctor(doctor_args)
    for check in checks:
        marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[check.status]
        stream = sys.stderr if check.status == "fail" else sys.stdout
        print(f"{marker} {check.name}: {check.message}", file=stream)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Brainstack into a target Hermes checkout.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--config", type=Path, help="Path to Hermes config.yaml")
    parser.add_argument("--compose-file", type=Path, help="Path to Docker compose file for doctor checks")
    parser.add_argument("--desktop-launcher", type=Path, help="Path to desktop launcher for doctor checks")
    parser.add_argument("--python", type=Path, help="Target Hermes Python interpreter for dependency install and doctor checks")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Patch config.yaml to enable Brainstack while keeping Hermes builtin memory and user profile enabled",
    )
    parser.add_argument("--skip-deps", action="store_true", help="Skip installing missing kuzu/chromadb into the target Hermes Python")
    parser.add_argument("--doctor", action="store_true", help="Run brainstack_doctor after install")
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without changing files")
    parser.add_argument(
        "--host-patch-mode",
        choices=tuple(HOST_PATCH_MODE_CATEGORIES),
        default="core",
        help=(
            "Host patch policy: core=minimal Brainstack seams only; "
            "compat=core plus opt-in provider/runtime hotfixes; "
            "legacy=previous broad host patch behavior for emergency rollback only"
        ),
    )
    parser.add_argument(
        "--check-release-hygiene",
        action="store_true",
        help="Fail if tracked or staged files include private runtime paths or high-confidence secrets.",
    )
    args = parser.parse_args()

    release_hygiene = _check_release_hygiene(REPO_ROOT)
    if args.check_release_hygiene and release_hygiene["status"] != "pass":
        print("FAIL release hygiene gate detected private or secret-like tracked content:", file=sys.stderr)
        for key in ("private_tracked", "private_staged", "secret_like_tracked"):
            values = release_hygiene.get(key) or []
            if values:
                print(f"  {key}: {', '.join(values[:12])}", file=sys.stderr)
        return 2

    target = Path(args.target).expanduser().resolve()
    if not (target / "run_agent.py").exists():
        print(f"FAIL target is not a Hermes checkout: {target}", file=sys.stderr)
        return 2
    if not SOURCE_PLUGIN.exists():
        print(f"FAIL Brainstack payload missing: {SOURCE_PLUGIN}", file=sys.stderr)
        return 2
    config_path: Path | None
    try:
        config_path = args.config.expanduser().resolve() if args.config else _default_config_path(target)
    except RuntimeError as exc:
        config_path = None
        if args.enable or args.doctor or args.runtime == "docker":
            print(f"FAIL {exc}", file=sys.stderr)
            return 2
        print(
            "INFO no Hermes agent config found; continuing in source-only install mode "
            "(payload + host patches only, no config enablement, runtime canonicalization, or doctor)."
        )
    if config_path is not None and not config_path.exists():
        print(
            f"FAIL config not found: {config_path}. Create or select an agent first, then rerun the installer.",
            file=sys.stderr,
        )
        return 2

    compose_path: Path | None = None
    if args.runtime == "docker" or args.compose_file:
        if config_path is None and not args.compose_file:
            print(
                "FAIL Docker runtime install requires a concrete agent config or an explicit --compose-file.",
                file=sys.stderr,
            )
            return 2
        if args.compose_file:
            compose_path = args.compose_file.expanduser().resolve()
        else:
            try:
                compose_path = _default_compose_path(target, config_path)
            except RuntimeError as exc:
                if args.runtime == "docker":
                    if config_path is None:
                        print("FAIL Docker runtime install requires a concrete agent config.", file=sys.stderr)
                        return 2
                    try:
                        compose_path = _generated_compose_path(target, config_path)
                    except RuntimeError:
                        print(f"FAIL {exc}", file=sys.stderr)
                        return 2
                else:
                    print(f"FAIL {exc}", file=sys.stderr)
                    return 2

    plugin_target = target / "plugins" / "memory" / "brainstack"
    selected_python = args.python.expanduser() if args.python else _default_target_python(target)
    files = _copy_tree(SOURCE_PLUGIN, plugin_target, args.dry_run)
    _assert_no_private_payload_files(files)
    helper_files: list[dict[str, str]] = []

    generated_files: list[dict[str, str]] = []
    if args.runtime == "docker":
        if config_path is None:
            print("FAIL Docker runtime install requires a concrete agent config.", file=sys.stderr)
            return 2
        assert compose_path is not None
        if not compose_path.exists():
            generated_compose = _write_docker_compose_file(target, config_path, compose_path, args.dry_run)
            generated_files.append({"source": "generated:docker-compose", "target": str(generated_compose)})
        docker_start = _write_docker_start_script(target, config_path, compose_path, args.dry_run)
        generated_files.append({"source": "generated:hermes-brainstack-start.sh", "target": str(docker_start)})
        docker_healthcheck = _write_docker_healthcheck_script(target, args.dry_run)
        generated_files.append({"source": "generated:hermes-gateway-healthcheck.py", "target": str(docker_healthcheck)})

    config_result = None
    if args.enable:
        assert config_path is not None
        config_result = _patch_config(config_path, args.dry_run)
    deps_result = _ensure_backend_dependencies(selected_python, dry_run=args.dry_run, skip_deps=args.skip_deps)

    host_helper_files: list[dict[str, str]] = []

    host_patches: list[str] = []
    host_patches.extend(_run_host_patch("_patch_run_agent", target / "run_agent.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_prompt_builder", target / "agent" / "prompt_builder.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_jobs", target / "cron" / "jobs.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_scheduler", target / "cron" / "scheduler.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_scheduler_tests", target / "tests" / "cron" / "test_scheduler.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_cron_tests", target / "tests" / "cron" / "test_jobs.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_auxiliary_client", target / "agent" / "auxiliary_client.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_credential_pool", target / "agent" / "credential_pool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_credential_pool_tests", target / "tests" / "agent" / "test_credential_pool.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_provider", target / "agent" / "memory_provider.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_manager_required_seam", target / "agent" / "memory_manager.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_memory_manager", target / "agent" / "memory_manager.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    host_patches.extend(_run_host_patch("_patch_gateway_run", target / "gateway" / "run.py", args.dry_run, host_patch_mode=args.host_patch_mode))
    if args.runtime == "docker":
        assert compose_path is not None
        host_patches.extend(_run_host_patch("_patch_compose_healthcheck", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_compose_runtime_identity", compose_path, args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_dockerignore", target / ".dockerignore", args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_dockerfile_backend_dependencies", target / "Dockerfile", args.dry_run, host_patch_mode=args.host_patch_mode))
        host_patches.extend(_run_host_patch("_patch_docker_entrypoint", target / "docker" / "entrypoint.sh", args.dry_run, host_patch_mode=args.host_patch_mode))

    if config_path is not None:
        runtime_state_canonicalization = _canonicalize_runtime_user_profile(config_path, args.dry_run)
        runtime_db_canonicalization = _canonicalize_runtime_brainstack_db(
            target,
            config_path,
            python_bin=selected_python,
            dry_run=args.dry_run,
        )
    else:
        runtime_state_canonicalization = {"status": "skipped", "reason": "source_only_install"}
        runtime_db_canonicalization = {"status": "skipped", "reason": "source_only_install"}

    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "source_repo": str(REPO_ROOT),
        "target_hermes": str(target),
        "runtime_mode": args.runtime,
        "host_patch_mode": args.host_patch_mode,
        "source_only_install": config_path is None,
        "plugin_target": str(plugin_target),
        "files": files,
        "helper_files": helper_files,
        "host_helper_files": host_helper_files,
        "host_patches": host_patches,
        "host_patch_inventory": _selected_host_patch_inventory(args.runtime, args.host_patch_mode),
        "release_hygiene": release_hygiene,
        "generated_files": generated_files,
        "config_path": str(config_path) if config_path is not None else None,
        "config": config_result,
        "dependency_install": deps_result,
        "runtime_state_canonicalization": runtime_state_canonicalization,
        "runtime_db_canonicalization": runtime_db_canonicalization,
        "secrets_included": False,
    }
    _write_manifest(target, manifest, args.dry_run)

    action = "DRY-RUN" if args.dry_run else "INSTALLED"
    print(f"{action} Brainstack payload files: {len(files)}")
    print(f"{action} helper files: {len(helper_files)}")
    inventory = _selected_host_patch_inventory(args.runtime, args.host_patch_mode)
    selected_inventory = [item for item in inventory if item.get("selected")]
    skipped_inventory = [item for item in inventory if not item.get("selected")]
    print(
        f"{action} host patch mode: {args.host_patch_mode} "
        f"({len(selected_inventory)} selected, {len(skipped_inventory)} skipped)"
    )
    if args.dry_run:
        if selected_inventory:
            selected_labels = ", ".join(
                f"{item['patcher']}[{item['category']}]" for item in selected_inventory
            )
            print(f"{action} selected installer patchers: {selected_labels}")
        if skipped_inventory:
            skipped_labels = ", ".join(
                f"{item['patcher']}[{item['category']}]" for item in skipped_inventory
            )
            print(f"{action} skipped installer patchers: {skipped_labels}")
    if host_helper_files:
        print(f"{action} host helper files: {len(host_helper_files)}")
    if host_patches:
        print(f"{action} host patches: {len(host_patches)}")
    if generated_files:
        print(f"{action} generated files: {len(generated_files)}")
    if config_result:
        print(f"{action} config: {config_result['config_path']}")
    elif config_path is None:
        print(f"{action} config: source-only (no agent config)")
    if deps_result.get("status") in {"planned", "installed", "already_satisfied"}:
        print(f"{action} backend deps: {deps_result['status']}")
    elif deps_result.get("status") == "skipped":
        print(f"{action} backend deps: skipped ({deps_result.get('reason')})")
    if not args.dry_run:
        print(f"Wrote manifest: {target / '.brainstack-install-manifest.json'}")

    if args.doctor:
        if config_path is None:
            print("FAIL Doctor requires a concrete agent config.", file=sys.stderr)
            return 2
        return _run_doctor(
            target,
            args,
            planned_install=args.dry_run,
            config_path=config_path,
            compose_path=compose_path,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
