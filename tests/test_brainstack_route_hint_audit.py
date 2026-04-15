from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "audit_brainstack_route_hint.py"


def _load_script_module():
    fake_agent = types.ModuleType("agent")
    fake_memory_provider = types.ModuleType("agent.memory_provider")
    fake_memory_provider.MemoryProvider = object
    sys.modules.setdefault("agent", fake_agent)
    sys.modules["agent.memory_provider"] = fake_memory_provider
    spec = importlib.util.spec_from_file_location("brainstack_route_hint_audit_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_select_entries_uses_canary_and_extra_audit_ids(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(module, "FIXED_CANARY_QUESTION_IDS", ["q2", "q1"])
    monkeypatch.setattr(module, "EXTRA_ROUTE_AUDIT_QUESTION_IDS", ["q3"])
    entries = [
        {"question_id": "q1", "question": "one", "question_type": "fact"},
        {"question_id": "q2", "question": "two", "question_type": "fact"},
        {"question_id": "q3", "question": "three", "question_type": "fact"},
    ]

    chosen = module._select_entries(
        entries,
        sample_size=2,
        seed=7,
        question_ids=[],
        canary=True,
        include_extra_route_audit_cases=True,
    )

    assert [entry["question_id"] for entry in chosen] == ["q2", "q1", "q3"]


def test_select_entries_prefers_explicit_question_ids_without_canary():
    module = _load_script_module()
    entries = [
        {"question_id": "q1", "question": "one", "question_type": "fact"},
        {"question_id": "q2", "question": "two", "question_type": "fact"},
    ]

    chosen = module._select_entries(
        entries,
        sample_size=2,
        seed=7,
        question_ids=["q2"],
        canary=False,
        include_extra_route_audit_cases=False,
    )

    assert [entry["question_id"] for entry in chosen] == ["q2"]
