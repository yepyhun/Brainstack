from __future__ import annotations

import json
from pathlib import Path

import yaml

from brainstack import BrainstackMemoryProvider
from brainstack.core.proactive import ProactiveEventKind, ProactiveIntendedNextAction


PRIVATE_TEXT = "private directive payload must not leak"


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "proactive_mode: live\n"
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


def _operator_control(provider: BrainstackMemoryProvider, args: dict[str, object]) -> dict[str, object]:
    return json.loads(
        provider.handle_tool_call(
            "brainstack_proactive_control",
            args,
            trusted_write_origin="test_operator",
        )
    )


def _create_evolver_item(provider: BrainstackMemoryProvider) -> str:
    assert provider._store is not None
    event = provider._store.upsert_proactive_event(
        source="evolver",
        kind=ProactiveEventKind.EVOLVER_CANDIDATE.value,
        principal_scope_key=provider._principal_scope_key,
        title="Evolver signal needs attention",
        summary="Evolver emitted host-runtime directive text; Hermes must decide whether to interpret it.",
        priority="normal",
        intended_next_action=ProactiveIntendedNextAction.ASK_PERMISSION.value,
        evidence_ids=["evolver:EVOLVER_DIRECTIVE_OBSERVED"],
        source_ref="evolver-health.json",
        idempotency_key="evolver:test-directive",
        metadata={
            "evolver_signal": {
                "schema": "hermes_proactive.evolver_signal.v1",
                "source": "evomap_evolver",
                "status": "actionable",
                "reason_code": "EVOLVER_DIRECTIVE_OBSERVED",
                "running": True,
                "actionable": True,
                "directive_count": 1,
                "directive_kinds": ["sessions_spawn"],
                "directive_execution": "inert_data_only",
                "safe_summary": "Evolver emitted host-runtime directive text; Hermes must decide whether to interpret it.",
                "public_metadata": {"stdout_redacted": True, "stdout_hash": "abc123"},
                "raw_output_present": True,
            },
            "wake": {
                "schema": "hermes_proactive.pulse_wake.v1",
                "decision": "ready",
                "reason_code": "READY_TO_RUN",
                "delivery_requested": True,
            },
        },
    )
    provider._store.create_proactive_outbox(
        event_id=str(event["event_id"]),
        delivery_target="proactive_runtime",
        idempotency_key="wake:test-directive",
        intended_next_action=ProactiveIntendedNextAction.ASK_PERMISSION.value,
    )
    return str(event["event_id"])


def test_agent_status_list_and_inspect_surface_evolver_wake_context(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_evolver_item(provider)

        status = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        assert status["counts"]["pending_outbox_count"] == 1
        assert status["counts"]["pending_outbox_sample"][0]["delivery_target"] == "proactive_runtime"
        assert status["counts"]["latest_item_summary"]["agent_summary"]["source"] == "evolver"
        assert status["counts"]["latest_item_summary"]["agent_summary"]["pending_or_failing_reason"] == "EVOLVER_DIRECTIVE_OBSERVED"

        listed = json.loads(provider.handle_tool_call("brainstack_proactive_list", {"limit": 10}))
        item = listed["items"][0]
        assert item["event_id"] == event_id
        assert item["source"] == "evolver"
        assert item["agent_summary"]["evolver_signal"]["reason_code"] == "EVOLVER_DIRECTIVE_OBSERVED"
        assert item["agent_summary"]["evolver_signal"]["directive_execution"] == "inert_data_only"
        assert item["agent_summary"]["pending_or_failing_reason"] == "EVOLVER_DIRECTIVE_OBSERVED"
        assert PRIVATE_TEXT not in _dump(listed)
        assert "sessions_spawn(task" not in _dump(listed)

        inspected = json.loads(provider.handle_tool_call("brainstack_proactive_inspect", {"event_id": event_id}))
        assert inspected["agent_summary"]["evolver_signal"]["directive_kinds"] == ["sessions_spawn"]
        assert inspected["outbox_summary"][0]["delivery_state"] == "pending"
        assert inspected["current_assignment_authority"] is False
        assert PRIVATE_TEXT not in _dump(inspected)
    finally:
        provider.shutdown()


def test_pause_resume_and_cooldown_controls_require_explicit_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        rejected = _operator_control(provider, {"action": "pause_proactive"})
        assert rejected["status"] == "rejected"
        assert rejected["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"
        for non_literal in [False, "false", "true", 1, 0]:
            rejected_non_literal = _operator_control(
                provider,
                {"action": "pause_proactive", "explicit_user_request": non_literal},
            )
            assert rejected_non_literal["status"] == "rejected"
            assert rejected_non_literal["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"

        model_supplied = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {"action": "pause_proactive", "explicit_user_request": True},
            )
        )
        assert model_supplied["status"] == "rejected"
        assert model_supplied["reason_code"] == "TRUSTED_OPERATOR_APPROVAL_REQUIRED"

        paused = _operator_control(
            provider,
            {"action": "pause_proactive", "explicit_user_request": True, "reason_code": "USER_PAUSED_PROACTIVE"},
        )
        assert paused["status"] == "committed"
        assert paused["action"] == "pause_proactive"
        config_path = Path(paused["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_mode"] == "disabled"
        assert data["proactive_control_last_reason"] == "USER_PAUSED_PROACTIVE"

        resumed = _operator_control(
            provider,
            {"action": "resume_proactive", "explicit_user_request": True, "reason_code": "USER_RESUMED_PROACTIVE"},
        )
        assert resumed["status"] == "committed"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_mode"] == "live"
        assert data["proactive_control_last_reason"] == "USER_RESUMED_PROACTIVE"

        cooldown = _operator_control(
            provider,
            {
                "action": "set_cooldown_seconds",
                "explicit_user_request": True,
                "cooldown_seconds": 120,
                "reason_code": "USER_TUNED_NOISE",
            },
        )
        assert cooldown["status"] == "committed"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_cooldown_seconds"] == 120
        assert data["proactive_control_last_reason"] == "USER_TUNED_NOISE"
    finally:
        provider.shutdown()


def test_model_facing_proactive_mode_tool_requires_explicit_user_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        rejected = json.loads(provider.handle_tool_call("brainstack_proactive_mode", {"mode": "live"}))
        assert rejected["status"] == "rejected"
        assert rejected["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"
        for non_literal in [False, "false", "true", 1, 0]:
            rejected_non_literal = json.loads(
                provider.handle_tool_call(
                    "brainstack_proactive_mode",
                    {"mode": "live", "explicit_user_request": non_literal},
                )
            )
            assert rejected_non_literal["status"] == "rejected"
            assert rejected_non_literal["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"
    finally:
        provider.shutdown()


def test_model_facing_proactive_mode_tool_updates_runtime_mode(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        committed = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_mode",
                {
                    "mode": "dry_run",
                    "explicit_user_request": True,
                    "reason_code": "USER_REQUESTED_SAFE_TEST_MODE",
                },
            )
        )
        assert committed["status"] == "committed"
        assert committed["action"] == "set_mode"
        assert committed["proactive_mode"] == "dry_run"
        assert committed["current_assignment_authority"] is False
        assert committed["effective_without_container_restart"] is True
        assert committed["effective_scope"] == "config_backed_status_and_next_proactive_pulse"
        config_path = Path(committed["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_mode"] == "dry_run"
        assert data["proactive_control_last_reason"] == "USER_REQUESTED_SAFE_TEST_MODE"

        live = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_mode",
                {"mode": "live", "explicit_user_request": True},
            )
        )
        assert live["status"] == "committed"
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_mode"] == "live"
    finally:
        provider.shutdown()


def test_model_facing_proactive_mode_tool_rejects_unknown_mode(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        rejected = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_mode",
                {"mode": "automatic", "explicit_user_request": True},
            )
        )
        assert rejected["status"] == "rejected"
        assert rejected["reason_code"] == "INVALID_PROACTIVE_MODE"
        assert rejected["allowed_modes"] == ["disabled", "dry_run", "live"]
    finally:
        provider.shutdown()


def test_snooze_and_mute_item_controls_are_bounded_state_changes(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_evolver_item(provider)

        snoozed = _operator_control(
            provider,
            {
                "action": "snooze_item",
                "explicit_user_request": True,
                "event_id": event_id,
                "snooze_until": "2026-05-03T00:00:00Z",
                "reason_code": "USER_SNOOZED_NOISY_SIGNAL",
            },
        )
        assert snoozed["status"] == "committed"
        assert snoozed["action"] == "snooze_item"
        assert snoozed["side_effect"] is True
        assert snoozed["current_assignment_authority"] is False
        assert snoozed["result"]["item"]["state"] == "suppressed"
        assert snoozed["result"]["item"]["metadata"]["snooze_until"] == "2026-05-03T00:00:00Z"

        muted = _operator_control(
            provider,
            {
                "action": "mute_item",
                "explicit_user_request": True,
                "event_id": event_id,
                "reason_code": "USER_MUTED_NOISY_SIGNAL",
            },
        )
        assert muted["status"] == "committed"
        assert muted["action"] == "mute_item"
        assert muted["result"]["item"]["state"] == "suppressed"
        assert muted["result"]["item"]["metadata"]["muted"] is True
        assert muted["result"]["outbox"][0]["delivery_state"] == "suppressed"
        assert provider._store is not None
        assert provider._store.list_pending_proactive_outbox(limit=10) == []
        assert "execute_task" in muted["blocked_actions"]
    finally:
        provider.shutdown()


def test_agent_controls_still_reject_execution_actions(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = _operator_control(
            provider,
            {"action": "execute_task", "explicit_user_request": True},
        )
        assert payload["status"] == "rejected"
        assert payload["reason_code"] == "UNSUPPORTED_PROACTIVE_CONTROL_ACTION"
        assert payload["side_effect"] is False
        assert "execute_task" in payload["blocked_actions"]
    finally:
        provider.shutdown()
