#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.admission_policy import admit_claim  # noqa: E402
from brainstack.canonical_memory_event import canonical_event_from_admission_decision  # noqa: E402
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind  # noqa: E402
from brainstack.current_truth_view import rebuild_current_truth_view  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.operating_truth import OPERATING_OWNER, OPERATING_RECORD_LIVE_SYSTEM_STATE  # noqa: E402
from brainstack.projection_conformance import build_projection_conformance_report  # noqa: E402
from brainstack.projection_inspect import build_projection_inspect_report  # noqa: E402
from brainstack.storage.projection_writer import ProjectionWriter  # noqa: E402
from brainstack.storage.store_runtime import utc_now_iso  # noqa: E402

REPORT_SCHEMA = "brainstack.admission_final_state_destructive_proof.v1"
PRINCIPAL_SCOPE_KEY = "principal:phase276_3"
WORKSPACE_SCOPE_KEY = "workspace:phase276_3"
SESSION_ID = "session-phase276_3"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _proposal(
    *,
    claim_id: str,
    storage_key: str,
    normalized_value: str,
    authority: SourceAuthority,
    speaker: AssertionSpeaker,
    span_kind: SpanKind,
    source_event_id: str,
    source_span_id: str,
    target_slot: str = "operating.live_system_state",
) -> ClaimProposal:
    return ClaimProposal(
        claim_id=claim_id,
        proposal_type=target_slot,
        source_event_id=source_event_id,
        source_turn_id=f"{SESSION_ID}:1",
        source_span_id=source_span_id,
        turn_role="user" if speaker == AssertionSpeaker.USER else "runtime",
        assertion_speaker=speaker,
        span_kind=span_kind,
        target_shelf="operating",
        target_slot=target_slot,
        target_scope=PRINCIPAL_SCOPE_KEY,
        storage_key=storage_key,
        subject="brainstack",
        predicate=target_slot,
        surface_value=normalized_value,
        normalized_value=normalized_value,
        candidate_value=normalized_value,
        language="en",
        normalization_method="phase276_3_public_fixture",
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
                "adapter_version": "phase276_3.local",
            },
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


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _receipt_for(store: BrainstackStore, claim_id: str) -> dict[str, Any] | None:
    for receipt in store.list_admission_receipts(limit=500):
        if _text(receipt.get("admission_id")) == claim_id:
            return receipt
    return None


def _events_for_receipt(store: BrainstackStore, receipt_id: int | str) -> list[dict[str, Any]]:
    if not receipt_id:
        return []
    return store.list_canonical_memory_events(limit=100, receipt_id=str(receipt_id))


def _canonical_events(store: BrainstackStore) -> list[dict[str, Any]]:
    rows = store.list_canonical_memory_events(limit=500)
    events = [dict(row.get("event") or {}) for row in rows if isinstance(row.get("event"), Mapping)]
    return list(reversed(events))


def _event_id(event: Mapping[str, Any]) -> str:
    return _text(_mapping(event.get("event")).get("event_id"))


def _source_event_id(event: Mapping[str, Any]) -> str:
    return _text(_mapping(event.get("source")).get("source_event_id"))


def _write_operating(
    writer: ProjectionWriter,
    proposal: ClaimProposal,
    *,
    metadata_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    decision = admit_claim(proposal)
    metadata = _base_metadata({**dict(proposal.metadata), **dict(metadata_extra or {})})
    row_id = writer.write_operating(
        decision=decision,
        principal_scope_key=PRINCIPAL_SCOPE_KEY,
        record_type=OPERATING_RECORD_LIVE_SYSTEM_STATE,
        content=proposal.admitted_value,
        owner=OPERATING_OWNER,
        source="phase276_3:admission_final_state_fixture",
        source_session_id=SESSION_ID,
        source_turn_number=1,
        metadata=metadata,
    )
    return _write_result(writer.store, proposal, decision=decision, durable_row_id=row_id)


def _record_rejection(writer: ProjectionWriter, proposal: ClaimProposal) -> dict[str, Any]:
    decision = admit_claim(proposal)
    receipt_id = writer.record_decision(decision=decision, metadata=_base_metadata(proposal.metadata))
    return _write_result(writer.store, proposal, decision=decision, durable_row_id=receipt_id)


def _record_missing_receipt_event(store: BrainstackStore, proposal: ClaimProposal) -> dict[str, Any]:
    decision = admit_claim(proposal)
    event = canonical_event_from_admission_decision(
        decision=decision,
        receipt_id=0,
        durable_row_id=0,
        metadata=_base_metadata(proposal.metadata),
        observed_at=utc_now_iso(),
    )
    store.record_canonical_memory_event(event)
    return {
        "claim_id": proposal.claim_id,
        "decision": decision.decision.value,
        "reason_code": decision.reason_code,
        "stable_key": decision.stable_key,
        "truth_eligible": decision.truth_eligible,
        "support_visibility": decision.support_visibility.value,
        "durable_row_id": 0,
        "admission_receipt_id": 0,
        "canonical_event_ids": [_event_id(event)],
        "source_event_id": proposal.source_event_id,
    }


def _write_result(
    store: BrainstackStore,
    proposal: ClaimProposal,
    *,
    decision: Any,
    durable_row_id: int,
) -> dict[str, Any]:
    receipt = _receipt_for(store, proposal.claim_id)
    events = _events_for_receipt(store, receipt.get("id") if receipt else "")
    return {
        "claim_id": proposal.claim_id,
        "decision": decision.decision.value,
        "reason_code": decision.reason_code,
        "stable_key": decision.stable_key,
        "truth_eligible": decision.truth_eligible,
        "support_visibility": decision.support_visibility.value,
        "durable_row_id": int(durable_row_id or 0),
        "admission_receipt_id": int(receipt.get("id") or 0) if receipt else 0,
        "canonical_event_ids": [_event_id(row.get("event") or {}) for row in events],
        "source_event_id": proposal.source_event_id,
    }


def _snapshot_rows(store: BrainstackStore) -> list[dict[str, Any]]:
    snapshot = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=500)
    return [dict(row) for row in (snapshot.get("current_truth_rows") or [])] + [
        dict(row) for row in (snapshot.get("non_answerable_rows") or [])
    ]


def _row_for_event_id(store: BrainstackStore, event_id: str) -> dict[str, Any]:
    for row in _snapshot_rows(store):
        if _text(row.get("event_id")) == event_id:
            return row
    return {}


def _rows_for_stable_key(store: BrainstackStore, stable_key: str) -> list[dict[str, Any]]:
    return [row for row in _snapshot_rows(store) if _text(row.get("stable_fact_id")) == stable_key]


def _answerable_event_ids(store: BrainstackStore, stable_key: str) -> list[str]:
    return [
        _text(row.get("event_id"))
        for row in _rows_for_stable_key(store, stable_key)
        if bool(row.get("answerable_current_truth"))
    ]


def _case_status(case_id: str, checks: Mapping[str, bool]) -> dict[str, Any]:
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "case_id": case_id,
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": dict(checks),
    }


def build_report(db_path: Path) -> dict[str, Any]:
    store = _open_store(db_path)
    try:
        writer = ProjectionWriter(store)
        cases: list[dict[str, Any]] = []

        old_support = _record_rejection(
            writer,
            _proposal(
                claim_id="phase276_3-old-support-diagnostics",
                storage_key="operating:diagnostics_output_shape",
                normalized_value="Earlier support evidence suggested diagnostics were large.",
                authority=SourceAuthority.TRANSCRIPT_EVENT,
                speaker=AssertionSpeaker.UNKNOWN,
                span_kind=SpanKind.SUMMARY,
                source_event_id="phase276_3-source-old-support",
                source_span_id="phase276_3-span-old-support",
            ),
        )
        old_support_event = old_support["canonical_event_ids"][0]
        old_support_row = _row_for_event_id(store, old_support_event)
        cases.append(
            _case_status(
                "receipt_backed_support_only_cannot_answer",
                {
                    "receipt_exists": old_support["admission_receipt_id"] > 0,
                    "canonical_event_exists": bool(old_support_event),
                    "final_state_non_answerable": bool(old_support_row) and not bool(old_support_row.get("answerable_current_truth")),
                    "final_state_not_answer_evidence": _text(old_support_row.get("support_visibility")) != "answer_evidence",
                },
            )
        )

        new_truth = _write_operating(
            writer,
            _proposal(
                claim_id="phase276_3-new-diagnostics-truth",
                storage_key="operating:diagnostics_output_shape",
                normalized_value="Current diagnostics are compact and bounded.",
                authority=SourceAuthority.TRUSTED_RUNTIME,
                speaker=AssertionSpeaker.RUNTIME,
                span_kind=SpanKind.RUNTIME_DIAGNOSTIC,
                source_event_id="phase276_3-source-new-truth",
                source_span_id="phase276_3-span-new-truth",
            ),
        )
        new_truth_event = new_truth["canonical_event_ids"][0]
        new_truth_row = _row_for_event_id(store, new_truth_event)
        cases.append(
            _case_status(
                "new_admitted_truth_is_final_answerable_state",
                {
                    "receipt_exists": new_truth["admission_receipt_id"] > 0,
                    "canonical_event_exists": bool(new_truth_event),
                    "final_state_answerable": bool(new_truth_row.get("answerable_current_truth")),
                    "old_support_stays_non_answerable": not bool(_row_for_event_id(store, old_support_event).get("answerable_current_truth")),
                    "single_answerable_for_stable_key": _answerable_event_ids(store, new_truth["stable_key"]) == [new_truth_event],
                },
            )
        )

        later_rejected = _record_rejection(
            writer,
            _proposal(
                claim_id="phase276_3-later-rejected-diagnostics",
                storage_key="operating:diagnostics_output_shape",
                normalized_value="A later assistant answer guessed diagnostics were large again.",
                authority=SourceAuthority.ASSISTANT_CLAIM,
                speaker=AssertionSpeaker.ASSISTANT,
                span_kind=SpanKind.ASSISTANT_ANSWER,
                source_event_id="phase276_3-source-later-rejected",
                source_span_id="phase276_3-span-later-rejected",
            ),
        )
        later_rejected_event = later_rejected["canonical_event_ids"][0]
        cases.append(
            _case_status(
                "later_rejected_receipt_cannot_override_current_truth",
                {
                    "receipt_exists": later_rejected["admission_receipt_id"] > 0,
                    "rejected_final_state_non_answerable": not bool(
                        _row_for_event_id(store, later_rejected_event).get("answerable_current_truth")
                    ),
                    "current_truth_still_new_admitted_event": _answerable_event_ids(store, new_truth["stable_key"])
                    == [new_truth_event],
                    "no_newer_wins_shortcut": later_rejected_event not in _answerable_event_ids(store, later_rejected["stable_key"]),
                },
            )
        )

        old_explicit = _write_operating(
            writer,
            _proposal(
                claim_id="phase276_3-old-explicit-operating",
                storage_key="operating:active_runtime_fact",
                normalized_value="The older runtime state was active.",
                authority=SourceAuthority.USER_EXPLICIT_ASSERTION,
                speaker=AssertionSpeaker.USER,
                span_kind=SpanKind.ASSERTION,
                source_event_id="phase276_3-source-old-explicit",
                source_span_id="phase276_3-span-old-explicit",
            ),
        )
        old_explicit_event = old_explicit["canonical_event_ids"][0]
        new_superseding = _write_operating(
            writer,
            _proposal(
                claim_id="phase276_3-new-explicit-operating",
                storage_key="operating:active_runtime_fact",
                normalized_value="The newer runtime state is active.",
                authority=SourceAuthority.USER_CORRECTION,
                speaker=AssertionSpeaker.USER,
                span_kind=SpanKind.CORRECTION,
                source_event_id="phase276_3-source-new-explicit",
                source_span_id="phase276_3-span-new-explicit",
            ),
            metadata_extra={"supersedes": [old_explicit_event]},
        )
        new_superseding_event = new_superseding["canonical_event_ids"][0]
        old_explicit_row = _row_for_event_id(store, old_explicit_event)
        new_superseding_row = _row_for_event_id(store, new_superseding_event)
        cases.append(
            _case_status(
                "explicit_supersession_changes_final_state",
                {
                    "old_prior_non_answerable": bool(old_explicit_row)
                    and bool(old_explicit_row.get("is_prior"))
                    and not bool(old_explicit_row.get("answerable_current_truth")),
                    "old_points_to_new": _text(old_explicit_row.get("superseded_by")) == new_superseding_event,
                    "new_answerable": bool(new_superseding_row.get("answerable_current_truth")),
                    "prior_reason_present": "projection_prior_superseded"
                    in [str(reason) for reason in old_explicit_row.get("projection_reason_codes") or []],
                },
            )
        )

        missing_receipt = _record_missing_receipt_event(
            store,
            _proposal(
                claim_id="phase276_3-missing-receipt-event",
                storage_key="operating:receiptless_truth_candidate",
                normalized_value="This event has answer-looking authority but no receipt.",
                authority=SourceAuthority.USER_EXPLICIT_ASSERTION,
                speaker=AssertionSpeaker.USER,
                span_kind=SpanKind.ASSERTION,
                source_event_id="phase276_3-source-missing-receipt",
                source_span_id="phase276_3-span-missing-receipt",
            ),
        )
        missing_receipt_event = missing_receipt["canonical_event_ids"][0]
        missing_receipt_row = _row_for_event_id(store, missing_receipt_event)
        cases.append(
            _case_status(
                "answer_looking_event_without_receipt_cannot_answer",
                {
                    "canonical_event_exists": bool(missing_receipt_event),
                    "no_receipt_record": missing_receipt["admission_receipt_id"] == 0,
                    "final_state_non_answerable": not bool(missing_receipt_row.get("answerable_current_truth")),
                    "missing_receipt_reason_present": "projection_missing_receipt_ref"
                    in [str(reason) for reason in missing_receipt_row.get("projection_reason_codes") or []],
                },
            )
        )

        events = _canonical_events(store)
        rebuilt = rebuild_current_truth_view(events, rebuilt_at="2026-05-06T00:00:00Z", checked_at="2026-05-06T00:00:00Z")
        parity = store.compare_current_truth_l0_to_rebuild(limit=500, checked_at="2026-05-06T00:00:00Z")
        conformance_events = [
            event
            for event in events
            if _source_event_id(event)
            in {
                old_support["source_event_id"],
                new_truth["source_event_id"],
                later_rejected["source_event_id"],
                missing_receipt["source_event_id"],
            }
        ]
        conformance = build_projection_conformance_report(conformance_events, max_active_tokens=96, max_packet_tokens=96)
        inspect = build_projection_inspect_report(conformance_report=conformance)
        packet_selected = set((conformance.get("packet") or {}).get("selected_event_ids") or [])
        packet_dropped = set((conformance.get("packet") or {}).get("dropped_event_ids") or [])
        final_snapshot = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=500)
        cases.append(
            _case_status(
                "packet_and_inspect_follow_final_answerability",
                {
                    "packet_selects_new_truth": new_truth_event in packet_selected,
                    "packet_drops_old_support": old_support_event in packet_dropped,
                    "packet_drops_later_rejected": later_rejected_event in packet_dropped,
                    "packet_drops_missing_receipt": missing_receipt_event in packet_dropped,
                    "inspect_verdict_pass": inspect.get("verdict") == "pass",
                    "inspect_has_public_reason_codes": all(
                        bool(item.get("reason_codes")) for item in inspect.get("event_explanations") or []
                    ),
                    "l0_matches_rebuild": parity.get("status") == "pass",
                },
            )
        )

        failures = [case for case in cases if case["status"] != "pass"]
        proof = {
            "dirty_live_shaped_fixture": True,
            "receipt_success_not_sufficient": old_support["admission_receipt_id"] > 0
            and not bool(_row_for_event_id(store, old_support_event).get("answerable_current_truth")),
            "rejected_receipt_not_answer_truth": later_rejected["admission_receipt_id"] > 0
            and not bool(_row_for_event_id(store, later_rejected_event).get("answerable_current_truth")),
            "support_only_cannot_answer": not bool(_row_for_event_id(store, old_support_event).get("answerable_current_truth")),
            "newer_rejected_cannot_override_current": _answerable_event_ids(store, new_truth["stable_key"]) == [new_truth_event],
            "explicit_supersession_final_state": bool(_row_for_event_id(store, new_superseding_event).get("answerable_current_truth"))
            and not bool(_row_for_event_id(store, old_explicit_event).get("answerable_current_truth")),
            "missing_receipt_event_not_answer_truth": not bool(
                _row_for_event_id(store, missing_receipt_event).get("answerable_current_truth")
            ),
            "packet_selected_only_answer_safe": packet_selected == {new_truth_event},
            "inspect_or_l0_reason_codes_present": inspect.get("verdict") == "pass"
            and bool(missing_receipt_row.get("projection_reason_codes")),
            "l0_matches_rebuild": parity.get("status") == "pass",
        }
        proof_failures = [key for key, value in proof.items() if value is not True]
        final_counts = {
            "admission_receipts": _count(store, "admission_receipts"),
            "canonical_memory_events": _count(store, "canonical_memory_events"),
            "operating_records": _count(store, "operating_records"),
            "current_truth_l0_rows": _count(store, "current_truth_l0_rows"),
            "proactive_outbox": _count(store, "proactive_outbox"),
        }
        report_issues = [*proof_failures, *[case["case_id"] for case in failures]]
        return {
            "schema": REPORT_SCHEMA,
            "status": "pass" if not report_issues else "fail",
            "public_safe": True,
            "llm_calls_performed": False,
            "issue_count": len(report_issues),
            "issues": report_issues,
            "proof": proof,
            "case_count": len(cases),
            "failure_case_ids": [case["case_id"] for case in failures],
            "final_counts": final_counts,
            "current_truth_final_state": {
                "status": final_snapshot.get("status"),
                "current_truth_row_count": len(final_snapshot.get("current_truth_rows") or []),
                "non_answerable_row_count": len(final_snapshot.get("non_answerable_rows") or []),
                "missing_receipt_count": (final_snapshot.get("counters") or {}).get("missing_receipt_count"),
                "support_only_count": (final_snapshot.get("counters") or {}).get("support_only_count"),
                "unsafe_answer_truth_projection_count": (final_snapshot.get("counters") or {}).get(
                    "unsafe_answer_truth_projection_count"
                ),
                "receipt_coverage": final_snapshot.get("receipt_coverage"),
                "rebuilt_status": rebuilt.get("status"),
                "l0_parity_status": parity.get("status"),
            },
            "packet_final_state": {
                "conformance_status": conformance.get("status"),
                "selected_event_ids": sorted(packet_selected),
                "dropped_event_ids": sorted(packet_dropped),
                "inspect_verdict": inspect.get("verdict"),
            },
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
        with tempfile.TemporaryDirectory(prefix="brainstack_phase276_3_") as tmp:
            report = build_report(Path(tmp) / "brainstack.sqlite3")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "schema": report.get("schema"),
                "status": report.get("status"),
                "case_count": report.get("case_count"),
                "issue_count": report.get("issue_count"),
                "issues": report.get("issues"),
            },
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
