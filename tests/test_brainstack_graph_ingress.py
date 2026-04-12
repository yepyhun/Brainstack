from pathlib import Path
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if "agent" not in sys.modules:
    agent_module = types.ModuleType("agent")
    agent_module.__path__ = []
    sys.modules["agent"] = agent_module

if "agent.memory_provider" not in sys.modules:
    memory_provider_module = types.ModuleType("agent.memory_provider")

    class MemoryProvider:  # pragma: no cover - import shim for source tests
        pass

    memory_provider_module.MemoryProvider = MemoryProvider
    sys.modules["agent.memory_provider"] = memory_provider_module

if "hermes_constants" not in sys.modules:
    hermes_constants = types.ModuleType("hermes_constants")
    hermes_constants.get_hermes_home = lambda: REPO_ROOT
    sys.modules["hermes_constants"] = hermes_constants

from brainstack.graph import _extract_graph_candidates


def test_legacy_graph_ingress_ignores_broad_role_like_sentences():
    candidates = _extract_graph_candidates("Do you think his rejection is a defense mechanism?")
    assert candidates == []


def test_legacy_graph_ingress_keeps_status_and_location_patterns():
    candidates = _extract_graph_candidates("Project Atlas is active now. Laura is in Budapest.")
    assert any(item["kind"] == "state" and item["attribute"] == "status" for item in candidates)
    assert any(item["kind"] == "state" and item["attribute"] == "location" for item in candidates)
