"""Minimal import shims for Brainstack source tests that import Bestie host code."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any, cast


def _module_stub(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(module, attr_name, attr_value)
    return module


def install_host_import_shims(*, hermes_home: Path | None = None) -> None:
    """Stabilize import-time-only host dependencies for source-repo tests."""
    sys.modules.setdefault("fire", _module_stub("fire", Fire=lambda *a, **k: None))
    sys.modules.setdefault("firecrawl", _module_stub("firecrawl", Firecrawl=object))
    sys.modules.setdefault("fal_client", _module_stub("fal_client"))
    agent_module = cast(Any, sys.modules.get("agent"))
    if agent_module is None:
        agent_module = cast(Any, _module_stub("agent"))
        agent_module.__path__ = []
        sys.modules["agent"] = agent_module
    memory_provider_module = cast(Any, sys.modules.get("agent.memory_provider"))
    if memory_provider_module is None:
        class MemoryProvider:  # pragma: no cover - import shim for source tests
            pass

        memory_provider_module = cast(Any, _module_stub("agent.memory_provider", MemoryProvider=MemoryProvider))
        sys.modules["agent.memory_provider"] = memory_provider_module

    hermes_constants = cast(Any, sys.modules.get("hermes_constants"))
    needs_real_constants = hermes_constants is None or not hasattr(hermes_constants, "OPENROUTER_BASE_URL")
    if needs_real_constants:
        bestie_constants = Path(__file__).resolve().parents[3] / "memory-repo-bakeoff" / "hermes-agent-bestie-latest" / "hermes_constants.py"
        if bestie_constants.exists():
            spec = importlib.util.spec_from_file_location("hermes_constants", bestie_constants)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                hermes_constants = cast(Any, module)
                sys.modules["hermes_constants"] = hermes_constants

    if hermes_constants is None:
        hermes_constants = cast(Any, _module_stub("hermes_constants"))
        sys.modules["hermes_constants"] = hermes_constants
    if not hasattr(hermes_constants, "OPENROUTER_BASE_URL"):
        hermes_constants.OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    if hermes_home is not None:
        hermes_constants.get_hermes_home = lambda: hermes_home
    elif not hasattr(hermes_constants, "get_hermes_home"):
        hermes_constants.get_hermes_home = lambda: Path("/tmp")
