from __future__ import annotations

from pathlib import Path

from brainstack.authority_policy import classify_evidence_authority
from brainstack.db import BrainstackStore
from brainstack.reconciler import reconcile_tier2_candidates


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_tier2_identity_uses_typed_handle_and_preferred_name_slots(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=3,
            source="tier2:test",
            metadata={"source_role": "user"},
            extracted={
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:platform_handle",
                        "content": "ExampleHandle",
                        "confidence": 0.9,
                    },
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": "Alex",
                        "confidence": 0.96,
                    },
                    {
                        "category": "identity",
                        "slot": "identity:name",
                        "content": "ExampleHandle",
                        "confidence": 0.7,
                    },
                ],
            },
        )

        assert store.get_profile_item(stable_key="identity:platform_handle")["content"] == "ExampleHandle"
        preferred = store.get_profile_item(stable_key="identity:preferred_address_name")
        assert preferred["content"] == "Alex"
        assert preferred["metadata"]["admission"]["truth_eligible"] is True
        assert store.get_profile_item(stable_key="identity:name") is None
        assert any(action.get("reason_code") == "GENERIC_IDENTITY_NAME_REJECTED" for action in result["actions"])
        receipts = store.list_admission_receipts(limit=10)
        assert {row["decision"] for row in receipts} >= {"ACCEPT_WITH_SUPERSESSION", "QUARANTINE_PROPOSAL"}
    finally:
        store.close()


def test_assistant_creator_claim_is_not_durable_graph_truth_but_user_correction_is(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        rejected = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=4,
            source="tier2:test",
            extracted={
                "relations": [
                    {
                        "subject": "Brainstack",
                        "predicate": "created_by",
                        "object": "StepFun",
                        "metadata": {"assertion_speaker": "assistant", "span_kind": "assistant_answer"},
                        "confidence": 0.9,
                    }
                ]
            },
        )
        accepted = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=5,
            source="tier2:test",
            metadata={"assertion_speaker": "user", "span_kind": "correction"},
            extracted={
                "relations": [
                    {
                        "subject": "Brainstack",
                        "predicate": "created_by",
                        "object": "Alex",
                        "confidence": 0.95,
                    }
                ]
            },
        )

        rows = store.conn.execute(
            """
            SELECT s.canonical_name AS subject, r.predicate, r.object_text
            FROM graph_relations r
            JOIN graph_entities s ON s.id = r.subject_entity_id
            WHERE r.active = 1
            ORDER BY r.id
            """
        ).fetchall()
        assert [(row["subject"], row["predicate"], row["object_text"]) for row in rows] == [
            ("Brainstack", "created_by", "Alex")
        ]
        assert any(action["action"] == "MARK_CORRECTED_FALSE_EVENT" for action in rejected["actions"])
        assert any(action["action"] == "ADD" for action in accepted["actions"])
    finally:
        store.close()


def test_project_metadata_state_uses_canonical_admission_slot_for_permit(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=7,
            source="tier2:test",
            metadata={"assertion_speaker": "user", "span_kind": "assertion"},
            extracted={
                "states": [
                    {
                        "subject": "Brainstack",
                        "attribute": "created_by",
                        "value": "Alex",
                        "confidence": 0.95,
                    }
                ]
            },
        )

        rows = store.list_current_graph_states(limit=10)
        assert any(row["subject"] == "Brainstack" and row["predicate"] == "created_by" for row in rows)
        assert any(action["action"] == "ADD" for action in result["actions"])
        receipts = store.list_admission_receipts(limit=10)
        assert any(row["target_slot"] == "project.created_by" for row in receipts)
    finally:
        store.close()


def test_tier2_project_creator_without_user_span_does_not_create_graph_conflict(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        first = store.upsert_graph_state(
            subject_name="Brainstack",
            attribute="created_by",
            value_text="User",
            source="tier2:idle_window",
            metadata={"principal_scope_key": "principal:graph-conflict-regression"},
        )
        second = store.upsert_graph_state(
            subject_name="Brainstack",
            attribute="created_by",
            value_text="Alex",
            source="tier2:final_output_validation",
            metadata={"principal_scope_key": "principal:graph-conflict-regression"},
        )
        empty_source = store.upsert_graph_state(
            subject_name="Brainstack",
            attribute="created_by",
            value_text="Casey",
            source="",
            metadata={"principal_scope_key": "principal:graph-conflict-regression"},
        )

        assert first["status"] == "admission_rejected"
        assert second["status"] == "admission_rejected"
        assert empty_source["status"] == "admission_rejected"
        assert store.list_current_graph_states(limit=10) == []
        assert store.list_graph_conflicts(limit=10) == []
    finally:
        store.close()


def test_profile_identity_is_not_project_creator_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=8,
            source="tier2:native_profile_mirror",
            metadata={
                "source_role": "user",
                "source_authority": "tier2_summary",
                "provenance": {"origin": "native_profile_mirror"},
            },
            extracted={
                "states": [
                    {
                        "subject": "Brainstack",
                        "attribute": "created_by",
                        "value": "Casey",
                        "confidence": 0.94,
                    }
                ]
            },
        )

        assert result["actions"][0]["action"] == "QUARANTINE_PROPOSAL"
        assert store.list_current_graph_states(limit=10) == []
        assert store.list_graph_conflicts(limit=10) == []
    finally:
        store.close()


def test_runtime_capability_claim_is_quarantined_from_graph_truth(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        result = reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=6,
            source="tier2:test",
            extracted={
                "states": [
                    {
                        "subject": "Assistant",
                        "attribute": "shell_access",
                        "value": "available",
                        "metadata": {"assertion_speaker": "runtime", "span_kind": "runtime_diagnostic"},
                    }
                ]
            },
        )
        rows = store.list_current_graph_states(limit=10)
        assert rows == []
        assert result["actions"][0]["reason_code"] == "RUNTIME_CAPABILITY_NOT_MEMORY_TRUTH"
        assert store.list_admission_receipts(limit=1)[0]["support_visibility"] == "inspect_only"
    finally:
        store.close()


def test_style_preference_becomes_typed_truth_eligible_profile_slot(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        reconcile_tier2_candidates(
            store,
            session_id="s1",
            turn_number=7,
            source="tier2:test",
            metadata={"assertion_speaker": "user"},
            extracted={
                "profile_items": [
                    {
                        "category": "preference",
                        "slot": "preference:formatting",
                        "content": "Avoid emoji and em dash.",
                        "confidence": 0.92,
                    }
                ]
            },
        )
        item = store.get_profile_item(stable_key="preference:formatting")
        assert item["content"] == "Avoid emoji and em dash."
        assert item["metadata"]["admission"]["truth_eligible"] is True
        assert item["metadata"]["admission"]["target_slot"] == "preference.formatting"
    finally:
        store.close()


def test_authority_policy_blocks_non_truth_eligible_admission_evidence() -> None:
    result = classify_evidence_authority(
        {
            "evidence_key": "graph:1",
            "shelf": "graph",
            "content": "Assistant has shell access",
            "metadata": {
                "admission": {
                    "truth_eligible": False,
                    "support_visibility": "inspect_only",
                    "decision": "QUARANTINE_PROPOSAL",
                }
            },
            "_brainstack_query_token_overlap": 4,
            "_brainstack_query_token_count": 4,
        }
    )
    assert result["answer_authority"] is False
    assert result["max_claim_strength"] == "none"
    assert result["reason_code"] == "ADMISSION_NOT_TRUTH_ELIGIBLE"
