from __future__ import annotations

from hermes_continuation.trace_replay import (
    build_checkpoint,
    render_replay_summary,
    replay_decision_trace,
    validate_decision_trace,
)


def _decision_event(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "trace_id": "tr-1",
        "workstream_id": "ws-1",
        "timestamp": "2026-05-15T00:00:00Z",
        "decision": "split",
        "confidence": 0.8,
        "expected_value": 0.9,
        "risk_class": "local",
        "reason_codes": ["INDEPENDENT_HIGH_VALUE_BRANCH"],
        "input_event_refs": ["event:1"],
        "work_graph_refs": ["graph:g1"],
        "kanban_task_refs": ["task:t1"],
        "artifact_refs": ["artifact:a1"],
        "postcondition": "fanout_created",
    }
    event.update(overrides)
    return event


def test_trace_missing_evidence_or_postcondition_is_rejected() -> None:
    verdict = validate_decision_trace({"trace_id": "bad", "decision": "continue"})

    assert verdict["verdict"] == "critical"
    assert "TRACE_EVIDENCE_OR_POSTCONDITION_MISSING" in verdict["reason_codes"]


def test_replay_ignores_duplicate_trace_events() -> None:
    event = _decision_event(trace_id="dup")
    replay = replay_decision_trace([event, event])

    assert replay["decision_count"] == 1
    assert replay["duplicate_event_count"] == 1
    assert replay["last_decision"] == "split"


def test_newer_critical_trace_overrides_older_healthy_checkpoint() -> None:
    checkpoint = build_checkpoint(
        [_decision_event(trace_id="old", decision="continue", postcondition="frontier_active")]
    )
    replay = replay_decision_trace(
        [
            _decision_event(trace_id="new", decision="repair", postcondition="recovery_needed"),
        ],
        checkpoint=checkpoint | {"verdict": "healthy"},
    )

    assert replay["verdict"] == "recovery_needed"
    assert replay["last_decision"] == "repair"
    assert "CHECKPOINT_SUPERSEDED_BY_TRACE" in replay["reason_codes"]


def test_human_needed_and_intentional_stop_survive_replay() -> None:
    human = replay_decision_trace(
        [_decision_event(trace_id="h", decision="human_needed", postcondition="approval_required")]
    )
    stopped = replay_decision_trace(
        [_decision_event(trace_id="s", decision="intentional_stop", postcondition="no_meaningful_next_step")]
    )

    assert human["verdict"] == "waiting_for_human"
    assert human["last_decision"] == "human_needed"
    assert stopped["verdict"] == "stopped_intentionally"
    assert stopped["last_decision"] == "intentional_stop"


def test_large_trace_history_renders_bounded_summary_without_private_payload() -> None:
    events = [
        _decision_event(
            trace_id=f"tr-{i}",
            decision="continue",
            postcondition="frontier_active",
            private_payload={"secret": "do-not-render"},
        )
        for i in range(80)
    ]
    replay = replay_decision_trace(events)
    summary = render_replay_summary(replay, max_reason_codes=5)

    assert summary["rendered_length"] < 1200
    assert "do-not-render" not in str(summary)
    assert summary["trace_event_count"] == 80

