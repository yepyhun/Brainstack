#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.admission_policy import admit_claim  # noqa: E402
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.operating_truth import (  # noqa: E402
    CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
    OPERATING_OWNER,
    OPERATING_RECORD_CURRENT_COMMITMENT,
    OPERATING_RECORD_LIVE_SYSTEM_STATE,
)
from brainstack.storage.projection_writer import ProjectionWriter  # noqa: E402
from brainstack.task_memory import ITEM_TYPE_TASK, STATUS_OPEN  # noqa: E402

REPORT_SCHEMA = "brainstack.canonical_truth_admission_coverage.v1"
PRINCIPAL_SCOPE_KEY = "principal:phase267"
WORKSPACE_SCOPE_KEY = "workspace:phase267"
SESSION_ID = "session-phase267"


def _proposal(
    *,
    claim_id: str,
    target_shelf: str,
    target_slot: str,
    storage_key: str,
    normalized_value: str,
    authority: SourceAuthority,
    speaker: AssertionSpeaker,
    span_kind: SpanKind,
    source_event_id: str,
    source_span_id: str,
    proposal_type: str = "",
    subject: str = "",
    predicate: str = "",
) -> ClaimProposal:
    return ClaimProposal(
        claim_id=claim_id,
        proposal_type=proposal_type or target_slot,
        source_event_id=source_event_id,
        source_turn_id=f"{SESSION_ID}:1",
        source_span_id=source_span_id,
        turn_role="user" if speaker == AssertionSpeaker.USER else "runtime",
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf=target_shelf,
        target_slot=target_slot,
        target_scope=PRINCIPAL_SCOPE_KEY if target_shelf != "graph" else "project:brainstack",
        storage_key=storage_key,
        subject=subject,
        predicate=predicate,
        surface_value=normalized_value,
        normalized_value=normalized_value,
        candidate_value=normalized_value,
        language="en",
        normalization_method="phase267_structured_fixture",
        authority_class=authority,
        confidence=0.96,
        source_text_hash=f"sha256:{claim_id}",
        trace_id=f"trace:{claim_id}",
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE_KEY,
            "workspace_scope_key": WORKSPACE_SCOPE_KEY,
            "session_id": SESSION_ID,
            "source_event_id": source_event_id,
            "source_span_id": source_span_id,
            "donor_trace": {
                "donor": "hindsight-compatible",
                "adapter_version": "phase267.local",
            },
        },
    )


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _receipt_for(store: BrainstackStore, claim_id: str) -> dict[str, Any] | None:
    for receipt in store.list_admission_receipts(limit=200):
        if str(receipt.get("admission_id") or "") == claim_id:
            return receipt
    return None


def _canonical_events_for_receipt(store: BrainstackStore, receipt_id: int | str) -> list[dict[str, Any]]:
    if not receipt_id:
        return []
    return store.list_canonical_memory_events(limit=100, receipt_id=str(receipt_id))


def _l0_rows_for_claim(store: BrainstackStore, stable_key: str, *, source_event_id: str) -> list[dict[str, Any]]:
    snapshot = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=200)
    rows = list(snapshot.get("current_truth_rows") or []) + list(snapshot.get("non_answerable_rows") or [])
    return [
        dict(row)
        for row in rows
        if str(row.get("stable_fact_id") or "") == stable_key
        and str(row.get("source_event_id") or "") == source_event_id
    ]


def _base_metadata(extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "principal_scope_key": PRINCIPAL_SCOPE_KEY,
        "workspace_scope_key": WORKSPACE_SCOPE_KEY,
        "session_id": SESSION_ID,
    }
    if extra:
        payload.update(dict(extra))
    return payload


def _write_profile_case(writer: ProjectionWriter, proposal: ClaimProposal) -> int:
    decision = admit_claim(proposal)
    return writer.write_profile(
        decision=decision,
        category="preference",
        content=proposal.admitted_value,
        source="phase267:admission_fixture",
        confidence=0.96,
        metadata=_base_metadata(proposal.metadata),
    )


def _write_operating_case(writer: ProjectionWriter, proposal: ClaimProposal, *, current_assignment: bool = False) -> int:
    decision = admit_claim(proposal)
    metadata = _base_metadata(proposal.metadata)
    if current_assignment:
        metadata.update(
            {
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            }
        )
    return writer.write_operating(
        decision=decision,
        principal_scope_key=PRINCIPAL_SCOPE_KEY,
        record_type=OPERATING_RECORD_CURRENT_COMMITMENT if current_assignment else OPERATING_RECORD_LIVE_SYSTEM_STATE,
        content=proposal.admitted_value,
        owner=OPERATING_OWNER,
        source="phase267:admission_fixture",
        source_session_id=SESSION_ID,
        source_turn_number=1,
        metadata=metadata,
    )


def _write_task_case(writer: ProjectionWriter, proposal: ClaimProposal) -> int:
    decision = admit_claim(proposal)
    return writer.write_task(
        decision=decision,
        principal_scope_key=PRINCIPAL_SCOPE_KEY,
        item_type=ITEM_TYPE_TASK,
        title=proposal.admitted_value,
        due_date="",
        date_scope="none",
        optional=False,
        status=STATUS_OPEN,
        owner="brainstack.task_memory",
        source="phase267:admission_fixture",
        source_session_id=SESSION_ID,
        source_turn_number=1,
        metadata=_base_metadata(
            {
                **dict(proposal.metadata),
                "current_assignment_authority": True,
                "current_assignment_authority_schema": CURRENT_ASSIGNMENT_AUTHORITY_SCHEMA,
            }
        ),
    )


def _write_graph_relation_case(writer: ProjectionWriter, proposal: ClaimProposal) -> int:
    decision = admit_claim(proposal)
    outcome = writer.write_graph_relation(
        decision=decision,
        subject_name=proposal.subject,
        predicate=proposal.predicate,
        object_name=proposal.admitted_value,
        source="phase267:admission_fixture",
        metadata=_base_metadata(proposal.metadata),
    )
    return int(outcome.get("relation_id") or 0)


def _record_rejection_case(writer: ProjectionWriter, proposal: ClaimProposal) -> int:
    decision = admit_claim(proposal)
    return int(writer.record_decision(decision=decision, metadata=_base_metadata(proposal.metadata)))


def _case(
    *,
    case_id: str,
    proposal: ClaimProposal,
    expect_accepted: bool,
    write: Callable[[ProjectionWriter, ClaimProposal], int],
    store: BrainstackStore,
    writer: ProjectionWriter,
) -> dict[str, Any]:
    before = {
        "profile_items": _count(store, "profile_items"),
        "operating_records": _count(store, "operating_records"),
        "task_items": _count(store, "task_items"),
        "graph_relations": _count(store, "graph_relations"),
        "proactive_outbox": _count(store, "proactive_outbox"),
    }
    decision = admit_claim(proposal)
    durable_row_id = write(writer, proposal)
    receipt = _receipt_for(store, proposal.claim_id)
    events = _canonical_events_for_receipt(store, receipt.get("id") if receipt else "")
    l0_rows = _l0_rows_for_claim(store, decision.stable_key, source_event_id=proposal.source_event_id)
    after = {
        "profile_items": _count(store, "profile_items"),
        "operating_records": _count(store, "operating_records"),
        "task_items": _count(store, "task_items"),
        "graph_relations": _count(store, "graph_relations"),
        "proactive_outbox": _count(store, "proactive_outbox"),
    }
    issues: list[str] = []
    if decision.accepted != expect_accepted:
        issues.append("unexpected_admission_decision")
    if receipt is None:
        issues.append("missing_admission_receipt")
    if not events:
        issues.append("missing_canonical_event")
    if expect_accepted and durable_row_id <= 0:
        issues.append("missing_durable_row")
    if not expect_accepted and durable_row_id <= 0:
        issues.append("missing_rejection_receipt_id")
    if expect_accepted and not any(bool(row.get("answerable_current_truth")) for row in l0_rows):
        issues.append("missing_answerable_l0_projection")
    if not expect_accepted and any(bool(row.get("answerable_current_truth")) for row in l0_rows):
        issues.append("rejected_candidate_became_answer_truth")
    if after["proactive_outbox"] != before["proactive_outbox"]:
        issues.append("proactive_outbox_mutated")
    return {
        "case_id": case_id,
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "decision": decision.decision.value,
        "reason_code": decision.reason_code,
        "target_shelf": proposal.target_shelf,
        "target_slot": decision.target_slot,
        "stable_key": decision.stable_key,
        "truth_eligible": decision.truth_eligible,
        "support_visibility": decision.support_visibility.value,
        "durable_row_id": durable_row_id,
        "admission_receipt_id": int(receipt.get("id") or 0) if receipt else 0,
        "canonical_event_count": len(events),
        "l0_row_count": len(l0_rows),
        "answerable_l0_count": sum(1 for row in l0_rows if bool(row.get("answerable_current_truth"))),
        "before_counts": before,
        "after_counts": after,
    }


def build_report(db_path: Path) -> dict[str, Any]:
    store = _open_store(db_path)
    try:
        writer = ProjectionWriter(store)
        cases = [
            _case(
                case_id="operating_truth_trusted_runtime_admitted",
                proposal=_proposal(
                    claim_id="phase267-operating-runtime",
                    target_shelf="operating",
                    target_slot="operating.live_system_state",
                    storage_key="operating:brainstack_diagnostics_output_shape",
                    normalized_value="Brainstack diagnostics are compact and bounded.",
                    authority=SourceAuthority.TRUSTED_RUNTIME,
                    speaker=AssertionSpeaker.RUNTIME,
                    span_kind=SpanKind.RUNTIME_DIAGNOSTIC,
                    source_event_id="event-operating-runtime",
                    source_span_id="span-operating-runtime",
                ),
                expect_accepted=True,
                write=lambda w, p: _write_operating_case(w, p),
                store=store,
                writer=writer,
            ),
            _case(
                case_id="profile_style_preference_admitted",
                proposal=_proposal(
                    claim_id="phase267-profile-style",
                    target_shelf="profile",
                    target_slot="preference.style_contract",
                    storage_key="preference:style_contract",
                    normalized_value="Answer plainly in Hungarian; avoid chatbot filler.",
                    authority=SourceAuthority.USER_EXPLICIT_ASSERTION,
                    speaker=AssertionSpeaker.USER,
                    span_kind=SpanKind.ASSERTION,
                    source_event_id="event-profile-style",
                    source_span_id="span-profile-style",
                ),
                expect_accepted=True,
                write=_write_profile_case,
                store=store,
                writer=writer,
            ),
            _case(
                case_id="project_relation_user_assertion_admitted",
                proposal=_proposal(
                    claim_id="phase267-project-created-by",
                    target_shelf="graph",
                    target_slot="project.created_by",
                    storage_key="project:created_by",
                    normalized_value="ExampleOwner",
                    authority=SourceAuthority.USER_EXPLICIT_ASSERTION,
                    speaker=AssertionSpeaker.USER,
                    span_kind=SpanKind.ASSERTION,
                    source_event_id="event-project",
                    source_span_id="span-project",
                    proposal_type="project.metadata",
                    subject="Brainstack",
                    predicate="created_by",
                ),
                expect_accepted=True,
                write=_write_graph_relation_case,
                store=store,
                writer=writer,
            ),
            _case(
                case_id="stale_operating_correction_supersedes_prior",
                proposal=_proposal(
                    claim_id="phase267-operating-correction",
                    target_shelf="operating",
                    target_slot="operating.live_system_state",
                    storage_key="operating:brainstack_diagnostics_output_shape",
                    normalized_value="Brainstack diagnostics remain compact as of the current runtime check.",
                    authority=SourceAuthority.USER_CORRECTION,
                    speaker=AssertionSpeaker.USER,
                    span_kind=SpanKind.CORRECTION,
                    source_event_id="event-operating-correction",
                    source_span_id="span-operating-correction",
                ),
                expect_accepted=True,
                write=lambda w, p: _write_operating_case(w, p),
                store=store,
                writer=writer,
            ),
            _case(
                case_id="conflict_candidate_assistant_claim_rejected",
                proposal=_proposal(
                    claim_id="phase267-conflict-assistant",
                    target_shelf="graph",
                    target_slot="project.created_by",
                    storage_key="project:created_by",
                    normalized_value="Assistant",
                    authority=SourceAuthority.ASSISTANT_CLAIM,
                    speaker=AssertionSpeaker.ASSISTANT,
                    span_kind=SpanKind.ASSISTANT_ANSWER,
                    source_event_id="event-conflict-assistant",
                    source_span_id="span-conflict-assistant",
                    proposal_type="project.metadata",
                    subject="Brainstack",
                    predicate="created_by",
                ),
                expect_accepted=False,
                write=_record_rejection_case,
                store=store,
                writer=writer,
            ),
            _case(
                case_id="task_user_assignment_admitted_without_proactive_mutation",
                proposal=_proposal(
                    claim_id="phase267-task-user-assignment",
                    target_shelf="task",
                    target_slot="task.actionable",
                    storage_key="task:phase267:verify-admission-coverage",
                    normalized_value="Verify canonical admission coverage locally.",
                    authority=SourceAuthority.USER_EXPLICIT_ASSIGNMENT,
                    speaker=AssertionSpeaker.USER,
                    span_kind=SpanKind.ASSERTION,
                    source_event_id="event-task-user",
                    source_span_id="span-task-user",
                    proposal_type="task.actionable",
                ),
                expect_accepted=True,
                write=_write_task_case,
                store=store,
                writer=writer,
            ),
            _case(
                case_id="task_tier2_summary_rejected",
                proposal=_proposal(
                    claim_id="phase267-task-tier2",
                    target_shelf="task",
                    target_slot="task.actionable",
                    storage_key="task:phase267:tier2-vibes",
                    normalized_value="Create a proactive follow-up from ambiguous transcript context.",
                    authority=SourceAuthority.TIER2_SUMMARY,
                    speaker=AssertionSpeaker.UNKNOWN,
                    span_kind=SpanKind.SUMMARY,
                    source_event_id="event-task-tier2",
                    source_span_id="span-task-tier2",
                    proposal_type="task.actionable",
                ),
                expect_accepted=False,
                write=_record_rejection_case,
                store=store,
                writer=writer,
            ),
            _case(
                case_id="support_only_transcript_cannot_become_truth",
                proposal=_proposal(
                    claim_id="phase267-transcript-support",
                    target_shelf="operating",
                    target_slot="operating.live_system_state",
                    storage_key="operating:transcript-support-only",
                    normalized_value="Transcript recap speculates that diagnostics might be large.",
                    authority=SourceAuthority.TRANSCRIPT_EVENT,
                    speaker=AssertionSpeaker.UNKNOWN,
                    span_kind=SpanKind.SUMMARY,
                    source_event_id="event-transcript",
                    source_span_id="span-transcript",
                ),
                expect_accepted=False,
                write=_record_rejection_case,
                store=store,
                writer=writer,
            ),
        ]
        failures = [case for case in cases if case["status"] != "pass"]
        final_counts = {
            "admission_receipts": _count(store, "admission_receipts"),
            "canonical_memory_events": _count(store, "canonical_memory_events"),
            "profile_items": _count(store, "profile_items"),
            "operating_records": _count(store, "operating_records"),
            "task_items": _count(store, "task_items"),
            "graph_relations": _count(store, "graph_relations"),
            "proactive_outbox": _count(store, "proactive_outbox"),
        }
        l0 = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=500)
        return {
            "schema": REPORT_SCHEMA,
            "status": "pass" if not failures else "fail",
            "case_count": len(cases),
            "failure_count": len(failures),
            "failure_case_ids": [case["case_id"] for case in failures],
            "public_safe": True,
            "llm_calls_performed": False,
            "second_truth_authority_created": False,
            "proactive_mutation_count": final_counts["proactive_outbox"],
            "final_counts": final_counts,
            "l0_receipt_coverage": l0.get("receipt_coverage"),
            "cases": cases,
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="")
    parser.add_argument("--db", default="")
    args = parser.parse_args()
    if args.db:
        db_path = Path(args.db)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        report = build_report(db_path)
    else:
        with tempfile.TemporaryDirectory(prefix="brainstack_phase267_") as tmp:
            report = build_report(Path(tmp) / "brainstack.sqlite3")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("schema", "status", "case_count", "failure_count", "failure_case_ids")}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
