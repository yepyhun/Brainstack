"""Brainstack-only host mode helpers.

These helpers define when Hermes must treat Brainstack as the sole memory
authority and hide legacy memory/session-search tool paths.
"""

from __future__ import annotations

from typing import Any, Iterable

LEGACY_MEMORY_TOOL_NAMES = frozenset({"memory", "session_search"})


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

