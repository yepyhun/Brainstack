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
from brainstack.core.admission import AssertionSpeaker, ClaimProposal, SourceAuthority, SpanKind  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.proactive_agent_contract import build_proactive_status  # noqa: E402
from brainstack.storage.projection_writer import ProjectionWriter  # noqa: E402
from brainstack.task_memory import ITEM_TYPE_TASK, STATUS_OPEN  # noqa: E402

REPORT_SCHEMA = "brainstack.source_backed_actionable_queue_substrate.v1"
PRINCIPAL_SCOPE_KEY = "principal:phase269"
WORKSPACE_SCOPE_KEY = "workspace:phase269"
SESSION_ID = "session-phase269"


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
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


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-phase269-") as tmp:
        root = Path(tmp)
        hermes_home = root / "hermes_home"
        hermes_home.mkdir()
        (hermes_home / "config.yaml").write_text(
            "proactive_mode: live\nproactive_cooldown_seconds: 21600\nproactive_kill_switch: false\n",
            encoding="utf-8",
        )
        store = _open_store(root / "brainstack.sqlite3")
        try:
            writer = ProjectionWriter(store)
            admitted = _proposal(
                claim_id="source-backed-task",
                value="Review the release checklist before any release claim.",
                authority=SourceAuthority.USER_EXPLICIT_ASSIGNMENT,
                speaker=AssertionSpeaker.USER,
                span_kind=SpanKind.ASSERTION,
            )
            rejected = _proposal(
                claim_id="ambiguous-tier2-task",
                value="Create proactive follow-up from ambiguous transcript context.",
                authority=SourceAuthority.TIER2_SUMMARY,
                speaker=AssertionSpeaker.UNKNOWN,
                span_kind=SpanKind.SUMMARY,
            )

            task_id = _write_task(writer, admitted)
            rejection_receipt_id = writer.record_decision(
                decision=admit_claim(rejected),
                metadata=_base_metadata(rejected.metadata),
            )
            before = {
                "proactive_events": _count(store, "proactive_events"),
                "proactive_outbox": _count(store, "proactive_outbox"),
                "proactive_attention_ledger": _count(store, "proactive_attention_ledger"),
            }
            status = build_proactive_status(
                store=store,
                principal_scope_key=PRINCIPAL_SCOPE_KEY,
                config={"hermes_home": str(hermes_home)},
            )
            after = {
                "proactive_events": _count(store, "proactive_events"),
                "proactive_outbox": _count(store, "proactive_outbox"),
                "proactive_attention_ledger": _count(store, "proactive_attention_ledger"),
            }
            substrate = status.get("counts", {}).get("actionable_substrate", {})
            sample = list(substrate.get("sampled_items") or [])
            first = sample[0] if sample else {}
            checks = {
                "admitted_task_written": task_id > 0,
                "rejected_candidate_receipt_recorded": rejection_receipt_id > 0,
                "status_read_only": status.get("read_only") is True and status.get("side_effect") is False,
                "pending_actionable_count_one": substrate.get("pending_count") == 1,
                "sample_has_source_refs": bool(first.get("source_event_id") and first.get("source_span_id")),
                "sample_has_receipt_ref": bool(first.get("receipt_id")),
                "sample_has_no_execution_payload": first.get("execution_payload_present") is False,
                "no_outbox_created": after.get("proactive_outbox") == 0,
                "no_proactive_event_created": after.get("proactive_events") == 0,
                "status_read_did_not_mutate_proactive_tables": before == after,
            }
            failed = sorted(key for key, passed in checks.items() if not passed)
            return {
                "schema": REPORT_SCHEMA,
                "status": "pass" if not failed else "fail",
                "issues": failed,
                "checks": checks,
                "counts": {
                    "task_items": _count(store, "task_items"),
                    "admission_receipts": _count(store, "admission_receipts"),
                    "canonical_memory_events": _count(store, "canonical_memory_events"),
                    "proactive_events": after.get("proactive_events"),
                    "proactive_outbox": after.get("proactive_outbox"),
                    "proactive_attention_ledger": after.get("proactive_attention_ledger"),
                },
                "actionable_substrate": {
                    "pending_count": substrate.get("pending_count"),
                    "rejected_or_degraded_count": substrate.get("rejected_or_degraded_count"),
                    "sampled_items": sample,
                    "reason_code": substrate.get("reason_code"),
                },
                "blocked_actions": status.get("blocked_actions"),
            }
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify source-backed actionable queue substrate.")
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
