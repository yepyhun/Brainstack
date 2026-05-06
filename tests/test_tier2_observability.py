from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider


def _provider(tmp_path: Path, extractor) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 4,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "tier2-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="tier2-session",
        turn_number=1,
        kind="turn",
        content="User: remember that ExampleUser uses Brainstack.\nAssistant: acknowledged.",
        source="test",
        metadata=provider._scoped_metadata(),
    )
    return provider


def test_tier2_lifecycle_reports_current_llm_route_without_terminal(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_mode": "shadow",
            "tier2_runtime": "hindsight_public_api_bridge",
            "tier2_hindsight_mode": "local_embedded",
            "tier2_hindsight_llm_provider": "hermes_managed",
            "tier2_hindsight_llm_model": "gpt-5.5",
            "tier2_hindsight_llm_base_url": "",
        }
    )

    route = provider.lifecycle_status()["tier2_runtime_route"]

    assert route["schema"] == "brainstack.tier2_runtime_route.v1"
    assert route["runtime"] == "hindsight_public_api_bridge"
    assert route["binding_status"] == "configured_unbound"
    assert route["binding_reason_code"] == "TIER2_HINDSIGHT_PUBLIC_API_BRIDGE_UNBOUND"
    assert route["runtime_invoked_by_worker"] is False
    assert route["mode"] == "shadow"
    assert route["llm_provider"] == "hermes_managed"
    assert route["effective_model"] == "gpt-5.5"
    assert route["uses_legacy_gpt_5_2_codex"] is False
    assert "gpt-5.5" in route["model_answer"]
    assert route["background_task_status"]["schema"] == "brainstack.background_task_status.v1"
    assert route["background_task_status"]["tier2_write_allowed"] is False


def test_tier2_doctor_reports_configured_hindsight_bridge_unbound(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_runtime": "hindsight_public_api_bridge",
            "tier2_hindsight_llm_provider": "hermes_managed",
            "tier2_hindsight_llm_model": "gpt-5.5",
        }
    )
    provider.initialize(
        "tier2-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        doctor = provider.memory_kernel_doctor(strict=True)
        tier2 = doctor["capabilities"]["tier2"]

        assert doctor["verdict"] == "fail"
        assert tier2["status"] == "unavailable"
        assert tier2["active"] is False
        assert tier2["reason_code"] == "TIER2_RUNTIME_CONFIGURED_UNBOUND"
        assert tier2["runtime_route"]["binding_status"] == "configured_unbound"
        assert any(
            issue["capability"] == "tier2" and issue["reason_code"] == "TIER2_RUNTIME_CONFIGURED_UNBOUND"
            for issue in doctor["issues"]
        )
    finally:
        provider.shutdown()


def test_tier2_session_end_flush_defaults_enabled(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )

    assert provider._tier2_session_end_flush_enabled is True


def test_tier2_session_end_flush_explicit_false_string_stays_disabled(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_session_end_flush_enabled": "false",
        }
    )

    assert provider._tier2_session_end_flush_enabled is False


def test_tier2_run_result_is_persisted_with_counts(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:preferred_address_name",
                    "content": "ExampleUser",
                    "confidence": 0.95,
                    "metadata": {"source_role": "user"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-session",
            turn_number=1,
            trigger_reason="test_flush",
        )
        assert result["status"] == "ok"
        assert result["json_parse_status"] == "ok"
        assert result["writes_performed"] == 0
        assert result["action_counts"]["QUARANTINE_PROPOSAL"] == 1
        assert provider._store is not None
        latest = provider._store.latest_tier2_run_record(session_id="tier2-session")
        assert latest is not None
        assert latest["run_id"] == result["run_id"]
        assert latest["status"] == "ok"
        assert latest["parse_status"] == "ok"
        assert latest["writes_performed"] == 0
        doctor = provider.memory_kernel_doctor(strict=True)
        assert doctor["capabilities"]["tier2"]["latest_persistent_run"]["run_id"] == result["run_id"]
    finally:
        provider.shutdown()


def test_tier2_doctor_degrades_from_latest_persisted_failed_run(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "tier2-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    try:
        assert provider._store is not None
        provider._store.record_tier2_run_result(
            {
                "run_id": "failed-tier2-run",
                "session_id": "tier2-session",
                "turn_number": 7,
                "trigger_reason": "session_end_flush",
                "request_status": "failed",
                "json_parse_status": "not_run",
                "status": "failed",
                "transcript_count": 2,
                "extracted_counts": {},
                "action_counts": {},
                "writes_performed": 0,
                "no_op_reasons": [],
                "error_reason": "private provider error detail must not be agent-facing",
                "duration_ms": 123,
            }
        )

        doctor = provider.memory_kernel_doctor(strict=True)
        tier2 = doctor["capabilities"]["tier2"]
        latest = tier2["latest_persistent_run"]

        assert doctor["verdict"] == "fail"
        assert tier2["status"] == "degraded"
        assert tier2["active"] is False
        assert tier2["reason_code"] == "TIER2_PERSISTED_RUN_FAILED"
        assert tier2["persistent_run_health"]["status"] == "failed"
        assert latest["run_id"] == "failed-tier2-run"
        assert latest["request_status"] == "failed"
        assert latest["parse_status"] == "not_run"
        assert latest["writes_performed"] == 0
        assert latest["error_recorded"] is True
        assert "error_reason" not in latest

        stats = json.loads(provider.handle_tool_call("brainstack_stats", {"strict": True}))
        assert stats["status"] == "fail"
        assert stats["doctor"]["capabilities"]["tier2"]["reason_code"] == "TIER2_PERSISTED_RUN_FAILED"
        assert stats["doctor"]["issues"][0]["reason_code"] == "TIER2_PERSISTED_RUN_FAILED"
    finally:
        provider.shutdown()


def test_tier2_rejects_assistant_authored_profile_truth(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "profile_items": [
                {
                    "category": "identity",
                    "slot": "identity:name",
                    "content": "Assistant self-diagnosis should not be user truth.",
                    "confidence": 0.95,
                    "metadata": {"source_role": "assistant"},
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="tier2-session",
            turn_number=1,
            trigger_reason="test_flush",
        )
        assert result["status"] == "ok"
        assert result["action_counts"]["REJECT_ASSISTANT_AUTHORED"] == 1
        assert result["writes_performed"] == 0
        assert "all_candidates_rejected_or_noop" in result["no_op_reasons"]
        assert provider._store is not None
        assert provider._store.get_profile_item(
            stable_key="identity:name",
            principal_scope_key=provider._principal_scope_key,
        ) is None
    finally:
        provider.shutdown()
