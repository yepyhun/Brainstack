from __future__ import annotations

import sys
import types


def install_host_shim_if_needed() -> None:
    """Allow Brainstack proof scripts to import the Hermes plugin outside Hermes."""
    if "agent.memory_provider" in sys.modules:
        return
    try:
        __import__("agent.memory_provider")
        return
    except ModuleNotFoundError:
        pass

    agent_module = types.ModuleType("agent")
    memory_provider_module = types.ModuleType("agent.memory_provider")

    class MemoryProvider:
        """Minimal base class used only when Hermes host modules are unavailable."""

    setattr(memory_provider_module, "MemoryProvider", MemoryProvider)
    sys.modules.setdefault("agent", agent_module)
    sys.modules.setdefault("agent.memory_provider", memory_provider_module)
