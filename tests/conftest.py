from __future__ import annotations

import sys
import types


agent_module = types.ModuleType("agent")
memory_provider_module = types.ModuleType("agent.memory_provider")


class MemoryProvider:
    pass


setattr(memory_provider_module, "MemoryProvider", MemoryProvider)
sys.modules.setdefault("agent", agent_module)
sys.modules.setdefault("agent.memory_provider", memory_provider_module)
