from __future__ import annotations

import sqlite3

from brainstack.proactive_agent_contract import _kanban_board_counts, _kanban_runtime_snapshot
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


def test_kanban_runtime_snapshot_finds_active_tasks_beyond_old_done_sample(tmp_path) -> None:
    db_path = tmp_path / "kanban.db"
    hermes_home = tmp_path / "hermes-home"
    (hermes_home / "profiles" / "builder").mkdir(parents=True)
    (hermes_home / "profiles" / "reviewer").mkdir(parents=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE tasks ("
            "id TEXT PRIMARY KEY, "
            "status TEXT, "
            "assignee TEXT, "
            "title TEXT, "
            "created_at INTEGER, "
            "started_at INTEGER, "
            "completed_at INTEGER, "
            "current_run_id TEXT"
            ")"
        )
        conn.execute(
            "CREATE TABLE task_runs ("
            "id TEXT PRIMARY KEY, "
            "task_id TEXT, "
            "status TEXT, "
            "outcome TEXT, "
            "summary TEXT, "
            "output_path TEXT, "
            "completed_at INTEGER"
            ")"
        )
        conn.execute(
            "CREATE TABLE task_events ("
            "id TEXT PRIMARY KEY, "
            "task_id TEXT, "
            "run_id TEXT, "
            "kind TEXT, "
            "created_at INTEGER"
            ")"
        )
        for index in range(60):
            conn.execute(
                "INSERT INTO tasks (id, status, assignee, title, created_at, completed_at, current_run_id) "
                "VALUES (?, 'done', 'builder', ?, ?, ?, ?)",
                (f"old-done-{index}", "old done", index, index + 1, f"old-run-{index}"),
            )
        conn.executemany(
            "INSERT INTO tasks (id, status, assignee, title, created_at, started_at, current_run_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("active-running", "running", "builder", "active running", 10_000, 10_010, "run-active"),
                ("active-ready", "ready", "builder", "active ready", 10_020, None, None),
                ("active-todo", "todo", "reviewer", "active todo", 10_030, None, None),
                ("blocked-debt", "blocked", "missing-worker", "blocked debt", 10_040, None, None),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = _kanban_runtime_snapshot(
        {"kanban_profile_names": ["builder", "reviewer"], "kanban_max_spawn": 4},
        None,
        {"accessible": True, "path": str(db_path), "task_count": 64},
        hermes_home,
    )

    assert snapshot["dispatcher_state"] == "workers_running"
    assert snapshot["running_worker_count"] == 1
    assert snapshot["ready_task_count"] == 2
    assert snapshot["blocked_task_count"] == 1
    assert snapshot["status_counts"]["blocked"] == 1
    assert {task["task_id"] for task in snapshot["running_tasks"]} == {"active-running"}
    assert {item["task_id"] for item in snapshot["wait_reasons"]} == {"active-ready", "active-todo"}
