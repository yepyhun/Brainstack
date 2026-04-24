from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor, build_query_inspect
from brainstack.operating_truth import OPERATING_OWNER
from brainstack.runtime_handoff_io import summarize_runtime_handoff_dirs
from scripts import brainstack_doctor


PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_doctor_reports_backend_error_class_for_unopenable_graph_backend(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store._graph_backend_name = "kuzu"
        store._graph_backend = None
        store._graph_backend_error = "std::bad_alloc"

        report = build_memory_kernel_doctor(
            store,
            strict=True,
            tier2_state={"enabled": False, "running": False},
        )

        graph = report["capabilities"]["graph"]
        assert report["verdict"] == "fail"
        assert graph["status"] == "degraded"
        assert graph["sqlite_fallback_active"] is True
        assert graph["error_class"] == "backend_open_memory_error"
    finally:
        store.close()


def test_installer_doctor_fails_when_configured_kuzu_path_exists_but_cannot_open(monkeypatch, tmp_path: Path) -> None:
    def fake_probe(*args, **kwargs):
        return {
            "path": str(tmp_path / "brainstack.kuzu"),
            "exists": True,
            "openable": False,
            "error": "std::bad_alloc",
            "error_class": "backend_open_memory_error",
        }

    monkeypatch.setattr(brainstack_doctor, "_run_python_probe", fake_probe)

    checks = brainstack_doctor._backend_openability_checks(
        backend="kuzu",
        configured_path=str(tmp_path / "brainstack.kuzu"),
        config_path=tmp_path / "config.yaml",
        planned_install=False,
        python_bin=None,
        runtime="local",
        compose_path=None,
    )

    assert checks == [
        brainstack_doctor.Check(
            "graph_backend_open",
            "fail",
            f"kuzu backend exists but cannot be opened at {tmp_path / 'brainstack.kuzu'}: backend_open_memory_error: std::bad_alloc",
        )
    ]


def test_runtime_handoff_summary_is_bounded_and_read_only(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    inbox = hermes_home / "home" / "brainstack" / "inbox"
    inbox.mkdir(parents=True)
    duplicate = {
        "id": "task-a",
        "type": "ALERT",
        "status": "pending",
        "payload": {"message": "187 stale task(s) in inbox"},
    }
    (inbox / "a.json").write_text(json.dumps(duplicate), encoding="utf-8")
    (inbox / "b.json").write_text(json.dumps(duplicate), encoding="utf-8")
    (inbox / "bad.json").write_text("{not-json", encoding="utf-8")

    summary = summarize_runtime_handoff_dirs(hermes_home, sample_limit=1)

    assert summary["schema"] == "brainstack.runtime_handoff_dirs.v1"
    assert summary["inbox_count"] == 3
    assert summary["invalid_json_count"] == 1
    assert summary["duplicate_identity_count"] == 1
    assert summary["inbox_duplicate_identity_count"] == 1
    assert summary["duplicate_identity_counts_by_directory"]["inbox"] == 1
    assert summary["status_counts"]["pending"] == 2
    assert summary["status_counts_by_directory"]["inbox"]["pending"] == 2
    assert summary["type_counts"]["ALERT"] == 2
    assert summary["type_counts_by_directory"]["inbox"]["ALERT"] == 2
    assert len(summary["samples"]) == 1
    assert (inbox / "a.json").exists()
    assert (inbox / "b.json").exists()


def test_runtime_handoff_snapshot_exposes_filesystem_summary_without_execution(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes-home"
    inbox = hermes_home / "home" / "brainstack" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "task.json").write_text(
        json.dumps({"id": "task-a", "type": "ALERT", "status": "pending", "payload": {"message": "Review runtime state"}}),
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "handoff-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
        hermes_home=str(hermes_home),
    )
    try:
        snapshot = provider.runtime_handoff_snapshot()
        assert snapshot is not None
        assert snapshot["runtime_handoff_filesystem"]["inbox_count"] == 1
        assert snapshot["runtime_handoff_filesystem"]["samples"][0]["title"] == "Review runtime state"
    finally:
        provider.shutdown()


def test_recent_work_operating_truth_beats_weak_stale_transcript_residue(monkeypatch, tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    cron_dir = hermes_home / "cron"
    cron_dir.mkdir(parents=True)
    (cron_dir / "jobs.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-04-24T12:00:00+00:00",
                "jobs": [
                    {
                        "id": "pulse",
                        "name": "Brainstack Proactive Pulse",
                        "state": "scheduled",
                        "enabled": True,
                        "schedule": {"display": "*/10 * * * *"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="operating_truth::recent_work",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type="recent_work_summary",
            content=(
                "Brainstack development status: Phase 79 stabilizes backend health, "
                "recent-work recall, and stale evidence suppression."
            ),
            owner=OPERATING_OWNER,
            source="test:phase79",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "semantic_terms": ["Brainstack development stabilization"],
            },
        )
        store.add_transcript_entry(
            session_id="old-session",
            turn_number=1,
            kind="turn",
            content=(
                "User: csinálj egy értesítőt, mert ezt ma kell megcsinálni.\n"
                "Assistant: Kész, az értesítő beállítva."
            ),
            source="test",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.add_continuity_event(
            session_id="old-session",
            turn_number=1,
            kind="turn",
            content="user: csinálj egy értesítőt, mert ezt ma kell megcsinálni.",
            source="test",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        report = build_query_inspect(
            store,
            query="emlékszel miket mondtak a Brainstackről hogy kell fejleszteni",
            session_id="new-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        operating = report["selected_evidence"]["operating"]
        assert operating
        assert "Brainstack development status: Phase 79" in operating[0]["excerpt"]
        selected_text = " ".join(
            item["excerpt"]
            for rows in report["selected_evidence"].values()
            for item in rows
        )
        assert "értesítőt" not in selected_text
        assert any(
            item.get("suppression_reason", "").startswith("weak_cross_session_keyword_residue")
            for item in report["suppressed_evidence"]
        )
    finally:
        store.close()
