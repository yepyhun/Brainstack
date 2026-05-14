from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import yaml

from brainstack import BrainstackMemoryProvider
from brainstack.proactive_agent_contract import (
    PROACTIVE_ALLOWED_CONTROL_ACTIONS,
    validate_proactive_candidate_intake,
)
from hermes_continuation.work_state import build_durable_work_state_contract
from brainstack.tool_schemas import proactive_control_tool_schema, proactive_mode_tool_schema


def _provider(tmp_path: Path, *, config_text: str | None = None, hermes_root: str = "") -> BrainstackMemoryProvider:
    tmp_path.mkdir(parents=True, exist_ok=True)
    hermes_home = tmp_path / "hermes_home"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        config_text
        or (
            "proactive_mode: live\n"
            "proactive_cooldown_seconds: 21600\n"
            "proactive_kill_switch: false\n"
        ),
        encoding="utf-8",
    )
    config = {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
    }
    if hermes_root:
        config["hermes_root"] = hermes_root
    provider = BrainstackMemoryProvider(config)
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _provider_with_plugin_config(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home_nested"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "plugins:\n"
        "  brainstack:\n"
        "    proactive_mode: live\n"

        "    proactive_cooldown_seconds: 21600\n"
        "    proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack-nested.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
        }
    )
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _provider_with_kernel_memory_config(tmp_path: Path) -> BrainstackMemoryProvider:
    hermes_home = tmp_path / "hermes_home_kernel_memory"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "kernel_memory:\n"
        "  proactive_mode: live\n"

        "  proactive_cooldown_seconds: 21600\n"
        "  proactive_kill_switch: false\n",
        encoding="utf-8",
    )
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack-kernel-memory.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "hermes_home": str(hermes_home),
        }
    )
    provider.initialize(
        "proactive-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _create_item(provider: BrainstackMemoryProvider, *, scope: str | None = None) -> str:
    assert provider._store is not None
    item = provider._store.upsert_proactive_event(
        source="test",
        kind="follow_up",
        principal_scope_key=scope or provider._principal_scope_key,
        title="Review release notes",
        summary="A proactive follow-up exists for the release notes.",
        priority="normal",
        intended_next_action="request_input",
        evidence_ids=["ev_public_1"],
        source_ref="test-fixture",
        idempotency_key=f"test:{scope or provider._principal_scope_key}",
    )
    return str(item["event_id"])


def _operator_control(provider: BrainstackMemoryProvider, args: dict[str, object]) -> dict[str, object]:
    return json.loads(
        provider.handle_tool_call(
            "brainstack_proactive_control",
            args,
            trusted_write_origin="test_operator",
        )
    )


def _table_counts(provider: BrainstackMemoryProvider) -> dict[str, int]:
    assert provider._store is not None
    return {
        name: int(provider._store.conn.execute(f"SELECT COUNT(*) AS count FROM {name}").fetchone()["count"])
        for name in ("proactive_events", "proactive_outbox", "proactive_attention_ledger")
    }


def test_proactive_control_tool_schema_matches_contract() -> None:
    schema = proactive_control_tool_schema()
    properties = schema["parameters"]["properties"]

    assert sorted(properties["action"]["enum"]) == sorted(PROACTIVE_ALLOWED_CONTROL_ACTIONS)
    assert "mode" in properties
    assert sorted(properties["mode"]["enum"]) == ["disabled", "dry_run", "live"]
    assert "cooldown_seconds" in properties
    assert "snooze_until" in properties
    assert "execute_task" not in properties["action"]["enum"]


def test_proactive_mode_tool_schema_is_model_facing_and_narrow() -> None:
    schema = proactive_mode_tool_schema()
    properties = schema["parameters"]["properties"]

    assert schema["name"] == "brainstack_proactive_mode"
    assert schema["x_brainstack_tool_class"] == "explicit_proactive_mode_control"
    assert sorted(properties["mode"]["enum"]) == ["disabled", "dry_run", "live"]
    assert set(properties) == {"mode", "explicit_user_request", "reason_code"}
    assert schema["parameters"]["required"] == ["mode", "explicit_user_request"]


def test_proactive_control_is_operator_only_not_model_facing(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        model_tool_names = {schema["name"] for schema in provider.get_tool_schemas()}
        lifecycle = provider.lifecycle_status()
        operator_tool_names = {schema["name"] for schema in lifecycle["operator_only_tools"]}

        assert "brainstack_proactive_control" not in model_tool_names
        assert "brainstack_proactive_mode" in model_tool_names
        assert "brainstack_proactive_control" in operator_tool_names
    finally:
        provider.shutdown()


def test_proactive_status_is_tool_backed_and_read_only(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        _create_item(provider)
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))

        assert payload["schema"] == "brainstack.proactive_agent_surface.v1"
        assert payload["operation"] == "status"
        assert payload["read_only"] is True
        assert payload["side_effect"] is False
        assert payload["config"]["mode"] == "live"
        assert payload["config"]["kill_switch"] is False
        assert payload["counts"]["total_items_sampled"] == 1
        assert payload["current_assignment_authority"] is False
        assert "send_notification" in payload["blocked_actions"]
        assert payload["operational_state"] == "candidate_available"
        assert payload["operational_verdict"]["blocked_actions_mean_safety_boundary"] is True
        assert payload["model_use_contract"]["state_instruction"] == "Inspect candidate before claims."
    finally:
        provider.shutdown()


def test_proactive_status_ready_idle_is_explicit_and_probe_is_side_effect_free(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        before = _table_counts(provider)
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        after = _table_counts(provider)

        assert payload["operational_state"] == "ready_idle"
        assert payload["idle_is_failure"] is False
        assert payload["agent_interpretation"] == "Proactive is ready and idle; no work is pending."
        assert payload["can_receive_candidates"] is True
        assert payload["can_wake_agent_when_candidate_exists"] is True
        assert payload["readiness_probe"]["status"] == "pass"
        assert payload["readiness_probe"]["live_delivery"] is False
        assert payload["readiness_probe"]["zero_side_effects"] is True
        assert after == before
    finally:
        provider.shutdown()


def test_proactive_operational_precedence_disabled_killed_degraded(tmp_path: Path) -> None:
    disabled = _provider(
        tmp_path / "disabled",
        config_text="proactive_mode: disabled\nproactive_cooldown_seconds: 21600\nproactive_kill_switch: false\n",
    )
    try:
        payload = json.loads(disabled.handle_tool_call("brainstack_proactive_status", {}))
        assert payload["operational_state"] == "disabled"
        assert payload["can_receive_candidates"] is False
    finally:
        disabled.shutdown()

    killed = _provider(
        tmp_path / "killed",
        config_text="proactive_mode: live\nproactive_cooldown_seconds: 21600\nproactive_kill_switch: true\n",
    )
    try:
        payload = json.loads(killed.handle_tool_call("brainstack_proactive_status", {}))
        assert payload["operational_state"] == "killed"
        assert payload["can_wake_agent_when_candidate_exists"] is False
    finally:
        killed.shutdown()

    degraded = _provider(
        tmp_path / "degraded",
        config_text="proactive_mode: automatic\nproactive_cooldown_seconds: 21600\nproactive_kill_switch: false\n",
    )
    try:
        payload = json.loads(degraded.handle_tool_call("brainstack_proactive_status", {}))
        assert payload["operational_state"] == "degraded"
        assert payload["operational_verdict"]["reason_code"] == "PROACTIVE_DEGRADED"
    finally:
        degraded.shutdown()


def test_proactive_status_kanban_boundary_is_read_only_and_donor_owned(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")
    provider = _provider(tmp_path / "kanban", hermes_root=str(hermes_root))
    try:
        before = _table_counts(provider)
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        after = _table_counts(provider)
        kanban = payload["workstation_integrations"]["kanban"]

        assert kanban["available"] is True
        assert kanban["kanban_verdict"] == "installed_only"
        assert kanban["owner"] == "hermes_kanban"
        assert kanban["proactive_role"] == "wake_surface_and_handoff_only"
        assert kanban["can_write_board"] is False
        assert kanban["claim_guard"]["claim_allowed"] is False
        assert "I used Kanban" in kanban["claim_guard"]["forbidden_phrases"]
        assert "dispatch" in kanban["blocked_board_actions"]
        assert payload["operational_state"] == "ready_idle"
        assert after == before
    finally:
        provider.shutdown()


def test_proactive_status_default_keeps_kanban_summary_model_bounded(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")
    provider = _provider(tmp_path / "kanban-compact", hermes_root=str(hermes_root))
    try:
        rendered = provider.handle_tool_call("brainstack_proactive_status", {})
        payload = json.loads(rendered)
        kanban = payload["workstation_integrations"]["kanban"]

        assert payload["detail_level"] == "compact"
        assert len(rendered.encode("utf-8")) < 3000
        assert kanban["kanban_verdict"] == "installed_only"
        assert kanban["can_write_board"] is False
        assert kanban["claim_allowed"] is False
        assert kanban["detail_omitted"] is True
        assert "blocked_board_actions" not in kanban
        assert "evidence_paths" not in kanban
        assert "claim_guard" not in kanban
    finally:
        provider.shutdown()


def test_proactive_status_reports_profile_local_cron_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "cron-profile-local")
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        cron = payload["workstation_integrations"]["cron_authority"]
        hermes_home = Path(provider._config["hermes_home"])

        assert cron["status"] == "healthy"
        assert cron["cron_authority_mode"] == "profile_local"
        assert cron["override_present"] is False
        assert cron["jobs_file"] == str(hermes_home / "cron" / "jobs.json")
        assert cron["output_dir"] == str(hermes_home / "cron" / "output")
        assert cron["expected_tick_lock"] == str(hermes_home / "cron" / ".tick.lock")
    finally:
        provider.shutdown()


def test_proactive_status_reports_explicit_shared_cron_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "cron-explicit-shared")
    try:
        shared_home = tmp_path / "shared-hermes-home"
        provider._config["cron_authority_home"] = str(shared_home)
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        cron = payload["workstation_integrations"]["cron_authority"]

        assert cron["status"] == "healthy"
        assert cron["cron_authority_mode"] == "explicit_shared"
        assert cron["override_present"] is True
        assert cron["jobs_file"] == str(shared_home / "cron" / "jobs.json")
        assert cron["output_dir"] == str(shared_home / "cron" / "output")
        assert cron["expected_tick_lock"] == str(shared_home / "cron" / ".tick.lock")
    finally:
        provider.shutdown()


def test_proactive_status_degrades_on_cron_tick_lock_mismatch(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "cron-mismatch")
    try:
        shared_home = tmp_path / "shared-hermes-home"
        profile_home = Path(provider._config["hermes_home"])
        provider._config["cron_authority_home"] = str(shared_home)
        provider._config["cron_scheduler_lock_path"] = str(profile_home / "cron" / ".tick.lock")
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        cron = payload["workstation_integrations"]["cron_authority"]

        assert cron["status"] == "degraded"
        assert cron["cron_authority_mode"] == "explicit_shared"
        assert cron["jobs_output_lock_agree"] is False
        assert cron["reason_code"] == "CRON_AUTHORITY_LOCK_MISMATCH"
    finally:
        provider.shutdown()


def test_proactive_status_default_stays_bounded_with_live_loop_diagnostics(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")
    kanban_db = tmp_path / "kanban-live.db"
    conn = sqlite3.connect(kanban_db)
    try:
        conn.execute(
            "CREATE TABLE tasks ("
            "id TEXT PRIMARY KEY, status TEXT, assignee TEXT, title TEXT, "
            "created_at INTEGER, started_at INTEGER, completed_at INTEGER, current_run_id INTEGER)"
        )
        conn.execute(
            "CREATE TABLE task_runs ("
            "id INTEGER PRIMARY KEY, task_id TEXT, status TEXT, outcome TEXT, "
            "summary TEXT, output_path TEXT, completed_at INTEGER)"
        )
        conn.execute(
            "CREATE TABLE task_events ("
            "id INTEGER PRIMARY KEY, task_id TEXT, kind TEXT, created_at INTEGER, run_id INTEGER)"
        )
        conn.execute(
            "INSERT INTO tasks (id, status, assignee, title, created_at) VALUES "
            "('task-ready', 'ready', 'missing-profile', 'Needs dispatch', 1)"
        )
        conn.execute(
            "INSERT INTO task_events (task_id, kind, created_at) VALUES "
            "('task-ready', 'spawn_failed', 2)"
        )
        conn.commit()
    finally:
        conn.close()

    provider = _provider(tmp_path / "kanban-live-compact", hermes_root=str(hermes_root))
    provider._config.update(
        {
            "kanban_db_path": str(kanban_db),
            "kanban_profile_names": ["default", "reviewer"],
            "kanban_max_spawn": 2,
            "scheduler_jobs": [
                {
                    "id": "signal-bus",
                    "lane": "signal",
                    "last_run_at": "2026-05-12T10:00:00Z",
                    "next_run_at": "2026-05-12T10:01:00Z",
                }
            ],
            "signal_bus": {"fresh": False, "stale": True},
            "executor": {"fresh": False, "stale": True},
            "builder": {"fresh": True},
            "next_action": {"exists": False},
        }
    )
    try:
        rendered = provider.handle_tool_call("brainstack_proactive_status", {})
        payload = json.loads(rendered)
        kanban = payload["workstation_integrations"]["kanban"]

        assert payload["detail_level"] == "compact"
        assert len(rendered.encode("utf-8")) < 3000
        assert kanban["kanban_verdict"] == "board_storage_accessible"
        assert kanban["blocked_unknown_assignee_count"] == 1
        assert payload["operating_loop"]["verdict"] in {"critical", "degraded"}
        assert "schema" not in kanban
        assert "lane_freshness" not in payload["operating_loop"]
    finally:
        provider.shutdown()


def test_proactive_status_compact_payload_surfaces_durable_work_state_verdict(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "durable-work-state-compact")
    provider._config.update(
        {
            "durable_work_state": build_durable_work_state_contract(
                {
                    "work_items": [
                        {
                            "id": "w1",
                            "status": "completed",
                            "authority": "verified",
                            "evidence_refs": ["artifact:1"],
                            "side_effect_durable": False,
                            "acknowledged": True,
                        }
                    ]
                }
            )
        }
    )
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        durable = payload["operating_loop"]["durable_work_state"]

        assert payload["detail_level"] == "compact"
        assert payload["operating_loop"]["verdict"] == "critical"
        assert "durable_work_state_critical" in payload["operating_loop"]["blockers"]
        assert durable["schema"] == "brainstack.external_work_state_summary.v1"
        assert durable["verdict"] == "critical"
        assert durable["repair_candidate_count"] == 1
    finally:
        provider.shutdown()


def test_proactive_status_compact_payload_surfaces_continuation_control_when_configured(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "continuation-control-compact")
    provider._config.update(
        {
            "continuation_control": {
                "verdict": "critical",
                "controller_mode": "prompt_primary",
                "token_policy": "violation",
                "reason_codes": ["PROMPT_PRIMARY_TOKEN_WASTE"],
            }
        }
    )
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        continuation = payload["continuation_control"]

        assert continuation["verdict"] == "critical"
        assert continuation["controller_mode"] == "prompt_primary"
        assert continuation["token_policy"] == "violation"
        assert payload["operating_loop"]["verdict"] == "critical"
    finally:
        provider.shutdown()


def test_proactive_status_compact_payload_surfaces_autonomy_continuation_when_configured(tmp_path: Path) -> None:
    provider = _provider(tmp_path / "autonomy-continuation-compact")
    provider._config.update(
        {
            "autonomy_continuation": {
                "verdict": "degraded",
                "decision": "repair",
                "reason_codes": ["LOCAL_REPAIR_REQUIRED"],
                "decision_journal": {
                    "confidence": 0.7,
                    "expected_value_next": 0.8,
                    "continue_score": 0.6,
                },
                "review": {"deep_verifier_required": True},
            }
        }
    )
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))
        continuation = payload["autonomy_continuation"]

        assert continuation["decision"] == "repair"
        assert continuation["verdict"] == "degraded"
        assert continuation["reason_code"] == "LOCAL_REPAIR_REQUIRED"
        assert continuation["deep_verifier_required"] is True
    finally:
        provider.shutdown()


def test_proactive_status_kanban_absent_does_not_degrade_ready_idle(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        kanban = payload["workstation_integrations"]["kanban"]

        assert kanban["available"] is False
        assert kanban["kanban_verdict"] == "not_installed"
        assert kanban["can_write_board"] is False
        assert payload["operational_state"] == "ready_idle"
    finally:
        provider.shutdown()


def test_proactive_status_kanban_board_storage_does_not_certify_write_or_workers(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")
    kanban_db = tmp_path / "kanban.db"
    conn = sqlite3.connect(kanban_db)
    try:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_runs (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE task_events (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO tasks (id) VALUES ('task-1')")
        conn.commit()
    finally:
        conn.close()

    provider = _provider(tmp_path / "kanban-board", hermes_root=str(hermes_root))
    provider._config["kanban_db_path"] = str(kanban_db)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        kanban = payload["workstation_integrations"]["kanban"]

        assert kanban["kanban_verdict"] == "board_storage_accessible"
        assert kanban["board"]["task_count"] == 1
        assert kanban["real_board_written"] is True
        assert kanban["can_write_board"] is False
        assert kanban["worker_lifecycle_certified"] is False
        assert "workers are running" in kanban["claim_guard"]["forbidden_phrases"]
    finally:
        provider.shutdown()


def test_proactive_status_kanban_tool_surface_requires_write_certification(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")

    provider = _provider(tmp_path / "kanban-tools", hermes_root=str(hermes_root))
    provider._config["kanban_tool_surface_exposed"] = True
    provider._config["kanban_profile_count"] = 1
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        kanban = payload["workstation_integrations"]["kanban"]

        assert kanban["kanban_verdict"] == "tool_surface_exposed"
        assert kanban["tool_surface"]["exposed"] is True
        assert kanban["can_write_board"] is False
        assert "Kanban can create cards" in kanban["claim_guard"]["forbidden_phrases"]
        assert "multi-agent board" in kanban["claim_guard"]["forbidden_phrases"]
    finally:
        provider.shutdown()


def test_proactive_status_kanban_write_and_worker_lifecycle_are_explicit_certifications(tmp_path: Path) -> None:
    hermes_root = tmp_path / "hermes_root"
    (hermes_root / "tools").mkdir(parents=True)
    (hermes_root / "hermes_cli").mkdir()
    (hermes_root / "plugins" / "kanban").mkdir(parents=True)
    (hermes_root / "tools" / "kanban_tools.py").write_text("# public fixture\n", encoding="utf-8")
    (hermes_root / "hermes_cli" / "kanban_db.py").write_text("# public fixture\n", encoding="utf-8")

    provider = _provider(tmp_path / "kanban-certified", hermes_root=str(hermes_root))
    provider._config["kanban_tool_surface_exposed"] = True
    provider._config["kanban_board_write_certified"] = True
    provider._config["kanban_worker_lifecycle_certified"] = True
    provider._config["kanban_profile_count"] = 3
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {"detail_level": "full"}))
        kanban = payload["workstation_integrations"]["kanban"]

        assert kanban["kanban_verdict"] == "worker_lifecycle_certified"
        assert kanban["can_write_board"] is True
        assert kanban["worker_lifecycle_certified"] is True
        assert kanban["claim_guard"]["claim_allowed"] is True
        assert "I used Kanban" not in kanban["claim_guard"]["forbidden_phrases"]
        assert "multi-agent board" not in kanban["claim_guard"]["forbidden_phrases"]
    finally:
        provider.shutdown()


def test_proactive_candidate_intake_rejects_forbidden_sources_and_payloads() -> None:
    valid = validate_proactive_candidate_intake(
        {
            "kind": "follow_up",
            "source_authority": "source_backed",
            "principal_scope_key": "principal:test",
            "source_refs": ["event:test"],
            "execution_payload_present": False,
            "current_assignment_authority": False,
        }
    )
    assert valid["classification"] == "candidate_visible"

    support_only = validate_proactive_candidate_intake(
        {
            "kind": "follow_up",
            "source_authority": "support_only",
            "principal_scope_key": "principal:test",
            "source_refs": ["event:test"],
        }
    )
    assert support_only["classification"] == "rejected"
    assert "UNSUPPORTED_CANDIDATE_AUTHORITY" in support_only["rejected_reasons"]

    raw = validate_proactive_candidate_intake(
        {
            "kind": "follow_up",
            "source_authority": "raw_transcript",
            "principal_scope_key": "principal:test",
        }
    )
    assert raw["classification"] == "rejected"
    assert "MISSING_SOURCE_REFERENCE" in raw["rejected_reasons"]

    heartbeat = validate_proactive_candidate_intake(
        {
            "kind": "heartbeat_ok",
            "source_authority": "source_backed",
            "principal_scope_key": "principal:test",
            "source_refs": ["heartbeat:ok"],
        }
    )
    assert heartbeat["classification"] == "rejected"
    assert "HEARTBEAT_IS_LIVENESS_NOT_WORK" in heartbeat["rejected_reasons"]

    execution_payload = validate_proactive_candidate_intake(
        {
            "kind": "follow_up",
            "source_authority": "source_backed",
            "principal_scope_key": "principal:test",
            "source_refs": ["event:test"],
            "execution_payload_present": True,
        }
    )
    assert execution_payload["classification"] == "rejected"
    assert "EXECUTION_PAYLOAD_FORBIDDEN" in execution_payload["rejected_reasons"]


def test_proactive_status_reads_brainstack_plugin_config(tmp_path: Path) -> None:
    provider = _provider_with_plugin_config(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))

        assert payload["config"]["mode"] == "live"
        assert payload["config"]["brainstack_plugin_mode"] == "live"
        assert payload["config"]["kill_switch"] is False
    finally:
        provider.shutdown()


def test_proactive_status_reads_kernel_memory_config(tmp_path: Path) -> None:
    provider = _provider_with_kernel_memory_config(tmp_path)
    try:
        payload = json.loads(provider.handle_tool_call("brainstack_proactive_status", {}))

        assert payload["config"]["mode"] == "live"
        assert payload["config"]["kernel_memory_mode"] == "live"
        assert payload["config"]["kill_switch"] is False
    finally:
        provider.shutdown()


def test_proactive_list_and_inspect_are_scope_safe(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        other_event_id = _create_item(provider, scope="other-scope")

        listed = json.loads(provider.handle_tool_call("brainstack_proactive_list", {"limit": 10}))
        assert listed["read_only"] is True
        assert listed["item_count"] == 1
        assert listed["items"][0]["event_id"] == event_id
        assert listed["items"][0]["current_assignment_authority"] is False

        inspected = json.loads(provider.handle_tool_call("brainstack_proactive_inspect", {"event_id": event_id}))
        assert inspected["reason_code"] == "PROACTIVE_INSPECT_TOOL_BACKED"
        assert inspected["read_only"] is True
        assert inspected["item"]["event_id"] == event_id

        rejected = json.loads(provider.handle_tool_call("brainstack_proactive_inspect", {"event_id": other_event_id}))
        assert rejected["reason_code"] == "PROACTIVE_ITEM_SCOPE_MISMATCH"
        assert rejected["status"] == "rejected"
    finally:
        provider.shutdown()


def test_proactive_control_requires_explicit_user_request(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        payload = _operator_control(
            provider,
            {"action": "set_item_state", "event_id": event_id, "state": "accepted"},
        )

        assert payload["schema"] == "brainstack.proactive_agent_control.v1"
        assert payload["status"] == "rejected"
        assert payload["reason_code"] == "EXPLICIT_USER_REQUEST_REQUIRED"
        assert payload["side_effect"] is False

        model_supplied = json.loads(
            provider.handle_tool_call(
                "brainstack_proactive_control",
                {"action": "set_item_state", "explicit_user_request": True, "event_id": event_id, "state": "accepted"},
            )
        )
        assert model_supplied["status"] == "rejected"
        assert model_supplied["reason_code"] == "TRUSTED_OPERATOR_APPROVAL_REQUIRED"
    finally:
        provider.shutdown()


def test_proactive_control_updates_item_state_without_current_assignment_authority(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        event_id = _create_item(provider)
        payload = _operator_control(
            provider,
            {
                "action": "set_item_state",
                "explicit_user_request": True,
                "event_id": event_id,
                "state": "accepted",
                "reason_code": "USER_ACCEPTED",
                "trace_id": "trace-public",
            },
        )

        assert payload["status"] == "committed"
        assert payload["side_effect"] is True
        assert payload["state"] == "accepted"
        assert payload["current_assignment_authority"] is False
        assert payload["result"]["item"]["state"] == "accepted"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_updates_only_runtime_config(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = _operator_control(
            provider,
            {
                "action": "set_kill_switch",
                "explicit_user_request": True,
                "kill_switch": True,
                "reason_code": "USER_DISABLED_PROACTIVE",
            },
        )

        assert payload["status"] == "committed"
        assert payload["action"] == "set_kill_switch"
        assert payload["side_effect"] is True
        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert data["proactive_kill_switch"] is True
        assert data["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_preserves_plugin_config_location(tmp_path: Path) -> None:
    provider = _provider_with_plugin_config(tmp_path)
    try:
        payload = _operator_control(
            provider,
            {
                "action": "set_kill_switch",
                "explicit_user_request": True,
                "kill_switch": True,
                "reason_code": "USER_DISABLED_PROACTIVE",
            },
        )

        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "proactive_kill_switch" not in data
        assert data["plugins"]["brainstack"]["proactive_kill_switch"] is True
        assert data["plugins"]["brainstack"]["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_kill_switch_control_preserves_kernel_memory_config_location(tmp_path: Path) -> None:
    provider = _provider_with_kernel_memory_config(tmp_path)
    try:
        payload = _operator_control(
            provider,
            {
                "action": "set_kill_switch",
                "explicit_user_request": True,
                "kill_switch": True,
                "reason_code": "USER_DISABLED_PROACTIVE",
            },
        )

        config_path = Path(payload["config_path"])
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert "proactive_kill_switch" not in data
        assert data["kernel_memory"]["proactive_kill_switch"] is True
        assert data["kernel_memory"]["proactive_control_last_reason"] == "USER_DISABLED_PROACTIVE"
    finally:
        provider.shutdown()


def test_proactive_control_rejects_unsupported_actions(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        payload = _operator_control(
            provider,
            {"action": "send_notification", "explicit_user_request": True},
        )

        assert payload["status"] == "rejected"
        assert payload["reason_code"] == "UNSUPPORTED_PROACTIVE_CONTROL_ACTION"
        assert payload["side_effect"] is False
        assert "send_notification" in payload["blocked_actions"]
    finally:
        provider.shutdown()
