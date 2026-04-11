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
SOURCE_HOST_PAYLOAD = REPO_ROOT / "host_payload"


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


def _replace_once(text: str, old: str, new: str, *, label: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"Installer patch anchor missing for {label} in {path}")
    return text.replace(old, new, 1)


def _patch_run_agent(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    import_anchor = "from agent.memory_manager import build_memory_context_block\n"
    import_inject = (
        "from agent.memory_manager import build_memory_context_block\n"
        "from agent.brainstack_mode import (\n"
        "    LEGACY_MEMORY_TOOL_NAMES,\n"
        "    filter_legacy_memory_tool_defs,\n"
        "    is_brainstack_only_mode,\n"
        ")\n"
    )
    if "from agent.brainstack_mode import (" not in text:
        text = _replace_once(text, import_anchor, import_inject, label="run_agent import", path=path)
        applied.append("run_agent:import_brainstack_mode")

    cfg_anchor = "        except Exception:\n            _agent_cfg = {}\n"
    cfg_inject = "        except Exception:\n            _agent_cfg = {}\n        self._brainstack_only_mode = is_brainstack_only_mode(_agent_cfg)\n"
    if "self._brainstack_only_mode = is_brainstack_only_mode(_agent_cfg)" not in text:
        text = _replace_once(text, cfg_anchor, cfg_inject, label="run_agent mode flag", path=path)
        applied.append("run_agent:set_brainstack_only_flag")

    filter_anchor = (
        "        if self._memory_manager and self.tools is not None:\n"
        "            for _schema in self._memory_manager.get_all_tool_schemas():\n"
        "                _wrapped = {\"type\": \"function\", \"function\": _schema}\n"
        "                self.tools.append(_wrapped)\n"
        "                _tname = _schema.get(\"name\", \"\")\n"
        "                if _tname:\n"
        "                    self.valid_tool_names.add(_tname)\n"
    )
    filter_inject = filter_anchor + (
        "        if self.tools is not None:\n"
        "            filtered_tools = filter_legacy_memory_tool_defs(self.tools, config=_agent_cfg)\n"
        "            if len(filtered_tools) != len(self.tools):\n"
        "                self.tools = filtered_tools\n"
        "                self.valid_tool_names = {\n"
        "                    tool[\"function\"][\"name\"]\n"
        "                    for tool in self.tools\n"
        "                    if tool.get(\"function\", {}).get(\"name\")\n"
        "                }\n"
    )
    if "filtered_tools = filter_legacy_memory_tool_defs(self.tools, config=_agent_cfg)" not in text:
        text = _replace_once(text, filter_anchor, filter_inject, label="run_agent tool filter", path=path)
        applied.append("run_agent:filter_legacy_tools")

    invoke_anchor = (
        "        Handles both agent-level tools (todo, memory, etc.) and registry-dispatched\n"
        "        tools. Used by the concurrent execution path; the sequential path retains\n"
        "        its own inline invocation for backward-compatible display handling.\n"
        "        \"\"\"\n"
    )
    invoke_inject = invoke_anchor + (
        "        if self._brainstack_only_mode and function_name in LEGACY_MEMORY_TOOL_NAMES:\n"
        "            return json.dumps(\n"
        "                {\n"
        "                    \"success\": False,\n"
        "                    \"error\": f\"{function_name} is disabled while Brainstack owns memory.\",\n"
        "                }\n"
        "            )\n"
    )
    if "is disabled while Brainstack owns memory." not in text:
        text = _replace_once(text, invoke_anchor, invoke_inject, label="run_agent invoke guard", path=path)
        applied.append("run_agent:block_legacy_dispatch")

    seq_anchor = "            if function_name == \"todo\":\n"
    seq_inject = (
        "            if self._brainstack_only_mode and function_name in LEGACY_MEMORY_TOOL_NAMES:\n"
        "                function_result = json.dumps(\n"
        "                    {\n"
        "                        \"success\": False,\n"
        "                        \"error\": f\"{function_name} is disabled while Brainstack owns memory.\",\n"
        "                    }\n"
        "                )\n"
        "                tool_duration = time.time() - tool_start_time\n"
        "                if self._should_emit_quiet_tool_messages():\n"
        "                    self._vprint(\n"
        "                        f\"  {_get_cute_tool_message_impl(function_name, function_args, tool_duration, result=function_result)}\"\n"
        "                    )\n"
        "            elif function_name == \"todo\":\n"
    )
    if "elif function_name == \"todo\":" not in text or "LEGACY_MEMORY_TOOL_NAMES" not in text:
        text = _replace_once(text, seq_anchor, seq_inject, label="run_agent sequential guard", path=path)
        applied.append("run_agent:block_legacy_sequential_path")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_gateway_run(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    import_anchor = "from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType\n"
    import_inject = (
        "from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType\n"
        "from agent.brainstack_mode import is_brainstack_only_mode\n"
    )
    if "from agent.brainstack_mode import is_brainstack_only_mode" not in text:
        text = _replace_once(text, import_anchor, import_inject, label="gateway import", path=path)
        applied.append("gateway:import_brainstack_mode")

    hooks_anchor = "        from gateway.hooks import HookRegistry\n        self.hooks = HookRegistry()\n"
    hooks_inject = hooks_anchor + (
        "\n"
        "    def _brainstack_only_mode_enabled(self) -> bool:\n"
        "        try:\n"
        "            return is_brainstack_only_mode(_load_gateway_config())\n"
        "        except Exception:\n"
        "            return False\n"
        "\n"
        "    def _maintenance_agent_toolsets(self) -> list[str]:\n"
        "        if self._brainstack_only_mode_enabled():\n"
        "            return []\n"
        "        return [\"memory\"]\n"
        "\n"
        "    def _finalize_brainstack_session_memory(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        history = self.session_store.load_transcript(session_id)\n"
        "        messages = [\n"
        "            {\"role\": m.get(\"role\"), \"content\": m.get(\"content\")}\n"
        "            for m in history or []\n"
        "            if m.get(\"role\") in (\"user\", \"assistant\") and m.get(\"content\")\n"
        "        ]\n"
        "\n"
        "        cached_agent = None\n"
        "        lock = getattr(self, \"_agent_cache_lock\", None)\n"
        "        cache = getattr(self, \"_agent_cache\", None)\n"
        "        if lock and cache is not None:\n"
        "            with lock:\n"
        "                entry = cache.get(session_key)\n"
        "                if entry and entry[0] is not None:\n"
        "                    cached_agent = entry[0]\n"
        "\n"
        "        if cached_agent and hasattr(cached_agent, \"shutdown_memory_provider\"):\n"
        "            cached_agent.shutdown_memory_provider(messages)\n"
        "            return\n"
        "\n"
        "        runtime_kwargs = _resolve_runtime_agent_kwargs()\n"
        "        if not runtime_kwargs.get(\"api_key\"):\n"
        "            return\n"
        "\n"
        "        from run_agent import AIAgent\n"
        "\n"
        "        tmp_agent = AIAgent(\n"
        "            **runtime_kwargs,\n"
        "            model=_resolve_gateway_model(),\n"
        "            max_iterations=1,\n"
        "            quiet_mode=True,\n"
        "            enabled_toolsets=[],\n"
        "            session_id=session_id,\n"
        "        )\n"
        "        tmp_agent._print_fn = lambda *a, **kw: None\n"
        "        tmp_agent.shutdown_memory_provider(messages)\n"
        "\n"
        "    def _finalize_session_memory_sync(\n"
        "        self,\n"
        "        session_key: str,\n"
        "        session_id: str,\n"
        "    ) -> None:\n"
        "        if self._brainstack_only_mode_enabled():\n"
        "            self._finalize_brainstack_session_memory(session_key, session_id)\n"
        "            return\n"
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
    )
    if "def _brainstack_only_mode_enabled(self) -> bool:" not in text:
        text = _replace_once(text, hooks_anchor, hooks_inject, label="gateway helper block", path=path)
        applied.append("gateway:add_boundary_helpers")

    flush_doc_anchor = (
        "        Synchronous worker — meant to be called via run_in_executor from\n"
        "        an async context so it doesn't block the event loop.\n"
        "        \"\"\"\n"
    )
    flush_doc_inject = flush_doc_anchor + (
        "        if self._brainstack_only_mode_enabled():\n"
        "            logger.debug(\n"
        "                \"Skipping legacy memory flush for session %s because Brainstack owns memory\",\n"
        "                old_session_id,\n"
        "            )\n"
        "            return\n"
    )
    if "Skipping legacy memory flush for session %s because Brainstack owns memory" not in text:
        text = _replace_once(text, flush_doc_anchor, flush_doc_inject, label="gateway legacy flush guard", path=path)
        applied.append("gateway:guard_legacy_flush")

    replacements = [
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
    ]
    for old, new, label in replacements:
        if new not in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


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

    host_helper_files: list[dict[str, str]] = []
    if SOURCE_HOST_PAYLOAD.exists():
        for src_file in _iter_payload_files(SOURCE_HOST_PAYLOAD):
            rel = src_file.relative_to(SOURCE_HOST_PAYLOAD)
            host_helper_files.append(_copy_file(src_file, target / rel, args.dry_run))

    host_patches: list[str] = []
    host_patches.extend(_patch_run_agent(target / "run_agent.py", args.dry_run))
    host_patches.extend(_patch_gateway_run(target / "gateway" / "run.py", args.dry_run))

    manifest = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "source_repo": str(REPO_ROOT),
        "target_hermes": str(target),
        "runtime_mode": args.runtime,
        "plugin_target": str(plugin_target),
        "files": files,
        "helper_files": helper_files,
        "host_helper_files": host_helper_files,
        "host_patches": host_patches,
        "generated_files": generated_files,
        "config": config_result,
        "secrets_included": False,
    }
    _write_manifest(target, manifest, args.dry_run)

    action = "DRY-RUN" if args.dry_run else "INSTALLED"
    print(f"{action} Brainstack payload files: {len(files)}")
    print(f"{action} helper files: {len(helper_files)}")
    if host_helper_files:
        print(f"{action} host helper files: {len(host_helper_files)}")
    if host_patches:
        print(f"{action} host patches: {len(host_patches)}")
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
