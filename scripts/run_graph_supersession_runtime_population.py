#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Mapping

from brainstack.admission_policy import admit_claim
from brainstack.control_plane import build_working_memory_packet
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind
from brainstack.current_truth_view import rebuild_current_truth_view
from brainstack.db import BrainstackStore
from brainstack.graphiti_projection import project_canonical_events_to_graphiti
from brainstack.storage.projection_writer import ProjectionWriter

REPORT_SCHEMA = "brainstack.graph_supersession_runtime_population.v1"
PRINCIPAL_SCOPE_KEY = "principal:phase268"
WORKSPACE_SCOPE_KEY = "workspace:phase268"
SESSION_ID = "session-phase268"


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
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
        normalization_method="phase268_runtime_fixture",
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
    return [row["event"] for row in store.list_canonical_memory_events(limit=100)]


def _event_id_for_claim(store: BrainstackStore, claim_id: str) -> str:
    for event in _events(store):
        if event["authority"]["admission_decision_id"] == claim_id:
            return str(event["event"]["event_id"])
    return ""


def _ids(rows: list[Mapping[str, Any]]) -> list[str]:
    return [str(row.get("event_id") or "") for row in rows]


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-phase268-") as tmp:
        db_path = Path(tmp) / "brainstack.sqlite3"
        store = _open_store(db_path)
        try:
            writer = ProjectionWriter(store)
            old = _proposal(claim_id="phase268-old-creator", value="Old support owner")
            new = _proposal(
                claim_id="phase268-new-creator",
                value="Laura",
                authority=SourceAuthority.USER_CORRECTION,
                span_kind=SpanKind.CORRECTION,
            )
            conflict = _proposal(
                claim_id="phase268-assistant-conflict",
                value="Assistant",
                authority=SourceAuthority.ASSISTANT_CLAIM,
                speaker=AssertionSpeaker.ASSISTANT,
                span_kind=SpanKind.ASSISTANT_ANSWER,
            )

            old_outcome = _write_graph_state(writer, old)
            old_event_id = _event_id_for_claim(store, old.claim_id)
            new_outcome = _write_graph_state(
                writer,
                new,
                metadata={**dict(new.metadata), "supersedes": [old_event_id]},
            )
            writer.record_decision(decision=admit_claim(conflict), metadata=_base_metadata(conflict.metadata))
            new_event_id = _event_id_for_claim(store, new.claim_id)

            projection = project_canonical_events_to_graphiti(_events(store))
            l0_snapshot = store.get_current_truth_l0_snapshot(principal_scope_key=PRINCIPAL_SCOPE_KEY, limit=100)
            rebuilt_view = rebuild_current_truth_view(_events(store), rebuilt_at="2026-05-05T00:00:00Z")
            packet = build_working_memory_packet(
                store,
                query="Who is the current Brainstack creator?",
                session_id=SESSION_ID,
                principal_scope_key=PRINCIPAL_SCOPE_KEY,
                profile_match_limit=1,
                continuity_recent_limit=1,
                continuity_match_limit=1,
                transcript_match_limit=1,
                transcript_char_budget=200,
                evidence_item_budget=3,
                graph_limit=2,
                corpus_limit=0,
                corpus_char_budget=0,
                record_retrievals=False,
                adaptive_route_signals={"required_evidence_classes": ["current_truth"]},
            )
            supersession = store.conn.execute(
                """
                SELECT prior_state_id, new_state_id
                FROM graph_supersessions
                WHERE prior_state_id = ? AND new_state_id = ?
                """,
                (int(old_outcome.get("state_id") or 0), int(new_outcome.get("state_id") or 0)),
            ).fetchone()

            current_ids = _ids(list(projection.get("current_edges") or []))
            prior_ids = _ids(list(projection.get("prior_edges") or []))
            inspect_ids = _ids(list(projection.get("inspect_only_edges") or []))
            l0_current_ids = _ids(list(l0_snapshot.get("current_truth_rows") or []))
            l0_non_answerable_ids = _ids(list(l0_snapshot.get("non_answerable_rows") or []))
            rebuilt_current_ids = _ids(list(rebuilt_view.get("current_truth_rows") or []))
            rebuilt_non_answerable_ids = _ids(list(rebuilt_view.get("non_answerable_rows") or []))
            packet_current_count = int(packet.get("current_truth_view", {}).get("current_truth_row_count") or 0)
            packet_non_answerable_count = int(packet.get("current_truth_view", {}).get("non_answerable_row_count") or 0)

            checks = {
                "graph_supersession_row_present": supersession is not None,
                "projection_status_pass": projection.get("status") == "pass",
                "projection_current_is_new": current_ids == [new_event_id],
                "projection_prior_is_old": prior_ids == [old_event_id],
                "conflict_inspectable_not_current": bool(inspect_ids) and not any(item in current_ids for item in inspect_ids),
                "l0_current_is_new": l0_current_ids == [new_event_id],
                "l0_old_non_answerable": old_event_id in l0_non_answerable_ids,
                "rebuild_current_is_new": rebuilt_current_ids == [new_event_id],
                "rebuild_old_non_answerable": old_event_id in rebuilt_non_answerable_ids,
                "packet_uses_l0_current_truth": packet.get("current_truth_view", {}).get("rebuild", {}).get("source")
                == "current_truth_l0_snapshot",
                "packet_current_truth_count_matches_l0": packet_current_count == len(l0_current_ids) == 1,
                "packet_non_answerable_count_matches_l0": packet_non_answerable_count == len(l0_non_answerable_ids) == 2,
                "second_graph_truth_authority_absent": not bool(
                    projection.get("graphiti_contract", {}).get("second_write_authority", True)
                ),
            }
            failed = sorted(key for key, passed in checks.items() if not passed)
            return {
                "schema": REPORT_SCHEMA,
                "status": "pass" if not failed else "fail",
                "issues": failed,
                "checks": checks,
                "event_ids": {
                    "old": old_event_id,
                    "new": new_event_id,
                    "conflict": _event_id_for_claim(store, conflict.claim_id),
                },
                "projection": {
                    "current_edge_ids": current_ids,
                    "prior_edge_ids": prior_ids,
                    "inspect_only_edge_ids": inspect_ids,
                    "critical_counters": projection.get("critical_counters"),
                },
                "l0_snapshot": {
                    "current_truth_ids": l0_current_ids,
                    "non_answerable_ids": l0_non_answerable_ids,
                    "deep_graph_path": l0_snapshot.get("deep_graph_path"),
                },
                "packet": {
                    "current_truth_row_count": packet_current_count,
                    "non_answerable_row_count": packet_non_answerable_count,
                    "route_class": packet.get("adaptive_route_plan", {}).get("route_class"),
                    "current_truth_source": packet.get("current_truth_view", {}).get("rebuild", {}).get("source"),
                },
            }
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify admitted graph supersession runtime population.")
    parser.add_argument("--out", default="", help="Write JSON report")
    args = parser.parse_args(argv)

    report = build_report()
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "issues": report["issues"]}, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
