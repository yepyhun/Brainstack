from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import OPERATING_RECORD_ACTIVE_WORK


PRINCIPAL_SCOPE = "principal:candidate-contract"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _seed_cross_shelf_fixture(store: BrainstackStore) -> None:
    metadata = {"principal_scope_key": PRINCIPAL_SCOPE}
    store.upsert_profile_item(
        stable_key="preference:cobalt",
        category="preference",
        content="Cobalt memory candidate prefers precise traceable recall.",
        source="candidate.fixture",
        confidence=0.99,
        metadata=metadata,
    )
    store.add_continuity_event(
        session_id="candidate-prior-session",
        turn_number=1,
        kind="session_summary",
        content="Cobalt continuity says traceable candidate projection must stay shadow-only.",
        source="candidate.fixture",
        metadata={**metadata, "workstream_id": "candidate-contract"},
    )
    store.add_transcript_entry(
        session_id="candidate-session",
        turn_number=2,
        kind="user",
        content="Cobalt transcript asks for multilingual Árvíztűrő trace metadata.",
        source="candidate.fixture",
        metadata=metadata,
    )
    store.upsert_operating_record(
        stable_key="recent:cobalt",
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_ACTIVE_WORK,
        content="Cobalt operating state keeps current work separate from background evidence.",
        owner="user_project",
        source="candidate.fixture",
        metadata={
            **metadata,
            "authority_level": "canonical",
            "workstream_id": "candidate-contract",
            "source_kind": "explicit_operating_truth",
        },
    )
    store.upsert_graph_state(
        subject_name="Cobalt Kernel",
        attribute="contract",
        value_text="traceable retrieval candidate",
        source="candidate.fixture",
        metadata=metadata,
    )
    store.ingest_corpus_source(
        {
            "source_adapter": "candidate_fixture",
            "source_id": "cobalt-doc",
            "stable_key": "doc:candidate:cobalt",
            "title": "Cobalt Candidate Corpus",
            "doc_kind": "proof_note",
            "source_uri": "fixture://candidate/cobalt",
            "content": "Cobalt corpus section provides citation-backed candidate evidence.",
            "metadata": metadata,
        }
    )


def test_query_inspect_projects_selected_candidates_across_shelves(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_cross_shelf_fixture(store)

        report = build_query_inspect(
            store,
            query="Cobalt traceable candidate recall Árvíztűrő corpus graph operating",
            session_id="candidate-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            profile_match_limit=4,
            continuity_match_limit=4,
            continuity_recent_limit=4,
            transcript_match_limit=4,
            operating_match_limit=4,
            graph_limit=4,
            corpus_limit=4,
            evidence_item_budget=20,
        )

        trace = report["retrieval_candidates"]
        assert trace["schema"] == "brainstack.retrieval_candidate_trace.v1"
        assert trace["mode"] == "shadow_read_only"

        selected_by_shelf = {candidate["shelf"] for candidate in trace["selected"]}
        assert {"profile", "continuity_match", "transcript", "operating", "graph", "corpus"} <= selected_by_shelf
        assert "retrieval_candidates" not in report["final_packet"]["preview"]

        for candidate in trace["selected"]:
            assert candidate["schema"] == "brainstack.retrieval_candidate.v1"
            assert len(candidate["candidate_id"]) == 24
            assert candidate["candidate_id"].isalnum()
            assert candidate["selection"]["status"] == "selected"
            assert "donor_metadata" in candidate
            assert candidate["modality"] == {"primary": "text", "metadata_ready": True}

        graph = next(candidate for candidate in trace["selected"] if candidate["shelf"] == "graph")
        assert "graphiti" in graph["donor_metadata"]
        corpus = next(candidate for candidate in trace["selected"] if candidate["shelf"] == "corpus")
        assert "mempalace" in corpus["donor_metadata"]
        assert corpus["donor_metadata"]["mempalace"]["citation_id"] == "doc:candidate:cobalt#s0"
        continuity = next(candidate for candidate in trace["selected"] if candidate["shelf"] == "continuity_match")
        assert "hindsight" in continuity["donor_metadata"]
    finally:
        store.close()


def test_query_inspect_projects_bounded_suppressed_candidates_without_content_ids(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _seed_cross_shelf_fixture(store)
        secret_text = "private-token-should-not-enter-candidate-id"
        for index in range(6):
            store.add_continuity_event(
                session_id="candidate-session",
                turn_number=10 + index,
                kind="session_summary",
                content=f"Cobalt overflow suppressed candidate {index} {secret_text}",
                source="candidate.fixture",
                metadata={"principal_scope_key": PRINCIPAL_SCOPE},
            )

        report = build_query_inspect(
            store,
            query="Cobalt overflow suppressed candidate private-token",
            session_id="candidate-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_match_limit=1,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
            evidence_item_budget=1,
        )

        trace = report["retrieval_candidates"]
        assert trace["suppressed_count"] > 0
        assert trace["suppressed_count"] <= trace["suppressed_limit"]
        first = trace["suppressed"][0]
        assert first["selection"]["status"] == "suppressed"
        assert first["selection"]["reason"]
        assert secret_text not in first["candidate_id"]

        repeated = build_query_inspect(
            store,
            query="Cobalt overflow suppressed candidate private-token",
            session_id="candidate-session",
            principal_scope_key=PRINCIPAL_SCOPE,
            continuity_match_limit=1,
            continuity_recent_limit=0,
            transcript_match_limit=0,
            operating_match_limit=0,
            graph_limit=0,
            corpus_limit=0,
            evidence_item_budget=1,
        )
        assert repeated["retrieval_candidates"]["suppressed"][0]["candidate_id"] == first["candidate_id"]
    finally:
        store.close()


def test_recall_tool_does_not_expose_debug_candidate_trace(tmp_path: Path) -> None:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "candidate-session",
        platform="test",
        user_id="candidate-user",
        chat_id="candidate-chat",
        thread_id="candidate-thread",
    )
    try:
        assert provider._store is not None
        provider._store.upsert_profile_item(
            stable_key="preference:candidate-tool",
            category="preference",
            content="Candidate trace remains inspect-only.",
            source="candidate.fixture",
            confidence=0.99,
            metadata=provider._scoped_metadata(),
        )

        recall = json.loads(provider.handle_tool_call("brainstack_recall", {"query": "candidate trace inspect-only"}))
        inspect = json.loads(provider.handle_tool_call("brainstack_inspect", {"query": "candidate trace inspect-only"}))

        assert "retrieval_candidates" not in recall
        assert inspect["report"]["retrieval_candidates"]["selected_count"] >= 1
    finally:
        provider.shutdown()
