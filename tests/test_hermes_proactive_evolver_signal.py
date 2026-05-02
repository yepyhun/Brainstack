from __future__ import annotations

import json
from pathlib import Path

from extensions.hermes_proactive.hermes_proactive.evolver_signal import (
    classify_evolver_signal,
    load_evolver_signal_file,
)
from extensions.hermes_proactive.hermes_proactive.pulse_producer import produce_pulse


PRIVATE_TEXT = "private source text should never leak"


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def test_evolver_signal_classifies_running_health_public_safely() -> None:
    decision = classify_evolver_signal(
        {
            "running": True,
            "version": "1.2.3",
            "secret_token": "super-secret",
            "content": PRIVATE_TEXT,
        },
        source_ref="health.json",
    ).to_public_dict()

    assert decision["status"] == "healthy"
    assert decision["reason_code"] == "EVOLVER_HEALTHY"
    assert decision["running"] is True
    assert decision["actionable"] is False
    assert decision["directive_execution"] == "inert_data_only"
    assert decision["public_metadata"]["secret_token_redacted"] is True
    assert decision["public_metadata"]["content_redacted"] is True
    assert PRIVATE_TEXT not in _dump(decision)
    assert "super-secret" not in _dump(decision)


def test_evolver_signal_classifies_stopped_health_as_actionable() -> None:
    decision = classify_evolver_signal({"running": False, "last_error": "process exited"}).to_public_dict()

    assert decision["status"] == "stopped"
    assert decision["reason_code"] == "EVOLVER_NOT_RUNNING"
    assert decision["running"] is False
    assert decision["actionable"] is True
    assert "process exited" not in _dump(decision)


def test_evolver_signal_keeps_stdout_directive_inert_and_redacted() -> None:
    decision = classify_evolver_signal(
        {
            "running": True,
            "stdout": "sessions_spawn(task='fix issue', secret='do-not-leak')\n" + PRIVATE_TEXT,
        }
    ).to_public_dict()

    assert decision["status"] == "actionable"
    assert decision["reason_code"] == "EVOLVER_DIRECTIVE_OBSERVED"
    assert decision["directive_count"] == 1
    assert decision["directive_kinds"] == ["sessions_spawn"]
    assert decision["directive_execution"] == "inert_data_only"
    assert decision["public_metadata"]["stdout_redacted"] is True
    assert "sessions_spawn(task" not in _dump(decision)
    assert PRIVATE_TEXT not in _dump(decision)
    assert "do-not-leak" not in _dump(decision)


def test_evolver_signal_file_malformed_is_visible(tmp_path: Path) -> None:
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text("{not-json", encoding="utf-8")

    decision = load_evolver_signal_file(signal_path).to_public_dict()

    assert decision["status"] == "malformed"
    assert decision["reason_code"] == "EVOLVER_SIGNAL_MALFORMED"
    assert decision["actionable"] is True
    assert decision["malformed"] is True
    assert decision["source_ref"] == str(signal_path)


def test_evolver_signal_redacts_stdout_aliases_and_unknown_text_keys() -> None:
    for key in ["output", "message", "log", "payload", "raw"]:
        decision = classify_evolver_signal(
            {"running": True, key: "sessions_spawn(task='ship', secret='do-not-leak')\n" + PRIVATE_TEXT}
        ).to_public_dict()

        assert decision["status"] == "actionable"
        assert decision["public_metadata"][f"{key}_redacted"] is True
        assert "sessions_spawn(task" not in _dump(decision)
        assert "do-not-leak" not in _dump(decision)
        assert PRIVATE_TEXT not in _dump(decision)


def test_evolver_signal_file_too_large_is_visible_without_full_parse(tmp_path: Path) -> None:
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text("{" + " " * (256 * 1024 + 1) + "}", encoding="utf-8")

    decision = load_evolver_signal_file(signal_path).to_public_dict()

    assert decision["status"] == "malformed"
    assert decision["reason_code"] == "EVOLVER_SIGNAL_MALFORMED"
    assert decision["public_metadata"]["malformed_reason"] == "signal_file_too_large"


def test_evolver_signal_rejects_non_regular_signal_path(tmp_path: Path) -> None:
    signal_path = tmp_path / "evolver-health-dir.json"
    signal_path.mkdir()

    decision = load_evolver_signal_file(signal_path).to_public_dict()

    assert decision["status"] == "malformed"
    assert decision["reason_code"] == "EVOLVER_SIGNAL_MALFORMED"
    assert decision["public_metadata"]["malformed_reason"] in {"signal_file_not_regular", "IsADirectoryError"}


def test_pulse_handoff_counts_are_bounded(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    inbox = hermes_home / "home" / "brainstack" / "inbox"
    inbox.mkdir(parents=True)
    for index in range(1005):
        (inbox / f"item-{index}.json").write_text("{}", encoding="utf-8")

    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
    )

    task = pulse["tasks"][0]
    assert task["source"] == "runtime_handoff"
    assert task["metadata"]["handoff_summary"]["inbox_count"] == 1000
    assert task["metadata"]["handoff_summary"]["inbox_truncated"] is True


def test_pulse_uses_sanitized_evolver_stopped_signal(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text(
        json.dumps({"running": False, "secret_token": "super-secret", "content": PRIVATE_TEXT}),
        encoding="utf-8",
    )

    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        evolver_health_file=signal_path,
    )

    assert pulse["status"] == "actionable"
    assert len(pulse["tasks"]) == 1
    task = pulse["tasks"][0]
    assert task["source"] == "evolver"
    assert task["kind"] == "evolver_candidate"
    assert task["metadata"]["evolver_signal"]["reason_code"] == "EVOLVER_NOT_RUNNING"
    assert task["metadata"]["evolver_signal"]["directive_execution"] == "inert_data_only"
    assert PRIVATE_TEXT not in _dump(pulse)
    assert "super-secret" not in _dump(pulse)


def test_pulse_turns_evolver_directive_into_public_safe_candidate(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    signal_path = tmp_path / "evolver-health.json"
    signal_path.write_text(
        json.dumps({"running": True, "stdout": "sessions_spawn(task='ship')\n" + PRIVATE_TEXT}),
        encoding="utf-8",
    )

    pulse = produce_pulse(
        hermes_home=hermes_home,
        principal_scope_key="principal",
        workspace_scope_key="workspace",
        evolver_health_file=signal_path,
    )

    assert pulse["status"] == "actionable"
    task = pulse["tasks"][0]
    signal = task["metadata"]["evolver_signal"]
    assert signal["status"] == "actionable"
    assert signal["directive_kinds"] == ["sessions_spawn"]
    assert signal["directive_execution"] == "inert_data_only"
    assert task["intended_next_action"] == "ask_permission"
    assert "sessions_spawn(task" not in _dump(pulse)
    assert PRIVATE_TEXT not in _dump(pulse)


def test_pulse_malformed_evolver_file_is_not_silent_success(tmp_path: Path) -> None:
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

    assert pulse["status"] == "actionable"
    task = pulse["tasks"][0]
    assert task["metadata"]["evolver_signal"]["status"] == "malformed"
    assert task["metadata"]["evolver_signal"]["reason_code"] == "EVOLVER_SIGNAL_MALFORMED"
