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
        "model": {"provider": "openai-codex", "default": "gpt-5.5"},
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
    assert status["summary"]["all_required_routes_ready"] is True
    assert set(config["plugins"]["brainstack"]["background_tasks"]) == {
        binding["task_id"] for binding in REQUIRED_BACKGROUND_TASK_BINDINGS
    }


def test_installer_defaults_brainstack_background_routes_to_current_main_model() -> None:
    config: dict = {
        "model": {"provider": "openai-codex", "default": "gpt-5.5"},
        "plugins": {"brainstack": {}},
        "auxiliary": {},
    }

    status = install_default_background_task_bindings(config)

    for binding in REQUIRED_BACKGROUND_TASK_BINDINGS:
        route = config["auxiliary"][binding["hermes_task_slot"]]
        assert route["provider"] == "main"
        assert route["model"] == ""
    assert status["summary"]["all_required_routes_explicit"] is True
    assert status["summary"]["all_required_routes_ready"] is True
    assert {task["effective_model_label"] for task in status["tasks"]} == {"gpt-5.5"}


def test_installer_normalizes_auto_background_routes_to_current_main_model() -> None:
    config: dict = {"plugins": {"brainstack": {}}, "auxiliary": {"flush_memories": {"provider": "auto"}}}

    status = install_default_background_task_bindings(config)

    assert config["auxiliary"]["flush_memories"]["provider"] == "main"
    assert config["auxiliary"]["flush_memories"]["model"] == ""
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
    auxiliary_module._get_auxiliary_task_config = lambda task: {"provider": "main", "model": "gpt-5.5"}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_module)

    require_explicit_hermes_auxiliary_route("flush_memories")


def test_runtime_guard_rejects_main_route_without_model(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_module = ModuleType("agent")
    auxiliary_module = ModuleType("agent.auxiliary_client")
    auxiliary_module._get_auxiliary_task_config = lambda task: {"provider": "main", "model": ""}  # type: ignore[attr-defined]
    hermes_cli_module = ModuleType("hermes_cli")
    config_module = ModuleType("hermes_cli.config")
    config_module.load_config = lambda: {"model": {"provider": "openai-codex", "default": ""}}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_module)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli_module)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    with pytest.raises(RuntimeError, match="AUXILIARY_MAIN_MODEL_UNRESOLVED"):
        require_explicit_hermes_auxiliary_route("flush_memories")


def test_runtime_guard_allows_main_route_when_current_model_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_module = ModuleType("agent")
    auxiliary_module = ModuleType("agent.auxiliary_client")
    auxiliary_module._get_auxiliary_task_config = lambda task: {"provider": "main", "model": ""}  # type: ignore[attr-defined]
    hermes_cli_module = ModuleType("hermes_cli")
    config_module = ModuleType("hermes_cli.config")
    config_module.load_config = lambda: {"model": {"provider": "openai-codex", "default": "gpt-5.5"}}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "agent", agent_module)
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", auxiliary_module)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli_module)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    require_explicit_hermes_auxiliary_route("flush_memories")


def test_installer_rewrites_stale_main_model_to_current_main_inheritance() -> None:
    config: dict = {
        "model": {"provider": "openai-codex", "default": "gpt-5.5"},
        "plugins": {"brainstack": {}},
        "auxiliary": {
            "flush_memories": {"provider": "main", "model": "gpt-5.5"},
            CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "main", "model": "stepfun/step-3.5-flash"},
            QUERY_UNDERSTANDING_HERMES_TASK_SLOT: {"provider": "main", "model": "gpt-5.5"},
        },
    }

    status = install_default_background_task_bindings(config)

    capture = next(
        task
        for task in status["tasks"]
        if task["hermes_task_slot"] == CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT
    )
    assert config["auxiliary"][CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT]["provider"] == "main"
    assert config["auxiliary"][CAPTURE_UNDERSTANDING_HERMES_TASK_SLOT]["model"] == ""
    assert capture["status"] == "active"
    assert capture["route_readiness_status"] == "ready"
    assert capture["effective_model_label"] == "gpt-5.5"
    assert status["summary"]["all_required_routes_ready"] is True
