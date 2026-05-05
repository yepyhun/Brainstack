from __future__ import annotations

import sys
from types import ModuleType

import pytest

from brainstack.background_task_binding import (
    BACKGROUND_CONSOLIDATION_TASK_ID,
    CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT,
    QUERY_UNDERSTANDING_HERMES_TASK_SLOT,
    REQUIRED_BACKGROUND_TASK_BINDINGS,
    build_background_task_status,
    install_default_background_task_bindings,
    require_explicit_hermes_auxiliary_route,
)


def test_background_task_status_fails_closed_without_explicit_routes() -> None:
    status = build_background_task_status({})

    assert status["schema"] == "brainstack.background_task_status.v1"
    assert status["tier2_write_allowed"] is False
    assert status["summary"]["configured_unavailable"] == len(REQUIRED_BACKGROUND_TASK_BINDINGS)
    assert {task["fallback_policy"] for task in status["tasks"]} == {"none"}
    assert all(task["secret_redacted"] is True for task in status["tasks"])


def test_background_task_status_blocks_ambient_auto_fallback() -> None:
    status = build_background_task_status(
        {
            "background_tasks": {
                BACKGROUND_CONSOLIDATION_TASK_ID: {
                    "status": "active",
                    "provider_label": "auto",
                    "fallback_policy": "none",
                }
            }
        }
    )

    task = next(item for item in status["tasks"] if item["task_id"] == BACKGROUND_CONSOLIDATION_TASK_ID)
    assert task["status"] == "blocked"
    assert task["tier2_write_allowed"] is False
    assert "ambient_auto_fallback_not_allowed" in task["issues"]


def test_installer_materializes_explicit_hermes_owned_background_routes() -> None:
    config: dict = {
        "plugins": {"brainstack": {}},
        "auxiliary": {
            "flush_memories": {"provider": "main"},
            CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "openrouter", "model": "example/model"},
            QUERY_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "custom", "base_url": "http://127.0.0.1:8000/v1"},
        },
    }

    status = install_default_background_task_bindings(config)

    assert config["auxiliary"]["flush_memories"]["provider"] == "main"
    assert config["auxiliary"][CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT]["provider"] == "openrouter"
    assert config["auxiliary"][QUERY_UNDERSTANDING_HERMES_TASK_SLOT]["provider"] == "custom"
    assert status["tier2_write_allowed"] is True
    assert status["summary"]["all_required_routes_explicit"] is True
    assert set(config["plugins"]["brainstack"]["background_tasks"]) == {
        binding["task_id"] for binding in REQUIRED_BACKGROUND_TASK_BINDINGS
    }


def test_installer_records_unavailable_without_silent_main_fallback() -> None:
    config: dict = {"plugins": {"brainstack": {}}, "auxiliary": {"flush_memories": {"provider": "auto"}}}

    status = install_default_background_task_bindings(config)

    assert config["auxiliary"]["flush_memories"]["provider"] == "auto"
    assert status["tier2_write_allowed"] is False
    assert status["summary"]["configured_unavailable"] == len(REQUIRED_BACKGROUND_TASK_BINDINGS)


def test_runtime_guard_rejects_ambient_auxiliary_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_module = ModuleType("agent")
    auxiliary_module = ModuleType("agent.auxiliary_client")
    auxiliary_module._get_auxiliary_task_config = lambda task: {"provider": "auto"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_module)

    with pytest.raises(RuntimeError, match="requires an explicit Hermes auxiliary route"):
        require_explicit_hermes_auxiliary_route("flush_memories")


def test_runtime_guard_allows_explicit_auxiliary_route(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_module = ModuleType("agent")
    auxiliary_module = ModuleType("agent.auxiliary_client")
    auxiliary_module._get_auxiliary_task_config = lambda task: {"provider": "main"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_module)

    require_explicit_hermes_auxiliary_route("flush_memories")
