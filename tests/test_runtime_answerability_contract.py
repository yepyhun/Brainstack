from __future__ import annotations

from pathlib import Path

from brainstack.answerability import build_memory_answerability
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA, OPERATING_RECORD_ACTIVE_WORK


PRINCIPAL_SCOPE = "principal:answerability"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def test_unsupported_query_with_accidental_overlap_is_not_answerable(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:example-user",
            category="identity",
            content="ExampleUser uses Brainstack as the memory kernel.",
            source="answerability.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="unsupported zeta omega no durable memory",
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=4,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        assert report["selected_evidence"]["profile"]
        answerability = report["memory_answerability"]
        assert answerability["can_answer"] is False
        assert answerability["reason_code"] == "ONLY_SUPPORTING_CONTEXT"
        assert answerability["answer_evidence_ids"] == []
        assert answerability["supporting_context_ids"] == ["profile:identity:example-user"]
        assert report["final_packet"]["answerable_evidence_count"] == 0
    finally:
        store.close()


def test_profile_preference_policy_keyword_match_is_supporting_only_for_memory_lookup(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="preference:memory_policy",
            category="preference",
            content="Requires evidence-based memory retrieval without guessing.",
            source="answerability.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )
        store.upsert_profile_item(
            stable_key="preference:strict_evidence_policy",
            category="preference",
            content="Do not guess if evidence is missing for memory truths.",
            source="answerability.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query=(
                "Kérdezek egy unsupported memory dolgot: zeta omega durable "
                "memory. Van erről rögzített memory truth? Ha nincs evidence, ne tippelj."
            ),
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=4,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        assert report["selected_evidence"]["profile"]
        answerability = report["memory_answerability"]
        assert answerability["can_answer"] is False
        assert answerability["reason_code"] == "ONLY_SUPPORTING_CONTEXT"
        assert answerability["answer_evidence_ids"] == []
        assert set(answerability["supporting_context_ids"]) == {
            "profile:preference:memory_policy",
            "profile:preference:strict_evidence_policy",
        }
        assert report["final_packet"]["answerable_evidence_count"] == 0
    finally:
        store.close()


def test_explicit_profile_fact_is_answerable_when_packet_contains_evidence(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_profile_item(
            stable_key="identity:example-user",
            category="identity",
            content="ExampleUser uses Brainstack as the memory kernel.",
            source="answerability.fixture",
            confidence=0.99,
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query="ExampleUser memory kernel",
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=4,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        answerability = report["memory_answerability"]
        assert answerability["can_answer"] is True
        assert answerability["max_claim_strength"] == "memory_truth"
        assert answerability["answer_type"] == "explicit_user_fact"
        assert answerability["answer_evidence_ids"] == ["profile:identity:example-user"]
        assert report["final_packet"]["memory_answerability"] == answerability
    finally:
        store.close()


def test_current_assignment_answerability_requires_typed_authority(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="operating:assignment:loose",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="Zero-human research is mentioned as active work but lacks typed authority.",
            owner="answerability.fixture",
            source="answerability.fixture",
            metadata={"owner_role": "agent_assignment", "source_kind": "explicit_operating_truth"},
        )

        loose = build_query_inspect(
            store,
            query="current assignment zero-human research",
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=4,
            graph_limit=0,
            corpus_limit=0,
        )

        assert loose["selected_evidence"]["operating"]
        assert loose["memory_answerability"]["can_answer"] is False
        assert loose["memory_answerability"]["answer_type"] == "current_assignment_absence"
        assert loose["memory_answerability"]["reason_code"] == "NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE"
        assert "current_assignment" in loose["memory_answerability"]["must_not_claim"]

        store.upsert_operating_record(
            stable_key="operating:assignment:typed",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_ACTIVE_WORK,
            content="Zero-human research is the typed current assignment.",
            owner="answerability.fixture",
            source="answerability.fixture",
            metadata={
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            },
        )

        typed = build_query_inspect(
            store,
            query="typed current assignment zero-human research",
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            continuity_match_limit=0,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=4,
            graph_limit=0,
            corpus_limit=0,
        )

        assert typed["memory_answerability"]["can_answer"] is True
        assert typed["memory_answerability"]["answer_type"] == "current_assignment"
        assert typed["memory_answerability"]["can_claim_current_assignment"] is True
    finally:
        store.close()


def test_assignment_question_does_not_promote_continuity_event_to_answer(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.add_continuity_event(
            session_id="answerability-session",
            turn_number=1,
            kind="event",
            content="Earlier conversation mentioned Brainstack Pulse and workstream planning.",
            source="answerability.fixture",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE},
        )

        report = build_query_inspect(
            store,
            query=(
                "If no explicit assigned workstream is recorded, can old session "
                "transcripts or Graph Truth decide what I am working on now?"
            ),
            session_id="answerability-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=0,
            continuity_match_limit=4,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
        )

        assert report["selected_evidence"]["continuity_match"]
        answerability = report["memory_answerability"]
        assert answerability["can_answer"] is False
        assert answerability["answer_type"] == "current_assignment_absence"
        assert answerability["reason_code"] == "NO_TYPED_CURRENT_ASSIGNMENT_EVIDENCE"
        assert answerability["answer_evidence_ids"] == []
        assert answerability["supporting_context_ids"] == ["continuity_match:1"]
        assert "current_assignment" in answerability["must_not_claim"]
    finally:
        store.close()


def test_packet_answerability_rejects_trace_evidence_missing_from_packet() -> None:
    selected = {
        "profile": [
            {
                "evidence_key": "profile:identity:example-user",
                "shelf": "profile",
                "excerpt": "ExampleUser uses Brainstack as the memory kernel.",
                "query_token_overlap": 3,
                "query_token_count": 3,
            }
        ]
    }

    answerability = build_memory_answerability(
        query="ExampleUser memory kernel",
        analysis={},
        selected_by_shelf=selected,
        packet_text="## Empty Packet\nNo answer evidence rendered.",
    )

    assert answerability["can_answer"] is False
    assert answerability["reason_code"] == "PACKET_SUPPRESSED"
    assert answerability["answer_evidence_ids"] == []
