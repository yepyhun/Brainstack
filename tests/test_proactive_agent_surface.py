from __future__ import annotations

import json
from pathlib import Path

import yaml

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "proactive_mode: automatic\n"
        "proactive_cooldown_seconds: 21600\n"
        "proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
        }
    )
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _provider_with_plugin_config(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home_nested"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "plugins:\n"
        "  brainstack:\n"
        "    proactive_mode: automatic\n"
        "    proactive_cooldown_seconds: 21600\n"
        "    proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack-nested.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
        }
    )
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _provider_with_kernel_memory_config(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home_kernel_memory"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "kernel_memory:\n"
        "  proactive_mode: automatic\n"
        "  proactive_cooldown_seconds: 21600\n"
        "  proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack-kernel-memory.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
        }
    )
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _create_item(provider: BrainstackMemoryProvider, *, scope: str | None = None) -> str:
    assert provider._store is not None
    item = provider._store.upsert_proactive_event(
        source="test",
        kind="follow_up",
        principal_scope_key=scope or provider._principal_scope_key,
        title="Review release notes",
        summary="A proactive follow-up exists for the release notes.",
        priority="normal",
        intended_next_action="request_input",
        evidence_ids=["ev_public_1"],
        source_ref="test-fixture",
        idempotency_key=f"test:{scope or provider._principal_scope_key}",
    )
    return str(item["event_id"])


def test_proactive_status_is_tool_backed_and_read_only(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _create_item(provider)
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))

        assert payload["schema"] == "brainstack.proactive_agent_surface.v1"
        assert payload["operation"] == "status"
        assert payload["read_only"] is True
        assert payload["side_effect"] is False
        assert payload["config"]["mode"] == "automatic"
        assert payload["config"]["kill_switch"] is False
        assert payload["counts"]["total_items_sampled"] == 1
        assert payload["current_assignment_authority"] is False
        assert "send_notification" in payload["blocked_actions"]
    finally:
        provider.shutdown()


def test_proactive_status_reads_brainstack_plugin_config(tmp_path: Path) -> None:
    provider = _provider_with_plugin_config(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))

        assert payload["config"]["mode"] == "automatic"
        assert payload["config"]["brainstack_plugin_mode"] == "automatic"
        assert payload["config"]["kill_switch"] is False
    finally:
        provider.shutdown()


def test_proactive_status_reads_kernel_memory_config(tmp_path: Path) -> None:
    provider = _provider_with_kernel_memory_config(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))

        assert payload["config"]["mode"] == "automatic"
        assert payload["config"]["kernel_memory_mode"] == "automatic"
        assert payload["config"]["kill_switch"] is False
    finally:
        provider.shutdown()


def test_proactive_list_and_inspect_are_scope_safe(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        other_event_id = _create_item(provider, scope="other-scope")

        listed = json.loads(provider.handle_tool_call("brainstack_proactive_list", {"limit": 10}))
        assert listed["read_only"] is True
        assert listed["item_count"] == 1
        assert listed["items"][0]["event_id"] == event_id
        assert listed["items"][0]["current_assignment_authority"] is False

        inspected = json.loads(provider.handle_tool_call("brainstack_proactive_inspect", {"event_id": event_id}))
        assert inspected["reason_code"] == "PROACTIVE_INSPECT_TOOL_BACKED"
        assert inspected["read_only"] is True
        assert inspected["item"]["event_id"] == event_id

        rejected = json.loads(provider.handle_tool_call("brainstack_proactive_inspect", {"event_id": other_event_id}))
        assert rejected["reason_code"] == "PROACTIVE_ITEM_SCOPE_MISMATCH"
        assert rejected["status"] == "rejected"
    finally:
        provider.shutdown()


def test_proactive_control_requires_explicit_user_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {"action": "set_item_state", "event_id": event_id, "state": "accepted"},
            )
        )

        assert payload["schema"] == "brainstack.proactive_agent_control.v1"
        assert payload["status"] == "rejected"
        assert payload["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"
        assert payload["side_effect"] is False
    finally:
        provider.shutdown()


def test_proactive_control_updates_item_state_without_current_assignment_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {
                    "action": "set_item_state",
                    "explicit_user_request": True,
                    "event_id": event_id,
                    "state": "accepted",
                    "reason_code": "USER_ACCEPTED",
                    "trace_id": "trace-public",
                },
            )
        )

        assert payload["status"] == "committed"
        assert payload["side_effect"] is True
        assert payload["state"] == "accepted"
        assert payload["current_assignment_authority"] is False
        assert payload["result"]["item"]["state"] == "accepted"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_updates_only_runtime_config(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {
                    "action": "set_kill_switch",
                    "explicit_user_request": True,
                    "kill_switch": True,
                    "reason_code": "USER_DISABLED_PROACTIVE",
                },
            )
        )

        assert payload["status"] == "committed"
        assert payload["action"] == "set_kill_switch"
        assert payload["side_effect"] is True
        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_kill_switch"] is True
        assert data["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_preserves_plugin_config_location(tmp_path: Path) -> None:
    provider = _provider_with_plugin_config(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {
                    "action": "set_kill_switch",
                    "explicit_user_request": True,
                    "kill_switch": True,
                    "reason_code": "USER_DISABLED_PROACTIVE",
                },
            )
        )

        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "proactive_kill_switch" not in data
        assert data["plugins"]["brainstack"]["proactive_kill_switch"] is True
        assert data["plugins"]["brainstack"]["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_preserves_kernel_memory_config_location(tmp_path: Path) -> None:
    provider = _provider_with_kernel_memory_config(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {
                    "action": "set_kill_switch",
                    "explicit_user_request": True,
                    "kill_switch": True,
                    "reason_code": "USER_DISABLED_PROACTIVE",
                },
            )
        )

        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "proactive_kill_switch" not in data
        assert data["kernel_memory"]["proactive_kill_switch"] is True
        assert data["kernel_memory"]["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_control_rejects_unsupported_actions(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {"action": "send_notification", "explicit_user_request": True},
            )
        )

        assert payload["status"] == "rejected"
        assert payload["reason_code"] == "UNSUPPORTED_PROACTIVE_CONTROL_ACTION"
        assert payload["side_effect"] is False
        assert "send_notification" in payload["blocked_actions"]
    finally:
        provider.shutdown()
