from __future__ import annotations

import json
from pathlib import Path

from extensions.hermes_proactive.hermes_proactive.config import load_runtime_config
from extensions.hermes_proactive.hermes_proactive.doctor import proactive_extension_doctor
from scripts.verify_hermes_proactive_runtime_parity import build_proactive_runtime_parity_report


PRIVATE_TEXT = "private doctor payload must not leak"


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _home(tmp_path: Path, *, config_text: str = "proactive_mode: live\nproactive_kill_switch: false\n") -> Path:
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir(parents=True)
    (hermes_home / "config.yaml").write_text(config_text, encoding="utf-8")
    return hermes_home


def _signal(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "evolver-health.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_proactive_doctor_reports_idle_active_paused_killed_and_malformed(tmp_path: Path) -> None:
    idle = proactive_extension_doctor(hermes_home=_home(tmp_path / "idle"))
    assert idle["status"] == "pass"
    assert idle["proactive_status"] == "idle"
    assert idle["wake"]["decision"] == "no_op"

    active = proactive_extension_doctor(
        hermes_home=_home(tmp_path / "active"),
        evolver_health_file=_signal(
            tmp_path / "active",
            {"running": True, "stdout": "sessions_spawn(task='ship')\n" + PRIVATE_TEXT},
        ),
    )
    assert active["status"] == "pass"
    assert active["proactive_status"] == "active"
    assert active["wake"]["decision"] == "ready"
    assert active["wake"]["delivery_requested"] is True
    assert active["pulse"]["task_count"] == 1
    assert PRIVATE_TEXT not in _dump(active)
    assert "sessions_spawn(task" not in _dump(active)

    paused = proactive_extension_doctor(
        hermes_home=_home(tmp_path / "paused", config_text="proactive_mode: disabled\nproactive_kill_switch: false\n"),
        evolver_health_file=_signal(tmp_path / "paused", {"running": True, "stdout": "sessions_spawn(task='ship')"}),
    )
    assert paused["status"] == "pass"
    assert paused["proactive_status"] == "paused"
    assert paused["wake"]["decision"] == "observed"
    assert paused["wake"]["delivery_requested"] is False

    dry_run = proactive_extension_doctor(
        hermes_home=_home(tmp_path / "dry_run", config_text="proactive_mode: dry_run\nproactive_kill_switch: false\n"),
        evolver_health_file=_signal(tmp_path / "dry_run", {"running": True, "stdout": "sessions_spawn(task='ship')"}),
    )
    assert dry_run["status"] == "pass"
    assert dry_run["proactive_status"] == "observed"
    assert dry_run["wake"]["decision"] == "observed"
    assert dry_run["wake"]["delivery_requested"] is False

    killed = proactive_extension_doctor(
        hermes_home=_home(tmp_path / "killed", config_text="proactive_mode: live\nproactive_kill_switch: true\n"),
        evolver_health_file=_signal(tmp_path / "killed", {"running": True, "stdout": "sessions_spawn(task='ship')"}),
    )
    assert killed["status"] == "pass"
    assert killed["proactive_status"] == "killed"
    assert killed["wake"]["decision"] == "disabled"
    assert killed["wake"]["delivery_requested"] is False

    malformed = proactive_extension_doctor(
        hermes_home=_home(tmp_path / "malformed"),
        evolver_health_file=_signal(tmp_path / "malformed", "{not-json"),
    )
    assert malformed["status"] == "degraded"
    assert malformed["proactive_status"] == "degraded"
    assert "EVOLVER_SIGNAL_MALFORMED" in malformed["issues"]
    assert malformed["wake"]["delivery_requested"] is True


def test_proactive_config_fallback_preserves_explicit_top_level_mode_without_yaml(tmp_path: Path, monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def import_without_yaml(name: str, *args: object, **kwargs: object) -> object:
        if name == "yaml":
            raise ImportError("blocked yaml for standalone runtime")
        return real_import(name, *args, **kwargs)

    hermes_home = _home(tmp_path, config_text="proactive_mode: live\nproactive_kill_switch: false\n")
    monkeypatch.setattr(builtins, "__import__", import_without_yaml)

    runtime_config = load_runtime_config(hermes_home)
    doctor = proactive_extension_doctor(hermes_home=hermes_home)

    assert runtime_config["status"] == "fallback_loaded"
    assert runtime_config["reason_code"] == "CONFIG_LINE_FALLBACK_LOADED"
    assert runtime_config["mode"] == "live"
    assert runtime_config["kill_switch"] is False
    assert doctor["status"] == "pass"
    assert doctor["config"]["mode"] == "live"


def test_proactive_runtime_parity_report_is_public_safe_and_checks_payload() -> None:
    report = build_proactive_runtime_parity_report()

    assert report["schema"] == "brainstack.hermes_proactive_runtime_parity.v1"
    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["public_safe"] is True
    assert report["payload_files"]["status"] == "present"
    assert report["scenario_statuses"] == {
        "idle": "idle",
        "active": "active",
        "paused": "paused",
        "dry_run": "observed",
        "killed": "killed",
        "malformed": "degraded",
    }
    assert PRIVATE_TEXT not in _dump(report)
    assert "sessions_spawn(task" not in _dump(report)
