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
BACKEND_DEPENDENCIES = {
    "kuzu": "kuzu",
    "chromadb": "chromadb",
}


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

    cmd = [str(python_bin), "-m", "pip", "install", *missing]
    proc = subprocess.run(cmd, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Dependency install failed for {' '.join(missing)} using {python_bin}")
    return {"status": "installed", "python": str(python_bin), "packages": missing}


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


def _patch_run_agent(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if "from agent.rtk_sidecar import build_rtk_sidecar_config, RTKSidecarStats, maybe_preprocess_tool_result" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "from agent.trajectory import (\n"
                    "    convert_scratchpad_to_think, has_incomplete_scratchpad,\n"
                    "    save_trajectory as _save_trajectory_to_file,\n"
                    ")\n",
                    "from agent.trajectory import (\n"
                    "    convert_scratchpad_to_think, has_incomplete_scratchpad,\n"
                    "    save_trajectory as _save_trajectory_to_file,\n"
                    ")\n"
                    "from agent.rtk_sidecar import build_rtk_sidecar_config, RTKSidecarStats, maybe_preprocess_tool_result\n",
                ),
            ],
            label="run_agent rtk import",
            path=path,
        )
        applied.append("run_agent:import_rtk_sidecar")

    if "from agent.brainstack_mode import (" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "from agent.memory_manager import build_memory_context_block\n",
                    "from agent.memory_manager import build_memory_context_block\n"
                    "from agent.brainstack_mode import (\n"
                    "    LEGACY_MEMORY_TOOL_NAMES,\n"
                    "    blocked_brainstack_only_tool_error,\n"
                    "    filter_legacy_memory_tool_defs,\n"
                    "    is_brainstack_only_mode,\n"
                    ")\n",
                ),
                (
                    "from agent.memory_manager import (\n"
                    "    build_memory_context_block,\n"
                    ")\n",
                    "from agent.memory_manager import (\n"
                    "    build_memory_context_block,\n"
                    ")\n"
                    "from agent.brainstack_mode import (\n"
                    "    LEGACY_MEMORY_TOOL_NAMES,\n"
                    "    blocked_brainstack_only_tool_error,\n"
                    "    filter_legacy_memory_tool_defs,\n"
                    "    is_brainstack_only_mode,\n"
                    ")\n",
                ),
                (
                    "from agent.memory_manager import build_memory_context_block, sanitize_context\n",
                    "from agent.memory_manager import build_memory_context_block, sanitize_context\n"
                    "from agent.brainstack_mode import (\n"
                    "    LEGACY_MEMORY_TOOL_NAMES,\n"
                    "    blocked_brainstack_only_tool_error,\n"
                    "    filter_legacy_memory_tool_defs,\n"
                    "    is_brainstack_only_mode,\n"
                    ")\n",
                ),
            ],
            label="run_agent import",
            path=path,
        )
        applied.append("run_agent:import_brainstack_mode")

    if "self._rtk_sidecar = build_rtk_sidecar_config(_agent_cfg)" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "        self._brainstack_only_mode = is_brainstack_only_mode(_agent_cfg)\n",
                    "        self._rtk_sidecar = build_rtk_sidecar_config(_agent_cfg)\n"
                    "        self._rtk_sidecar_stats = RTKSidecarStats()\n"
                    "        self._brainstack_only_mode = is_brainstack_only_mode(_agent_cfg)\n",
                ),
                (
                    "        except Exception:\n            _agent_cfg = {}\n",
                    "        except Exception:\n"
                    "            _agent_cfg = {}\n"
                    "        self._rtk_sidecar = build_rtk_sidecar_config(_agent_cfg)\n"
                    "        self._rtk_sidecar_stats = RTKSidecarStats()\n",
                ),
            ],
            label="run_agent rtk init",
            path=path,
        )
        applied.append("run_agent:init_rtk_sidecar")

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
    filter_anchor_with_existing_names = (
        "        if self._memory_manager and self.tools is not None:\n"
        "            _existing_tool_names = {\n"
        "                t.get(\"function\", {}).get(\"name\")\n"
        "                for t in self.tools\n"
        "                if isinstance(t, dict)\n"
        "            }\n"
        "            for _schema in self._memory_manager.get_all_tool_schemas():\n"
        "                _tname = _schema.get(\"name\", \"\")\n"
        "                if _tname and _tname in _existing_tool_names:\n"
        "                    continue  # already registered via plugin path\n"
        "                _wrapped = {\"type\": \"function\", \"function\": _schema}\n"
        "                self.tools.append(_wrapped)\n"
        "                if _tname:\n"
        "                    self.valid_tool_names.add(_tname)\n"
        "                    _existing_tool_names.add(_tname)\n"
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
        text = _replace_once_any(
            text,
            [
                (filter_anchor, filter_inject),
                (
                    filter_anchor_with_existing_names,
                    filter_anchor_with_existing_names + (
                        "        if self.tools is not None:\n"
                        "            filtered_tools = filter_legacy_memory_tool_defs(self.tools, config=_agent_cfg)\n"
                        "            if len(filtered_tools) != len(self.tools):\n"
                        "                self.tools = filtered_tools\n"
                        "                self.valid_tool_names = {\n"
                        "                    tool[\"function\"][\"name\"]\n"
                        "                    for tool in self.tools\n"
                        "                    if tool.get(\"function\", {}).get(\"name\")\n"
                        "                }\n"
                    ),
                ),
            ],
            label="run_agent tool filter",
            path=path,
        )
        applied.append("run_agent:filter_legacy_tools")

    guidance_replacements = [
        (
            "        if \"session_search\" in self.valid_tool_names:\n"
            "            tool_guidance.append(SESSION_SEARCH_GUIDANCE)\n"
            "        if \"skill_manage\" in self.valid_tool_names:\n"
            "            tool_guidance.append(SKILLS_GUIDANCE)\n"
        ),
        (
            "        if \"session_search\" in self.valid_tool_names:\n"
            "            tool_guidance.append(SESSION_SEARCH_GUIDANCE)\n"
            "        if \"skill_manage\" in self.valid_tool_names:\n"
            "            if self._brainstack_only_mode:\n"
            "                tool_guidance.append(\n"
            "                    \"Use skill_manage only for reusable procedures or workflows. Never store personal profile, identity, communication style, or project memory there while Brainstack owns memory.\"\n"
            "                )\n"
            "            else:\n"
            "                tool_guidance.append(SKILLS_GUIDANCE)\n"
        ),
    ]
    guidance_inject = (
        "        if \"session_search\" in self.valid_tool_names:\n"
        "            tool_guidance.append(SESSION_SEARCH_GUIDANCE)\n"
        "        if self._brainstack_only_mode:\n"
        "            tool_guidance.append(\n"
        "                \"Brainstack owns personal memory in this mode. Keep user identity, preferences, communication style, and project context inside Brainstack. Do not create or maintain notes files, MEMORY.md, USER.md, persona.md, or side skill files for that kind of memory. Do not use ad hoc code, terminal writes, file edits, cronjob scheduling, or other automation detours to persist or recover personal memory. Do not use secondary memory APIs from ad hoc code either. session_search may be used only as explicit conversation search, not as a second personal-memory system. Use skill_manage only for reusable procedures or workflows.\"\n"
        "            )\n"
        "        elif \"skill_manage\" in self.valid_tool_names:\n"
        "            tool_guidance.append(SKILLS_GUIDANCE)\n"
    )
    if "Brainstack owns personal memory in this mode." not in text:
        text = _replace_once_any(
            text,
            [(anchor, guidance_inject) for anchor in guidance_replacements],
            label="run_agent skill guidance",
            path=path,
        )
        applied.append("run_agent:scope_personal_memory_guidance")

    nudge_anchor = (
        "            if (self._skill_nudge_interval > 0\n"
        "                    and \"skill_manage\" in self.valid_tool_names):\n"
        "                self._iters_since_skill += 1\n"
    )
    nudge_inject = (
        "            if (self._skill_nudge_interval > 0\n"
        "                    and \"skill_manage\" in self.valid_tool_names\n"
        "                    and not self._brainstack_only_mode):\n"
        "                self._iters_since_skill += 1\n"
    )
    if "and not self._brainstack_only_mode):\n                self._iters_since_skill += 1" not in text:
        text = _replace_once(text, nudge_anchor, nudge_inject, label="run_agent skill nudge counter", path=path)
        applied.append("run_agent:disable_skill_nudge_counter_in_brainstack_only")

    review_anchor = (
        "        if (self._skill_nudge_interval > 0\n"
        "                and self._iters_since_skill >= self._skill_nudge_interval\n"
        "                and \"skill_manage\" in self.valid_tool_names):\n"
        "            _should_review_skills = True\n"
        "            self._iters_since_skill = 0\n"
    )
    review_inject = (
        "        if (self._skill_nudge_interval > 0\n"
        "                and self._iters_since_skill >= self._skill_nudge_interval\n"
        "                and \"skill_manage\" in self.valid_tool_names\n"
        "                and not self._brainstack_only_mode):\n"
        "            _should_review_skills = True\n"
        "            self._iters_since_skill = 0\n"
    )
    if "and not self._brainstack_only_mode):\n            _should_review_skills = True" not in text:
        text = _replace_once(text, review_anchor, review_inject, label="run_agent skill nudge review gate", path=path)
        applied.append("run_agent:disable_skill_nudge_review_in_brainstack_only")

    invoke_anchor = (
        "        Handles both agent-level tools (todo, memory, etc.) and registry-dispatched\n"
        "        tools. Used by the concurrent execution path; the sequential path retains\n"
        "        its own inline invocation for backward-compatible display handling.\n"
        "        \"\"\"\n"
    )
    invoke_inject = invoke_anchor + (
        "        brainstack_only_error = blocked_brainstack_only_tool_error(function_name, function_args)\n"
        "        if self._brainstack_only_mode and brainstack_only_error:\n"
        "            return json.dumps(\n"
        "                {\n"
        "                    \"success\": False,\n"
        "                    \"error\": brainstack_only_error,\n"
        "                }\n"
        "            )\n"
    )
    if "brainstack_only_error = blocked_brainstack_only_tool_error(function_name, function_args)" not in text:
        text = _replace_once(text, invoke_anchor, invoke_inject, label="run_agent invoke guard", path=path)
        applied.append("run_agent:block_legacy_dispatch")

    seq_anchor = "            if function_name == \"todo\":\n"
    seq_inject = (
        "            brainstack_only_error = blocked_brainstack_only_tool_error(function_name, function_args)\n"
        "            if self._brainstack_only_mode and brainstack_only_error:\n"
        "                function_result = json.dumps(\n"
        "                    {\n"
        "                        \"success\": False,\n"
        "                        \"error\": brainstack_only_error,\n"
        "                    }\n"
        "                )\n"
        "                tool_duration = time.time() - tool_start_time\n"
        "                if self._should_emit_quiet_tool_messages():\n"
        "                    self._vprint(\n"
        "                        f\"  {_get_cute_tool_message_impl(function_name, function_args, tool_duration, result=function_result)}\"\n"
        "                    )\n"
        "            elif function_name == \"todo\":\n"
    )
    if "brainstack_only_error = blocked_brainstack_only_tool_error(function_name, function_args)" not in text or "elif function_name == \"todo\":" not in text:
        text = _replace_once(text, seq_anchor, seq_inject, label="run_agent sequential guard", path=path)
        applied.append("run_agent:block_legacy_sequential_path")

    if "self._rtk_sidecar_stats.record_preprocessing_effect(raw_result, preprocessed_result)" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=function_result,\n"
                    "                tool_name=name,\n"
                    "                tool_use_id=tc.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "            )\n",
                    "            raw_result = function_result\n"
                    "            preprocessed_result = maybe_preprocess_tool_result(function_result, self._rtk_sidecar)\n"
                    "            self._rtk_sidecar_stats.record_preprocessing_effect(raw_result, preprocessed_result)\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=preprocessed_result,\n"
                    "                tool_name=name,\n"
                    "                tool_use_id=tc.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                ),
                (
                    "            raw_result = function_result\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=function_result,\n"
                    "                tool_name=name,\n"
                    "                tool_use_id=tc.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                    "            raw_result = function_result\n"
                    "            preprocessed_result = maybe_preprocess_tool_result(function_result, self._rtk_sidecar)\n"
                    "            self._rtk_sidecar_stats.record_preprocessing_effect(raw_result, preprocessed_result)\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=preprocessed_result,\n"
                    "                tool_name=name,\n"
                    "                tool_use_id=tc.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                ),
                (
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=function_result,\n"
                    "                tool_name=function_name,\n"
                    "                tool_use_id=tool_call.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "            )\n",
                    "            raw_result = function_result\n"
                    "            preprocessed_result = maybe_preprocess_tool_result(function_result, self._rtk_sidecar)\n"
                    "            self._rtk_sidecar_stats.record_preprocessing_effect(raw_result, preprocessed_result)\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=preprocessed_result,\n"
                    "                tool_name=function_name,\n"
                    "                tool_use_id=tool_call.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                ),
                (
                    "            raw_result = function_result\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=function_result,\n"
                    "                tool_name=function_name,\n"
                    "                tool_use_id=tool_call.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                    "            raw_result = function_result\n"
                    "            preprocessed_result = maybe_preprocess_tool_result(function_result, self._rtk_sidecar)\n"
                    "            self._rtk_sidecar_stats.record_preprocessing_effect(raw_result, preprocessed_result)\n"
                    "            function_result = maybe_persist_tool_result(\n"
                    "                content=preprocessed_result,\n"
                    "                tool_name=function_name,\n"
                    "                tool_use_id=tool_call.id,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            self._rtk_sidecar_stats.record_result(raw_result, function_result)\n",
                ),
            ],
            label="run_agent rtk preprocess path",
            path=path,
        )
        applied.append("run_agent:rtk_preprocess_path")

    if "self._rtk_sidecar_stats.record_turn_budget_effect(before_budget_total, after_budget_total)" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "            enforce_turn_budget(turn_tool_msgs, env=get_active_env(effective_task_id))\n",
                    "            before_budget_total = sum(len(msg.get(\"content\", \"\")) for msg in turn_tool_msgs)\n"
                    "            enforce_turn_budget(\n"
                    "                turn_tool_msgs,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            after_budget_total = sum(len(msg.get(\"content\", \"\")) for msg in turn_tool_msgs)\n"
                    "            self._rtk_sidecar_stats.record_turn_budget_effect(before_budget_total, after_budget_total)\n",
                ),
                (
                    "            enforce_turn_budget(messages[-num_tools_seq:], env=get_active_env(effective_task_id))\n",
                    "            turn_tool_msgs = messages[-num_tools_seq:]\n"
                    "            before_budget_total = sum(len(msg.get(\"content\", \"\")) for msg in turn_tool_msgs)\n"
                    "            enforce_turn_budget(\n"
                    "                turn_tool_msgs,\n"
                    "                env=get_active_env(effective_task_id),\n"
                    "                config=self._rtk_sidecar.budget,\n"
                    "            )\n"
                    "            after_budget_total = sum(len(msg.get(\"content\", \"\")) for msg in turn_tool_msgs)\n"
                    "            self._rtk_sidecar_stats.record_turn_budget_effect(before_budget_total, after_budget_total)\n",
                ),
            ],
            label="run_agent rtk turn budget",
            path=path,
        )
        applied.append("run_agent:rtk_turn_budget")

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
        '        "When recalled memory provides a specific, non-conflicted user fact such as a name, number, date, or preference, treat it as authoritative over assistant suggestions or generic prior knowledge unless another recalled fact in this memory block conflicts with it.]\\n\\n"\n'
    )
    current_private_note = (
        '        "[System note: The following is private recalled memory context, NOT new user input. "\n'
        '        "Apply it silently in your reply. Do not mention memory blocks, recalled-memory headings, "\n'
        '        "or internal memory state unless the user explicitly asks about memory behavior or debugging.]\\n\\n"\n'
    )
    if new_note not in text:
        text = _replace_once_any(
            text,
            [
                (old_note, new_note),
                (current_private_note, new_note),
            ],
            label="memory_manager private recall note",
            path=path,
        )
        applied.append("memory_manager:private_recall_note")

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_gateway_run(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    if "from agent.brainstack_mode import is_brainstack_only_mode" not in text:
        text = _replace_once_any(
            text,
            [
                (
                    "from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType\n",
                    "from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType\n"
                    "from agent.brainstack_mode import is_brainstack_only_mode\n",
                ),
                (
                    "from gateway.platforms.base import (\n"
                    "    BasePlatformAdapter,\n"
                    "    MessageEvent,\n"
                    "    MessageType,\n"
                    "    merge_pending_message_event,\n"
                    ")\n",
                    "from gateway.platforms.base import (\n"
                    "    BasePlatformAdapter,\n"
                    "    MessageEvent,\n"
                    "    MessageType,\n"
                    "    merge_pending_message_event,\n"
                    ")\n"
                    "from agent.brainstack_mode import is_brainstack_only_mode\n",
                ),
            ],
            label="gateway import",
            path=path,
        )
        applied.append("gateway:import_brainstack_mode")

    hooks_anchor = "    # -- Setup skill availability ----------------------------------------\n\n    def _has_setup_skill(self) -> bool:\n"
    hooks_inject = (
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
        "\n"
        + hooks_anchor
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
    if (
        "Skipping legacy memory flush for session %s because Brainstack owns memory" not in text
        and flush_doc_anchor in text
    ):
        text = _replace_once(text, flush_doc_anchor, flush_doc_inject, label="gateway legacy flush guard", path=path)
        applied.append("gateway:guard_legacy_flush")

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
    ]
    for old, new, label in replacements:
        if new not in text and old in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_gateway_status(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []

    constant_anchor = '_IS_WINDOWS = sys.platform == "win32"\n'
    constant_inject = constant_anchor + "_UNSET = object()\n"
    if "_UNSET = object()" not in text:
        text = _replace_once(text, constant_anchor, constant_inject, label="gateway status unset sentinel", path=path)
        applied.append("gateway_status:add_unset")

    old_signature = (
        "def write_runtime_status(\n"
        "    *,\n"
        "    gateway_state: Optional[str] = None,\n"
        "    exit_reason: Optional[str] = None,\n"
        "    platform: Optional[str] = None,\n"
        "    platform_state: Optional[str] = None,\n"
        "    error_code: Optional[str] = None,\n"
        "    error_message: Optional[str] = None,\n"
        ") -> None:\n"
    )
    new_signature = (
        "def write_runtime_status(\n"
        "    *,\n"
        "    gateway_state: Any = _UNSET,\n"
        "    exit_reason: Any = _UNSET,\n"
        "    platform: Optional[str] = None,\n"
        "    platform_state: Any = _UNSET,\n"
        "    error_code: Any = _UNSET,\n"
        "    error_message: Any = _UNSET,\n"
        ") -> None:\n"
    )
    current_signature = (
        "def write_runtime_status(\n"
        "    *,\n"
        "    gateway_state: Any = _UNSET,\n"
        "    exit_reason: Any = _UNSET,\n"
        "    restart_requested: Any = _UNSET,\n"
        "    active_agents: Any = _UNSET,\n"
        "    platform: Any = _UNSET,\n"
        "    platform_state: Any = _UNSET,\n"
        "    error_code: Any = _UNSET,\n"
        "    error_message: Any = _UNSET,\n"
        ") -> None:\n"
    )
    if new_signature not in text and current_signature not in text:
        text = _replace_once(text, old_signature, new_signature, label="gateway status signature", path=path)
        applied.append("gateway_status:signature")

    replacements = [
        ("    if gateway_state is not None:\n", "    if gateway_state is not _UNSET:\n", "gateway_status:gateway_state_clear"),
        ("    if exit_reason is not None:\n", "    if exit_reason is not _UNSET:\n", "gateway_status:exit_reason_clear"),
        (
            "        if platform_state is not None:\n            platform_payload[\"state\"] = platform_state\n",
            "        if platform_state is not _UNSET:\n            if platform_state is None:\n                platform_payload.pop(\"state\", None)\n            else:\n                platform_payload[\"state\"] = platform_state\n",
            "gateway_status:platform_state_clear",
        ),
        (
            "        if error_code is not None:\n            platform_payload[\"error_code\"] = error_code\n",
            "        if error_code is not _UNSET:\n            if error_code is None:\n                platform_payload.pop(\"error_code\", None)\n            else:\n                platform_payload[\"error_code\"] = error_code\n",
            "gateway_status:error_code_clear",
        ),
        (
            "        if error_message is not None:\n            platform_payload[\"error_message\"] = error_message\n",
            "        if error_message is not _UNSET:\n            if error_message is None:\n                platform_payload.pop(\"error_message\", None)\n            else:\n                platform_payload[\"error_message\"] = error_message\n",
            "gateway_status:error_message_clear",
        ),
    ]
    for old, new, label in replacements:
        if new not in text and old in text:
            text = _replace_once(text, old, new, label=label, path=path)
            applied.append(label)

    if applied and not dry_run:
        path.write_text(text, encoding="utf-8")
    return applied


def _patch_discord_platform(path: Path, dry_run: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    applied: list[str] = []
    modern_post_connect_flow = (
        "self._post_connect_task: Optional[asyncio.Task] = None" in text
        and "async def _run_post_connect_initialization(self) -> None:" in text
    )

    init_anchor = "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n        self._bot_task: Optional[asyncio.Task] = None\n"
    init_inject = (
        "        self._typing_tasks: Dict[str, asyncio.Task] = {}\n"
        "        self._bot_task: Optional[asyncio.Task] = None\n"
        "        self._slash_sync_task: Optional[asyncio.Task] = None\n"
    )
    if "self._slash_sync_task: Optional[asyncio.Task] = None" not in text:
        text = _replace_once(text, init_anchor, init_inject, label="discord slash sync task field", path=path)
        applied.append("discord:add_slash_sync_task_field")

    helper_anchor = "        self._reply_to_mode: str = getattr(config, 'reply_to_mode', 'first') or 'first'\n\n    async def connect(self) -> bool:\n"
    helper_inject = (
        "        self._reply_to_mode: str = getattr(config, 'reply_to_mode', 'first') or 'first'\n"
        "\n"
        "    async def _sync_slash_commands_background(self) -> None:\n"
        "        \"\"\"Sync slash commands without blocking Discord readiness.\"\"\"\n"
        "        if not self._client:\n"
        "            return\n"
        "        try:\n"
        "            synced = await asyncio.wait_for(self._client.tree.sync(), timeout=120)\n"
        "            logger.info(\"[%s] Synced %d slash command(s)\", self.name, len(synced))\n"
        "        except asyncio.TimeoutError:\n"
        "            logger.warning(\"[%s] Slash command sync timed out after startup\", self.name, exc_info=True)\n"
        "        except Exception as e:  # pragma: no cover - defensive logging\n"
        "            logger.warning(\"[%s] Slash command sync failed: %s\", self.name, e, exc_info=True)\n"
        "        finally:\n"
        "            self._slash_sync_task = None\n"
        "\n"
        "    def _ensure_background_slash_sync(self) -> None:\n"
        "        if self._slash_sync_task and not self._slash_sync_task.done():\n"
        "            return\n"
        "        self._slash_sync_task = asyncio.create_task(self._sync_slash_commands_background())\n"
        "\n"
        "    async def connect(self) -> bool:\n"
    )
    if "async def _sync_slash_commands_background(self) -> None:" not in text and not modern_post_connect_flow:
        text = _replace_once(text, helper_anchor, helper_inject, label="discord slash sync helpers", path=path)
        applied.append("discord:add_background_slash_sync")

    ready_old = (
        "                # Sync slash commands with Discord\n"
        "                try:\n"
        "                    synced = await adapter_self._client.tree.sync()\n"
        "                    logger.info(\"[%s] Synced %d slash command(s)\", adapter_self.name, len(synced))\n"
        "                except Exception as e:  # pragma: no cover - defensive logging\n"
        "                    logger.warning(\"[%s] Slash command sync failed: %s\", adapter_self.name, e, exc_info=True)\n"
        "                adapter_self._ready_event.set()\n"
    )
    ready_new = (
        "                adapter_self._ready_event.set()\n"
        "                adapter_self._ensure_background_slash_sync()\n"
    )
    if "adapter_self._ensure_background_slash_sync()" not in text and not modern_post_connect_flow:
        text = _replace_once(text, ready_old, ready_new, label="discord ready before slash sync", path=path)
        applied.append("discord:decouple_ready_from_slash_sync")

    disconnect_anchor = (
        "        if self._client:\n"
        "            try:\n"
        "                await self._client.close()\n"
        "            except Exception as e:  # pragma: no cover - defensive logging\n"
        "                logger.warning(\"[%s] Error during disconnect: %s\", self.name, e, exc_info=True)\n"
        "\n"
        "        self._running = False\n"
    )
    disconnect_inject = (
        "        if self._client:\n"
        "            try:\n"
        "                await self._client.close()\n"
        "            except Exception as e:  # pragma: no cover - defensive logging\n"
        "                logger.warning(\"[%s] Error during disconnect: %s\", self.name, e, exc_info=True)\n"
        "\n"
        "        if self._slash_sync_task:\n"
        "            self._slash_sync_task.cancel()\n"
        "            try:\n"
        "                await self._slash_sync_task\n"
        "            except asyncio.CancelledError:\n"
        "                pass\n"
        "            except Exception as e:  # pragma: no cover - defensive logging\n"
        "                logger.debug(\"[%s] Slash sync task cleanup: %s\", self.name, e)\n"
        "            self._slash_sync_task = None\n"
        "\n"
        "        self._running = False\n"
    )
    if "Slash sync task cleanup" not in text and not modern_post_connect_flow:
        text = _replace_once(text, disconnect_anchor, disconnect_inject, label="discord slash sync cleanup", path=path)
        applied.append("discord:cleanup_background_slash_sync")

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
    config.setdefault("sidecars", {})
    if not isinstance(config["sidecars"], dict):
        raise RuntimeError("config.yaml has non-object `sidecars` section")
    rtk = config["sidecars"].setdefault("rtk", {})
    if not isinstance(rtk, dict):
        rtk = {}
        config["sidecars"]["rtk"] = rtk
    rtk.setdefault("enabled", True)
    rtk.setdefault("mode", "balanced")
    if not dry_run:
        _write_yaml(config_path, config)
    return {
        "config_path": str(config_path),
        "memory_provider": "brainstack",
        "memory_enabled": False,
        "user_profile_enabled": False,
        "rtk_sidecar_enabled": bool(rtk.get("enabled", False)),
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
HERMES_HOME_DEFAULT=$(CDPATH= cd -- "$(dirname -- "$CONFIG_FILE")" && pwd)
HERMES_HOME_DIR="${HERMES_HOME_DIR:-$HERMES_HOME_DEFAULT}"

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

normalize_runtime_ownership() {
  FIXUP_SERVICE="$SERVICE"
  if [ -z "$FIXUP_SERVICE" ]; then
    return 0
  fi
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps --entrypoint sh "$FIXUP_SERVICE" -lc '
    for path in \
      /opt/data/.env \
      /opt/data/config.yaml \
      /opt/data/auth.json \
      /opt/data/auth.lock \
      /opt/data/gateway_state.json \
      /opt/data/gateway.pid \
      /opt/data/state.db \
      /opt/data/state.db-shm \
      /opt/data/state.db-wal \
      /opt/data/brainstack \
      /opt/data/sessions \
      /opt/data/memories
    do
      [ -e "$path" ] || continue
      chown -R hermes:hermes "$path" 2>/dev/null || true
    done
  ' >/dev/null
}

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
    normalize_runtime_ownership
    dc up -d
    wait_for_ready
    ;;
  rebuild)
    normalize_runtime_ownership
    dc up -d --build
    wait_for_ready
    ;;
  full|full-rebuild)
    normalize_runtime_ownership
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
    normalize_runtime_ownership
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
    doctor = REPO_ROOT / "scripts" / "brainstack_doctor.py"
    cmd = [
        sys.executable,
        str(doctor),
        str(target),
        "--config",
        str(config_path),
        "--runtime",
        args.runtime,
        "--check-docker",
        "--check-desktop-launcher",
    ]
    if planned_install:
        cmd.append("--planned-install")
    if compose_path:
        cmd.extend(["--compose-file", str(compose_path)])
    if args.desktop_launcher:
        cmd.extend(["--desktop-launcher", str(args.desktop_launcher)])
    doctor_python = args.python or _default_target_python(target)
    if doctor_python:
        cmd.extend(["--python", str(doctor_python)])
    proc = subprocess.run(cmd, text=True)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Brainstack into a target Hermes checkout.")
    parser.add_argument("target", help="Path to target Hermes checkout")
    parser.add_argument("--config", type=Path, help="Path to Hermes config.yaml")
    parser.add_argument("--compose-file", type=Path, help="Path to Docker compose file for doctor checks")
    parser.add_argument("--desktop-launcher", type=Path, help="Path to desktop launcher for doctor checks")
    parser.add_argument("--python", type=Path, help="Target Hermes Python interpreter for dependency install and doctor checks")
    parser.add_argument("--runtime", choices=["auto", "docker", "local"], default="auto", help="Target runtime mode")
    parser.add_argument("--enable", action="store_true", help="Patch config.yaml to enable Brainstack and disable builtin memory")
    parser.add_argument("--skip-deps", action="store_true", help="Skip installing missing kuzu/chromadb into the target Hermes Python")
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
    try:
        config_path = args.config.expanduser().resolve() if args.config else _default_config_path(target)
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2
    if not config_path.exists():
        print(
            f"FAIL config not found: {config_path}. Create or select an agent first, then rerun the installer.",
            file=sys.stderr,
        )
        return 2

    compose_path: Path | None = None
    if args.runtime == "docker" or args.compose_file or args.doctor:
        if args.compose_file:
            compose_path = args.compose_file.expanduser().resolve()
        else:
            try:
                compose_path = _default_compose_path(target, config_path)
            except RuntimeError as exc:
                if args.runtime == "docker":
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
    helper_files: list[dict[str, str]] = []
    if SOURCE_RTK.exists() and (target / "agent").is_dir():
        helper_target = target / "agent" / "rtk_sidecar.py"
        helper_files.append({"source": "rtk_sidecar.py", "target": str(helper_target), "sha256": _hash_file(SOURCE_RTK)})
        if not args.dry_run:
            shutil.copy2(SOURCE_RTK, helper_target)

    generated_files: list[dict[str, str]] = []
    if args.runtime == "docker":
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
        config_result = _patch_config(config_path, args.dry_run)
    deps_result = _ensure_backend_dependencies(selected_python, dry_run=args.dry_run, skip_deps=args.skip_deps)

    host_helper_files: list[dict[str, str]] = []
    if SOURCE_HOST_PAYLOAD.exists():
        for src_file in _iter_payload_files(SOURCE_HOST_PAYLOAD):
            rel = src_file.relative_to(SOURCE_HOST_PAYLOAD)
            host_helper_files.append(_copy_file(src_file, target / rel, args.dry_run))

    host_patches: list[str] = []
    host_patches.extend(_patch_run_agent(target / "run_agent.py", args.dry_run))
    host_patches.extend(_patch_memory_manager(target / "agent" / "memory_manager.py", args.dry_run))
    host_patches.extend(_patch_gateway_run(target / "gateway" / "run.py", args.dry_run))
    host_patches.extend(_patch_gateway_status(target / "gateway" / "status.py", args.dry_run))
    host_patches.extend(_patch_discord_platform(target / "gateway" / "platforms" / "discord.py", args.dry_run))
    if args.runtime == "docker":
        assert compose_path is not None
        host_patches.extend(_patch_compose_healthcheck(compose_path, args.dry_run))
        host_patches.extend(_patch_dockerignore(target / ".dockerignore", args.dry_run))
        host_patches.extend(_patch_docker_entrypoint(target / "docker" / "entrypoint.sh", args.dry_run))

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
        "dependency_install": deps_result,
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
    if deps_result.get("status") in {"planned", "installed", "already_satisfied"}:
        print(f"{action} backend deps: {deps_result['status']}")
    elif deps_result.get("status") == "skipped":
        print(f"{action} backend deps: skipped ({deps_result.get('reason')})")
    if not args.dry_run:
        print(f"Wrote manifest: {target / '.brainstack-install-manifest.json'}")

    if args.doctor:
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
