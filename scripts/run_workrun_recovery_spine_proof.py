#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
extension_root = ROOT / "extensions" / "hermes_proactive"
if str(extension_root) not in sys.path:
    sys.path.insert(0, str(extension_root))

from brainstack.db import BrainstackStore  # noqa: E402
from extensions.hermes_proactive.hermes_proactive.pulse_producer import produce_pulse, project_pulse_output  # noqa: E402
from extensions.hermes_proactive.hermes_proactive.workrun import (  # noqa: E402
    finish_workrun,
    list_recovery_candidates,
    recovery_card,
    start_workrun,
)


PRIVATE_CANARY = "private recovery transcript must not leak"


def _table_count(store: BrainstackStore, table: str) -> int:
    return int(store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def build_report() -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-workrun-recovery-") as raw:
        base = Path(raw)
        hermes_home = base / "hermes_home"
        hermes_home.mkdir(parents=True)
        db_path = base / "brainstack.sqlite3"

        stale = start_workrun(
            hermes_home=hermes_home,
            source_kind="cron",
            source_id="job:overnight-analysis",
            objective="Continue a source-backed long-running analysis without leaking raw transcript.",
            session_id="session:public-safe",
            checkpoint_refs=["cron/output/job/last.md"],
            output_refs=[],
            recovery_policy="inspect checkpoint before retry",
            side_effect_risk="medium",
            next_safe_action="ask approval before rerunning worker",
            metadata={"private": PRIVATE_CANARY},
            heartbeat_at="2026-05-08T00:00:00+00:00",
        )
        fresh = start_workrun(
            hermes_home=hermes_home,
            source_kind="goal",
            source_id="goal:active",
            objective="Fresh active goal should not be reclaimed yet.",
            side_effect_risk="low",
        )
        interrupted = start_workrun(
            hermes_home=hermes_home,
            source_kind="kanban",
            source_id="card:handoff",
            objective="Recover a Kanban-owned handoff without taking board ownership.",
            checkpoint_refs=["kanban/card/handoff"],
            side_effect_risk="low",
            heartbeat_at="2026-05-08T00:00:00+00:00",
        )
        finish_workrun(
            hermes_home=hermes_home,
            run_id=str(interrupted["run_id"]),
            status="interrupted",
            error_summary="gateway shutdown",
            next_safe_action="inspect Kanban card and let Hermes Kanban own dispatch",
        )
        completed = start_workrun(
            hermes_home=hermes_home,
            source_kind="proactive_pulse",
            source_id="pulse:complete",
            objective="Completed pulse should not become recovery work.",
            side_effect_risk="none",
        )
        finish_workrun(hermes_home=hermes_home, run_id=str(completed["run_id"]), status="completed")

        candidates = list_recovery_candidates(hermes_home=hermes_home, stale_after_seconds=60, limit=10)
        candidate_ids = {str(item.get("run_id") or "") for item in candidates}
        if str(stale["run_id"]) not in candidate_ids:
            issues.append({"code": "stale_running_run_not_recoverable"})
        if str(interrupted["run_id"]) not in candidate_ids:
            issues.append({"code": "interrupted_run_not_recoverable"})
        if str(fresh["run_id"]) in candidate_ids:
            issues.append({"code": "fresh_running_run_reclaimed"})
        if str(completed["run_id"]) in candidate_ids:
            issues.append({"code": "completed_run_reclaimed"})

        stale_card = recovery_card(stale, now=datetime(2026, 5, 8, 0, 20, tzinfo=timezone.utc), stale_after_seconds=60) or {}
        if stale_card.get("state") != "reclaimable":
            issues.append({"code": "stale_running_state_not_reclaimable", "state": stale_card.get("state")})
        if stale_card.get("side_effect_risk") != "medium":
            issues.append({"code": "side_effect_risk_missing"})
        serialized_card = json.dumps(stale_card, ensure_ascii=True, sort_keys=True)
        if PRIVATE_CANARY in serialized_card:
            issues.append({"code": "private_metadata_leaked_to_recovery_card"})

        pulse = produce_pulse(
            hermes_home=hermes_home,
            principal_scope_key="principal:workrun-proof",
            workspace_scope_key="workspace:workrun-proof",
        )
        workrun_tasks = [
            item for item in pulse.get("tasks") or []
            if isinstance(item, dict) and item.get("source") == "workrun_recovery"
        ]
        if len(workrun_tasks) < 2:
            issues.append({"code": "pulse_did_not_surface_recovery_candidates", "task_count": len(workrun_tasks)})
        if pulse.get("provider_calls") != 0 or pulse.get("prompt_tokens") != 0 or pulse.get("completion_tokens") != 0:
            issues.append({"code": "pulse_recovery_used_provider"})

        projected = project_pulse_output(db_path=db_path, output=pulse, create_outbox=False)
        store = BrainstackStore(str(db_path))
        store.open()
        try:
            proactive_events = _table_count(store, "proactive_events")
            proactive_outbox = _table_count(store, "proactive_outbox")
        finally:
            store.close()
        if proactive_events < len(workrun_tasks):
            issues.append({"code": "projected_recovery_events_missing", "event_count": proactive_events})
        if proactive_outbox != 0:
            issues.append({"code": "recovery_projection_created_outbox_without_delivery"})
        if (projected.get("wake") or {}).get("delivery_requested") is True:
            issues.append({"code": "recovery_projection_requested_delivery_without_permission"})

    report = {
        "schema": "brainstack.workrun_recovery_spine_proof.v1",
        "status": "pass" if not issues else "fail",
        "issues": issues,
        "public_safe": True,
        "llm_calls_performed": False,
        "proof": {
            "stale_running_reclaimable": not any(issue["code"] == "stale_running_run_not_recoverable" for issue in issues),
            "fresh_running_not_reclaimed": not any(issue["code"] == "fresh_running_run_reclaimed" for issue in issues),
            "completed_not_reclaimed": not any(issue["code"] == "completed_run_reclaimed" for issue in issues),
            "interrupted_recoverable": not any(issue["code"] == "interrupted_run_not_recoverable" for issue in issues),
            "recovery_card_public_safe": not any(issue["code"] == "private_metadata_leaked_to_recovery_card" for issue in issues),
            "pulse_surfaces_recovery_candidates": not any(issue["code"] == "pulse_did_not_surface_recovery_candidates" for issue in issues),
            "projection_is_side_effect_bounded": not any(issue["code"] in {"recovery_projection_created_outbox_without_delivery", "recovery_projection_requested_delivery_without_permission"} for issue in issues),
        },
    }
    serialized = json.dumps(report, ensure_ascii=True, sort_keys=True)
    if PRIVATE_CANARY in serialized:
        report["status"] = "fail"
        report["public_safe"] = False
        report["issues"].append({"code": "private_canary_leaked"})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify durable WorkRun recovery spine.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
