from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from extensions.hermes_proactive.hermes_proactive.pulse_producer import produce_pulse
from extensions.hermes_proactive.hermes_proactive.workrun import (
    finish_workrun,
    list_recovery_candidates,
    recovery_card,
    start_workrun,
)
from scripts.run_workrun_recovery_spine_proof import build_report


def test_stale_workrun_becomes_public_safe_recovery_candidate(tmp_path: Path) -> None:
    home = tmp_path / "hermes_home"
    record = start_workrun(
        hermes_home=home,
        source_kind="cron",
        source_id="job:research",
        objective="Recover long-running research from checkpoint.",
        checkpoint_refs=["cron/output/job/last.md"],
        side_effect_risk="medium",
        next_safe_action="ask approval before retry",
        metadata={"private": "private transcript text"},
        heartbeat_at="2026-05-08T00:00:00+00:00",
    )

    card = recovery_card(record, now=datetime(2026, 5, 8, 0, 20, tzinfo=timezone.utc), stale_after_seconds=60)

    assert card is not None
    assert card["state"] == "reclaimable"
    assert card["run_id"] == record["run_id"]
    assert "private transcript text" not in str(card)


def test_completed_and_fresh_runs_are_not_recovery_candidates(tmp_path: Path) -> None:
    home = tmp_path / "hermes_home"
    completed = start_workrun(
        hermes_home=home,
        source_kind="goal",
        source_id="goal:done",
        objective="Done work.",
        side_effect_risk="low",
    )
    finish_workrun(hermes_home=home, run_id=str(completed["run_id"]), status="completed")
    start_workrun(
        hermes_home=home,
        source_kind="goal",
        source_id="goal:fresh",
        objective="Fresh work.",
        side_effect_risk="low",
    )

    candidates = list_recovery_candidates(hermes_home=home, stale_after_seconds=3600)

    assert candidates == []


def test_proactive_pulse_surfaces_recovery_candidate_without_provider_calls(tmp_path: Path) -> None:
    home = tmp_path / "hermes_home"
    start_workrun(
        hermes_home=home,
        source_kind="kanban",
        source_id="card:handoff",
        objective="Kanban-owned handoff recovery.",
        side_effect_risk="low",
        heartbeat_at="2026-05-08T00:00:00+00:00",
    )

    output = produce_pulse(
        hermes_home=home,
        principal_scope_key="principal:test",
        workspace_scope_key="workspace:test",
    )
    tasks = [item for item in output["tasks"] if item["source"] == "workrun_recovery"]

    assert tasks
    assert output["workrun_recovery_count"] == 1
    assert output["provider_calls"] == 0
    assert output["prompt_tokens"] == 0
    assert output["completion_tokens"] == 0


def test_workrun_recovery_spine_release_proof_passes() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["issues"] == []
    assert report["public_safe"] is True
    assert report["proof"]["pulse_surfaces_recovery_candidates"] is True
