from __future__ import annotations

from brainstack.memory_use_record import (
    build_memory_use_record,
    summarize_memory_use_records,
    validate_memory_use_record,
)


def test_memory_use_record_is_operating_telemetry_not_truth() -> None:
    record = build_memory_use_record(
        consumer_id="agent-alpha",
        task_id="workflow-1",
        source_packet_id="packet-1",
        selected_memory_ids=["m1", "m2"],
        used_memory_ids=["m1"],
        ignored_memory_ids=["m2"],
        provenance_refs=["receipt:1"],
        outcome_metrics={"answer_correct": True, "used_in_answer": True},
    )

    assert record["schema"] == "brainstack.memory_use_record.v1"
    assert record["truth_eligible"] is False
    assert record["model_facing_default"] is False
    assert record["storage_lane"] == "operating_telemetry"
    assert record["record_id"] == build_memory_use_record(
        consumer_id="agent-alpha",
        task_id="workflow-1",
        source_packet_id="packet-1",
        selected_memory_ids=["m1", "m2"],
        used_memory_ids=["m1"],
        ignored_memory_ids=["m2"],
        provenance_refs=["receipt:1"],
        outcome_metrics={"answer_correct": True, "used_in_answer": True},
    )["record_id"]
    assert validate_memory_use_record(record) == []


def test_memory_use_record_rejects_raw_content_and_private_paths() -> None:
    record = build_memory_use_record(
        consumer_id="agent-alpha",
        task_id="workflow-1",
        source_packet_id="packet-1",
        selected_memory_ids=["m1"],
        used_memory_ids=["m1"],
        provenance_refs=["receipt:1"],
    )

    poisoned_raw = dict(record)
    poisoned_raw["raw_packet"] = "full prompt body"
    assert "forbidden_raw_field:raw_packet" in validate_memory_use_record(poisoned_raw)

    poisoned_path = dict(record)
    poisoned_path["artifact_ref"] = "/private/runtime/path/secret"
    assert "private_marker_leak:/private/runtime/path" in validate_memory_use_record(poisoned_path)

    poisoned_truth = dict(record)
    poisoned_truth["truth_eligible"] = True
    poisoned_truth["model_facing_default"] = True
    assert "truth_eligible_must_be_false" in validate_memory_use_record(poisoned_truth)
    assert "model_facing_default_must_be_false" in validate_memory_use_record(poisoned_truth)


def test_memory_use_summary_counts_usage_without_raw_text() -> None:
    records = [
        build_memory_use_record(
            consumer_id="agent-alpha",
            task_id="workflow-1",
            source_packet_id="packet-1",
            selected_memory_ids=["m1", "m2"],
            used_memory_ids=["m1"],
            ignored_memory_ids=["m2"],
            provenance_refs=["receipt:1"],
            outcome_metrics={"answer_correct": True},
        ),
        build_memory_use_record(
            consumer_id="agent-alpha",
            task_id="workflow-2",
            source_packet_id="packet-2",
            selected_memory_ids=["m3"],
            used_memory_ids=[],
            ignored_memory_ids=["m3"],
            provenance_refs=[],
            outcome_metrics={"answer_correct": False},
        ),
    ]

    summary = summarize_memory_use_records(records)

    assert summary["record_count"] == 2
    assert summary["selected_memory_id_count"] == 3
    assert summary["used_memory_id_count"] == 1
    assert summary["usage_rate"] == 1 / 3
    assert "raw_packet" not in str(summary)
