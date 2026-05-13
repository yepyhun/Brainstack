from __future__ import annotations

import sys
from pathlib import Path

import yaml

from scripts import update_hermes_with_brainstack


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_update_wrapper_restores_runtime_overrides_after_pull_and_install(tmp_path, monkeypatch):
    target = tmp_path / "hermes"
    target.mkdir()
    (target / "run_agent.py").write_text("print('hermes')\n", encoding="utf-8")
    config = target / "hermes-config" / "runtime" / "config.yaml"
    _write_yaml(
        config,
        {
            "model": {"default": "user-model", "provider": "openrouter"},
            "compression": {"enabled": True, "threshold": 0.9, "target_ratio": 0.2},
            "discord": {"require_mention": True, "reactions": False},
            "proactive_mode": "live",
            "proactive_kill_switch": False,
            "memory": {"provider": "brainstack"},
        },
    )
    observed_by_doctor: list[dict] = []
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], cwd=None) -> None:
        calls.append(cmd)
        if cmd[:3] == ["git", "pull", "--ff-only"]:
            _write_yaml(
                config,
                {
                    "model": {"default": "user-model", "provider": "openrouter"},
                    "compression": {"enabled": True, "threshold": 0.5, "target_ratio": 0.2},
                    "discord": {"require_mention": True, "reactions": True},
                    "memory": {"provider": "brainstack"},
                },
            )
        elif cmd[1].endswith("install_into_hermes.py"):
            data = _load_yaml(config)
            data.pop("compression", None)
            data["discord"] = {"require_mention": True, "reactions": True}
            data["proactive_mode"] = "dry_run"
            _write_yaml(config, data)
        elif cmd[1].endswith("brainstack_doctor.py"):
            observed_by_doctor.append(_load_yaml(config))

    monkeypatch.setattr(update_hermes_with_brainstack, "_run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_hermes_with_brainstack.py",
            str(target),
            "--config",
            str(config),
            "--runtime",
            "local",
            "--pull",
            "--reinstall",
            "--doctor",
        ],
    )

    assert update_hermes_with_brainstack.main() == 0

    final = _load_yaml(config)
    assert final["compression"]["threshold"] == 0.9
    assert final["discord"]["reactions"] is False
    assert final["proactive_mode"] == "live"
    assert final["proactive_kill_switch"] is False
    assert observed_by_doctor
    assert observed_by_doctor[0]["compression"]["threshold"] == 0.9
    assert observed_by_doctor[0]["discord"]["reactions"] is False
    assert observed_by_doctor[0]["proactive_mode"] == "live"
    install_calls = [cmd for cmd in calls if cmd[1].endswith("install_into_hermes.py")]
    doctor_calls = [cmd for cmd in calls if cmd[1].endswith("brainstack_doctor.py")]
    assert install_calls
    assert "--doctor" not in install_calls[0]
    assert doctor_calls


def test_runtime_override_restore_only_restores_existing_runtime_keys(tmp_path):
    config = tmp_path / "config.yaml"
    _write_yaml(config, {"discord": {"reactions": False}, "memory": {"provider": "brainstack"}})

    snapshot = update_hermes_with_brainstack._snapshot_runtime_overrides(config)
    _write_yaml(config, {"memory": {"provider": "brainstack"}})
    result = update_hermes_with_brainstack._restore_runtime_overrides(config, snapshot)

    assert result == {"status": "restored", "restored_keys": ["discord"]}
    assert _load_yaml(config) == {"memory": {"provider": "brainstack"}, "discord": {"reactions": False}}
