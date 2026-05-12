from __future__ import annotations

import sqlite3

from brainstack.proactive_agent_contract import _kanban_board_counts
from scripts.verify_kanban_capability_evidence_ladder import build_report


def test_kanban_capability_evidence_ladder_blocks_overclaims() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["read_only"] is True
    assert report["issues"] == []
    assert report["scenario_verdicts"]["not_installed"] == "not_installed"
    assert report["scenario_verdicts"]["installed_only"] == "installed_only"
    assert report["scenario_verdicts"]["board_storage_accessible"] == "board_storage_accessible"
    assert report["scenario_verdicts"]["tool_surface_exposed"] == "tool_surface_exposed"
    assert report["scenario_verdicts"]["worker_lifecycle_certified"] == "worker_lifecycle_certified"
    assert report["scenario_verdicts"]["dispatcher_snapshot"] == "worker_lifecycle_certified"
    assert all(report["proof"].values())
    assert report["outbox_split"]["pending_outbox_count"] == 1
    assert report["outbox_split"]["runtime_scope_pending_outbox_count"] == 1
    assert report["outbox_split"]["user_visible_pending_outbox_count"] == 0
    snapshot = report["scenario_snapshots"]["dispatcher_snapshot"]["runtime_snapshot"]
    assert snapshot["blocked_unknown_assignee_count"] == 1
    assert snapshot["blocked_unknown_assignees"] == {"missing-worker": 1}
    assert "blocked_unknown_assignee" in {item["reason_code"] for item in snapshot["wait_reasons"]}


def test_kanban_board_counts_reads_default_hermes_home_db(tmp_path) -> None:
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    db_path = hermes_home / "kanban.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_runs (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_events (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO tasks (id) VALUES ('task-1')")
        conn.commit()
    finally:
        conn.close()

    counts = _kanban_board_counts({}, tmp_path / "hermes-root", hermes_home)

    assert counts["accessible"] is True
    assert counts["path"] == str(db_path)
    assert counts["task_count"] == 1
