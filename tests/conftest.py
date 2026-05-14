from __future__ import annotations

from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
HERMES_CONTINUATION_EXTENSION = ROOT / "extensions" / "hermes_continuation"
if HERMES_CONTINUATION_EXTENSION.exists() and str(HERMES_CONTINUATION_EXTENSION) not in sys.path:
    sys.path.insert(0, str(HERMES_CONTINUATION_EXTENSION))


agent_module = types.ModuleType("agent")
memory_provider_module = types.ModuleType("agent.memory_provider")


class MemoryProvider:
    pass


setattr(memory_provider_module, "MemoryProvider", MemoryProvider)
sys.modules.setdefault("agent", agent_module)
sys.modules.setdefault("agent.memory_provider", memory_provider_module)
