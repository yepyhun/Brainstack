"""Agent-facing contract for Brainstack proactive state.

This module exposes proactive memory as explicit status and control data.
It does not schedule, notify, execute, approve actions, or rewrite output.
"""

from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from .core.proactive import ProactiveEventKind, ProactiveEventState, ProactiveReasonCode
from .operating_loop import (
    build_kanban_recovery_candidates,
    build_operating_loop_verdict,
    build_scheduler_lane_health,
    recovery_summary,
)
from .workstream_controller import controller_status


PROACTIVE_AGENT_CONTRACT_SCHEMA = "brainstack.proactive_agent_surface.v1"
PROACTIVE_AGENT_CONTROL_SCHEMA = "brainstack.proactive_agent_control.v1"
ACTIONABLE_SUBSTRATE_SCHEMA = "brainstack.actionable_substrate.v1"
PROACTIVE_OPERATIONAL_VERDICT_SCHEMA = "brainstack.proactive_operational_verdict.v1"
PROACTIVE_READINESS_PROBE_SCHEMA = "brainstack.proactive_readiness_probe.v1"
PROACTIVE_CANDIDATE_INTAKE_SCHEMA = "brainstack.proactive_candidate_intake.v1"
KANBAN_WORKSTATION_SCHEMA = "brainstack.workstation_integration.kanban.v1"
KANBAN_RUNTIME_SNAPSHOT_SCHEMA = "brainstack.workstation_integration.kanban_runtime_snapshot.v1"
PROACTIVE_STATUS_DETAIL_LEVELS = ("compact", "full")

PROACTIVE_ALLOWED_READ_ACTIONS = ("status", "doctor", "list", "inspect")
PROACTIVE_ALLOWED_CONTROL_ACTIONS = (
    "set_item_state",
    "snooze_item",
    "mute_item",
    "set_mode",
    "set_kill_switch",
    "pause_proactive",
    "resume_proactive",
    "set_cooldown_seconds",
)
PROACTIVE_BLOCKED_ACTIONS = (
    "send_notification",
    "start_scheduler",
    "install_evolver",
    "execute_task",
    "create_current_assignment",
)
PROACTIVE_MODE_VALUES = ("disabled", "dry_run", "live")
PROACTIVE_OPERATIONAL_STATES = (
    "unavailable",
    "disabled",
    "killed",
    "ready_idle",
    "candidate_available",
    "wake_queued",
    "degraded",
)
PROACTIVE_ACTIVE_ITEM_STATES = {
    ProactiveEventState.OBSERVED.value,
    ProactiveEventState.QUEUED.value,
    ProactiveEventState.BLOCKED.value,
}
KANBAN_BLOCKED_BOARD_ACTIONS = (
    "write",
    "claim",
    "assign",
    "complete",
    "retry",
    "reclaim",
    "dispatch",
    "create_kanban_task",
    "claim_kanban_task",
    "assign_kanban_task",
    "complete_kanban_task",
    "retry_kanban_task",
    "reclaim_kanban_task",
    "dispatch_kanban_worker",
)
KANBAN_VERDICT_ORDER = (
    "not_installed",
    "installed_only",
    "cli_available",
    "board_storage_accessible",
    "tool_surface_exposed",
    "board_write_certified",
    "worker_lifecycle_certified",
)
KANBAN_WRITE_TOOL_NAMES = frozenset(
    {
        "kanban_create_task",
        "kanban_list_tasks",
        "kanban_claim_task",
        "kanban_assign_task",
        "kanban_complete_task",
        "kanban_retry_task",
        "kanban_reclaim_task",
        "kanban_dispatch_worker",
        "create_kanban_task",
        "claim_kanban_task",
        "assign_kanban_task",
        "complete_kanban_task",
        "retry_kanban_task",
        "reclaim_kanban_task",
        "dispatch_kanban_worker",
    }
)
KANBAN_TERMINAL_EVENT_KINDS = frozenset({"completed", "blocked", "crashed", "timed_out", "spawn_failed", "auto_blocked"})
KANBAN_FAILURE_EVENT_KINDS = frozenset({"blocked", "crashed", "timed_out", "spawn_failed", "auto_blocked"})


def proactive_capability_card() -> dict[str, Any]:
    return {
        "schema": "brainstack.proactive_capability_card.v1",
        "summary": (
            "Brainstack proactive state is an inspectable memory-kernel surface. "
            "Use proactive status/list/inspect tools for facts. Control is limited "
            "to explicit user-requested state changes."
        ),
        "allowed_read_actions": list(PROACTIVE_ALLOWED_READ_ACTIONS),
        "allowed_control_actions": list(PROACTIVE_ALLOWED_CONTROL_ACTIONS),
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _resolve_hermes_home(config: Mapping[str, Any] | None = None) -> Path | None:
    raw = ""
    if isinstance(config, Mapping):
        raw = str(config.get("hermes_home") or config.get("_hermes_home") or "").strip()
    if not raw:
        raw = os.getenv("HERMES_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    try:
        from hermes_constants import get_hermes_home  # type: ignore[import-not-found]

        return Path(get_hermes_home()).expanduser()
    except Exception:
        return None


def _resolve_hermes_root_from_package() -> Path | None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if parent.name == "brainstack" and parent.parent.name == "memory" and parent.parent.parent.name == "plugins":
            return parent.parent.parent.parent
    return None


def _resolve_hermes_root(config: Mapping[str, Any] | None = None) -> Path | None:
    raw = ""
    if isinstance(config, Mapping):
        raw = str(config.get("hermes_root") or config.get("_hermes_root") or "").strip()
    if not raw:
        raw = os.getenv("HERMES_ROOT", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _resolve_hermes_root_from_package()


def _config_path_from_home(hermes_home: Path | None) -> Path | None:
    if hermes_home is None:
        return None
    return hermes_home / "config.yaml"


def _load_yaml(path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        return {}, {"status": "unavailable", "reason_code": "HERMES_HOME_UNRESOLVED"}
    if not path.exists():
        return {}, {"status": "missing", "config_path": str(path), "reason_code": "CONFIG_FILE_MISSING"}
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "PYYAML_UNAVAILABLE"}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "CONFIG_READ_FAILED", "error": str(exc)}
    if not isinstance(data, dict):
        return {}, {"status": "unavailable", "config_path": str(path), "reason_code": "CONFIG_NOT_OBJECT"}
    return data, {"status": "loaded", "config_path": str(path), "reason_code": "CONFIG_LOADED"}


def _write_yaml(path: Path, data: Mapping[str, Any]) -> None:
    import yaml  # type: ignore[import-untyped]

    path.write_text(
        yaml.safe_dump(dict(data), default_flow_style=False, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _runtime_config_summary(config_data: Mapping[str, Any], load_status: Mapping[str, Any]) -> dict[str, Any]:
    plugins = config_data.get("plugins") if isinstance(config_data, Mapping) else {}
    plugin_cfg = {}
    brainstack_cfg = {}
    if isinstance(plugins, Mapping):
        raw = plugins.get("hermes_proactive") or plugins.get("proactive") or {}
        if isinstance(raw, Mapping):
            plugin_cfg = dict(raw)
        raw_brainstack = plugins.get("brainstack") or {}
        if isinstance(raw_brainstack, Mapping):
            brainstack_cfg = dict(raw_brainstack)
    proactive_block = config_data.get("proactive")
    proactive_cfg = dict(proactive_block) if isinstance(proactive_block, Mapping) else {}
    kernel_memory_block = config_data.get("kernel_memory")
    kernel_memory_cfg = dict(kernel_memory_block) if isinstance(kernel_memory_block, Mapping) else {}
    mode = (
        config_data.get("proactive_mode")
        or kernel_memory_cfg.get("proactive_mode")
        or brainstack_cfg.get("proactive_mode")
        or plugin_cfg.get("mode")
        or proactive_cfg.get("mode")
    )
    kill_switch = config_data.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = kernel_memory_cfg.get("proactive_kill_switch")
    if kill_switch is None:
        kill_switch = brainstack_cfg.get("proactive_kill_switch")
    cooldown = config_data.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = kernel_memory_cfg.get("proactive_cooldown_seconds")
    if cooldown is None:
        cooldown = brainstack_cfg.get("proactive_cooldown_seconds")
    return {
        "status": str(load_status.get("status") or "unknown"),
        "reason_code": str(load_status.get("reason_code") or ""),
        "config_path": str(load_status.get("config_path") or ""),
        "mode": str(mode or "unknown"),
        "kill_switch": bool(kill_switch) if kill_switch is not None else False,
        "cooldown_seconds": _safe_int(cooldown, 0),
        "kernel_memory_mode": str(kernel_memory_cfg.get("proactive_mode") or ""),
        "brainstack_plugin_mode": str(brainstack_cfg.get("proactive_mode") or ""),
        "plugin_mode": str(plugin_cfg.get("mode") or ""),
        "source": "hermes_config_yaml",
    }


def _brainstack_plugin_config(data: Mapping[str, Any]) -> dict[str, Any]:
    plugins = data.get("plugins") if isinstance(data, Mapping) else None
    if not isinstance(plugins, dict):
        return {}
    raw = plugins.get("brainstack") or {}
    return raw if isinstance(raw, dict) else {}


def _runtime_config_target(data: dict[str, Any], key: str) -> dict[str, Any]:
    if key in data or "proactive_mode" in data or "proactive_kill_switch" in data or "proactive_cooldown_seconds" in data:
        return data
    kernel_memory_cfg = data.get("kernel_memory")
    if isinstance(kernel_memory_cfg, dict) and (
        key in kernel_memory_cfg
        or "proactive_mode" in kernel_memory_cfg
        or "proactive_kill_switch" in kernel_memory_cfg
        or "proactive_cooldown_seconds" in kernel_memory_cfg
    ):
        return kernel_memory_cfg
    brainstack_cfg = _brainstack_plugin_config(data)
    if isinstance(brainstack_cfg, dict) and (
        key in brainstack_cfg
        or "proactive_mode" in brainstack_cfg
        or "proactive_kill_switch" in brainstack_cfg
        or "proactive_cooldown_seconds" in brainstack_cfg
    ):
        return brainstack_cfg
    return data


def _write_runtime_config_value(data: dict[str, Any], key: str, value: Any, reason_code: str) -> None:
    target = _runtime_config_target(data, key)
    target[key] = value
    target["proactive_control_last_reason"] = reason_code


def _write_kill_switch_to_config(data: dict[str, Any], kill_switch: bool, reason_code: str) -> None:
    _write_runtime_config_value(data, "proactive_kill_switch", bool(kill_switch), reason_code)


def _extension_status(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root = _resolve_hermes_root(config)
    if root is None:
        return {
            "installed": False,
            "status": "unknown",
            "reason_code": "HERMES_ROOT_UNRESOLVED",
            "source": "brainstack_package_path",
        }
    extension_path = root / "extensions" / "hermes_proactive"
    return {
        "installed": extension_path.exists(),
        "status": "installed" if extension_path.exists() else "missing",
        "path": str(extension_path),
        "reason_code": "EXTENSION_PATH_EXISTS" if extension_path.exists() else "EXTENSION_PATH_MISSING",
        "source": "brainstack_package_path",
    }


def _config_bool(config: Mapping[str, Any] | None, key: str) -> bool:
    if not isinstance(config, Mapping):
        return False
    value = config.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _config_list(config: Mapping[str, Any] | None, key: str) -> list[str]:
    if not isinstance(config, Mapping):
        return []
    value = config.get(key)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _sqlite_table_counts(db_path: Path) -> dict[str, int]:
    wanted = ("tasks", "task_runs", "task_events")
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        names = {str(row[0]) for row in rows}
        counts: dict[str, int] = {}
        for name in wanted:
            if name not in names:
                counts[name] = 0
                continue
            counts[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0])
        return counts
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def _kanban_db_candidates(
    config: Mapping[str, Any] | None,
    root: Path | None,
    hermes_home: Path | None = None,
) -> list[Path]:
    candidates: list[Path] = []
    if isinstance(config, Mapping) and str(config.get("kanban_db_path") or "").strip():
        candidates.append(Path(str(config["kanban_db_path"])).expanduser())
    env_path = str(os.environ.get("HERMES_KANBAN_DB") or "").strip()
    if env_path:
        candidates.append(Path(env_path).expanduser())
    if hermes_home is not None:
        candidates.extend(
            [
                hermes_home / "kanban.db",
                hermes_home / "kanban" / "kanban.db",
            ]
        )
    if root is not None:
        candidates.extend(
            [
                root / "kanban.db",
                root.parent / "kanban.db",
            ]
        )
    return candidates


def _kanban_board_counts(
    config: Mapping[str, Any] | None,
    root: Path | None,
    hermes_home: Path | None = None,
) -> dict[str, Any]:
    candidates = _kanban_db_candidates(config, root, hermes_home)
    for candidate in candidates:
        counts = _sqlite_table_counts(candidate)
        if counts:
            return {
                "accessible": True,
                "path_present": candidate.exists(),
                "path": str(candidate),
                "task_count": _safe_int(counts.get("tasks"), 0),
                "task_run_count": _safe_int(counts.get("task_runs"), 0),
                "task_event_count": _safe_int(counts.get("task_events"), 0),
            }
    return {
        "accessible": False,
        "path_present": any(candidate.exists() for candidate in candidates),
        "path": "",
        "task_count": 0,
        "task_run_count": 0,
        "task_event_count": 0,
    }


def _sqlite_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.Error:
        return set()
    return {str(row[1]) for row in rows}


def _sqlite_select_rows(conn: sqlite3.Connection, table: str, columns: set[str], wanted: tuple[str, ...], *, limit: int = 25) -> list[dict[str, Any]]:
    selected = [name for name in wanted if name in columns]
    if not selected:
        return []
    query = f"SELECT {', '.join(selected)} FROM {table} LIMIT ?"
    try:
        rows = conn.execute(query, (max(1, min(limit, 100)),)).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            key: value
            for key, value in zip(selected, row, strict=False)
        }
        for row in rows
    ]


def _kanban_profile_names(config: Mapping[str, Any] | None, hermes_home: Path | None) -> set[str]:
    profile_names = set(_config_list(config, "kanban_profile_names")) or set(_config_list(config, "kanban_profiles"))
    if hermes_home is not None and hermes_home.exists():
        profile_names.add("default")
        profiles_dir = hermes_home / "profiles"
        if profiles_dir.exists():
            try:
                profile_names.update(path.name for path in profiles_dir.iterdir() if path.is_dir())
            except OSError:
                pass
    return {name for name in profile_names if name}


def _kanban_runtime_snapshot(
    config: Mapping[str, Any] | None,
    root: Path | None,
    board: Mapping[str, Any],
    hermes_home: Path | None = None,
) -> dict[str, Any]:
    db_path = Path(str(board.get("path") or "")).expanduser() if str(board.get("path") or "").strip() else None
    profile_names = _kanban_profile_names(config, hermes_home)
    profile_count = max(_safe_int(config.get("kanban_profile_count") if isinstance(config, Mapping) else 0, 0), len(profile_names), 1)
    max_spawn = _safe_int(config.get("kanban_max_spawn") if isinstance(config, Mapping) else 0, 0)
    dispatch_interval_seconds = _safe_int(config.get("kanban_dispatch_interval_seconds") if isinstance(config, Mapping) else 60, 60)
    last_tick_at = str(config.get("kanban_last_dispatch_tick_at") or "") if isinstance(config, Mapping) else ""
    next_tick_at = str(config.get("kanban_next_dispatch_tick_at") or "") if isinstance(config, Mapping) else ""
    running_rows: list[dict[str, Any]] = []
    ready_rows: list[dict[str, Any]] = []
    terminal_events: list[str] = []
    failure_events: list[str] = []
    last_e2e_proof: dict[str, Any] = {
        "status": "unavailable",
        "reason_code": "KANBAN_BOARD_STORAGE_UNAVAILABLE",
        "created": False,
        "claimed": False,
        "spawned": False,
        "completed": False,
        "output_persisted": False,
    }
    if db_path is not None and db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            conn = None
        if conn is not None:
            try:
                task_columns = _sqlite_table_columns(conn, "tasks")
                event_columns = _sqlite_table_columns(conn, "task_events")
                run_columns = _sqlite_table_columns(conn, "task_runs")
                tasks = _sqlite_select_rows(
                    conn,
                    "tasks",
                    task_columns,
                    ("id", "status", "assignee", "title", "created_at", "started_at", "completed_at", "current_run_id"),
                    limit=50,
                )
                for row in tasks:
                    status = str(row.get("status") or "").lower()
                    if status == "running":
                        running_rows.append(row)
                    if status in {"ready", "todo"}:
                        ready_rows.append(row)
                event_rows = _sqlite_select_rows(
                    conn,
                    "task_events",
                    event_columns,
                    ("kind", "created_at", "run_id", "task_id"),
                    limit=100,
                )
                event_kinds = {str(row.get("kind") or "") for row in event_rows}
                terminal_events = sorted(event_kinds & KANBAN_TERMINAL_EVENT_KINDS)
                failure_events = sorted(event_kinds & KANBAN_FAILURE_EVENT_KINDS)
                run_rows = _sqlite_select_rows(
                    conn,
                    "task_runs",
                    run_columns,
                    ("id", "status", "outcome", "summary", "output_path", "completed_at", "task_id"),
                    limit=50,
                )
                created = bool(tasks) or "created" in event_kinds
                claimed = "claimed" in event_kinds or any(row.get("current_run_id") for row in tasks)
                spawned = "spawned" in event_kinds or bool(run_rows)
                completed = "completed" in event_kinds or any(str(row.get("status") or "").lower() in {"done", "completed"} for row in tasks)
                output_persisted = any(str(row.get("summary") or row.get("output_path") or "").strip() for row in run_rows)
                last_e2e_proof = {
                    "status": "complete" if all((created, claimed, spawned, completed)) else "partial",
                    "reason_code": "KANBAN_E2E_PROOF_COMPLETE" if all((created, claimed, spawned, completed)) else "KANBAN_E2E_PROOF_PARTIAL",
                    "created": created,
                    "claimed": claimed,
                    "spawned": spawned,
                    "completed": completed,
                    "output_persisted": output_persisted,
                    "terminal_event_kinds": terminal_events,
                    "run_count_sampled": len(run_rows),
                }
            finally:
                conn.close()
    running_count = len(running_rows)
    wait_reasons: list[dict[str, Any]] = []
    running_tasks: list[dict[str, Any]] = []
    blocked_unknown_assignee_count = 0
    blocked_unknown_assignees: dict[str, int] = {}
    for row in ready_rows[:12]:
        status = str(row.get("status") or "").lower()
        assignee = str(row.get("assignee") or "")
        reason = "spawnable_pending_dispatch_tick"
        if status == "todo":
            reason = "waiting_for_parent_promotion_or_recompute"
        elif assignee and profile_names and assignee not in profile_names:
            reason = "blocked_unknown_assignee"
            blocked_unknown_assignee_count += 1
            blocked_unknown_assignees[assignee] = blocked_unknown_assignees.get(assignee, 0) + 1
        elif max_spawn and running_count >= max_spawn:
            reason = "waiting_for_worker_capacity"
        wait_reasons.append(
            {
                "task_id": str(row.get("id") or ""),
                "status": status or "unknown",
                "assignee": assignee,
                "reason_code": reason,
            }
        )
    for row in running_rows[:12]:
        running_tasks.append(
            {
                "task_id": str(row.get("id") or ""),
                "status": "running",
                "assignee": str(row.get("assignee") or ""),
                "started_at": _safe_int(row.get("started_at"), 0),
            }
        )
    dispatcher_state = "unknown"
    if board.get("accessible") is not True:
        dispatcher_state = "unavailable"
    elif running_count:
        dispatcher_state = "workers_running"
    elif blocked_unknown_assignee_count:
        dispatcher_state = "blocked_ready_tasks"
    elif wait_reasons:
        dispatcher_state = "ready_waiting"
    elif board.get("task_count"):
        dispatcher_state = "idle_with_board"
    else:
        dispatcher_state = "ready_idle"
    return {
        "schema": KANBAN_RUNTIME_SNAPSHOT_SCHEMA,
        "read_only": True,
        "source": "hermes_kanban_board_readonly",
        "board_accessible": bool(board.get("accessible")),
        "dispatcher_state": dispatcher_state,
        "last_dispatch_tick_at": last_tick_at,
        "next_dispatch_tick_at": next_tick_at,
        "dispatch_interval_seconds": dispatch_interval_seconds,
        "running_worker_count": running_count,
        "ready_task_count": len(ready_rows),
        "running_tasks": running_tasks,
        "wait_reasons": wait_reasons,
        "blocked_unknown_assignee_count": blocked_unknown_assignee_count,
        "blocked_unknown_assignees": dict(sorted(blocked_unknown_assignees.items())) if blocked_unknown_assignees else {},
        "worker_capacity": {
            "configured_max_spawn": max_spawn,
            "running_count": running_count,
            "profile_count": profile_count,
            "profile_names": sorted(profile_names)[:12],
        },
        "recent_failure_event_kinds": failure_events,
        "last_e2e_proof": last_e2e_proof,
    }


def _kanban_claim_guard(verdict: str, *, profile_count: int) -> dict[str, Any]:
    level = KANBAN_VERDICT_ORDER.index(verdict) if verdict in KANBAN_VERDICT_ORDER else 0
    write_level = KANBAN_VERDICT_ORDER.index("board_write_certified")
    worker_level = KANBAN_VERDICT_ORDER.index("worker_lifecycle_certified")
    forbidden = []
    if level < write_level:
        forbidden.extend(["I used Kanban", "cards were created", "Kanban can create cards"])
    if level < worker_level:
        forbidden.extend(["workers are running", "workers are working"])
    if profile_count <= 1:
        forbidden.append("multi-agent board")
    safe_phrases = {
        "not_installed": "Hermes Kanban is not detected in this runtime.",
        "installed_only": "Hermes Kanban files are installed, but this agent has no certified board tools.",
        "cli_available": "Hermes Kanban appears CLI-inspectable, but this agent has no certified board tools.",
        "board_storage_accessible": "Hermes Kanban board storage is readable, but this agent is not certified to write cards.",
        "tool_surface_exposed": "Hermes Kanban tools are exposed, but board writes are not certified.",
        "board_write_certified": "Hermes Kanban board writes are certified for this runtime.",
        "worker_lifecycle_certified": "Hermes Kanban worker lifecycle is certified for this runtime.",
    }
    return {
        "claim_allowed": level >= write_level,
        "safe_phrase": safe_phrases.get(verdict, safe_phrases["not_installed"]),
        "forbidden_phrases": sorted(set(forbidden)),
    }


def _kanban_workstation_status(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    root = _resolve_hermes_root(config)
    hermes_home = _resolve_hermes_home(config)
    evidence_paths: list[str] = []
    if root is not None:
        candidates = (
            root / "tools" / "kanban_tools.py",
            root / "hermes_cli" / "kanban_db.py",
            root / "plugins" / "kanban",
            root / "website" / "docs" / "user-guide" / "features" / "kanban.md",
        )
        evidence_paths = [str(path) for path in candidates if path.exists()]
    installed = len(evidence_paths) >= 2
    cli_available = installed and _config_bool(config, "kanban_cli_available")
    exposed_tools = set(_config_list(config, "exposed_tool_names")) & KANBAN_WRITE_TOOL_NAMES
    tool_surface_exposed = _config_bool(config, "kanban_tool_surface_exposed") or bool(exposed_tools)
    board = _kanban_board_counts(config, root, hermes_home)
    runtime_snapshot = _kanban_runtime_snapshot(config, root, board, hermes_home)
    recovery_candidates = build_kanban_recovery_candidates(runtime_snapshot)
    recovery = recovery_summary(recovery_candidates)
    board_write_certified = tool_surface_exposed and _config_bool(config, "kanban_board_write_certified")
    worker_lifecycle_certified = board_write_certified and _config_bool(config, "kanban_worker_lifecycle_certified")
    profile_count = max(
        _safe_int(config.get("kanban_profile_count") if isinstance(config, Mapping) else 0, 0),
        _safe_int(_mapping(runtime_snapshot.get("worker_capacity")).get("profile_count"), 0),
        1,
    )
    local_artifact_path = (
        Path(str(config.get("local_kanban_artifact_path"))).expanduser()
        if isinstance(config, Mapping) and str(config.get("local_kanban_artifact_path") or "").strip()
        else None
    )
    local_artifact_present = bool(local_artifact_path and local_artifact_path.exists())
    if worker_lifecycle_certified:
        verdict = "worker_lifecycle_certified"
    elif board_write_certified:
        verdict = "board_write_certified"
    elif tool_surface_exposed:
        verdict = "tool_surface_exposed"
    elif board["accessible"]:
        verdict = "board_storage_accessible"
    elif cli_available:
        verdict = "cli_available"
    elif installed:
        verdict = "installed_only"
    else:
        verdict = "not_installed"
    can_write_board = verdict in {"board_write_certified", "worker_lifecycle_certified"}
    reason_code = "HERMES_KANBAN_NOT_DETECTED" if verdict == "not_installed" else f"HERMES_KANBAN_{verdict.upper()}"
    payload = {
        "schema": KANBAN_WORKSTATION_SCHEMA,
        "available": installed,
        "evidence_level": verdict,
        "kanban_verdict": verdict,
        "can_write_board": can_write_board,
        "real_board_written": bool(board["task_count"] > 0),
        "worker_lifecycle_certified": worker_lifecycle_certified,
        "profile_count": profile_count,
        "local_kanban_artifact_present": local_artifact_present,
        "kanban_ready_graph_only": local_artifact_present and not can_write_board,
        "board": board,
        "runtime_snapshot": runtime_snapshot,
        "recovery": recovery,
        "recovery_candidates": recovery_candidates[:8],
        "tool_surface": {
            "exposed": tool_surface_exposed,
            "exposed_tool_count": len(exposed_tools),
        },
        "claim_guard": _kanban_claim_guard(verdict, profile_count=profile_count),
        "reason_code": reason_code,
    }
    if installed:
        payload.update(
            {
                "owner": "hermes_kanban",
                "proactive_role": "wake_surface_and_handoff_only",
                "blocked_board_actions": [] if can_write_board else list(KANBAN_BLOCKED_BOARD_ACTIONS),
                "evidence_paths": evidence_paths[:8],
            }
        )
    return payload


def _compact_kanban_workstation_status(status: Mapping[str, Any]) -> dict[str, Any]:
    claim_guard = status.get("claim_guard") if isinstance(status.get("claim_guard"), Mapping) else {}
    runtime_snapshot = _mapping(status.get("runtime_snapshot"))
    last_e2e = _mapping(runtime_snapshot.get("last_e2e_proof"))
    payload: dict[str, Any] = {
        "available": bool(status.get("available")),
        "evidence_level": str(status.get("evidence_level") or ""),
        "kanban_verdict": str(status.get("kanban_verdict") or ""),
        "can_write_board": bool(status.get("can_write_board")),
        "worker_lifecycle_certified": bool(status.get("worker_lifecycle_certified")),
        "profile_count": _safe_int(status.get("profile_count"), 0),
        "claim_allowed": bool(claim_guard.get("claim_allowed")),
        "dispatcher_state": str(runtime_snapshot.get("dispatcher_state") or ""),
        "ready_task_count": _safe_int(runtime_snapshot.get("ready_task_count"), 0),
        "running_worker_count": _safe_int(runtime_snapshot.get("running_worker_count"), 0),
        "blocked_unknown_assignee_count": _safe_int(runtime_snapshot.get("blocked_unknown_assignee_count"), 0),
        "recovery_candidate_count": _safe_int(_mapping(status.get("recovery")).get("candidate_count"), 0),
        "last_e2e_proof_status": str(last_e2e.get("status") or ""),
        "reason_code": str(status.get("reason_code") or ""),
        "detail_level": "compact",
        "detail_omitted": True,
    }
    owner = str(status.get("owner") or "")
    proactive_role = str(status.get("proactive_role") or "")
    if owner:
        payload["owner"] = owner
    if proactive_role:
        payload["proactive_role"] = proactive_role
    return payload


def _compact_runtime_config_summary(runtime_config: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "status": str(runtime_config.get("status") or ""),
        "reason_code": str(runtime_config.get("reason_code") or ""),
        "mode": str(runtime_config.get("mode") or ""),
        "kill_switch": bool(runtime_config.get("kill_switch")),
        "cooldown_seconds": _safe_int(runtime_config.get("cooldown_seconds"), 0),
    }
    for key in ("kernel_memory_mode", "brainstack_plugin_mode", "plugin_mode"):
        value = str(runtime_config.get(key) or "")
        if value:
            payload[key] = value
    return payload


def _compact_operational_verdict(operational_verdict: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "operational_state": str(operational_verdict.get("operational_state") or ""),
        "reason_code": str(operational_verdict.get("reason_code") or ""),
        "agent_interpretation": str(operational_verdict.get("agent_interpretation") or ""),
    }


def _compact_scheduler_lane_health(scheduler_health: Mapping[str, Any]) -> dict[str, Any]:
    lane_states = _mapping(scheduler_health.get("lane_states"))
    jobs = scheduler_health.get("jobs") if isinstance(scheduler_health.get("jobs"), list) else []
    return {
        "verdict": str(scheduler_health.get("verdict") or ""),
        "starvation_risk": bool(scheduler_health.get("starvation_risk")),
        "reason_codes": [str(item) for item in scheduler_health.get("reason_codes") or [] if str(item)],
        "lane_state_count": len(lane_states),
        "job_count": len(jobs),
    }


def _compact_operating_loop_verdict(operating_loop: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "verdict": str(operating_loop.get("verdict") or ""),
        "reason_codes": [str(item) for item in operating_loop.get("reason_codes") or [] if str(item)],
        "split_brain_detected": bool(operating_loop.get("split_brain_detected")),
        "has_frontier": bool(operating_loop.get("has_frontier")),
        "blockers": [str(item) for item in operating_loop.get("blockers") or [] if str(item)],
        "warnings": [str(item) for item in operating_loop.get("warnings") or [] if str(item)],
        "agent_claim": str(operating_loop.get("agent_claim") or ""),
    }


def _compact_workstream_controller_status(workstream_controller: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": str(workstream_controller.get("status") or ""),
        "agent_claim": str(workstream_controller.get("agent_claim") or ""),
    }


def _compact_agent_use_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state_instruction": str(contract.get("state_instruction") or ""),
    }


def _normalize_proactive_status_detail_level(value: Any) -> str:
    normalized = str(value or "compact").strip().lower()
    if normalized in PROACTIVE_STATUS_DETAIL_LEVELS:
        return normalized
    return "compact"


def _scheduler_jobs_from_config(config: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(config, Mapping):
        return []
    value = config.get("scheduler_jobs") or config.get("proactive_scheduler_jobs")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _agent_item_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item, Mapping) else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}
    signal = metadata.get("evolver_signal") if isinstance(metadata, Mapping) else None
    wake = metadata.get("wake") if isinstance(metadata, Mapping) else None
    signal_summary: dict[str, Any] = {}
    if isinstance(signal, Mapping):
        signal_summary = {
            "status": str(signal.get("status") or ""),
            "reason_code": str(signal.get("reason_code") or ""),
            "actionable": bool(signal.get("actionable")),
            "directive_count": _safe_int(signal.get("directive_count"), 0),
            "directive_kinds": [str(value) for value in signal.get("directive_kinds") or []],
            "directive_execution": str(signal.get("directive_execution") or ""),
            "raw_output_present": bool(signal.get("raw_output_present")),
        }
    wake_summary: dict[str, Any] = {}
    if isinstance(wake, Mapping):
        wake_summary = {
            "decision": str(wake.get("decision") or ""),
            "reason_code": str(wake.get("reason_code") or ""),
            "delivery_requested": bool(wake.get("delivery_requested")),
        }
    pending_or_failing_reason = ""
    if signal_summary.get("reason_code"):
        pending_or_failing_reason = str(signal_summary["reason_code"])
    elif wake_summary.get("reason_code"):
        pending_or_failing_reason = str(wake_summary["reason_code"])
    else:
        pending_or_failing_reason = str(item.get("reason_code") or "")
    return {
        "source": str(item.get("source") or ""),
        "kind": str(item.get("kind") or ""),
        "state": str(item.get("state") or ""),
        "priority": str(item.get("priority") or ""),
        "intended_next_action": str(item.get("intended_next_action") or ""),
        "pending_or_failing_reason": pending_or_failing_reason,
        "evolver_signal": signal_summary,
        "wake": wake_summary,
        "current_assignment_authority": False,
    }


def _outbox_summary(items: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "outbox_id": str(item.get("outbox_id") or ""),
            "event_id": str(item.get("event_id") or ""),
            "delivery_target": str(item.get("delivery_target") or ""),
            "delivery_state": str(item.get("delivery_state") or ""),
            "attempt_count": _safe_int(item.get("attempt_count"), 0),
            "intended_next_action": str(item.get("intended_next_action") or ""),
            "last_error_present": bool(str(item.get("last_error") or "")),
            "kind": str(item.get("kind") or ""),
            "priority": str(item.get("priority") or ""),
            "title": str(item.get("title") or "")[:160],
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        }
        for item in items
    ]


def _is_agent_visible_candidate_item(item: Mapping[str, Any]) -> bool:
    kind = str(item.get("kind") or "")
    state = str(item.get("state") or "")
    if kind == ProactiveEventKind.HEARTBEAT_OK.value:
        return False
    return state in PROACTIVE_ACTIVE_ITEM_STATES


def _canonical_receipts_by_task_source(store: Any, principal_scope_key: str) -> dict[tuple[str, str], str]:
    if not hasattr(store, "list_canonical_memory_events"):
        return {}
    receipts: dict[tuple[str, str], str] = {}
    for row in store.list_canonical_memory_events(limit=500):
        event = _mapping(row.get("event"))
        scope = _mapping(event.get("scope"))
        claim = _mapping(event.get("claim"))
        authority = _mapping(event.get("authority"))
        source = _mapping(event.get("source"))
        if str(scope.get("principal_scope_key") or "") != str(principal_scope_key or ""):
            continue
        if str(claim.get("target_slot") or "") != "task.actionable":
            continue
        stable_fact_id = str(claim.get("stable_fact_id") or "")
        source_event_id = str(source.get("source_event_id") or "")
        receipt_id = str(authority.get("receipt_id") or "")
        if stable_fact_id and source_event_id and receipt_id:
            receipts[(stable_fact_id, source_event_id)] = receipt_id
    return receipts


def _actionable_substrate_summary(store: Any, principal_scope_key: str) -> dict[str, Any]:
    if not hasattr(store, "list_task_items"):
        return {
            "available": False,
            "reason_code": "TASK_STORE_UNAVAILABLE",
            "pending_count": 0,
        }
    receipt_index = _canonical_receipts_by_task_source(store, principal_scope_key)
    rows = store.list_task_items(
        principal_scope_key=principal_scope_key,
        item_type="task",
        statuses=("open",),
        limit=50,
    )
    sampled: list[dict[str, Any]] = []
    rejected_or_degraded = 0
    for row in rows:
        metadata = _mapping(row.get("metadata"))
        admission = _mapping(metadata.get("admission"))
        source_event_id = str(metadata.get("source_event_id") or admission.get("source_event_id") or "")
        source_span_id = str(metadata.get("source_span_id") or admission.get("source_span_id") or "")
        stable_key = str(row.get("stable_key") or admission.get("stable_key") or "")
        receipt_id = receipt_index.get((stable_key, source_event_id), "")
        is_actionable = (
            str(admission.get("target_slot") or "") == "task.actionable"
            and str(admission.get("decision") or "") in {"ACCEPT_DURABLE", "ACCEPT_WITH_SUPERSESSION"}
            and bool(metadata.get("truth_eligible"))
            and str(metadata.get("support_visibility") or "") == "answer_evidence"
            and bool(source_event_id and source_span_id and receipt_id)
        )
        if not is_actionable:
            rejected_or_degraded += 1
            continue
        sampled.append(
            {
                "stable_key": stable_key,
                "status": str(row.get("status") or ""),
                "title": str(row.get("title") or "")[:160],
                "source_event_id": source_event_id,
                "source_span_id": source_span_id,
                "receipt_id": receipt_id,
                "admission_reason_code": str(metadata.get("admission_reason_code") or admission.get("reason_code") or ""),
                "actionable_reason_code": "SOURCE_BACKED_ACTIONABLE_ADMITTED",
                "intended_next_action": "agent_may_consider_when_user_context_requires",
                "execution_payload_present": False,
                "current_assignment_authority": False,
            }
        )
    summary: dict[str, Any] = {
        "available": True,
        "pending_count": len(sampled),
        "reason_code": "SOURCE_BACKED_ACTIONABLE_SUBSTRATE_COMPACT",
    }
    if rejected_or_degraded:
        summary["rejected_or_degraded_count"] = rejected_or_degraded
    if sampled:
        summary["sampled_items"] = sampled[:5]
    return summary


def _store_counts(store: Any, principal_scope_key: str) -> dict[str, Any]:
    items = store.list_proactive_items(principal_scope_key=principal_scope_key, limit=200)
    state_counts = Counter(str(item.get("state") or "") for item in items)
    candidate_items = [item for item in items if _is_agent_visible_candidate_item(item)]
    heartbeat_items = [
        item
        for item in items
        if str(item.get("kind") or "") == ProactiveEventKind.HEARTBEAT_OK.value
    ]
    pending_outbox = store.list_pending_proactive_outbox(limit=200)
    user_visible_pending_outbox = [
        item
        for item in pending_outbox
        if str(item.get("principal_scope_key") or "") == str(principal_scope_key or "")
    ]
    runtime_scope_pending_outbox = [
        item
        for item in pending_outbox
        if str(item.get("principal_scope_key") or "") != str(principal_scope_key or "")
    ]
    latest = items[0] if items else {}
    actionable_substrate = _actionable_substrate_summary(store, principal_scope_key)
    counts: dict[str, Any] = {
        "total_items_sampled": len(items),
        "candidate_item_count": len(candidate_items),
        "heartbeat_item_count": len(heartbeat_items),
        "pending_outbox_count": len(pending_outbox),
        "user_visible_pending_outbox_count": len(user_visible_pending_outbox),
        "runtime_scope_pending_outbox_count": len(runtime_scope_pending_outbox),
        "outbox_scope_split_status": "split" if pending_outbox else "empty",
        "actionable_substrate": actionable_substrate,
        "pending_actionable_substrate_count": actionable_substrate.get("pending_count", 0),
    }
    if state_counts:
        counts["state_counts"] = dict(sorted(state_counts.items()))
    if pending_outbox:
        counts["pending_outbox_sample"] = _outbox_summary(pending_outbox[:5])
    if latest:
        counts["latest_item_summary"] = {
            "event_id": str(latest.get("event_id") or ""),
            "updated_at": str(latest.get("updated_at") or ""),
            "agent_summary": _agent_item_summary(latest),
        }
    return counts


def _can_receive_candidates(runtime_config: Mapping[str, Any], counts: Mapping[str, Any]) -> bool:
    substrate = _mapping(counts.get("actionable_substrate"))
    if substrate.get("available") is False:
        return False
    if str(runtime_config.get("mode") or "") == "disabled":
        return False
    if bool(runtime_config.get("kill_switch")):
        return False
    return str(runtime_config.get("status") or "") == "loaded"


def _agent_interpretation_for_state(state: str) -> str:
    return {
        "unavailable": "Proactive status is unavailable; do not claim it is running.",
        "disabled": "Proactive is disabled by config.",
        "killed": "Proactive is installed but the kill switch is on.",
        "ready_idle": "Proactive is ready and idle; no work is pending.",
        "candidate_available": "Proactive has a source-backed candidate; inspect it before making claims.",
        "wake_queued": "Proactive has queued a wake handoff; work is not executed yet.",
        "degraded": "Proactive is degraded; report the reason and do not infer capability.",
    }.get(state, "Proactive status is unknown; inspect the reason code.")


def _operational_state_reason(state: str) -> str:
    return {
        "unavailable": "PROACTIVE_STATUS_UNAVAILABLE",
        "disabled": "PROACTIVE_DISABLED",
        "killed": "PROACTIVE_KILL_SWITCH_ON",
        "ready_idle": "PROACTIVE_READY_IDLE",
        "candidate_available": "PROACTIVE_CANDIDATE_AVAILABLE",
        "wake_queued": "PROACTIVE_WAKE_QUEUED",
        "degraded": "PROACTIVE_DEGRADED",
    }.get(state, "PROACTIVE_STATE_UNKNOWN")


def _build_operational_verdict(
    *,
    runtime_config: Mapping[str, Any],
    counts: Mapping[str, Any],
    extension: Mapping[str, Any],
) -> dict[str, Any]:
    config_status = str(runtime_config.get("status") or "")
    mode = str(runtime_config.get("mode") or "")
    substrate = _mapping(counts.get("actionable_substrate"))
    user_visible_pending_outbox_count = _safe_int(counts.get("user_visible_pending_outbox_count"), 0)
    pending_actionable_count = _safe_int(counts.get("pending_actionable_substrate_count"), 0)
    candidate_item_count = _safe_int(counts.get("candidate_item_count"), 0)
    state = "ready_idle"
    if config_status in {"unavailable", "missing"}:
        state = "unavailable"
    elif mode == "disabled":
        state = "disabled"
    elif bool(runtime_config.get("kill_switch")):
        state = "killed"
    elif substrate.get("available") is False:
        state = "degraded"
    elif config_status == "loaded" and mode not in PROACTIVE_MODE_VALUES:
        state = "degraded"
    elif user_visible_pending_outbox_count > 0:
        state = "wake_queued"
    elif pending_actionable_count > 0 or candidate_item_count > 0:
        state = "candidate_available"

    can_receive = _can_receive_candidates(runtime_config, counts)
    can_wake = can_receive and mode == "live"
    return {
        "operational_state": state,
        "reason_code": _operational_state_reason(state),
        "idle_is_failure": False,
        "can_receive_candidates": can_receive,
        "can_wake_agent_when_candidate_exists": can_wake,
        "blocked_actions_mean_safety_boundary": True,
        "agent_interpretation": _agent_interpretation_for_state(state),
    }


def _agent_use_contract(operational_state: str) -> dict[str, Any]:
    state_instruction = {
        "ready_idle": "Ready idle is healthy.",
        "candidate_available": "Inspect candidate before claims.",
        "wake_queued": "Wake queued is pending handoff, not execution.",
        "degraded": "Report reason; do not infer capability.",
        "disabled": "Disabled by config.",
        "killed": "Kill switch is on.",
        "unavailable": "Status unavailable.",
    }.get(operational_state, "Use operational_state and reason_code.")
    return {
        "state_instruction": state_instruction,
        "blocked_actions_mean_safety_boundary": True,
        "must_not_claim": ["execute", "current_assignment", "idle_failure", "kanban_owner"],
    }


def validate_proactive_candidate_intake(candidate: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(candidate.get("kind") or "")
    source_authority = str(candidate.get("source_authority") or "")
    principal_scope_key = str(candidate.get("principal_scope_key") or "")
    source_refs = candidate.get("source_refs") if isinstance(candidate.get("source_refs"), list) else []
    receipt_id = str(candidate.get("receipt_id") or "")
    source_event_id = str(candidate.get("source_event_id") or "")
    execution_payload_present = bool(candidate.get("execution_payload_present"))
    current_assignment_authority = bool(candidate.get("current_assignment_authority"))
    rejected_reasons: list[str] = []
    if kind == ProactiveEventKind.HEARTBEAT_OK.value:
        rejected_reasons.append("HEARTBEAT_IS_LIVENESS_NOT_WORK")
    if source_authority not in {"source_backed", "kanban_owner"}:
        rejected_reasons.append("UNSUPPORTED_CANDIDATE_AUTHORITY")
    if not principal_scope_key:
        rejected_reasons.append("MISSING_PRINCIPAL_SCOPE")
    if not source_refs and not receipt_id and not source_event_id:
        rejected_reasons.append("MISSING_SOURCE_REFERENCE")
    if execution_payload_present:
        rejected_reasons.append("EXECUTION_PAYLOAD_FORBIDDEN")
    if current_assignment_authority:
        rejected_reasons.append("CURRENT_ASSIGNMENT_AUTHORITY_FORBIDDEN")

    classification = "candidate_visible" if not rejected_reasons else "rejected"
    return {
        "schema": PROACTIVE_CANDIDATE_INTAKE_SCHEMA,
        "classification": classification,
        "can_surface": classification == "candidate_visible",
        "can_wake": classification == "candidate_visible",
        "reason_code": "CANDIDATE_INTAKE_VALID" if not rejected_reasons else "CANDIDATE_INTAKE_REJECTED",
        "rejected_reasons": rejected_reasons,
        "current_assignment_authority": False,
        "execution_authority": False,
    }


def _readiness_probe(runtime_config: Mapping[str, Any], counts: Mapping[str, Any]) -> dict[str, Any]:
    synthetic_candidate = {
        "kind": ProactiveEventKind.FOLLOW_UP.value,
        "source_authority": "source_backed",
        "principal_scope_key": "principal:probe",
        "source_refs": ["probe:source"],
        "receipt_id": "probe:receipt",
        "execution_payload_present": False,
        "current_assignment_authority": False,
    }
    candidate = validate_proactive_candidate_intake(synthetic_candidate)
    try:
        from extensions.hermes_proactive.hermes_proactive.pulse_producer import classify_pulse_wake
        from extensions.hermes_proactive.hermes_proactive.surfacing import (
            SurfacingContext,
            decide_proactive_surfacing,
        )

        task = {
            "source": "readiness_probe",
            "kind": ProactiveEventKind.FOLLOW_UP.value,
            "title": "Synthetic readiness probe",
            "summary": "Synthetic source-backed candidate for no-write readiness proof.",
            "priority": "normal",
            "intended_next_action": "request_input",
            "evidence_ids": ["probe:source"],
            "candidate_key": "probe:source-backed",
        }
        surfacing = decide_proactive_surfacing(task, SurfacingContext(allow_notify=True))
        wake = classify_pulse_wake(
            {
                "schema": "brainstack.proactive_readiness_probe.synthetic_pulse.v1",
                "run_id": "readiness-probe",
                "tasks": [task],
                "no_op": False,
                "provider_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
            },
            create_outbox=False,
        )
        import_status = "available"
        import_error = ""
    except Exception as exc:
        surfacing = {}
        wake = {}
        import_status = "unavailable"
        import_error = exc.__class__.__name__

    counters = {
        "provider_calls": _safe_int(wake.get("provider_calls"), 0),
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "db_mutation": 0,
        "proactive_events_written": 0,
        "proactive_outbox_written": 0,
        "transcript_writes": _safe_int(wake.get("transcript_writes"), 0),
    }
    zero_side_effects = all(value == 0 for value in counters.values())
    probe_pass = (
        candidate.get("classification") == "candidate_visible"
        and import_status == "available"
        and str(wake.get("decision") or "") == "observed"
        and wake.get("delivery_requested") is False
        and str(surfacing.get("decision") or "") in {"needs_approval", "notify_user"}
        and zero_side_effects
    )
    return {
        "schema": PROACTIVE_READINESS_PROBE_SCHEMA,
        "status": "pass" if probe_pass else "fail",
        "synthetic": True,
        "read_only": True,
        "side_effect": False,
        "live_delivery": False,
        "provider_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "proof_counters": counters,
        "zero_side_effects": zero_side_effects,
        "candidate_intake": candidate,
        "surfacing": {
            "decision": str(surfacing.get("decision") or ""),
            "reason_code": str(surfacing.get("reason_code") or ""),
            "should_notify": bool(surfacing.get("should_notify")),
            "requires_approval": bool(surfacing.get("requires_approval")),
        },
        "wake": {
            "decision": str(wake.get("decision") or ""),
            "reason_code": str(wake.get("reason_code") or ""),
            "delivery_requested": bool(wake.get("delivery_requested")),
            "task_count": _safe_int(wake.get("task_count"), 0),
        },
        "import_status": import_status,
        "import_error": import_error,
        "config_mode": str(runtime_config.get("mode") or ""),
        "pending_outbox_count": _safe_int(counts.get("pending_outbox_count"), 0),
        "reason_code": "READINESS_PROBE_PASS" if probe_pass else "READINESS_PROBE_FAIL",
    }


def _compact_readiness_probe(probe: Mapping[str, Any]) -> dict[str, Any]:
    wake = _mapping(probe.get("wake"))
    surfacing = _mapping(probe.get("surfacing"))
    intake = _mapping(probe.get("candidate_intake"))
    return {
        "status": str(probe.get("status") or ""),
        "live_delivery": bool(probe.get("live_delivery")),
        "zero_side_effects": bool(probe.get("zero_side_effects")),
        "candidate_classification": str(intake.get("classification") or ""),
        "surfacing_decision": str(surfacing.get("decision") or ""),
        "wake_decision": str(wake.get("decision") or ""),
        "wake_delivery_requested": bool(wake.get("delivery_requested")),
        "reason_code": str(probe.get("reason_code") or ""),
    }


def build_proactive_status(
    *,
    store: Any,
    principal_scope_key: str,
    config: Mapping[str, Any] | None = None,
    detail_level: str = "compact",
) -> dict[str, Any]:
    normalized_detail_level = _normalize_proactive_status_detail_level(detail_level)
    hermes_home = _resolve_hermes_home(config)
    config_data, load_status = _load_yaml(_config_path_from_home(hermes_home))
    runtime_config = _runtime_config_summary(config_data, load_status)
    counts = _store_counts(store, principal_scope_key)
    extension = _extension_status(config)
    operational_verdict = _build_operational_verdict(
        runtime_config=runtime_config,
        counts=counts,
        extension=extension,
    )
    kanban_status = _kanban_workstation_status(config)
    scheduler_health = build_scheduler_lane_health(_scheduler_jobs_from_config(config))
    kanban_runtime = _mapping(kanban_status.get("runtime_snapshot"))
    operating_loop = build_operating_loop_verdict(
        {
            "kanban_runtime_snapshot": kanban_runtime,
            "scheduler_lane_health": scheduler_health,
            "signal_bus": _mapping(config.get("signal_bus") if isinstance(config, Mapping) else {}),
            "executor": _mapping(config.get("executor") if isinstance(config, Mapping) else {}),
            "builder": _mapping(config.get("builder") if isinstance(config, Mapping) else {}),
            "next_action": _mapping(config.get("next_action") if isinstance(config, Mapping) else {}),
        }
    )
    workstation_integrations = {
        "kanban": kanban_status if normalized_detail_level == "full" else _compact_kanban_workstation_status(kanban_status),
    }
    workstream_controller = controller_status([])
    model_use_contract = _agent_use_contract(str(operational_verdict["operational_state"]))
    if normalized_detail_level == "compact":
        config_payload = _compact_runtime_config_summary(runtime_config)
        scheduler_health_payload = _compact_scheduler_lane_health(scheduler_health)
        operating_loop_payload = _compact_operating_loop_verdict(operating_loop)
        workstream_controller_payload = _compact_workstream_controller_status(workstream_controller)
        model_use_contract_payload = _compact_agent_use_contract(model_use_contract)
    else:
        config_payload = runtime_config
        scheduler_health_payload = scheduler_health
        operating_loop_payload = operating_loop
        workstream_controller_payload = workstream_controller
        model_use_contract_payload = model_use_contract
    readiness_probe = _compact_readiness_probe(_readiness_probe(runtime_config, counts))
    operational_verdict_payload = (
        operational_verdict
        if normalized_detail_level == "full"
        else _compact_operational_verdict(operational_verdict)
    )
    return {
        "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
        "operation": "status",
        "detail_level": normalized_detail_level,
        "read_only": True,
        "side_effect": False,
        "bounded_model_facing": True,
        "operational_state": operational_verdict["operational_state"],
        "operational_verdict": operational_verdict_payload,
        "agent_interpretation": operational_verdict["agent_interpretation"],
        "idle_is_failure": operational_verdict["idle_is_failure"],
        "can_receive_candidates": operational_verdict["can_receive_candidates"],
        "can_wake_agent_when_candidate_exists": operational_verdict["can_wake_agent_when_candidate_exists"],
        "blocked_actions_mean_safety_boundary": operational_verdict["blocked_actions_mean_safety_boundary"],
        "config": config_payload,
        "counts": counts,
        "readiness_probe": readiness_probe,
        "workstation_integrations": workstation_integrations,
        "workstream_controller": workstream_controller_payload,
        "scheduler_lane_health": scheduler_health_payload,
        "operating_loop": operating_loop_payload,
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
        "model_use_contract": model_use_contract_payload,
        "reason_code": "PROACTIVE_STATUS_TOOL_BACKED_COMPACT",
    }


def list_proactive_agent_items(
    *,
    store: Any,
    principal_scope_key: str,
    state: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    items = store.list_proactive_items(
        principal_scope_key=principal_scope_key,
        state=str(state or ""),
        limit=max(1, min(int(limit or 20), 50)),
    )
    summaries = []
    for item in items:
        summaries.append(
            {
                "event_id": str(item.get("event_id") or ""),
                "source": str(item.get("source") or ""),
                "source_ref": str(item.get("source_ref") or ""),
                "kind": str(item.get("kind") or ""),
                "title": str(item.get("title") or ""),
                "summary": str(item.get("summary") or "")[:500],
                "priority": str(item.get("priority") or ""),
                "state": str(item.get("state") or ""),
                "reason_code": str(item.get("reason_code") or ""),
                "intended_next_action": str(item.get("intended_next_action") or ""),
                "evidence_count": len(item.get("evidence_ids") or []),
                "updated_at": str(item.get("updated_at") or ""),
                "agent_summary": _agent_item_summary(item),
                "current_assignment_authority": False,
            }
        )
    return {
        "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
        "operation": "list",
        "read_only": True,
        "side_effect": False,
        "principal_scope_key": str(principal_scope_key or ""),
        "state_filter": str(state or ""),
        "limit": max(1, min(int(limit or 20), 50)),
        "items": summaries,
        "item_count": len(summaries),
        "current_assignment_authority": False,
        "model_use_contract": _agent_use_contract("candidate_available" if summaries else "ready_idle"),
        "reason_code": "PROACTIVE_LIST_TOOL_BACKED",
    }


def inspect_proactive_agent_item(
    *,
    store: Any,
    principal_scope_key: str,
    event_id: str,
) -> dict[str, Any]:
    try:
        payload = store.inspect_proactive_item(event_id=str(event_id or ""))
    except KeyError:
        return {
            "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
            "operation": "inspect",
            "status": "not_found",
            "read_only": True,
            "side_effect": False,
            "event_id": str(event_id or ""),
            "reason_code": "PROACTIVE_ITEM_NOT_FOUND",
        }
    item = payload.get("item") or {}
    if str(item.get("principal_scope_key") or "") != str(principal_scope_key or ""):
        return {
            "schema": PROACTIVE_AGENT_CONTRACT_SCHEMA,
            "operation": "inspect",
            "status": "rejected",
            "read_only": True,
            "side_effect": False,
            "event_id": str(event_id or ""),
            "reason_code": "PROACTIVE_ITEM_SCOPE_MISMATCH",
        }
    payload["schema"] = PROACTIVE_AGENT_CONTRACT_SCHEMA
    payload["operation"] = "inspect"
    payload["read_only"] = True
    payload["side_effect"] = False
    payload["current_assignment_authority"] = False
    payload["agent_summary"] = _agent_item_summary(item)
    payload["outbox_summary"] = _outbox_summary([entry for entry in payload.get("outbox") or [] if isinstance(entry, Mapping)])
    payload["model_use_contract"] = _agent_use_contract("candidate_available")
    payload["reason_code"] = "PROACTIVE_INSPECT_TOOL_BACKED"
    return payload


def _require_explicit_request(args: Mapping[str, Any]) -> dict[str, Any] | None:
    if not str(args.get("_trusted_operator_origin") or "").strip():
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "TRUSTED_OPERATOR_APPROVAL_REQUIRED",
            "error": "Proactive control requires a host-supplied trusted operator approval origin.",
        }
    if args.get("explicit_user_request") is True:
        return None
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "status": "rejected",
        "read_only": False,
        "side_effect": False,
        "reason_code": "EXPLICIT_USER_REQUEST_REQUIRED",
        "error": "Proactive control requires explicit_user_request=true.",
    }


def _set_kill_switch(
    *,
    config: Mapping[str, Any] | None,
    kill_switch: bool,
    reason_code: str,
) -> dict[str, Any]:
    hermes_home = _resolve_hermes_home(config)
    config_path = _config_path_from_home(hermes_home)
    data, load_status = _load_yaml(config_path)
    if str(load_status.get("status") or "") != "loaded" or config_path is None:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_kill_switch",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": str(load_status.get("reason_code") or "CONFIG_UNAVAILABLE"),
            "config": _runtime_config_summary(data, load_status),
        }
    _write_kill_switch_to_config(data, bool(kill_switch), reason_code)
    _write_yaml(config_path, data)
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": "set_kill_switch",
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "config_path": str(config_path),
        "kill_switch": bool(kill_switch),
        "reason_code": "PROACTIVE_KILL_SWITCH_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
    }


def _update_runtime_config(
    *,
    config: Mapping[str, Any] | None,
    action: str,
    key: str,
    value: Any,
    reason_code: str,
) -> dict[str, Any]:
    hermes_home = _resolve_hermes_home(config)
    config_path = _config_path_from_home(hermes_home)
    data, load_status = _load_yaml(config_path)
    if str(load_status.get("status") or "") != "loaded" or config_path is None:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": str(load_status.get("reason_code") or "CONFIG_UNAVAILABLE"),
            "config": _runtime_config_summary(data, load_status),
        }
    _write_runtime_config_value(data, key, value, reason_code)
    _write_yaml(config_path, data)
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": action,
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "config_path": str(config_path),
        key: value,
        "reason_code": "PROACTIVE_RUNTIME_CONFIG_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
        "effective_without_container_restart": True,
        "effective_scope": "config_backed_status_and_next_proactive_pulse",
    }


def _normalize_proactive_mode(value: Any) -> str:
    return str(value or "").strip().lower()


def _set_proactive_mode(
    *,
    config: Mapping[str, Any] | None,
    mode: str,
    action: str,
    reason_code: str,
) -> dict[str, Any]:
    normalized_mode = _normalize_proactive_mode(mode)
    if normalized_mode not in PROACTIVE_MODE_VALUES:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "mode": normalized_mode,
            "allowed_modes": list(PROACTIVE_MODE_VALUES),
            "reason_code": "INVALID_PROACTIVE_MODE",
            "current_assignment_authority": False,
        }
    return _update_runtime_config(
        config=config,
        action=action,
        key="proactive_mode",
        value=normalized_mode,
        reason_code=reason_code or "EXPLICIT_USER_REQUEST",
    )


def set_proactive_mode_from_explicit_request(
    *,
    args: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if args.get("explicit_user_request") is not True:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_mode",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "EXPLICIT_USER_REQUEST_REQUIRED",
            "error": "Changing proactive mode requires explicit_user_request=true.",
            "current_assignment_authority": False,
        }
    return _set_proactive_mode(
        config=config,
        mode=str(args.get("mode") or ""),
        action="set_mode",
        reason_code=str(args.get("reason_code") or "EXPLICIT_USER_REQUEST"),
    )


def control_proactive_agent_surface(
    *,
    store: Any,
    principal_scope_key: str,
    args: Mapping[str, Any],
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rejection = _require_explicit_request(args)
    if rejection is not None:
        return rejection
    action = str(args.get("action") or "").strip()
    reason_code = str(args.get("reason_code") or ProactiveReasonCode.BLOCKED.value).strip()
    if action == "set_mode":
        return _set_proactive_mode(
            config=config,
            mode=str(args.get("mode") or ""),
            action=action,
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "set_kill_switch":
        return _set_kill_switch(
            config=config,
            kill_switch=bool(args.get("kill_switch")),
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "pause_proactive":
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_mode",
            value="disabled",
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "resume_proactive":
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_mode",
            value="live",
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action == "set_cooldown_seconds":
        cooldown = max(0, min(_safe_int(args.get("cooldown_seconds"), 0), 604800))
        return _update_runtime_config(
            config=config,
            action=action,
            key="proactive_cooldown_seconds",
            value=cooldown,
            reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        )
    if action in {"snooze_item", "mute_item"}:
        event_id = str(args.get("event_id") or "").strip()
        inspected = inspect_proactive_agent_item(store=store, principal_scope_key=principal_scope_key, event_id=event_id)
        if inspected.get("reason_code") != "PROACTIVE_INSPECT_TOOL_BACKED":
            inspected["schema"] = PROACTIVE_AGENT_CONTROL_SCHEMA
            inspected["operation"] = "control"
            inspected["action"] = action
            inspected["read_only"] = False
            inspected["side_effect"] = False
            return inspected
        metadata = {"explicit_user_request": True}
        if action == "snooze_item":
            metadata["snooze_until"] = str(args.get("snooze_until") or "")
            metadata["control"] = "snoozed"
        else:
            metadata["muted"] = True
            metadata["control"] = "muted"
        payload = store.set_proactive_item_state(
            event_id=event_id,
            state=ProactiveEventState.SUPPRESSED.value,
            reason_code=reason_code or (ProactiveReasonCode.SNOOZED.value if action == "snooze_item" else "MUTED"),
            actor="agent_explicit_user_request",
            trace_id=str(args.get("trace_id") or ""),
            metadata=metadata,
        )
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "committed",
            "read_only": False,
            "side_effect": True,
            "event_id": event_id,
            "state": ProactiveEventState.SUPPRESSED.value,
            "result": payload,
            "reason_code": "PROACTIVE_ITEM_STATE_UPDATED",
            "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
            "current_assignment_authority": False,
        }
    if action != "set_item_state":
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": action,
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "reason_code": "UNSUPPORTED_PROACTIVE_CONTROL_ACTION",
            "allowed_actions": list(PROACTIVE_ALLOWED_CONTROL_ACTIONS),
            "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        }
    event_id = str(args.get("event_id") or "").strip()
    state = str(args.get("state") or "").strip()
    valid_states = {item.value for item in ProactiveEventState}
    if state not in valid_states:
        return {
            "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
            "operation": "control",
            "action": "set_item_state",
            "status": "rejected",
            "read_only": False,
            "side_effect": False,
            "event_id": event_id,
            "reason_code": "INVALID_PROACTIVE_ITEM_STATE",
            "allowed_states": sorted(valid_states),
        }
    inspected = inspect_proactive_agent_item(store=store, principal_scope_key=principal_scope_key, event_id=event_id)
    if inspected.get("reason_code") != "PROACTIVE_INSPECT_TOOL_BACKED":
        inspected["schema"] = PROACTIVE_AGENT_CONTROL_SCHEMA
        inspected["operation"] = "control"
        inspected["action"] = "set_item_state"
        inspected["read_only"] = False
        inspected["side_effect"] = False
        return inspected
    payload = store.set_proactive_item_state(
        event_id=event_id,
        state=state,
        reason_code=reason_code or "EXPLICIT_USER_REQUEST",
        actor="agent_explicit_user_request",
        trace_id=str(args.get("trace_id") or ""),
        metadata={"explicit_user_request": True},
    )
    return {
        "schema": PROACTIVE_AGENT_CONTROL_SCHEMA,
        "operation": "control",
        "action": "set_item_state",
        "status": "committed",
        "read_only": False,
        "side_effect": True,
        "event_id": event_id,
        "state": state,
        "result": payload,
        "reason_code": "PROACTIVE_ITEM_STATE_UPDATED",
        "blocked_actions": list(PROACTIVE_BLOCKED_ACTIONS),
        "current_assignment_authority": False,
    }
