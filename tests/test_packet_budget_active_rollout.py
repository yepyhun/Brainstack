from __future__ import annotations

from brainstack import BrainstackMemoryProvider
from brainstack.control_plane import build_working_memory_packet
from brainstack.core.packet_budget import (
    ALLOWED_PACKET_BUDGET_REASON_CODES,
    validate_packet_budget_trace,
)
from brainstack.db import BrainstackStore
from scripts.measure_packet_budget_active_rollout import measure_active_rollout


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 4,
        "continuity_recent_limit": 4,
        "continuity_match_limit": 4,
        "transcript_match_limit": 4,
        "transcript_char_budget": 1200,
        "evidence_item_budget": 8,
        "graph_limit": 2,
        "corpus_limit": 1,
        "corpus_char_budget": 320,
        "operating_match_limit": 2,
        "record_retrievals": False,
    }


def test_provider_prefetch_supported_path_uses_active_budget(tmp_path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "packet_budget_mode": "active",
            "packet_budget_max_candidate_tokens": 18,
        }
    )
    provider.initialize(
        "session:phase208-default",
        platform="test",
        user_id="phase208-user",
        agent_identity="phase208-agent",
        agent_workspace="phase208-workspace",
    )
    assert provider._store is not None
    store = provider._store
    scope = provider._principal_scope_key
    session = provider._session_id
    try:
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="The user's name is PublicExample.",
            source="test",
            confidence=0.99,
            metadata={"principal_scope_key": scope, "target_slot": "identity.preferred_address_name"},
        )
        for index in range(8):
            store.add_continuity_event(
                session_id=session,
                turn_number=index + 1,
                kind="user",
                content=f"PUBLIC_SUPPORT_NOISE_{index}",
                source="test",
                metadata={"principal_scope_key": scope},
            )

        block = provider.prefetch("What is my name?", session_id=session)
        packet_budget = provider._last_prefetch_policy["packet_budget"]

        assert packet_budget["mode"] == "active"
        assert packet_budget["applied_to_output"] is True
        assert packet_budget["budget_reason_code_registry_pass"] is True
        assert packet_budget["raw_text_in_budget_trace"] is False
        assert "PublicExample" in block
    finally:
        provider.shutdown()


def test_invalid_packet_budget_mode_is_explicit_not_silent(tmp_path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    try:
        packet = build_working_memory_packet(
            store,
            query="Invalid packet budget mode probe",
            session_id="session:invalid-budget-mode",
            principal_scope_key="principal:invalid-budget-mode",
            packet_budget_mode="not-a-mode",
            **_packet_defaults(),
        )

        assert packet["packet_budget"]["enabled"] is False
        assert packet["packet_budget"]["disabled_reason"] == "invalid_packet_budget_mode"
    finally:
        store.close()


def test_packet_budget_reason_code_registry_rejects_unknown_reason() -> None:
    trace = {
        "candidates": [],
        "packet_budget": {
            "budget_decisions": [
                {
                    "candidate_id": "candidate-public",
                    "decision": "dropped",
                    "reason_code": "free_text_reason",
                    "token_estimate": 1,
                }
            ],
            "budget_reason_code_registry_pass": False,
            "raw_text_in_budget_trace": False,
        },
    }

    errors = validate_packet_budget_trace(trace)

    assert "budget_reason_code_not_registered" in errors
    assert "budget_reason_code_registry_failed" in errors
    assert "free_text_reason" not in ALLOWED_PACKET_BUDGET_REASON_CODES


def test_active_rollout_measurement_meets_thresholds() -> None:
    report = measure_active_rollout(sample_count=24, max_candidate_tokens=120)

    assert report["active_budget_enabled_for_supported_paths"] is True
    assert report["scenario_count"] >= 20
    assert report["distinct_scenario_family_count"] >= 6
    assert report["protected_truth_drop_attempts"] == 0
    assert report["budget_decision_trace_present"] is True
    assert report["budget_reason_code_registry_pass"] is True
    assert report["raw_text_in_budget_trace"] is False
    assert report["candidate_token_delta_percent"] > 0
    assert (
        report["packet_build_latency_overhead_ms_p95"]
        <= report["packet_build_latency_overhead_threshold_ms"]
    )
    assert report["unsupported_path_fail_closed_count"] == 1
