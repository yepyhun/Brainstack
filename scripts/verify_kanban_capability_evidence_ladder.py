#!/usr/bin/env python3
"""Verify Brainstack reports Hermes Kanban capability at the proven evidence level."""

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

from brainstack import BrainstackMemoryProvider  # noqa: E402
from brainstack.core.proactive import ProactiveEventKind, ProactiveIntendedNextAction  # noqa: E402


REPORT_SCHEMA = "brainstack.kanban_capability_evidence_ladder.v1"


def _provider(root: Path, *, hermes_root: Path | None = None) -> BrainstackMemoryProvider:
    hermes_home = root / "hermes_home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    (hermes_home / "config.yaml").write_text(
        "proactive_mode: live\n"
        "proactive_cooldown_seconds: 21600\n"
        "proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    config: dict[str, Any] = {
        "db_path": str(root / "brainstack.sqlite3"),
        "graph_backend": "sqlite",
        "corpus_backend": "sqlite",
        "hermes_home": str(hermes_home),
    }
    if hermes_root is not None:
        config["hermes_root"] = str(hermes_root)
    provider = BrainstackMemoryProvider(config)
    provider.initialize(
        "kanban-ladder",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    return provider


def _seed_kanban_files(root: Path) -> None:
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "hermes_cli").mkdir(parents=True, exist_ok=True)
    (root / "plugins" / "kanban").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")


def _seed_board_db(path: Path, *, task_count: int = 0, run_count: int = 0, event_count: int = 0) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_runs (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_events (id TEXT PRIMARY KEY)")
        for index in range(task_count):
            conn.execute("INSERT INTO tasks (id) VALUES (?)", (f"task-{index}",))
        for index in range(run_count):
            conn.execute("INSERT INTO task_runs (id) VALUES (?)", (f"run-{index}",))
        for index in range(event_count):
            conn.execute("INSERT INTO task_events (id) VALUES (?)", (f"event-{index}",))
        conn.commit()
    finally:
        conn.close()


def _status(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    return json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))


def _kanban(provider: BrainstackMemoryProvider) -> dict[str, Any]:
    status = _status(provider)
    return status["workstation_integrations"]["kanban"]


def _scenario_not_installed(root: Path) -> dict[str, Any]:
    provider = _provider(root / "not-installed")
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_installed_only(root: Path) -> dict[str, Any]:
    hermes_root = root / "hermes-installed"
    _seed_kanban_files(hermes_root)
    provider = _provider(root / "installed-only", hermes_root=hermes_root)
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_board_storage(root: Path) -> dict[str, Any]:
    hermes_root = root / "hermes-board"
    _seed_kanban_files(hermes_root)
    db_path = root / "kanban.db"
    _seed_board_db(db_path, task_count=1)
    provider = _provider(root / "board-storage", hermes_root=hermes_root)
    provider._config["kanban_db_path"] = str(db_path)
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_local_artifact(root: Path) -> dict[str, Any]:
    artifact = root / "local_kanban_board.json"
    artifact.write_text('{"schema":"local-only"}\n', encoding="utf-8")
    provider = _provider(root / "local-artifact")
    provider._config["local_kanban_artifact_path"] = str(artifact)
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_tool_surface(root: Path) -> dict[str, Any]:
    hermes_root = root / "hermes-tools"
    _seed_kanban_files(hermes_root)
    provider = _provider(root / "tool-surface", hermes_root=hermes_root)
    provider._config["kanban_tool_surface_exposed"] = True
    provider._config["kanban_profile_count"] = 1
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_worker_certified(root: Path) -> dict[str, Any]:
    hermes_root = root / "hermes-worker"
    _seed_kanban_files(hermes_root)
    provider = _provider(root / "worker-certified", hermes_root=hermes_root)
    provider._config["kanban_tool_surface_exposed"] = True
    provider._config["kanban_board_write_certified"] = True
    provider._config["kanban_worker_lifecycle_certified"] = True
    provider._config["kanban_profile_count"] = 3
    try:
        return _kanban(provider)
    finally:
        provider.shutdown()


def _scenario_runtime_outbox_split(root: Path) -> dict[str, Any]:
    provider = _provider(root / "outbox-split")
    assert provider._store is not None
    try:
        event = provider._store.upsert_proactive_event(
            source="phase298",
            kind=ProactiveEventKind.FOLLOW_UP.value,
            principal_scope_key="runtime:brainstack",
            title="Runtime scoped wake",
            summary="Public fixture runtime wake.",
            intended_next_action=ProactiveIntendedNextAction.REQUEST_INPUT.value,
            idempotency_key="phase298:runtime",
        )
        provider._store.create_proactive_outbox(
            event_id=str(event["event_id"]),
            delivery_target="runtime",
            idempotency_key="phase298:runtime:outbox",
            intended_next_action=ProactiveIntendedNextAction.REQUEST_INPUT.value,
        )
        return _status(provider)["counts"]
    finally:
        provider.shutdown()


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-kanban-ladder-") as tmpdir:
        root = Path(tmpdir)
        scenarios = {
            "not_installed": _scenario_not_installed(root),
            "installed_only": _scenario_installed_only(root),
            "board_storage_accessible": _scenario_board_storage(root),
            "local_artifact_only": _scenario_local_artifact(root),
            "tool_surface_exposed": _scenario_tool_surface(root),
            "worker_lifecycle_certified": _scenario_worker_certified(root),
        }
        outbox_split = _scenario_runtime_outbox_split(root)

    proof = {
        "not_installed_level": scenarios["not_installed"].get("kanban_verdict") == "not_installed",
        "installed_only_blocks_write_claim": scenarios["installed_only"].get("kanban_verdict") == "installed_only"
        and scenarios["installed_only"].get("can_write_board") is False
        and "I used Kanban" in scenarios["installed_only"].get("claim_guard", {}).get("forbidden_phrases", []),
        "board_storage_does_not_certify_workers": scenarios["board_storage_accessible"].get("kanban_verdict")
        == "board_storage_accessible"
        and scenarios["board_storage_accessible"].get("real_board_written") is True
        and scenarios["board_storage_accessible"].get("worker_lifecycle_certified") is False,
        "local_artifact_not_real_kanban": scenarios["local_artifact_only"].get("local_kanban_artifact_present") is True
        and scenarios["local_artifact_only"].get("real_board_written") is False
        and scenarios["local_artifact_only"].get("kanban_ready_graph_only") is True,
        "tool_surface_without_write_cert_blocks_card_claim": scenarios["tool_surface_exposed"].get("kanban_verdict")
        == "tool_surface_exposed"
        and scenarios["tool_surface_exposed"].get("can_write_board") is False
        and "Kanban can create cards" in scenarios["tool_surface_exposed"].get("claim_guard", {}).get("forbidden_phrases", []),
        "worker_lifecycle_requires_explicit_certification": scenarios["worker_lifecycle_certified"].get("kanban_verdict")
        == "worker_lifecycle_certified"
        and scenarios["worker_lifecycle_certified"].get("can_write_board") is True
        and scenarios["worker_lifecycle_certified"].get("worker_lifecycle_certified") is True,
        "single_profile_blocks_multi_worker_claim": "multi-agent board"
        in scenarios["tool_surface_exposed"].get("claim_guard", {}).get("forbidden_phrases", []),
        "runtime_outbox_split_from_user_queue": outbox_split.get("pending_outbox_count") == 1
        and outbox_split.get("runtime_scope_pending_outbox_count") == 1
        and outbox_split.get("user_visible_pending_outbox_count") == 0,
    }
    issues = sorted(key for key, value in proof.items() if value is not True)
    return {
        "schema": REPORT_SCHEMA,
        "status": "pass" if not issues else "fail",
        "public_safe": True,
        "read_only": True,
        "issues": issues,
        "proof": proof,
        "scenario_verdicts": {
            key: value.get("kanban_verdict")
            for key, value in scenarios.items()
            if isinstance(value, dict)
        },
        "outbox_split": {
            "pending_outbox_count": outbox_split.get("pending_outbox_count"),
            "runtime_scope_pending_outbox_count": outbox_split.get("runtime_scope_pending_outbox_count"),
            "user_visible_pending_outbox_count": outbox_split.get("user_visible_pending_outbox_count"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Kanban capability evidence ladder.")
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
