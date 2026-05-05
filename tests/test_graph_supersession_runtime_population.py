from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from brainstack.admission_policy import admit_claim
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind
from brainstack.current_truth_view import rebuild_current_truth_view
from brainstack.db import BrainstackStore
from brainstack.graphiti_projection import project_canonical_events_to_graphiti
from brainstack.storage.projection_writer import ProjectionWriter


PRINCIPAL_SCOPE_KEY = "principal:phase268"
WORKSPACE_SCOPE_KEY = "workspace:phase268"
SESSION_ID = "session-phase268"


def _open_store(tmp_path: Path) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _proposal(
    *,
    claim_id: str,
    value: str,
    authority: SourceAuthority = SourceAuthority.USER_EXPLICIT_ASSERTION,
    speaker: AssertionSpeaker = AssertionSpeaker.USER,
    span_kind: SpanKind = SpanKind.ASSERTION,
) -> ClaimProposal:
    return ClaimProposal(
        claim_id=claim_id,
        proposal_type="project.metadata",
        source_event_id=f"event:{claim_id}",
        source_turn_id=f"{SESSION_ID}:1",
        source_span_id=f"span:{claim_id}",
        turn_role="user" if speaker == AssertionSpeaker.USER else "assistant",
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf="graph",
        target_slot="project.created_by",
        target_scope="project:brainstack",
        storage_key="project:created_by",
        subject="Brainstack",
        predicate="created_by",
        surface_value=value,
        normalized_value=value,
        candidate_value=value,
        language="en",
        normalization_method="phase268_fixture",
        authority_class=authority,
        confidence=0.97,
        source_text_hash=f"sha256:{claim_id}",
        trace_id=f"trace:{claim_id}",
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE_KEY,
            "workspace_scope_key": WORKSPACE_SCOPE_KEY,
            "session_id": SESSION_ID,
            "donor_trace": {"donor": "graphiti-compatible", "adapter_version": "phase268.local"},
        },
    )


def _base_metadata(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "principal_scope_key": PRINCIPAL_SCOPE_KEY,
        "workspace_scope_key": WORKSPACE_SCOPE_KEY,
        "session_id": SESSION_ID,
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _write_graph_state(
    writer: ProjectionWriter,
    proposal: ClaimProposal,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return writer.write_graph_state(
        decision=admit_claim(proposal),
        subject_name=proposal.subject,
        attribute=proposal.predicate,
        value_text=proposal.admitted_value,
        source="phase268:graph_supersession_fixture",
        metadata=_base_metadata(metadata or proposal.metadata),
    )


def _events(store: BrainstackStore) -> list[dict[str, Any]]:
    return [row["event"] for row in store.list_canonical_memory_events(limit=50)]


def _event_id_for_claim(store: BrainstackStore, claim_id: str) -> str:
    for event in _events(store):
        if event["authority"]["admission_decision_id"] == claim_id:
            return str(event["event"]["event_id"])
    raise AssertionError(f"missing canonical event for {claim_id}")


def test_admitted_graph_supersession_marks_prior_current_and_supersession_rows(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        writer = ProjectionWriter(store)
        old = _proposal(claim_id="phase268-old-creator", value="Old support owner")
        new = _proposal(
            claim_id="phase268-new-creator",
            value="Laura",
            authority=SourceAuthority.USER_CORRECTION,
            span_kind=SpanKind.CORRECTION,
        )

        old_outcome = _write_graph_state(writer, old)
        old_event_id = _event_id_for_claim(store, old.claim_id)
        new_outcome = _write_graph_state(
            writer,
            new,
            metadata={**dict(new.metadata), "supersedes": [old_event_id]},
        )

        assert old_outcome["status"] == "inserted"
        assert new_outcome["status"] == "superseded"
        l0_snapshot = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=20)
        assert [row["event_id"] for row in l0_snapshot["current_truth_rows"]] == [_event_id_for_claim(store, new.claim_id)]
        assert [row["event_id"] for row in l0_snapshot["non_answerable_rows"]] == [old_event_id]
        assert l0_snapshot["non_answerable_rows"][0]["superseded_by"] == _event_id_for_claim(store, new.claim_id)

        supersession = store.conn.execute(
            """
            SELECT prior_state_id, new_state_id
            FROM graph_supersessions
            WHERE prior_state_id = ? AND new_state_id = ?
            """,
            (int(old_outcome["state_id"]), int(new_outcome["state_id"])),
        ).fetchone()
        assert supersession is not None

        projection = project_canonical_events_to_graphiti(_events(store))

        assert projection["status"] == "pass"
        assert [edge["event_id"] for edge in projection["current_edges"]] == [_event_id_for_claim(store, new.claim_id)]
        assert [edge["event_id"] for edge in projection["prior_edges"]] == [old_event_id]
        prior = projection["prior_edges"][0]
        current = projection["current_edges"][0]
        assert prior["answerable"] is False
        assert prior["current"] is False
        assert prior["superseded_by"] == current["event_id"]
        assert current["supersedes"] == [old_event_id]
        assert "projection_prior_superseded" in prior["projection_reason_codes"]
        assert prior["projection_semantics"]["is_prior"] is True
        assert current["projection_semantics"]["is_answer_safe"] is True

        view = rebuild_current_truth_view(_events(store), rebuilt_at="2026-05-05T00:00:00Z")
        assert view["status"] == "pass"
        assert [row["event_id"] for row in view["current_truth_rows"]] == [current["event_id"]]
        assert [row["event_id"] for row in view["non_answerable_rows"]] == [old_event_id]
        assert view["non_answerable_rows"][0]["answerable_current_truth"] is False
        assert "projection_prior_superseded" in view["non_answerable_rows"][0]["projection_reason_codes"]
    finally:
        store.close()


def test_rejected_conflict_candidate_is_inspectable_not_answer_truth(tmp_path: Path) -> None:
    store = _open_store(tmp_path)
    try:
        writer = ProjectionWriter(store)
        conflict = _proposal(
            claim_id="phase268-assistant-conflict",
            value="Assistant",
            authority=SourceAuthority.ASSISTANT_CLAIM,
            speaker=AssertionSpeaker.ASSISTANT,
            span_kind=SpanKind.ASSISTANT_ANSWER,
        )
        writer.record_decision(decision=admit_claim(conflict), metadata=_base_metadata(conflict.metadata))

        projection = project_canonical_events_to_graphiti(_events(store))

        assert projection["status"] == "pass"
        assert projection["current_edges"] == []
        assert projection["prior_edges"] == []
        assert len(projection["inspect_only_edges"]) == 1
        edge = projection["inspect_only_edges"][0]
        assert edge["answerable"] is False
        assert edge["conflicted"] is True
        assert "projection_contradiction_only" in edge["projection_reason_codes"]
    finally:
        store.close()
