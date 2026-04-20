"""Legacy Brainstack-only host mode helpers.

These helpers were used by the older Brainstack-only host mode where Hermes
builtin explicit memory and user-profile writes were disabled. Phase-52 native
seam mode keeps these helpers as legacy compatibility code only; new installs do
not copy them by default.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

LEGACY_MEMORY_TOOL_NAMES = frozenset({"memory"})
PERSONAL_MEMORY_FILE_TOOL_NAMES = frozenset({"read_file", "write_file", "patch"})
PERSONAL_MEMORY_EXECUTION_TOOL_NAMES = frozenset({"execute_code", "terminal"})
PERSONAL_MEMORY_AUTONOMY_TOOL_NAMES = frozenset({"cronjob"})
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
PERSONAL_MEMORY_SIDE_FILE_SUFFIXES = (
    "/memory.md",
    "/user.md",
    "/persona.md",
)
PERSONAL_MEMORY_SKILL_PATH_MARKERS = (
    "/.hermes/skills/",
    "~/.hermes/skills/",
)
PERSONAL_MEMORY_AUTONOMY_ACTIONS = frozenset({"create", "update", "run"})
PERSONAL_MEMORY_AUTONOMY_MARKERS = (
    "remember",
    "memorize",
    "memory",
    "profile",
    "preference",
    "preferences",
    "persona",
    "style",
    "communication",
    "identity",
    "assistant name",
    "store user",
)
PERSONAL_MEMORY_SECONDARY_MEMORY_API_MARKERS = (
    "plur_learn",
    "plur_recall",
    "plur_recall_hybrid",
    "plur_inject",
    "plur_inject_hybrid",
    "hermes_tools",
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
            PERSONAL_MEMORY_SIDE_FILE_SUFFIXES
        ):
            return True
    return False


def _payload_targets_personal_memory(function_args: dict[str, Any] | None) -> bool:
    if not isinstance(function_args, dict):
        return False
    payload = "\n".join(
        _normalize_candidate_path(function_args.get(key))
        for key in ("code", "command", "content", "file_content", "path", "file_path")
    )
    if not payload:
        return False
    if any(marker in payload for marker in PERSONAL_MEMORY_NOTES_PATH_MARKERS):
        return True
    if any(marker in payload for marker in PERSONAL_MEMORY_SIDE_FILE_SUFFIXES):
        return True
    if any(marker in payload for marker in PERSONAL_MEMORY_SECONDARY_MEMORY_API_MARKERS):
        return True
    return any(marker in payload for marker in PERSONAL_MEMORY_SKILL_PATH_MARKERS) and any(
        marker in payload for marker in PERSONAL_MEMORY_SKILL_MARKERS
    )


def _autonomy_tool_targets_personal_memory(function_args: dict[str, Any] | None) -> bool:
    if not isinstance(function_args, dict):
        return False
    action = str(function_args.get("action", "")).strip().lower()
    if action not in PERSONAL_MEMORY_AUTONOMY_ACTIONS:
        return False
    payload = "\n".join(
        str(function_args.get(key, "")).strip().lower()
        for key in ("name", "prompt", "description", "skills", "script")
    )
    return any(marker in payload for marker in PERSONAL_MEMORY_AUTONOMY_MARKERS)


def brainstack_only_personal_memory_guidance() -> str:
    return (
        "Brainstack owns personal memory in this mode. Keep user identity, preferences, "
        "communication style, and project context inside Brainstack. Do not create or "
        "maintain notes files, MEMORY.md, USER.md, persona.md, or side skill files for that kind "
        "of memory. Do not use ad hoc code, terminal writes, file edits, cronjob scheduling, or "
        "other automation detours to persist or recover personal memory. Do not use secondary "
        "memory APIs from ad hoc code either. session_search may be used only as explicit "
        "conversation search, not as a second personal-memory system. Use skill_manage only for "
        "reusable procedures or workflows."
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
    if name in PERSONAL_MEMORY_EXECUTION_TOOL_NAMES and _payload_targets_personal_memory(function_args):
        return (
            f"{name} cannot use code or shell detours to read or write Hermes side-memory files or "
            "secondary memory APIs while Brainstack owns personal memory."
        )
    if name in PERSONAL_MEMORY_AUTONOMY_TOOL_NAMES and _autonomy_tool_targets_personal_memory(function_args):
        return (
            f"{name} cannot create or update automation jobs that store personal identity, preferences, "
            "or communication style while Brainstack owns personal memory."
        )
    return None


def _find_brainstack_provider(memory_manager: Any) -> Any | None:
    providers = getattr(memory_manager, "providers", None)
    if not isinstance(providers, list):
        return None
    for provider in providers:
        if getattr(provider, "name", "") == "brainstack":
            return provider
    return None


def _default_output_validation_result(content: str) -> dict[str, Any]:
    text = str(content or "")
    return {
        "content": text,
        "applied": False,
        "changed": False,
        "status": "skipped",
        "blocked": False,
        "can_ship": True,
        "remaining_violations": [],
    }


def _blocked_output_delivery_text() -> str:
    return (
        "Brainstack output blocked because the reply breaks an active communication rule. "
        "Please regenerate the answer in compliant form."
    )


def validate_brainstack_output(memory_manager: Any, content: str) -> dict[str, Any]:
    text = str(content or "")
    result = _default_output_validation_result(text)
    if not text or memory_manager is None:
        return result
    provider = _find_brainstack_provider(memory_manager)
    if provider is None:
        return result
    validator = getattr(provider, "validate_assistant_output", None)
    if not callable(validator):
        return result
    try:
        validated = validator(text)
    except Exception:
        logger.warning("Brainstack final-output validation failed", exc_info=True)
        return result
    if isinstance(validated, dict):
        result.update(validated)
    result["content"] = str(result.get("content") or text)
    result["applied"] = bool(result.get("applied", False))
    result["changed"] = bool(result.get("changed", False))
    result["blocked"] = bool(result.get("blocked", False))
    result["can_ship"] = bool(result.get("can_ship", not result["blocked"]))
    result["remaining_violations"] = list(result.get("remaining_violations") or [])
    delivered_content = result["content"]
    if result["blocked"] or not result["can_ship"]:
        result["status"] = "blocked"
        result["blocked"] = True
        result["can_ship"] = False
        delivered_content = _blocked_output_delivery_text()
        result["content"] = delivered_content
    recorder = getattr(provider, "record_output_validation_delivery", None)
    if callable(recorder):
        try:
            recorder(result, delivered_content=delivered_content)
        except Exception:
            logger.warning("Brainstack output delivery trace failed", exc_info=True)
    return result


def apply_brainstack_output_validation(memory_manager: Any, content: str) -> str:
    result = validate_brainstack_output(memory_manager, content)
    text = str(content or "")
    if not isinstance(result, dict):
        return text
    validated = str(result.get("content") or text)
    return validated or text
