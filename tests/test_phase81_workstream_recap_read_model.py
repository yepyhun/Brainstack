from __future__ import annotations

from pathlib import Path

from brainstack.db import BrainstackStore
from brainstack.diagnostics import build_query_inspect
from brainstack.operating_truth import (
    OPERATING_OWNER,
    OPERATING_RECORD_RECENT_WORK_SUMMARY,
    RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
    recent_work_stable_key,
)


PRINCIPAL_SCOPE = "platform:test|user_id:user|agent_identity:agent-smoke|agent_workspace:workspace"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _add_scoped_recent_work(store: BrainstackStore, *, workstream_id: str, content: str) -> None:
    store.upsert_operating_record(
        stable_key=recent_work_stable_key(
            principal_scope_key=PRINCIPAL_SCOPE,
            workstream_id=workstream_id,
        ),
        principal_scope_key=PRINCIPAL_SCOPE,
        record_type=OPERATING_RECORD_RECENT_WORK_SUMMARY,
        content=content,
        owner=OPERATING_OWNER,
        source="phase81.proof",
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE,
            "workstream_id": workstream_id,
            "owner_role": RECENT_WORK_OWNER_AGENT_ASSIGNMENT,
        },
    )


def _add_unscoped_tier2_summary(store: BrainstackStore, *, content: str) -> None:
    store.add_continuity_event(
        session_id="old-session",
        turn_number=3,
        kind="tier2_summary",
        content=content,
        source="tier2:idle_window",
        metadata={"principal_scope_key": PRINCIPAL_SCOPE, "batch_reason": "idle_window"},
    )


def test_scoped_workstream_recap_selects_operating_anchor_before_broad_tier2_summary(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _add_scoped_recent_work(
            store,
            workstream_id="autonomous-income-research",
            content=(
                "Autonomous income research recap: viable company conditions require "
                "durable memory, an evolver loop, and bounded human approval gates."
            ),
        )
        _add_unscoped_tier2_summary(
            store,
            content=(
                "Autonomous income research and Brainstack development were both discussed "
                "with durable memory, evolver work, and backend health updates."
            ),
        )

        report = build_query_inspect(
            store,
            query="autonomous income research recap durable memory evolver conditions",
            session_id="new-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        operating = report["selected_evidence"]["operating"]
        assert operating
        assert operating[0]["workstream_id"] == "autonomous-income-research"
        assert operating[0]["recap_surface"] is True
        assert operating[0]["supporting_evidence_only"] is False
        assert operating[0]["workstream_recap_reason"] == "scoped_workstream_recap_anchor"
        assert any(
            item["suppression_reason"] == "supporting_only_unscoped_tier2_summary"
            and item["supporting_evidence_only"] is True
            for item in report["suppressed_evidence"]
        )
    finally:
        store.close()


def test_brainstack_workstream_recap_does_not_anchor_on_mixed_tier2_summary(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _add_scoped_recent_work(
            store,
            workstream_id="brainstack-development",
            content=(
                "Brainstack development recap: scoped recent-work authority, backend health, "
                "and query inspect proof are the active kernel work."
            ),
        )
        _add_unscoped_tier2_summary(
            store,
            content=(
                "Brainstack development and autonomous income research were mixed in one "
                "idle summary about backend health and company conditions."
            ),
        )

        report = build_query_inspect(
            store,
            query="backend health query inspect scoped recent work",
            session_id="new-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        operating = report["selected_evidence"]["operating"]
        assert operating
        assert operating[0]["workstream_id"] == "brainstack-development"
        assert "active kernel work" in operating[0]["excerpt"]
        selected_text = " ".join(
            item["excerpt"]
            for rows in report["selected_evidence"].values()
            for item in rows
        )
        assert "company conditions" not in selected_text
    finally:
        store.close()


def test_unscoped_tier2_summary_remains_supporting_evidence_when_no_scoped_anchor_exists(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        _add_unscoped_tier2_summary(
            store,
            content=(
                "Research recap mentioned durable memory, evolver work, approval gates, "
                "and broad project context without a scoped workstream."
            ),
        )

        report = build_query_inspect(
            store,
            query="research recap durable memory approval gates",
            session_id="new-session",
            principal_scope_key=PRINCIPAL_SCOPE,
        )

        continuity = report["selected_evidence"]["continuity_match"]
        assert continuity
        assert continuity[0]["supporting_evidence_only"] is True
        assert continuity[0]["workstream_recap_reason"] == "supporting_only_unscoped_tier2_summary"
        assert not report["selected_evidence"]["operating"]
    finally:
        store.close()

