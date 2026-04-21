"""Compatibility helpers for older host payload imports.

These names remain importable so older Hermes checkouts do not explode on
import, but Phase 52/53 native-seam mode does not use Brainstack-only tool
gating or host-level output enforcement.
"""

from __future__ import annotations

from typing import Any, Iterable


LEGACY_MEMORY_TOOL_NAMES = frozenset()


def is_brainstack_only_mode(config: dict[str, Any] | None) -> bool:
    del config
    return False


def filter_legacy_memory_tool_defs(
    tool_defs: Iterable[dict[str, Any]] | None,
    *,
    config: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    del config
    return list(tool_defs or [])


def brainstack_only_personal_memory_guidance() -> str:
    return ""


def blocked_brainstack_only_tool_error(
    function_name: str,
    function_args: dict[str, Any] | None = None,
) -> str | None:
    del function_name, function_args
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


def validate_brainstack_output(memory_manager: Any, content: str) -> dict[str, Any]:
    del memory_manager
    return _default_output_validation_result(str(content or ""))
