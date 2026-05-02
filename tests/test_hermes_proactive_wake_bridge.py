from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from brainstack.db import BrainstackStore
from extensions.hermes_proactive.hermes_proactive.heartbeat_wake import HeartbeatWakeState
from extensions.hermes_proactive.hermes_proactive.pulse_producer import (
    classify_pulse_wake,
    produce_pulse,
    project_pulse_output,
)


PRIVATE_TEXT = "private directive payload must not leak"


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _actionable_pulse(tmp_path: Path) -> dict[str, object]:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text(
        json.dumps({"running": True, "stdout": "sessions_spawn(task='ship')\n" + PRIVATE_TEXT}),
        encoding="utf-8",
    )
    return produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        evolver_health_file=signal_path,
    )


def test_pulse_wake_distinguishes_noop_from_delivery_request(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        stale_inbox_threshold=999,
    )

    wake = classify_pulse_wake(pulse, create_outbox=True)

    assert wake["schema"] == "hermes_proactive.pulse_wake.v1"
    assert wake["decision"] == "no_op"
    assert wake["reason_code"] == "NO_ACTIONABLE_ITEM"
    assert wake["delivery_requested"] is False
    assert wake["provider_calls"] == 0
    assert wake["transcript_writes"] == 0


def test_pulse_wake_reports_dry_run_as_not_requested(tmp_path: Path) -> None:
    pulse = _actionable_pulse(tmp_path)

    wake = classify_pulse_wake(pulse, create_outbox=False)

    assert wake["decision"] == "observed"
    assert wake["reason_code"] == "WAKE_NOT_REQUESTED"
    assert wake["delivery_requested"] is False
    assert wake["task_count"] == 1


def test_pulse_wake_reports_ready_busy_duplicate_disabled_and_stale(tmp_path: Path) -> None:
    pulse = _actionable_pulse(tmp_path)

    ready = classify_pulse_wake(pulse, create_outbox=True)
    assert ready["decision"] == "ready"
    assert ready["reason_code"] == "READY_TO_RUN"
    assert ready["delivery_requested"] is True

    busy = classify_pulse_wake(pulse, create_outbox=True, wake_state=HeartbeatWakeState(main_lane_busy=True))
    assert busy["decision"] == "retry_later"
    assert busy["reason_code"] == "MAIN_LANE_BUSY"
    assert busy["delivery_requested"] is False
    assert busy["retry_after_seconds"] == 30

    duplicate = classify_pulse_wake(
        pulse,
        create_outbox=True,
        wake_state=HeartbeatWakeState(running_idempotency_key=str(ready["idempotency_key"])),
    )
    assert duplicate["decision"] == "coalesced"
    assert duplicate["reason_code"] == "DUPLICATE_IN_FLIGHT"
    assert duplicate["delivery_requested"] is False

    disabled = classify_pulse_wake(pulse, create_outbox=True, wake_state=HeartbeatWakeState(enabled=False))
    assert disabled["decision"] == "disabled"
    assert disabled["reason_code"] == "HEARTBEAT_DISABLED"
    assert disabled["delivery_requested"] is False

    stale = classify_pulse_wake(
        pulse,
        create_outbox=True,
        wake_state=HeartbeatWakeState(
            running_idempotency_key="older-key",
            running_since=datetime.now(UTC) - timedelta(seconds=3600),
            stale_after_seconds=10,
        ),
    )
    assert stale["decision"] == "stale_cancelled"
    assert stale["reason_code"] == "STALE_RUNNING_LOCK"
    assert stale["delivery_requested"] is True
    assert stale["stale_lock_cancelled"] is True


def test_projection_creates_outbox_only_when_wake_ready(tmp_path: Path) -> None:
    pulse = _actionable_pulse(tmp_path)
    db_path = tmp_path / "brainstack.sqlite3"

    projection = project_pulse_output(db_path=db_path, output=pulse, create_outbox=True)

    assert projection["written_count"] == 1
    assert projection["outbox_count"] == 1
    assert projection["wake"]["decision"] == "ready"
    assert projection["wake"]["delivery_requested"] is True
    assert projection["outbox"][0]["state"] == "pending"
    assert PRIVATE_TEXT not in _dump(projection)
    assert "sessions_spawn(task" not in _dump(projection)

    store = BrainstackStore(str(db_path))
    store.open()
    try:
        pending = store.list_pending_proactive_outbox(limit=10)
        assert len(pending) == 1
        assert pending[0]["delivery_target"] == "proactive_runtime"
        inspected = store.inspect_proactive_item(event_id=projection["written"][0]["event_id"])
        assert inspected["item"]["metadata"]["evolver_signal"]["directive_execution"] == "inert_data_only"
        assert PRIVATE_TEXT not in _dump(inspected)
        assert "sessions_spawn(task" not in _dump(inspected)
    finally:
        store.close()


def test_projection_blocks_outbox_when_wake_not_requested_or_busy(tmp_path: Path) -> None:
    pulse = _actionable_pulse(tmp_path)

    dry_run_projection = project_pulse_output(
        db_path=tmp_path / "dry.sqlite3",
        output=pulse,
        create_outbox=False,
    )
    assert dry_run_projection["written_count"] == 1
    assert dry_run_projection["outbox_count"] == 0
    assert dry_run_projection["wake"]["decision"] == "observed"
    assert dry_run_projection["wake"]["delivery_requested"] is False

    busy_projection = project_pulse_output(
        db_path=tmp_path / "busy.sqlite3",
        output=pulse,
        create_outbox=True,
        wake_state=HeartbeatWakeState(main_lane_busy=True),
    )
    assert busy_projection["written_count"] == 1
    assert busy_projection["outbox_count"] == 0
    assert busy_projection["wake"]["decision"] == "retry_later"
    assert busy_projection["wake"]["reason_code"] == "MAIN_LANE_BUSY"


def test_projection_preserves_malformed_signal_visibility_without_execution(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text("{not-json", encoding="utf-8")
    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        evolver_health_file=signal_path,
    )

    projection = project_pulse_output(db_path=tmp_path / "malformed.sqlite3", output=pulse, create_outbox=True)

    assert projection["written_count"] == 1
    assert projection["outbox_count"] == 1
    assert projection["wake"]["delivery_requested"] is True
    item = projection["written"][0]
    assert item["metadata"]["evolver_signal"]["reason_code"] == "EVOLVER_SIGNAL_MALFORMED"
    assert item["metadata"]["provider_calls"] == 0
    assert item["metadata"]["prompt_tokens"] == 0
    assert item["metadata"]["completion_tokens"] == 0
