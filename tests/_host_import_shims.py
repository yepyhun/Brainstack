"""Minimal import shims for Brainstack source tests that import Hermes host code."""

from __future__ import annotations

import importlib.util
import importlib
import sys
import types
from pathlib import Path
from typing import Any, cast


def _module_stub(name: str, **attrs: object) -> types.ModuleType:
    module = types.ModuleType(name)
    for attr_name, attr_value in attrs.items():
        setattr(module, attr_name, attr_value)
    return module


def _locate_hermes_checkout() -> Path | None:
    repo_root = Path(__file__).resolve().parents[1]

    env_candidates = []
    for key in ("BRAINSTACK_HERMES_ROOT", "HERMES_ROOT"):
        value = str(__import__("os").environ.get(key, "")).strip()
        if value:
            env_candidates.append(Path(value).expanduser())

    candidates = list(env_candidates)
    search_roots = [repo_root.parent, repo_root.parent.parent]
    for root in search_roots:
        if not root.exists():
            continue
        for pattern in ("*", "*/*"):
            for candidate in root.glob(pattern):
                if candidate.is_dir():
                    candidates.append(candidate)
    for candidate in candidates:
        if (candidate / "run_agent.py").exists() and (candidate / "hermes_constants.py").exists():
            return candidate
    return None


def install_host_import_shims(*, hermes_home: Path | None = None) -> None:
    """Stabilize import-time-only host dependencies for source-repo tests."""
    hermes_checkout = _locate_hermes_checkout()
    if hermes_checkout is not None:
        hermes_path = str(hermes_checkout)
        if hermes_path not in sys.path:
            sys.path.insert(0, hermes_path)

    sys.modules.setdefault("fire", _module_stub("fire", Fire=lambda *a, **k: None))
    sys.modules.setdefault("firecrawl", _module_stub("firecrawl", Firecrawl=object))
    sys.modules.setdefault("fal_client", _module_stub("fal_client"))
    if "openai" not in sys.modules:
        class _FakeOpenAI:  # pragma: no cover - import shim for source tests
            def __init__(self, **kwargs):
                self.api_key = kwargs.get("api_key")
                self.base_url = kwargs.get("base_url")

            def close(self) -> None:
                return None

        sys.modules["openai"] = _module_stub("openai", OpenAI=_FakeOpenAI)
    agent_module = cast(Any, sys.modules.get("agent"))
    if agent_module is None and hermes_checkout is not None and (hermes_checkout / "agent").exists():
        agent_module = cast(Any, _module_stub("agent"))
        agent_module.__path__ = [str(hermes_checkout / "agent")]
        sys.modules["agent"] = agent_module
    elif agent_module is None:
        agent_module = cast(Any, _module_stub("agent"))
        agent_module.__path__ = []
        sys.modules["agent"] = agent_module

    memory_provider_module = cast(Any, sys.modules.get("agent.memory_provider"))
    if memory_provider_module is None:
        try:
            importlib.import_module("agent.memory_provider")
        except Exception:
            class MemoryProvider:  # pragma: no cover - import shim for source tests
                pass

            memory_provider_module = cast(Any, _module_stub("agent.memory_provider", MemoryProvider=MemoryProvider))
            sys.modules["agent.memory_provider"] = memory_provider_module

    hermes_constants = cast(Any, sys.modules.get("hermes_constants"))
    needs_real_constants = hermes_constants is None or not hasattr(hermes_constants, "OPENROUTER_BASE_URL")
    if needs_real_constants:
        constants_path = hermes_checkout / "hermes_constants.py" if hermes_checkout is not None else None
        if constants_path and constants_path.exists():
            spec = importlib.util.spec_from_file_location("hermes_constants", constants_path)
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
