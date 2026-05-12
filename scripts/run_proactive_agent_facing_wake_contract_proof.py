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
from brainstack.core.proactive import ProactiveEventKind, ProactiveIntendedNextAction  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402
from brainstack.proactive_agent_contract import (  # noqa: E402
    _readiness_probe,
    build_proactive_status,
    validate_proactive_candidate_intake,
)
from brainstack.storage.projection_writer import ProjectionWriter  # noqa: E402
from brainstack.task_memory import ITEM_TYPE_TASK, STATUS_OPEN  # noqa: E402


REPORT_SCHEMA = "brainstack.proactive_agent_facing_wake_contract_proof.v1"
PRINCIPAL_SCOPE_KEY = "principal:phase283"
WORKSPACE_SCOPE_KEY = "workspace:phase283"
SESSION_ID = "session-phase283"


def _open_store(path: Path) -> BrainstackStore:
    store = BrainstackStore(str(path), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    return store


def _table_count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])


def _proactive_counts(store: BrainstackStore) -> dict[str, int]:
    return {
        "proactive_events": _table_count(store, "proactive_events"),
        "proactive_outbox": _table_count(store, "proactive_outbox"),
        "proactive_attention_ledger": _table_count(store, "proactive_attention_ledger"),
    }


def _hermes_home(root: Path, *, mode: str = "live", kill_switch: bool = False) -> Path:
    home = root / "hermes_home"
    home.mkdir(exist_ok=True)
    home.joinpath("config.yaml").write_text(
        f"proactive_mode: {mode}\n"
        "proactive_cooldown_seconds: 21600\n"
        f"proactive_kill_switch: {'true' if kill_switch else 'false'}\n",
        encoding="utf-8",
    )
    return home


def _hermes_root(root: Path) -> Path:
    hermes = root / "hermes_root"
    hermes.joinpath("tools").mkdir(parents=True, exist_ok=True)
    hermes.joinpath("hermes_cli").mkdir(parents=True, exist_ok=True)
    hermes.joinpath("plugins", "kanban").mkdir(parents=True, exist_ok=True)
    hermes.joinpath("tools", "kanban_tools.py").write_text("# phase283 fixture\n", encoding="utf-8")
    hermes.joinpath("hermes_cli", "kanban_db.py").write_text("# phase283 fixture\n", encoding="utf-8")
    return hermes


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
        storage_key=f"task:phase283:{claim_id}",
        subject="principal",
        predicate="task.actionable",
        surface_value=value,
        normalized_value=value,
        candidate_value=value,
        language="en",
        normalization_method="phase283_fixture",
        authority_class=authority,
        confidence=0.96,
        source_text_hash=f"sha256:{claim_id}",
        trace_id=f"trace:{claim_id}",
        metadata={
            "principal_scope_key": PRINCIPAL_SCOPE_KEY,
            "workspace_scope_key": WORKSPACE_SCOPE_KEY,
            "session_id": SESSION_ID,
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
        source="phase283:actionable_fixture",
        source_session_id=SESSION_ID,
        source_turn_number=1,
        metadata=_base_metadata(proposal.metadata),
    )


def _status(store: BrainstackStore, hermes_home: Path, hermes_root: Path | None = None) -> dict[str, Any]:
    config: dict[str, str] = {"hermes_home": str(hermes_home)}
    if hermes_root is not None:
        config["hermes_root"] = str(hermes_root)
    return build_proactive_status(
        store=store,
        principal_scope_key=PRINCIPAL_SCOPE_KEY,
        config=config,
        detail_level="full" if hermes_root is not None else "compact",
    )


def build_report() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="brainstack-phase283-") as tmp:
        root = Path(tmp)
        hermes_home = _hermes_home(root)
        store = _open_store(root / "brainstack.sqlite3")
        try:
            before_idle = _proactive_counts(store)
            idle = _status(store, hermes_home)
            probe_detail = _readiness_probe(idle["config"], idle["counts"])
            after_idle = _proactive_counts(store)

            writer = ProjectionWriter(store)
            admitted = _proposal(
                claim_id="source-backed-task",
                value="Review a public release proof before claiming proactive readiness.",
                authority=SourceAuthority.USER_EXPLICIT_ASSIGNMENT,
                speaker=AssertionSpeaker.USER,
                span_kind=SpanKind.ASSERTION,
            )
            rejected = _proposal(
                claim_id="support-only-task",
                value="Infer proactive work from support-only context.",
                authority=SourceAuthority.TIER2_SUMMARY,
                speaker=AssertionSpeaker.UNKNOWN,
                span_kind=SpanKind.SUMMARY,
            )
            task_id = _write_task(writer, admitted)
            rejection_receipt_id = writer.record_decision(
                decision=admit_claim(rejected),
                metadata=_base_metadata(rejected.metadata),
            )
            candidate = _status(store, hermes_home)

            event = store.upsert_proactive_event(
                source="phase283",
                kind=ProactiveEventKind.FOLLOW_UP.value,
                principal_scope_key=PRINCIPAL_SCOPE_KEY,
                title="Public proactive handoff",
                summary="A source-backed proactive handoff exists.",
                priority="normal",
                intended_next_action=ProactiveIntendedNextAction.REQUEST_INPUT.value,
                evidence_ids=["event:source-backed-task"],
                source_ref="phase283",
                idempotency_key="phase283:wake",
            )
            store.create_proactive_outbox(
                event_id=str(event["event_id"]),
                delivery_target="proactive_runtime",
                idempotency_key="phase283:wake:outbox",
                intended_next_action=ProactiveIntendedNextAction.REQUEST_INPUT.value,
            )
            wake = _status(store, hermes_home)

            hermes_root = _hermes_root(root)
            kanban = _status(store, hermes_home, hermes_root)["workstation_integrations"]["kanban"]

            valid = validate_proactive_candidate_intake(
                {
                    "kind": "follow_up",
                    "source_authority": "source_backed",
                    "principal_scope_key": PRINCIPAL_SCOPE_KEY,
                    "source_refs": ["event:source-backed-task"],
                }
            )
            support_only = validate_proactive_candidate_intake(
                {
                    "kind": "follow_up",
                    "source_authority": "support_only",
                    "principal_scope_key": PRINCIPAL_SCOPE_KEY,
                    "source_refs": ["event:support-only"],
                }
            )
            heartbeat = validate_proactive_candidate_intake(
                {
                    "kind": ProactiveEventKind.HEARTBEAT_OK.value,
                    "source_authority": "source_backed",
                    "principal_scope_key": PRINCIPAL_SCOPE_KEY,
                    "source_refs": ["heartbeat:ok"],
                }
            )
            execution_payload = validate_proactive_candidate_intake(
                {
                    "kind": "follow_up",
                    "source_authority": "source_backed",
                    "principal_scope_key": PRINCIPAL_SCOPE_KEY,
                    "source_refs": ["event:exec"],
                    "execution_payload_present": True,
                }
            )

            probe = idle.get("readiness_probe") if isinstance(idle.get("readiness_probe"), Mapping) else {}
            proof = {
                "ready_idle_explicit": idle.get("operational_state") == "ready_idle"
                and idle.get("idle_is_failure") is False,
                "idle_status_read_only_no_side_effect": before_idle == after_idle,
                "readiness_probe_zero_side_effect": probe.get("status") == "pass"
                and probe.get("zero_side_effects") is True
                and probe_detail.get("proof_counters") == {
                    "provider_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "db_mutation": 0,
                    "proactive_events_written": 0,
                    "proactive_outbox_written": 0,
                    "transcript_writes": 0,
                }
                and probe.get("live_delivery") is False,
                "blocked_actions_are_safety_boundary": idle.get("blocked_actions_mean_safety_boundary") is True
                and "execute_task" in (idle.get("blocked_actions") or []),
                "source_backed_candidate_visible": task_id > 0
                and candidate.get("operational_state") == "candidate_available"
                and candidate.get("counts", {}).get("pending_actionable_substrate_count") == 1,
                "support_only_not_actionable": rejection_receipt_id > 0
                and support_only.get("classification") == "rejected",
                "heartbeat_not_work": heartbeat.get("classification") == "rejected",
                "execution_payload_rejected": execution_payload.get("classification") == "rejected",
                "wake_queued_not_executed": wake.get("operational_state") == "wake_queued"
                and wake.get("current_assignment_authority") is False,
                "kanban_boundary_read_only": kanban.get("available") is True
                and kanban.get("owner") == "hermes_kanban"
                and kanban.get("proactive_role") == "wake_surface_and_handoff_only"
                and kanban.get("can_write_board") is False
                and "dispatch" in (kanban.get("blocked_board_actions") or []),
                "candidate_intake_valid_accepts_source_backed": valid.get("classification") == "candidate_visible",
            }
            issues = sorted(key for key, value in proof.items() if value is not True)
            return {
                "schema": REPORT_SCHEMA,
                "status": "pass" if not issues else "fail",
                "public_safe": True,
                "issues": issues,
                "proof": proof,
                "llm_calls_performed": False,
                "readiness_probe_counters": probe_detail.get("proof_counters"),
                "states": {
                    "idle": idle.get("operational_state"),
                    "candidate": candidate.get("operational_state"),
                    "wake": wake.get("operational_state"),
                },
                "kanban": {
                    "available": kanban.get("available"),
                    "owner": kanban.get("owner"),
                    "proactive_role": kanban.get("proactive_role"),
                    "can_write_board": kanban.get("can_write_board"),
                },
            }
        finally:
            store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify proactive agent-facing wake contract.")
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
