from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brainstack import BrainstackMemoryProvider
from brainstack.adaptive_evidence_broker import build_broker_trace_from_packet, validate_broker_trace
from brainstack.control_plane import build_working_memory_packet
from brainstack.core.packet_budget import (
    DEFAULT_PACKET_BUDGET_MODE,
    BUDGET_STATUS_INSUFFICIENT_AUTHORITY,
    PacketBudgetPolicy,
    apply_packet_budget,
    resolve_packet_budget_mode,
    validate_packet_budget_trace,
)
from brainstack.db import BrainstackStore
from scripts.verify_packet_budget_active_default import verify_active_default


PRIVATE_TEXT = "private-active-default-proof-text-must-not-leak"


def _candidate(candidate_id: str, **overrides: Any) -> dict[str, Any]:
    item = {
        "candidate_id": candidate_id,
        "evidence_id": candidate_id,
        "authority": "durable_truth",
        "decision": "selected",
        "source_role": "user",
        "truth_eligible": True,
        "answer_evidence_allowed": True,
        "answer_evidence": True,
        "protected": True,
        "source_event_id": f"turn-{candidate_id}",
        "source_span_id": f"span-{candidate_id}",
        "admission_id": f"admission-{candidate_id}",
        "receipt_id": f"receipt-{candidate_id}",
        "token_estimate": 8,
        "content": PRIVATE_TEXT,
    }
    item.update(overrides)
    return item


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 4,
        "continuity_recent_limit": 6,
        "continuity_match_limit": 6,
        "transcript_match_limit": 4,
        "transcript_char_budget": 1800,
        "evidence_item_budget": 10,
        "graph_limit": 3,
        "corpus_limit": 2,
        "corpus_char_budget": 420,
        "operating_match_limit": 3,
        "record_retrievals": False,
    }


def test_default_packet_budget_mode_is_active() -> None:
    assert DEFAULT_PACKET_BUDGET_MODE == "active"
    assert resolve_packet_budget_mode(None) == "active"


def test_active_matrix_preserves_protected_truth_and_drops_support() -> None:
    candidates = [
        _candidate("truth-current", token_estimate=8),
        _candidate(
            "support-only",
            authority="support_only",
            truth_eligible=False,
            answer_evidence_allowed=False,
            answer_evidence=False,
            protected=False,
            receipt_id="",
            admission_id="",
            token_estimate=20,
        ),
        _candidate(
            "conflict",
            authority="conflict",
            row_type="conflict",
            support_visibility="contradiction_only",
            truth_eligible=False,
            answer_evidence_allowed=False,
            answer_evidence=False,
            protected=False,
            receipt_id="",
            admission_id="",
            token_estimate=10,
        ),
        _candidate(
            "prior-stale",
            authority="support_only",
            stale=True,
            freshness="prior",
            truth_eligible=False,
            answer_evidence_allowed=False,
            answer_evidence=False,
            protected=False,
            receipt_id="",
            admission_id="",
            token_estimate=10,
        ),
        _candidate("multilingual-cjk-proof", token_estimate=8),
    ]

    result = apply_packet_budget(candidates, PacketBudgetPolicy(max_candidate_tokens=16))
    trace = {"candidates": result.candidates, "packet_budget": result.to_trace_packet_budget()}
    broker = build_broker_trace_from_packet({"packet_budget": {"budget_decisions": result.candidates}})

    selected_ids = {item["candidate_id"] for item in result.candidates if item["decision"] == "selected"}
    dropped_ids = {item["candidate_id"] for item in result.candidates if item["decision"] == "dropped"}

    assert {"truth-current", "multilingual-cjk-proof"} <= selected_ids
    assert {"support-only", "conflict", "prior-stale"} <= dropped_ids
    assert validate_packet_budget_trace(trace) == []
    assert validate_broker_trace(broker) == []
    assert broker["unsafe_answer_truth_upgrade_count"] == 0
    assert PRIVATE_TEXT not in json.dumps(result.to_trace_packet_budget(), sort_keys=True)
    assert PRIVATE_TEXT not in json.dumps(broker, sort_keys=True)


def test_tiny_budget_fails_closed_without_dropping_protected_truth() -> None:
    result = apply_packet_budget(
        [_candidate("truth-a", token_estimate=9), _candidate("truth-b", token_estimate=9)],
        PacketBudgetPolicy(max_candidate_tokens=1),
    )

    selected = [item for item in result.candidates if item["decision"] == "selected"]

    assert result.status == BUDGET_STATUS_INSUFFICIENT_AUTHORITY
    assert result.fail_closed is True
    assert {item["candidate_id"] for item in selected} == {"truth-a", "truth-b"}
    assert result.to_trace_packet_budget()["answer_evidence_preserved"] is True


def test_build_working_memory_packet_uses_active_default_without_explicit_mode(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:m007:s03:default"
        session = "session:m007:s03:default"
        store.upsert_profile_item(
            stable_key="identity:m007:s03",
            category="identity",
            content="The public active-default proof name is ActiveDefaultUser.",
            source="active-default.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": scope, "truth_eligible": True},
        )
        for index in range(10):
            store.add_continuity_event(
                session_id=session,
                turn_number=index + 1,
                kind="user",
                content=f"SUPPORT_NOISE_ACTIVE_DEFAULT_{index} {PRIVATE_TEXT}",
                source="active-default.fixture",
                metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
            )

        packet = build_working_memory_packet(
            store,
            query="What is the public active-default proof name?",
            session_id=session,
            principal_scope_key=scope,
            **_packet_defaults(),
        )

        assert packet["packet_budget"]["mode"] == "active"
        assert packet["packet_budget"]["applied_to_output"] is True
        assert packet["packet_budget"]["budget_reason_code_registry_pass"] is True
        assert packet["packet_budget"]["raw_text_in_budget_trace"] is False
        assert packet["packet_budget"]["answer_evidence_preserved"] is True
        assert "ActiveDefaultUser" in packet["block"]
    finally:
        store.close()


def test_provider_supported_path_uses_active_default_without_config(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize("session:m007:s03:provider", platform="test", user_id="m007-s03-user")
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="identity:m007:s03:provider",
            category="identity",
            content="The public provider active-default proof name is ProviderActiveUser.",
            source="active-default.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": provider._principal_scope_key, "truth_eligible": True},
        )

        block = provider.prefetch("What is the public provider active-default proof name?")
        budget = provider._last_prefetch_policy["packet_budget"]

        assert budget["mode"] == "active"
        assert budget["applied_to_output"] is True
        assert budget["raw_text_in_budget_trace"] is False
        assert "ProviderActiveUser" in block
    finally:
        provider.shutdown()


def test_active_default_verifier_public_safe_report(tmp_path: Path) -> None:
    report = verify_active_default(out_path=tmp_path / "active-default.json")

    assert report["schema"] == "brainstack.packet_budget_active_default_proof.v1"
    assert report["status"] == "pass"
    assert report["active_default"] is True
    assert report["default_off_detected"] is False
    assert report["shadow_only_detected"] is False
    assert report["hidden_fallback_count"] == 0
    assert report["protected_truth_drop_attempts"] == 0
    assert report["public_safe"] is True
    assert (tmp_path / "active-default.json").exists()
    assert PRIVATE_TEXT not in json.dumps(report, sort_keys=True)
