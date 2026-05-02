from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from extensions.hermes_proactive.hermes_proactive.pulse_producer import produce_pulse, project_pulse_output


PRIVATE_TEXT = "private no bypass payload must not leak"


def _table_count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if int(row[0]) == 0:
            return 0
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(count[0])


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def test_evolver_directive_projection_does_not_write_durable_memory_or_execute(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text(
        json.dumps({"running": True, "stdout": "sessions_spawn(task='ship', secret='do-not-leak')\n" + PRIVATE_TEXT}),
        encoding="utf-8",
    )
    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        evolver_health_file=signal_path,
    )
    db_path = tmp_path / "brainstack.sqlite3"

    projection = project_pulse_output(db_path=db_path, output=pulse, create_outbox=True)

    assert projection["written_count"] == 1
    assert projection["outbox_count"] == 1
    assert projection["wake"]["delivery_requested"] is True
    assert projection["wake"]["provider_calls"] == 0
    assert projection["wake"]["transcript_writes"] == 0
    assert _table_count(db_path, "proactive_events") == 1
    assert _table_count(db_path, "proactive_outbox") == 1
    assert _table_count(db_path, "canonical_memory_events") == 0
    assert _table_count(db_path, "memory_events") == 0
    assert "sessions_spawn(task" not in _dump(projection)
    assert "do-not-leak" not in _dump(projection)
    assert PRIVATE_TEXT not in _dump(projection)


def test_agent_control_surface_blocks_scheduler_executor_and_external_actions(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "proactive_mode: live\nproactive_kill_switch: false\n",
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
    try:
        for action in [
            "send_notification",
            "start_scheduler",
            "install_evolver",
            "execute_task",
            "create_current_assignment",
        ]:
            model_supplied = json.loads(
                provider.handle_tool_call(
                    "brainstack_proactive_control",
                    {"action": action, "explicit_user_request": True},
                )
            )
            assert model_supplied["status"] == "rejected"
            assert model_supplied["reason_code"] == "TRUSTED_OPERATOR_APPROVAL_REQUIRED"
            payload = json.loads(
                provider.handle_tool_call(
                    "brainstack_proactive_control",
                    {"action": action, "explicit_user_request": True},
                    trusted_write_origin="test_operator",
                )
            )
            assert payload["status"] == "rejected"
            assert payload["reason_code"] == "UNSUPPORTED_PROACTIVE_CONTROL_ACTION"
            assert payload["side_effect"] is False
            assert action in payload["blocked_actions"]
    finally:
        provider.shutdown()
