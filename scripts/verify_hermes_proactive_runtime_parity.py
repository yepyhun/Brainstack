#!/usr/bin/env python3
"""Verify Hermes proactive runtime parity public-safely."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_CANARY = "private doctor payload must not leak"
REQUIRED_PAYLOAD_FILES = (
    "extensions/hermes_proactive/hermes_proactive/control.py",
    "extensions/hermes_proactive/hermes_proactive/doctor.py",
    "extensions/hermes_proactive/hermes_proactive/evolver_signal.py",
    "extensions/hermes_proactive/hermes_proactive/heartbeat_wake.py",
    "extensions/hermes_proactive/hermes_proactive/pulse_producer.py",
    "extensions/hermes_proactive/scripts/hermes_proactive_doctor.py",
    "extensions/hermes_proactive/scripts/hermes_proactive_pulse.py",
    "extensions/hermes_proactive/hermes_proactive/workrun.py",
)


def _write_home(base: Path, name: str, *, config: str) -> Path:
    home = base / name / "hermes_home"
    home.mkdir(parents=True)
    (home / "config.yaml").write_text(config, encoding="utf-8")
    return home


def _write_signal(base: Path, name: str, payload: object) -> Path:
    path = base / name / "evolver-health.json"
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_cli_doctor(*, hermes_home: Path, evolver_health_file: Path | None = None) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "extensions" / "hermes_proactive" / "scripts" / "hermes_proactive_doctor.py"),
        "--hermes-home",
        str(hermes_home),
    ]
    if evolver_health_file is not None:
        command.extend(["--evolver-health-file", str(evolver_health_file)])
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"status": "invalid_json", "stdout": proc.stdout[:200], "stderr": proc.stderr[:200]}
    payload["_cli_returncode"] = proc.returncode
    return payload


def _public_safe(value: Any) -> bool:
    text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    denied = (
        PRIVATE_CANARY,
        "sessions_spawn(task",
        "secret='do-not-leak'",
        "super-secret",
    )
    return not any(item in text for item in denied)


def _payload_files_report() -> dict[str, Any]:
    files = []
    missing = []
    for rel in REQUIRED_PAYLOAD_FILES:
        path = ROOT / rel
        entry = {"path": rel, "present": path.exists()}
        files.append(entry)
        if not path.exists():
            missing.append(rel)
    return {
        "status": "present" if not missing else "missing",
        "files": files,
        "missing": missing,
    }


def build_proactive_runtime_parity_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-proactive-parity-") as raw:
        base = Path(raw)
        idle_home = _write_home(base, "idle", config="proactive_mode: live\nproactive_kill_switch: false\n")
        active_home = _write_home(base, "active", config="proactive_mode: live\nproactive_kill_switch: false\n")
        active_signal = _write_signal(
            base,
            "active",
            {"running": True, "stdout": "sessions_spawn(task='ship', secret='do-not-leak')\n" + PRIVATE_CANARY},
        )
        paused_home = _write_home(base, "paused", config="proactive_mode: disabled\nproactive_kill_switch: false\n")
        paused_signal = _write_signal(base, "paused", {"running": True, "stdout": "sessions_spawn(task='ship')"})
        dry_run_home = _write_home(base, "dry_run", config="proactive_mode: dry_run\nproactive_kill_switch: false\n")
        dry_run_signal = _write_signal(base, "dry_run", {"running": True, "stdout": "sessions_spawn(task='ship')"})
        killed_home = _write_home(base, "killed", config="proactive_mode: live\nproactive_kill_switch: true\n")
        killed_signal = _write_signal(base, "killed", {"running": True, "stdout": "sessions_spawn(task='ship')"})
        malformed_home = _write_home(base, "malformed", config="proactive_mode: live\nproactive_kill_switch: false\n")
        malformed_signal = _write_signal(base, "malformed", "{not-json")
        scenarios: dict[str, Mapping[str, Any]] = {
            "idle": _run_cli_doctor(hermes_home=idle_home),
            "active": _run_cli_doctor(hermes_home=active_home, evolver_health_file=active_signal),
            "paused": _run_cli_doctor(hermes_home=paused_home, evolver_health_file=paused_signal),
            "dry_run": _run_cli_doctor(hermes_home=dry_run_home, evolver_health_file=dry_run_signal),
            "killed": _run_cli_doctor(hermes_home=killed_home, evolver_health_file=killed_signal),
            "malformed": _run_cli_doctor(hermes_home=malformed_home, evolver_health_file=malformed_signal),
        }
    payload_files = _payload_files_report()
    expected = {
        "idle": "idle",
        "active": "active",
        "paused": "paused",
        "dry_run": "observed",
        "killed": "killed",
        "malformed": "degraded",
    }
    scenario_statuses = {name: str(report.get("proactive_status") or "") for name, report in scenarios.items()}
    issues: list[str] = []
    for name, expected_status in expected.items():
        if scenario_statuses.get(name) != expected_status:
            issues.append(f"scenario_{name}_expected_{expected_status}_got_{scenario_statuses.get(name)}")
    for name, report in scenarios.items():
        if int(report.get("_cli_returncode") or 0) != 0:
            issues.append(f"scenario_{name}_cli_returncode_{report.get('_cli_returncode')}")
    if payload_files["status"] != "present":
        issues.append("payload_files_missing")
    public_safe = _public_safe(scenarios)
    if not public_safe:
        issues.append("public_safety_failed")
    zero_runtime_side_effects = all(
        int(report.get("provider_calls") or 0) == 0
        and int(report.get("prompt_tokens") or 0) == 0
        and int(report.get("completion_tokens") or 0) == 0
        and int((report.get("wake") or {}).get("transcript_writes") or 0) == 0
        for report in scenarios.values()
    )
    if not zero_runtime_side_effects:
        issues.append("runtime_side_effects_observed")
    return {
        "schema": "brainstack.hermes_proactive_runtime_parity.v1",
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "public_safe": public_safe,
        "zero_runtime_side_effects": zero_runtime_side_effects,
        "scenario_statuses": scenario_statuses,
        "scenarios": scenarios,
        "payload_files": payload_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hermes proactive runtime parity.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_proactive_runtime_parity_report()
    text = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True, default=str)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
