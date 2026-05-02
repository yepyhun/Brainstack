from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstack.db import BrainstackStore


ROOT = Path(__file__).resolve().parents[1]
PULSE_SCRIPT = ROOT / "extensions" / "hermes_proactive" / "scripts" / "hermes_proactive_pulse.py"
PRIVATE_TEXT = "private cli payload must not leak"


def _home(tmp_path: Path, *, mode: str) -> Path:
    hermes_home = tmp_path / f"hermes-{mode}"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        f"proactive_mode: {mode}\nproactive_kill_switch: false\n",
        encoding="utf-8",
    )
    return hermes_home


def _signal(tmp_path: Path) -> Path:
    path = tmp_path / "evolver-health.json"
    path.write_text(
        json.dumps({"running": True, "stdout": "sessions_spawn(task='ship')\n" + PRIVATE_TEXT}),
        encoding="utf-8",
    )
    return path


def _run_pulse(*, tmp_path: Path, mode: str) -> dict[str, object]:
    db_path = tmp_path / f"{mode}.sqlite3"
    proc = subprocess.run(
        [
            sys.executable,
            str(PULSE_SCRIPT),
            "trigger",
            "--hermes-home",
            str(_home(tmp_path, mode=mode)),
            "--db",
            str(db_path),
            "--principal-scope-key",
            "principal",
            "--workspace-scope-key",
            "workspace",
            "--evolver-health-file",
            str(_signal(tmp_path)),
            "--create-outbox",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    store = BrainstackStore(str(db_path))
    store.open()
    try:
        payload["pending_outbox"] = store.list_pending_proactive_outbox(limit=10)
    finally:
        store.close()
    return payload


def test_pulse_cli_dry_run_does_not_create_outbox_even_with_create_outbox_flag(tmp_path: Path) -> None:
    payload = _run_pulse(tmp_path=tmp_path, mode="dry_run")

    projection = payload["projection"]
    assert projection["written_count"] == 1
    assert projection["outbox_count"] == 0
    assert projection["wake"]["decision"] == "observed"
    assert projection["wake"]["delivery_requested"] is False
    assert payload["pending_outbox"] == []
    assert PRIVATE_TEXT not in json.dumps(payload, ensure_ascii=True, sort_keys=True)


def test_pulse_cli_live_creates_outbox_with_create_outbox_flag(tmp_path: Path) -> None:
    payload = _run_pulse(tmp_path=tmp_path, mode="live")

    projection = payload["projection"]
    assert projection["written_count"] == 1
    assert projection["outbox_count"] == 1
    assert projection["wake"]["decision"] == "ready"
    assert projection["wake"]["delivery_requested"] is True
    assert len(payload["pending_outbox"]) == 1
