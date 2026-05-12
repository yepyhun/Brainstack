#!/usr/bin/env python3
"""Verify live-safe Kanban workstation usefulness without creating real user work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_kanban_capability_evidence_ladder import _kanban, _provider, _seed_kanban_files  # noqa: E402
from scripts.verify_wizard_capability_enablement_matrix import build_report as build_wizard_report  # noqa: E402


REPORT_SCHEMA = "brainstack.live_safe_kanban_gauntlet.v1"


def _seed_task_db(path: Path, *, outcome: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE tasks ("
            "id TEXT PRIMARY KEY, status TEXT, assignee TEXT, title TEXT, current_run_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE task_runs ("
            "id TEXT PRIMARY KEY, task_id TEXT, status TEXT, outcome TEXT, summary TEXT)"
        )
        conn.execute(
            "CREATE TABLE task_events ("
            "id TEXT PRIMARY KEY, task_id TEXT, run_id TEXT, kind TEXT, created_at INTEGER)"
        )
        status = "done" if outcome == "completed" else "blocked"
        terminal = "completed" if outcome == "completed" else "blocked"
        conn.execute(
            "INSERT INTO tasks (id, status, assignee, title, current_run_id) VALUES (?, ?, ?, ?, ?)",
            ("t-smoke", status, "default", "Brainstack disposable Kanban smoke", "r-smoke"),
        )
        conn.execute(
            "INSERT INTO task_runs (id, task_id, status, outcome, summary) VALUES (?, ?, ?, ?, ?)",
            ("r-smoke", "t-smoke", status, outcome, f"disposable smoke {outcome}"),
        )
        conn.executemany(
            "INSERT INTO task_events (id, task_id, run_id, kind, created_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("e-created", "t-smoke", "r-smoke", "created", 1),
                ("e-claimed", "t-smoke", "r-smoke", "claimed", 2),
                ("e-spawned", "t-smoke", "r-smoke", "spawned", 3),
                ("e-terminal", "t-smoke", "r-smoke", terminal, 4),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _status_for(root: Path, *, outcome: str, worker_certified: bool) -> dict[str, Any]:
    hermes_root = root / f"hermes-{outcome}"
    _seed_kanban_files(hermes_root)
    db_path = root / f"kanban-{outcome}.db"
    _seed_task_db(db_path, outcome=outcome)
    provider = _provider(root / f"provider-{outcome}", hermes_root=hermes_root)
    provider._config["kanban_db_path"] = str(db_path)
    provider._config["kanban_tool_surface_exposed"] = True
    provider._config["kanban_board_write_certified"] = True
    provider._config["kanban_worker_lifecycle_certified"] = worker_certified
    provider._config["kanban_profile_count"] = 1
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-live-safe-kanban-") as raw:
        root = Path(raw)
        completed = _status_for(root, outcome="completed", worker_certified=True)
        blocked = _status_for(root, outcome="blocked", worker_certified=False)
    wizard = build_wizard_report()
    completed_snapshot = completed.get("runtime_snapshot") if isinstance(completed.get("runtime_snapshot"), dict) else {}
    blocked_snapshot = blocked.get("runtime_snapshot") if isinstance(blocked.get("runtime_snapshot"), dict) else {}
    completed_e2e = completed_snapshot.get("last_e2e_proof") if isinstance(completed_snapshot.get("last_e2e_proof"), dict) else {}
    blocked_e2e = blocked_snapshot.get("last_e2e_proof") if isinstance(blocked_snapshot.get("last_e2e_proof"), dict) else {}
    wizard_proof = wizard.get("proof") if isinstance(wizard.get("proof"), dict) else {}
    proof = {
        "wizard_default_exposes_kanban_workstation": wizard_proof.get("default_install_adds_kanban_toolset") is True,
        "wizard_preserves_existing_toolsets": wizard_proof.get("existing_toolsets_preserved") is True,
        "wizard_default_does_not_certify_workers": wizard_proof.get("default_kanban_pending_proof_does_not_certify_workers") is True,
        "disposable_completed_task_reaches_final_state": completed_e2e.get("status") == "complete"
        and completed_e2e.get("completed") is True
        and completed_e2e.get("output_persisted") is True,
        "disposable_completed_task_certifies_worker_lifecycle": completed.get("worker_lifecycle_certified") is True
        and completed.get("kanban_verdict") == "worker_lifecycle_certified",
        "controlled_block_is_not_false_success": "blocked" in blocked_snapshot.get("recent_failure_event_kinds", [])
        and blocked_e2e.get("status") == "partial"
        and blocked.get("worker_lifecycle_certified") is False,
        "blocked_case_does_not_claim_can_write_workers": blocked.get("kanban_verdict") == "board_write_certified"
        and blocked.get("claim_guard", {}).get("claim_allowed") is True
        and "workers are running" in blocked.get("claim_guard", {}).get("forbidden_phrases", []),
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "issues": issues,
        "proof": proof,
        "completed_verdict": completed.get("kanban_verdict"),
        "blocked_verdict": blocked.get("kanban_verdict"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify live-safe Kanban workstation usefulness.")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
