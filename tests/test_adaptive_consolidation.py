from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from brainstack.adaptive_consolidation import (
    ADAPTIVE_CONSOLIDATION_SCHEMA_VERSION,
    DERIVED_WORK_STATES,
    DurableTruthMustRemainSynchronousError,
    build_adaptive_consolidation_report,
    build_derived_work_item,
    defer_durable_truth_write,
    validate_adaptive_consolidation_public_safety,
)
from brainstack.db import BrainstackStore
from brainstack.persistent_bloat import build_persistent_bloat_report
from scripts.verify_adaptive_consolidation import build_report as build_consolidation_report


def _open_store(tmp_path: Path, **kwargs: Any) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), **kwargs)
    store.open()
    return store


def test_async_consolidation_contract_keeps_durable_truth_synchronous_and_public_safe() -> None:
    item = build_derived_work_item(
        work_id="dw_current_truth_1",
        work_kind="current_truth_view",
        state="queued",
        source_event_id="evt_1",
        source_span_id="span_1",
        freshness_status="pending",
    )

    report = build_adaptive_consolidation_report([item])

    assert report["schema"] == ADAPTIVE_CONSOLIDATION_SCHEMA_VERSION
    assert report["status"] == "degraded"
    assert set(DERIVED_WORK_STATES) == {"queued", "pending", "failed", "complete", "skipped"}
    assert report["contract"]["admission_synchronous"] is True
    assert report["contract"]["write_receipt_synchronous"] is True
    assert report["contract"]["derived_work_async_only"] is True
    assert report["readiness"]["ready"] is False
    assert report["readiness"]["ready_claim_allowed"] is False
    assert report["counters"]["queued_count"] == 1
    assert validate_adaptive_consolidation_public_safety(report) == []

    with pytest.raises(DurableTruthMustRemainSynchronousError):
        defer_durable_truth_write({"stable_fact_id": "identity:name", "value": "ExampleUser"})


def test_async_consolidation_failure_paths_are_explicit_without_hidden_readiness() -> None:
    items = [
        build_derived_work_item(
            work_id="dw_pending_stalled",
            work_kind="graph_projection",
            state="pending",
            source_event_id="evt_2",
            source_span_id="span_2",
            retry_count=2,
            last_error_class="stalled_queue",
            freshness_status="stale",
        ),
        build_derived_work_item(
            work_id="dw_malformed",
            work_kind="current_truth_view",
            state="failed",
            source_event_id="evt_3",
            source_span_id="span_3",
            retry_count=1,
            last_error_class="malformed_derived_payload",
            freshness_status="failed",
            payload={"raw_text": "private source text"},
        ),
        build_derived_work_item(
            work_id="dw_mismatch",
            work_kind="current_truth_view",
            state="failed",
            source_event_id="evt_4",
            source_span_id="span_4",
            retry_count=1,
            last_error_class="rebuild_mismatch",
            freshness_status="failed",
        ),
        build_derived_work_item(
            work_id="dw_backend",
            work_kind="corpus_index",
            state="failed",
            source_event_id="evt_5",
            source_span_id="span_5",
            retry_count=3,
            last_error_class="backend_unavailable",
            freshness_status="failed",
        ),
    ]

    report = build_adaptive_consolidation_report(items)

    assert report["status"] == "degraded"
    assert report["counters"]["pending_count"] == 1
    assert report["counters"]["failed_count"] == 3
    assert report["counters"]["stalled_count"] == 1
    assert report["counters"]["malformed_payload_count"] == 1
    assert report["counters"]["rebuild_mismatch_count"] == 1
    assert report["counters"]["backend_unavailable_count"] == 1
    assert report["readiness"]["ready"] is False
    assert report["readiness"]["hidden_fallback_claim_count"] == 0
    assert "private source text" not in str(report)
    assert report["failure_bundles"]
    assert all(bundle["public_safe"] is True for bundle in report["failure_bundles"])


def test_async_consolidation_bounds_write_amplification_and_packet_growth() -> None:
    items = [
        build_derived_work_item("dw_graph_done", "graph_projection", "complete", source_event_id="evt_1", source_span_id="span_1"),
        build_derived_work_item("dw_current_done", "current_truth_view", "complete", source_event_id="evt_2", source_span_id="span_2"),
        build_derived_work_item("dw_corpus_done", "corpus_index", "complete", source_event_id="evt_3", source_span_id="span_3"),
    ]

    report = build_adaptive_consolidation_report(
        items,
        baseline={"write_amplification": 6, "active_packet_tokens": 420, "projection_rebuild_size": 9},
        write_amplification=4,
        active_packet_tokens=360,
        projection_rebuild_size=7,
        duplicate_support_only_accumulation=0,
    )

    assert report["status"] == "pass"
    assert report["readiness"]["ready"] is True
    assert report["bloat_control"]["write_amplification_delta"] == -2
    assert report["bloat_control"]["active_packet_growth_delta"] == -60
    assert report["bloat_control"]["projection_rebuild_size_delta"] == -2
    assert report["bloat_control"]["bounded"] is True
    assert report["anti_goal_proof"]["async_without_lying"] is True


def test_persistent_bloat_report_includes_derived_async_state(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        derived = build_adaptive_consolidation_report(
            [
                build_derived_work_item(
                    "dw_pending",
                    "current_truth_view",
                    "pending",
                    source_event_id="evt_1",
                    source_span_id="span_1",
                    retry_count=1,
                )
            ]
        )
        report = build_persistent_bloat_report(store, derived_async_state=derived)

        assert report["derived_async_state"]["schema"] == ADAPTIVE_CONSOLIDATION_SCHEMA_VERSION
        assert report["derived_async_state"]["counters"]["pending_count"] == 1
        assert report["metrics"]["derived_async_queued_count"] == 0
        assert report["metrics"]["derived_async_retry_count"] == 1
        assert report["critical_counters"]["derived_async_hidden_readiness"] == 0
    finally:
        store.close()


def test_adaptive_consolidation_verifier_passes_public_safe_bounds() -> None:
    report = build_consolidation_report()

    assert report["status"] == "pass"
    assert report["summary"]["async_without_lying"] is True
    assert report["summary"]["bounded_state_garbage"] is True
    assert report["summary"]["durable_truth_deferred_count"] == 0
    assert report["summary"]["hidden_readiness_claim_count"] == 0
