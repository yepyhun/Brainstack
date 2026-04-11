"""Brainstack-only host mode helpers.

These helpers define when Hermes must treat Brainstack as the sole memory
authority and hide legacy memory/session-search tool paths.
"""

from __future__ import annotations

from typing import Any, Iterable

LEGACY_MEMORY_TOOL_NAMES = frozenset({"memory", "session_search"})
PERSONAL_MEMORY_FILE_TOOL_NAMES = frozenset({"read_file", "write_file", "patch"})
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
PERSONAL_MEMORY_NOTES_PATH_MARKERS = (
    "/.hermes/notes/",
    "~/.hermes/notes/",
)
PERSONAL_MEMORY_HERMES_ROOT_MARKERS = (
    "/.hermes/",
    "~/.hermes/",
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


def _normalize_candidate_path(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\\", "/").lower()


def _file_tool_targets_personal_memory(function_args: dict[str, Any] | None) -> bool:
    if not isinstance(function_args, dict):
        return False
    candidate_paths = [
        _normalize_candidate_path(function_args.get("path")),
        _normalize_candidate_path(function_args.get("file_path")),
    ]
    for candidate in candidate_paths:
        if not candidate:
            continue
        if any(marker in candidate for marker in PERSONAL_MEMORY_NOTES_PATH_MARKERS):
            return True
        if any(marker in candidate for marker in PERSONAL_MEMORY_HERMES_ROOT_MARKERS) and candidate.endswith(
            ("/memory.md", "/user.md")
        ):
            return True
    return False


def brainstack_only_personal_memory_guidance() -> str:
    return (
        "Brainstack owns personal memory in this mode. Keep user identity, preferences, "
        "communication style, and project context inside Brainstack. Do not create or "
        "maintain notes files, MEMORY.md, USER.md, or skill records for that kind of memory. "
        "Use skill_manage only for reusable procedures or workflows."
    )


def blocked_brainstack_only_tool_error(function_name: str, function_args: dict[str, Any] | None = None) -> str | None:
    name = str(function_name or "").strip()
    if name in LEGACY_MEMORY_TOOL_NAMES:
        return f"{name} is disabled while Brainstack owns memory."
    if name == "skill_manage" and _skill_manage_targets_personal_memory(function_args):
        return "skill_manage cannot store personal profile or communication-style memory while Brainstack owns memory."
    if name in PERSONAL_MEMORY_FILE_TOOL_NAMES and _file_tool_targets_personal_memory(function_args):
        return (
            f"{name} cannot read or write Hermes side-memory files while Brainstack owns personal memory. "
            "Keep personal preferences and identity in Brainstack instead."
        )
    return None
