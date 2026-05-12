from __future__ import annotations

from pathlib import Path

from brainstack.control_plane import build_working_memory_packet
from brainstack.db import BrainstackStore


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


def _seed_store(tmp_path: Path) -> tuple[BrainstackStore, str, str]:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"))
    store.open()
    scope = "principal:budget-working-memory"
    session = "session:budget-working-memory"
    store.upsert_profile_item(
        stable_key="identity:name",
        category="identity",
        content="The user's name is ExampleUser.",
        source="test",
        confidence=0.99,
        metadata={"principal_scope_key": scope, "target_slot": "identity.preferred_address_name"},
    )
    for index in range(4):
        store.add_continuity_event(
            session_id=session,
            turn_number=index + 1,
            kind="user",
            content=f"SUPPORT_NOISE_SHOULD_DROP_{index} repeated budget-only context.",
            source="test",
            metadata={"principal_scope_key": scope},
        )
    return store, scope, session


def test_working_memory_packet_budget_shadow_does_not_change_block(tmp_path: Path) -> None:
    store, scope, session = _seed_store(tmp_path)
    try:
        base = build_working_memory_packet(
            store,
            query="What is my name?",
            session_id=session,
            principal_scope_key=scope,
            packet_budget_mode="off",
            **_packet_defaults(),
        )
        shadow = build_working_memory_packet(
            store,
            query="What is my name?",
            session_id=session,
            principal_scope_key=scope,
            packet_budget_mode="shadow",
            packet_budget_max_candidate_tokens=18,
            **_packet_defaults(),
        )

        assert shadow["block"] == base["block"]
        assert shadow["packet_budget"]["mode"] == "shadow"
        assert shadow["packet_budget"]["applied_to_output"] is False
        assert shadow["packet_budget"]["dropped_candidate_tokens"] > 0
    finally:
        store.close()


def test_working_memory_packet_budget_active_drops_support_not_profile_truth(tmp_path: Path) -> None:
    store, scope, session = _seed_store(tmp_path)
    try:
        active = build_working_memory_packet(
            store,
            query="What is my name?",
            session_id=session,
            principal_scope_key=scope,
            packet_budget_mode="active",
            packet_budget_max_candidate_tokens=18,
            **_packet_defaults(),
        )

        assert "ExampleUser" in active["block"]
        assert "SUPPORT_NOISE_SHOULD_DROP" not in active["block"]
        assert active["packet_budget"]["mode"] == "active"
        assert active["packet_budget"]["applied_to_output"] is True
        assert active["packet_budget"]["dropped_candidate_tokens"] > 0
    finally:
        store.close()


def test_working_memory_packet_budget_active_fails_closed_for_tiny_budget(tmp_path: Path) -> None:
    store, scope, session = _seed_store(tmp_path)
    try:
        active = build_working_memory_packet(
            store,
            query="What is my name?",
            session_id=session,
            principal_scope_key=scope,
            packet_budget_mode="active",
            packet_budget_max_candidate_tokens=1,
            **_packet_defaults(),
        )

        assert "ExampleUser" in active["block"]
        assert active["packet_budget"]["status"] == "insufficient_for_authority_minimum"
        assert active["packet_budget"]["fail_closed"] is True
    finally:
        store.close()


def test_working_memory_packet_budget_does_not_collapse_distinct_graph_subjects(tmp_path: Path) -> None:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        scope = "principal:budget-graph-distinct-subjects"
        session = "session:budget-graph-distinct-subjects"
        for subject in ("Budget Graph Alpha", "Budget Graph Beta"):
            store.upsert_graph_state(
                subject_name=subject,
                attribute="status",
                value_text="active",
                source="budget-graph.fixture",
                metadata={"principal_scope_key": scope},
            )

        active = build_working_memory_packet(
            store,
            query="Budget Graph status active",
            session_id=session,
            principal_scope_key=scope,
            packet_budget_mode="active",
            packet_budget_max_candidate_tokens=120,
            **_packet_defaults(),
        )

        subjects = {row["subject"] for row in active["graph_rows"]}
        duplicate_drops = [
            item
            for item in active["packet_budget"]["budget_decisions"]
            if item["reason_code"] == "dropped_budget_duplicate_lower_authority"
        ]

        assert subjects == {"Budget Graph Alpha", "Budget Graph Beta"}
        assert duplicate_drops == []
    finally:
        store.close()
