from __future__ import annotations

from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_memory_kernel_doctor
from scripts.run_runtime_spine_capability_parity_proof import build_report


def test_runtime_spine_capability_parity_proof_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["llm_calls_performed"] is False
    assert report["issues"] == []
    assert all(report["proof"].values())


def test_default_tier2_runtime_is_bound_internal_extractor(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "runtime-spine-test",
        platform="test",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    try:
        route = provider.lifecycle_status()["tier2_runtime_route"]

        assert route["runtime"] == "internal_extractor"
        assert route["actual_worker_path"] == "internal_extractor"
        assert route["binding_status"] == "bound"
        assert route["configured_runtime_equals_worker_path"] is True
        assert route["runtime_invoked_by_worker"] is True
    finally:
        provider.shutdown()


def test_explicit_hindsight_runtime_fails_closed_instead_of_silent_internal_fallback(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_runtime": "hindsight_public_api_bridge",
            "background_tasks": {
                "brainstack.background_consolidation": {
                    "status": "active",
                    "provider_label": "main",
                    "model_label": "",
                    "main_provider_label": "primary-provider",
                    "main_model_label": "gpt-5.5",
                    "route_readiness": {
                        "status": "ready",
                        "reason_code": "AUXILIARY_ROUTE_READY",
                        "task_slot": "flush_memories",
                        "effective_provider_label": "primary-provider",
                        "effective_model_label": "gpt-5.5",
                    },
                    "fallback_policy": "none",
                }
            },
        }
    )
    provider.initialize(
        "runtime-spine-test",
        platform="test",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    try:
        assert provider._store is not None
        provider._store.add_transcript_entry(
            session_id="runtime-spine-test",
            turn_number=1,
            kind="turn",
            content="User: public verification turn.\nAssistant: acknowledged.",
            source="test",
            metadata=provider._scoped_metadata(),
        )

        result = provider._run_tier2_batch(
            session_id="runtime-spine-test",
            turn_number=1,
            trigger_reason="runtime_spine_test",
        )

        assert result["status"] == "failed"
        assert result["request_status"] == "failed"
        assert "no Hindsight worker binding is installed" in result["error_reason"]
    finally:
        provider.shutdown()


def test_explicit_capture_reconcile_uses_typed_result_no_tuple_drift(tmp_path: Path) -> None:
    def extractor(*_args, **_kwargs):
        return {
            "profile_items": [
                {
                    "slot": "identity:preferred_address_name",
                    "content": "PublicVerifier",
                    "confidence": 0.95,
                }
            ],
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "runtime-spine-test",
        platform="test",
        user_id="public-safe-user",
        agent_identity="brainstack-verifier",
        agent_workspace="verification",
    )
    try:
        trace = provider._validate_explicit_capture_receipts(
            user_content="Remember that my preferred address name is PublicVerifier.",
            session_id="runtime-spine-test",
        )
        tier2 = trace["tier2"]

        assert "reconcile_error" not in tier2
        assert "writes_performed" in tier2
        assert "consolidation_plan" in tier2
    finally:
        provider.shutdown()


def test_corrupt_corpus_backend_has_safe_repair_plan(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    try:
        store._corpus_backend_name = "chroma"
        store._corpus_backend = None
        store._corpus_backend_error = "sqlite3.DatabaseError: file is not a database"

        doctor = build_memory_kernel_doctor(store, strict=True, tier2_state={"enabled": False, "running": False})
        corpus = doctor["capabilities"]["corpus"]
        health = doctor["backend_health"]["backends"]["corpus"]

        assert doctor["verdict"] == "fail"
        assert corpus["error_class"] == "backend_store_corrupt"
        assert health["reason_code"] == "BACKEND_STORE_CORRUPT"
        assert health["repair_plan"]["status"] == "repairable_empty_cache"
        assert health["repair_plan"]["auto_rebuild_allowed"] is True
    finally:
        store.close()
