from __future__ import annotations

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
    assert route["mode"] == "shadow"
    assert route["llm_provider"] == "hermes_managed"
    assert route["effective_model"] == "gpt-5.5"
    assert route["uses_legacy_gpt_5_2_codex"] is False
    assert "gpt-5.5" in route["model_answer"]


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
