from __future__ import annotations

from scripts.verify_store_concurrency_contract import build_report


def test_store_concurrency_contract_blocks_default_read_path_mutation() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["read_path_mutation_probe"]["default_packet_mutated_retrieval_telemetry"] is False
    assert report["compiled_behavior_policy_read_probe"]["compiled_record_returned"] is True
    assert report["compiled_behavior_policy_read_probe"]["direct_read_created_durable_row"] is False
    assert report["compiled_behavior_policy_read_probe"]["packet_read_created_durable_row"] is False
    assert report["read_path_mutation_probe"]["explicit_opt_in_retrieval_telemetry_written"] is True
    assert report["single_writer_queue"]["status"] == "not_claimed"
    assert report["write_callsite_audit"]["full_single_writer_safe_to_claim"] is False
    assert report["write_callsite_audit"]["read_mutation_risk"] == []
    assert report["write_callsite_audit"]["lane_taxonomy"]["status"] == "mapped"
    assert report["write_callsite_audit"]["lane_taxonomy"]["unknown_lane_count"] == 0
    assert report["write_callsite_audit"]["store_lane_refactor_decision"]["status"] == "blocked_with_exact_refactor_map"
    assert report["write_callsite_audit"]["runtime_write_map"]
