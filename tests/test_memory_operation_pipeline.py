from __future__ import annotations

from brainstack.memory_operation_pipeline import (
    build_memory_operation_pipeline_record,
    build_referenced_category_projection,
    build_retrieval_sufficiency_trace,
)


def test_memory_operation_pipeline_is_read_only_and_stage_visible() -> None:
    record = build_memory_operation_pipeline_record(
        operation="retrieval_packet_assembly",
        selected_seam="route_plan_to_packet_diagnostics",
        stages=[
            {"name": "route_plan", "status": "ok", "input_ref": "query", "output_ref": "plan"},
            {"name": "packet_budget", "status": "ok", "input_ref": "plan", "output_ref": "packet"},
        ],
        final_packet_state={"changed": False, "char_count": 420},
    )

    assert record["schema"] == "brainstack.memory_operation_pipeline.v1"
    assert record["read_only"] is True
    assert record["truth_writer"] is False
    assert record["verdict"] == "healthy"
    assert record["stage_count"] == 2
    assert record["reason_codes"] == ["PIPELINE_DIAGNOSTIC_HEALTHY"]


def test_memory_operation_pipeline_fails_closed_if_authority_changes() -> None:
    record = build_memory_operation_pipeline_record(
        operation="retrieval_packet_assembly",
        selected_seam="route_plan_to_packet_diagnostics",
        stages=[{"name": "projection", "status": "ok"}],
        unchanged_authority=False,
    )

    assert record["verdict"] == "critical"
    assert "PIPELINE_CHANGED_AUTHORITY_FORBIDDEN" in record["reason_codes"]


def test_referenced_projection_keeps_refs_and_excludes_stale_authority() -> None:
    projection = build_referenced_category_projection(
        category="current_truth",
        rows=[
            {
                "claim": "The active config threshold is 0.9.",
                "receipt_id": "receipt-current",
                "truth_eligible": True,
                "is_current": True,
            },
            {
                "claim": "The old threshold was 0.5.",
                "receipt_id": "receipt-old",
                "truth_eligible": True,
                "is_current": False,
                "superseded_by": "receipt-current",
            },
            {
                "claim": "A support note mentioned threshold tuning.",
                "receipt_id": "receipt-support",
                "truth_eligible": False,
                "support_only": True,
            },
        ],
    )

    assert projection["truth_writer"] is False
    assert projection["authority_claim_count"] == 1
    assert projection["support_claim_count"] == 1
    assert projection["excluded_count"] == 1
    assert projection["authority_claims"][0]["rendered"].endswith("[ref:receipt-current]")
    assert projection["excluded_rows"][0]["reason_code"] == "STALE_OR_SUPERSEDED_NOT_AUTHORITY"


def test_retrieval_sufficiency_trace_stops_fast_for_authoritative_profile() -> None:
    trace = build_retrieval_sufficiency_trace(
        query_class="profile",
        route_class="fast",
        evidence_counts={"profile": 2, "current_truth": 1, "corpus": 0, "graph": 0},
    )

    assert trace["decision"] == "stop_fast"
    assert trace["reason_code"] == "FAST_AUTHORITATIVE_CONTEXT_SUFFICIENT"


def test_retrieval_sufficiency_trace_marks_degraded_semantic_backend() -> None:
    trace = build_retrieval_sufficiency_trace(
        query_class="documentation",
        route_class="semantic",
        evidence_counts={"profile": 0, "current_truth": 0, "corpus": 0, "graph": 0},
        backend_health={"semantic_status": "timeout"},
    )

    assert trace["decision"] == "degraded_partial"
    assert trace["reason_code"] == "SEMANTIC_BACKEND_DEGRADED_VISIBLE"


def test_retrieval_sufficiency_trace_deepens_for_corpus_or_graph_need() -> None:
    trace = build_retrieval_sufficiency_trace(
        query_class="documentation",
        route_class="corpus",
        evidence_counts={"profile": 0, "current_truth": 0, "corpus": 2, "graph": 1},
    )

    assert trace["decision"] == "deepen"
    assert trace["reason_code"] == "DEEPER_RETRIEVAL_REQUIRED"
