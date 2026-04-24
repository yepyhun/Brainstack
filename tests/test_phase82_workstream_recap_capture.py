from __future__ import annotations

import json
from pathlib import Path

from brainstack import BrainstackMemoryProvider
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import (
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    RECENT_WORK_AUTHORITY_CANONICAL,
    recent_work_stable_key,
)


PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _provider(tmp_path: Path) -> BrainstackMemoryProvider:
    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
        }
    )
    provider.initialize(
        "phase82-session",
        platform="test",
        user_id="user",
        agent_identity="agent-smoke",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    return provider


def _write_recap(provider: BrainstackMemoryProvider, *, workstream_id: str, summary: str) -> dict:
    return json.loads(
        provider.handle_tool_call(
            "brainstack_workstream_recap",
            {
                "workstream_id": workstream_id,
                "summary": summary,
                "source_role": "operator",
                "owner_role": "agent_assignment",
                "source_kind": "explicit_operating_truth",
                "source": "phase82.proof",
            },
        )
    )


def test_scoped_workstream_recap_tool_creates_idempotent_recent_work_anchor(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        first = _write_recap(
            provider,
            workstream_id="autonomous-income-research",
            summary="Autonomous income recap: durable memory, evolver loop, and approval gates are required.",
        )
        second = _write_recap(
            provider,
            workstream_id="autonomous-income-research",
            summary="Autonomous income recap: durable memory, evolver loop, and approval gates are required.",
        )

        assert first["status"] == "committed"
        assert second["status"] == "committed"
        assert first["stable_key"] == second["stable_key"]
        assert first["stable_key"] == recent_work_stable_key(
            principal_scope_key=PRINCIPAL_SCOPE,
            workstream_id="autonomous-income-research",
        )
        assert provider._store is not None
        rows = provider._store.list_operating_records(
            principal_scope_key=PRINCIPAL_SCOPE,
            record_types=[OPERATING_RECORD_RECENT_WORK_SUMMARY],
            limit=8,
        )
        assert len(rows) == 1
        assert rows[0]["metadata"]["workstream_id"] == "autonomous-income-research"
        assert rows[0]["metadata"]["authority_level"] == RECENT_WORK_AUTHORITY_CANONICAL
    finally:
        provider.shutdown()


def test_workstream_recap_tool_rejects_missing_workstream_scope(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        receipt = _write_recap(
            provider,
            workstream_id="",
            summary="This summary has no typed workstream scope.",
        )
        assert receipt["status"] == "rejected"
        assert receipt["errors"][0]["code"] == "missing_workstream_id"
        assert provider._store is not None
        rows = provider._store.list_operating_records(
            principal_scope_key=PRINCIPAL_SCOPE,
            record_types=[OPERATING_RECORD_RECENT_WORK_SUMMARY],
            limit=8,
        )
        assert rows == []
    finally:
        provider.shutdown()


def test_scoped_recap_write_changes_query_inspect_from_missing_anchor_to_anchor(tmp_path: Path) -> None:
    provider = _provider(tmp_path)
    try:
        assert provider._store is not None
        provider._store.add_continuity_event(
            session_id="old-session",
            turn_number=1,
            kind="tier2_summary",
            content=(
                "Autonomous income and Brainstack development were mixed in broad continuity "
                "without an explicit workstream anchor."
            ),
            source="tier2:idle_window",
            metadata={"principal_scope_key": PRINCIPAL_SCOPE, "batch_reason": "idle_window"},
        )
        before = build_query_inspect(
            provider._store,
            query="autonomous income durable memory evolver approval gates",
            session_id="phase82-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )
        assert not any(
            item["recap_surface"]
            for item in before["selected_evidence"]["operating"]
        )

        receipt = _write_recap(
            provider,
            workstream_id="autonomous-income-research",
            summary=(
                "Autonomous income recap: durable memory, evolver loop, and approval gates "
                "are the active workstream conditions."
            ),
        )
        assert receipt["status"] == "committed"
        after = build_query_inspect(
            provider._store,
            query="autonomous income durable memory evolver approval gates",
            session_id="phase82-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )
        operating = after["selected_evidence"]["operating"]
        assert operating
        assert operating[0]["workstream_id"] == "autonomous-income-research"
        assert operating[0]["recap_surface"] is True
        assert any(
            item["suppression_reason"] == "supporting_only_unscoped_tier2_summary"
            for item in after["suppressed_evidence"]
        )
    finally:
        provider.shutdown()

