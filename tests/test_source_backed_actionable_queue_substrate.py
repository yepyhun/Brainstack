from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from brainstack.admission_policy import admit_claim
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind
from brainstack.db import BrainstackStore
from brainstack.proactive_agent_contract import build_proactive_status
from brainstack.storage.projection_writer import ProjectionWriter
from brainstack.task_memory import ITEM_TYPE_TASK, STATUS_OPEN


PRINCIPAL_SCOPE_KEY = "principal:phase269"
WORKSPACE_SCOPE_KEY = "workspace:phase269"
SESSION_ID = "session-phase269"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _proposal(
    *,
    claim_id: str,
    value: str,
    authority: SourceAuthority,
    speaker: AssertionSpeaker,
    span_kind: SpanKind,
) -> ClaimProposal:
    return ClaimProposal(
        claim_id=claim_id,
        proposal_type="task.actionable",
        source_event_id=f"event:{claim_id}",
        source_turn_id=f"{SESSION_ID}:1",
        source_span_id=f"span:{claim_id}",
        turn_role="user" if speaker == AssertionSpeaker.USER else "assistant",
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf="task",
        target_slot="task.actionable",
        target_scope=PRINCIPAL_SCOPE_KEY,
        storage_key=f"task:phase269:{claim_id}",
        subject="principal",
        predicate="task.actionable",
        surface_value=value,
        normalized_value=value,
        candidate_value=value,
        language="en",
        normalization_method="phase269_fixture",
        authority_class=authority,
        confidence=0.96,
        source_text_hash=f"sha256:{claim_id}",
        trace_id=f"trace:{claim_id}",
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE_KEY,
            "workspace_scope_key": WORKSPACE_SCOPE_KEY,
            "session_id": SESSION_ID,
            "donor_trace": {"donor": "hindsight-compatible", "adapter_version": "phase269.local"},
        },
    )


def _base_metadata(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "principal_scope_key": PRINCIPAL_SCOPE_KEY,
        "workspace_scope_key": WORKSPACE_SCOPE_KEY,
        "session_id": SESSION_ID,
        "current_assignment_authority": True,
        "current_assignment_authority_schema": "brainstack.current_assignment_authority.v1",
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _write_task(writer: ProjectionWriter, proposal: ClaimProposal) -> int:
    return writer.write_task(
        decision=admit_claim(proposal),
        principal_scope_key=PRINCIPAL_SCOPE_KEY,
        item_type=ITEM_TYPE_TASK,
        title=proposal.admitted_value,
        due_date="",
        date_scope="none",
        optional=False,
        status=STATUS_OPEN,
        owner="brainstack.task_memory",
        source="phase269:actionable_fixture",
        source_session_id=SESSION_ID,
        source_turn_number=1,
        metadata=_base_metadata(proposal.metadata),
    )


def _count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def test_source_backed_task_actionable_is_visible_in_proactive_status_without_outbox(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        writer = ProjectionWriter(store)
        proposal = _proposal(
            claim_id="source-backed-task",
            value="Review the release checklist before any release claim.",
            authority=SourceAuthority.USER_EXPLICIT_ASSIGNMENT,
            speaker=AssertionSpeaker.USER,
            span_kind=SpanKind.ASSERTION,
        )

        task_id = _write_task(writer, proposal)
        before = {
            "proactive_events": _count(store, "proactive_events"),
            "proactive_outbox": _count(store, "proactive_outbox"),
            "proactive_attention_ledger": _count(store, "proactive_attention_ledger"),
        }

        status = build_proactive_status(store=store, principal_scope_key=PRINCIPAL_SCOPE_KEY, config={})

        assert task_id > 0
        assert status["read_only"] is True
        assert status["side_effect"] is False
        substrate = status["counts"]["actionable_substrate"]
        assert substrate["pending_count"] == 1
        item = substrate["sampled_items"][0]
        assert item["source_event_id"] == "event:source-backed-task"
        assert item["source_span_id"] == "span:source-backed-task"
        assert item["receipt_id"]
        assert item["execution_payload_present"] is False
        assert item["current_assignment_authority"] is False
        assert status["counts"]["pending_outbox_count"] == 0
        after = {
            "proactive_events": _count(store, "proactive_events"),
            "proactive_outbox": _count(store, "proactive_outbox"),
            "proactive_attention_ledger": _count(store, "proactive_attention_ledger"),
        }
        assert after == before
    finally:
        store.close()


def test_support_only_action_candidate_records_rejection_but_not_actionable_substrate(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        writer = ProjectionWriter(store)
        rejected = _proposal(
            claim_id="ambiguous-tier2-task",
            value="Create proactive follow-up from ambiguous transcript context.",
            authority=SourceAuthority.TIER2_SUMMARY,
            speaker=AssertionSpeaker.UNKNOWN,
            span_kind=SpanKind.SUMMARY,
        )
        receipt_id = writer.record_decision(
            decision=admit_claim(rejected),
            metadata=_base_metadata(rejected.metadata),
        )

        status = build_proactive_status(store=store, principal_scope_key=PRINCIPAL_SCOPE_KEY, config={})

        assert receipt_id > 0
        assert store.list_task_items(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=10) == []
        assert status["counts"]["actionable_substrate"]["pending_count"] == 0
        assert status["counts"]["pending_outbox_count"] == 0
        assert _count(store, "proactive_events") == 0
        assert _count(store, "proactive_outbox") == 0
    finally:
        store.close()
