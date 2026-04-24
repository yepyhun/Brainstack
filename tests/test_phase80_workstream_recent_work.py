from __future__ import annotations

from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import (
    OPERATING_OWNER,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    RECENT_WORK_AUTHORITY_BACKGROUND,
    RECENT_WORK_AUTHORITY_CANONICAL,
    RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
    recent_work_stable_key,
)


PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


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
        "phase80-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="phase80-session",
        turn_number=1,
        kind="turn",
        content="User: continue the assigned research.\nAssistant: acknowledged.",
        source="test",
        metadata=provider._scoped_metadata(),
    )
    return provider


def test_tier2_idle_recent_work_without_workstream_is_background_evidence(tmp_path: Path) -> None:
    def extractor(*args, **kwargs):
        return {
            "continuity_summary": (
                "Zero-human assignment and Brainstack development were both mentioned, "
                "but this idle-window summary has no explicit workstream scope."
            ),
            "_meta": {"json_parse_status": "ok", "parse_context": "test"},
        }

    provider = _provider(tmp_path, extractor)
    try:
        result = provider._run_tier2_batch(
            session_id="phase80-session",
            turn_number=1,
            trigger_reason="idle_window",
        )
        assert result["operating_promotions"]["recent_work_promoted"] is True
        assert provider._store is not None
        rows = provider._store.list_operating_records(
            principal_scope_key=provider._principal_scope_key,
            record_types=[OPERATING_RECORD_RECENT_WORK_SUMMARY],
            limit=4,
        )
        assert rows
        metadata = rows[0]["metadata"]
        assert metadata["authority_level"] == RECENT_WORK_AUTHORITY_BACKGROUND
        assert metadata["source_kind"] == "tier2_idle_window"
        assert "workstream_id" not in metadata
    finally:
        provider.shutdown()


def test_scoped_recent_work_beats_unscoped_idle_summary_for_same_principal(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key="operating_truth::test::recent_work_summary",
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content=(
                "Zero-human assignment and Brainstack development were mixed by an "
                "unscoped idle-window summary."
            ),
            owner=OPERATING_OWNER,
            source="tier2:idle_window:recent_work",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE, "batch_reason": "idle_window"},
        )
        store.upsert_operating_record(
            stable_key=recent_work_stable_key(
                principal_scope_key=PRINCIPAL_SCOPE,
                workstream_id="brainstack-development",
            ),
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content=(
                "Brainstack development status: Phase 80 scopes recent-work authority "
                "so project status does not merge with agent assignments."
            ),
            owner=OPERATING_OWNER,
            source="phase80.proof",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "workstream_id": "brainstack-development",
                "semantic_terms": ["Brainstack development recent work authority"],
            },
        )

        report = build_query_inspect(
            store,
            query="Brainstack zero-human recent work authority",
            session_id="phase80-query",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        selected_operating = report["selected_evidence"]["operating"]
        assert selected_operating
        assert selected_operating[0]["authority_level"] == RECENT_WORK_AUTHORITY_CANONICAL
        assert selected_operating[0]["workstream_id"] == "brainstack-development"
        assert "Phase 80 scopes recent-work authority" in selected_operating[0]["excerpt"]
        assert all("Zero-human assignment" not in item["excerpt"] for item in selected_operating)
        assert any(
            item["authority_level"] == RECENT_WORK_AUTHORITY_BACKGROUND
            and item["suppression_reason"].startswith("background_recent_work_summary")
            for item in report["suppressed_evidence"]
        )
    finally:
        store.close()

def test_agent_assignment_recent_work_can_be_scoped_and_retrieved(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        store.upsert_operating_record(
            stable_key=recent_work_stable_key(
                principal_scope_key=PRINCIPAL_SCOPE,
                workstream_id="zero-human-research",
            ),
            principal_scope_key=PRINCIPAL_SCOPE,
            record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
            content="Zero-human research assignment: evaluate autonomous income models and summarize viable paths.",
            owner=OPERATING_OWNER,
            source="phase80.proof",
            metadata={
                "principal_scope_key": PRINCIPAL_SCOPE,
                "workstream_id": "zero-human-research",
                "owner_role": RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
            },
        )

        report = build_query_inspect(
            store,
            query="zero human autonomous income research assignment",
            session_id="phase80-query",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        selected_operating = report["selected_evidence"]["operating"]
        assert selected_operating
        assert selected_operating[0]["workstream_id"] == "zero-human-research"
        assert "autonomous income models" in selected_operating[0]["excerpt"]
    finally:
        store.close()
