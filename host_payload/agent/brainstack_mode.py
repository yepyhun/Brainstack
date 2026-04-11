"""Brainstack-only host mode helpers.

These helpers define when Hermes must treat Brainstack as the sole memory
authority and hide legacy memory/session-search tool paths.
"""

from __future__ import annotations

from typing import Any, Iterable

LEGACY_MEMORY_TOOL_NAMES = frozenset({"memory", "session_search"})
PERSONAL_MEMORY_SKILL_ACTIONS = frozenset({"create", "edit", "patch", "write_file"})
PERSONAL_MEMORY_SKILL_MARKERS = (
    "user-profile",
    "user_profile",
    "profile",
    "preference",
    "preferences",
    "communication",
    "communication-style",
    "communication_style",
    "identity",
    "persona",
    "humanizer",
    "emoji",
    "em dash",
    "jargon",
    "tone",
    "style",
)


def _memory_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    memory = config.get("memory", {})
    return memory if isinstance(memory, dict) else {}


def is_brainstack_only_mode(config: dict[str, Any] | None) -> bool:
    memory = _memory_config(config)
    provider = str(memory.get("provider", "")).strip().lower()
    if provider != "brainstack":
        return False
    if bool(memory.get("memory_enabled", False)):
        return False
    if bool(memory.get("user_profile_enabled", False)):
        return False
    return True


def filter_legacy_memory_tool_defs(
    tool_defs: Iterable[dict[str, Any]] | None,
    *,
    config: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    defs = list(tool_defs or [])
    if not is_brainstack_only_mode(config):
        return defs
    return [
        item
        for item in defs
        if item.get("function", {}).get("name") not in LEGACY_MEMORY_TOOL_NAMES
    ]


def _skill_manage_targets_personal_memory(function_args: dict[str, Any] | None) -> bool:
    if not isinstance(function_args, dict):
        return False
    action = str(function_args.get("action", "")).strip().lower()
    if action not in PERSONAL_MEMORY_SKILL_ACTIONS:
        return False
    payload = "\n".join(
        str(function_args.get(key, "")).strip().lower()
        for key in ("name", "category", "content", "file_path", "file_content", "old_string", "new_string")
    )
    return any(marker in payload for marker in PERSONAL_MEMORY_SKILL_MARKERS)


def blocked_brainstack_only_tool_error(function_name: str, function_args: dict[str, Any] | None = None) -> str | None:
    name = str(function_name or "").strip()
    if name in LEGACY_MEMORY_TOOL_NAMES:
        return f"{name} is disabled while Brainstack owns memory."
    if name == "skill_manage" and _skill_manage_targets_personal_memory(function_args):
        return "skill_manage cannot store personal profile or communication-style memory while Brainstack owns memory."
    return None
