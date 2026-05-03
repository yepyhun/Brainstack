from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.adaptive_route_plan import (
    ADAPTIVE_ROUTE_PLAN_SCHEMA_VERSION,
    ROUTE_CLASSES,
    build_adaptive_route_plan,
    evaluate_tank_shadow_oracle,
    route_plan_limit_overrides,
    validate_route_plan_public_safety,
)
from brainstack.db import BrainstackStore
from brainstack.control_plane import build_working_memory_packet
from scripts.verify_adaptive_route_plan import build_report as build_route_report
from scripts.verify_tank_escalation_safety import build_report as build_tank_report


def _open_store(tmp_path: Path, **kwargs: Any) -> BrainstackStore:
    store = BrainstackStore(str(tmp_path / "brainstack.sqlite3"), **kwargs)
    store.open()
    return store


def _current_truth_view(row_count: int = 1) -> dict[str, Any]:
    return {
        "schema": "brainstack.current_truth_view.v1",
        "status": "pass",
        "current_truth_rows": [
            {
                "event_id": "cme_current_1",
                "stable_fact_id": "profile:preferred_language",
                "target_slot": "profile.preferred_language",
                "answerable_current_truth": True,
                "receipt_id": "receipt_1",
                "source_event_id": "evt_1",
                "source_span_id": "span_1",
                "source_quote_hash": "sha256:quote",
            }
        ][:row_count],
        "counters": {"unsafe_answer_truth_projection_count": 0},
        "rebuild": {"freshness_status": "fresh", "freshness_diagnostics_present": True},
    }


def test_adaptive_route_plan_contract_covers_required_routes_without_keyword_sprawl() -> None:
    plans = {
        "no_memory_minimal": build_adaptive_route_plan(
            "",
            query_understanding={"memory_intent": "none"},
            current_truth_view=_current_truth_view(0),
        ),
        "profile": build_adaptive_route_plan(
            "structured profile request",
            query_understanding={"profile_slot_targets": ["profile.preferred_language"]},
            current_truth_view=_current_truth_view(0),
        ),
        "current_truth": build_adaptive_route_plan(
            "structured current truth request",
            query_understanding={"required_evidence_classes": ["current_truth"]},
            current_truth_view=_current_truth_view(1),
        ),
        "temporal_graph": build_adaptive_route_plan(
            "structured temporal request",
            query_understanding={"required_evidence_classes": ["temporal_graph"]},
            current_truth_view=_current_truth_view(0),
        ),
        "aggregate": build_adaptive_route_plan(
            "structured aggregate request",
            query_understanding={"required_evidence_classes": ["aggregate"]},
            current_truth_view=_current_truth_view(0),
        ),
        "corpus": build_adaptive_route_plan(
            "structured corpus request",
            query_understanding={"required_evidence_classes": ["corpus"]},
            current_truth_view=_current_truth_view(0),
        ),
        "continuity": build_adaptive_route_plan(
            "structured continuity request",
            query_understanding={"required_evidence_classes": ["continuity"]},
            current_truth_view=_current_truth_view(0),
        ),
        "deep_mixed": build_adaptive_route_plan(
            "structured deep request",
            query_understanding={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
            current_truth_view=_current_truth_view(0),
        ),
    }

    assert set(ROUTE_CLASSES).issubset({*plans})
    for expected_route, plan in plans.items():
        assert plan["schema"] == ADAPTIVE_ROUTE_PLAN_SCHEMA_VERSION
        assert plan["route_class"] == expected_route
        assert plan["status"] == "pass"
        assert plan["contract"]["second_truth_authority"] is False
        assert plan["guardrails"]["keyword_sprawl_guard"] is True
        assert plan["guardrails"]["language_specific_keyword_count"] == 0
        assert plan["route_decision"]["full_depth_escalation_considered"] is True
        assert validate_route_plan_public_safety(plan) == []


def test_adaptive_route_plan_escalates_uncertainty_disagreement_degraded_and_protected_risk() -> None:
    risky_cases = [
        {"uncertainty": True},
        {"ambiguity": True},
        {"broker_disagreement": True},
        {"low_candidate_confidence": True},
        {"protected_evidence_risk": True},
        {"required_evidence_classes": ["corpus"], "backend_health": {"corpus": "degraded"}},
    ]

    for signals in risky_cases:
        backend_health = signals.pop("backend_health", {}) if "backend_health" in signals else {}
        plan = build_adaptive_route_plan(
            "structured risky request",
            query_understanding=signals,
            current_truth_view=_current_truth_view(1),
            backend_health=backend_health,
        )

        assert plan["route_class"] == "deep_mixed"
        assert plan["route_decision"]["escalated_to_tank"] is True
        assert plan["route_decision"]["escalation_reasons"]
        assert "tank" in plan["activated_shelves"]
        assert plan["fallback"]["degraded_backend_states"] == backend_health


def test_route_plan_limit_overrides_reduce_simple_fanout_and_preserve_deep_depth() -> None:
    simple = build_adaptive_route_plan(
        "structured profile request",
        query_understanding={"profile_slot_targets": ["identity.name"]},
        current_truth_view=_current_truth_view(0),
    )
    deep = build_adaptive_route_plan(
        "structured deep request",
        query_understanding={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
        current_truth_view=_current_truth_view(0),
    )

    simple_overrides = route_plan_limit_overrides(simple)
    deep_overrides = route_plan_limit_overrides(deep)

    assert simple_overrides["profile_limit"] >= 1
    assert simple_overrides["graph_limit"] == 0
    assert simple_overrides["corpus_limit"] == 0
    assert simple_overrides["continuity_match_limit"] <= 1
    assert deep_overrides["graph_limit"] >= 4
    assert deep_overrides["corpus_limit"] >= 4
    assert deep_overrides["continuity_match_limit"] >= 4
    assert deep_overrides["evidence_item_budget"] >= 8


def test_build_working_memory_packet_uses_adaptive_route_plan_to_reduce_simple_profile_fanout(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="ExampleUser is Laura.",
            source="test",
            confidence=0.99,
            metadata={"principal_scope_key": "principal:test"},
        )
        packet = build_working_memory_packet(
            store,
            query="structured profile request",
            session_id="session:test",
            principal_scope_key="principal:test",
            profile_match_limit=6,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=4,
            transcript_char_budget=800,
            evidence_item_budget=10,
            graph_limit=5,
            corpus_limit=5,
            corpus_char_budget=900,
            record_retrievals=False,
            adaptive_route_signals={"profile_slot_targets": ["identity.name"]},
        )

        assert packet["adaptive_route_plan"]["route_class"] == "profile"
        assert packet["policy"]["adaptive_route_plan"]["route_class"] == "profile"
        assert packet["policy"]["graph_limit"] == 0
        assert packet["policy"]["corpus_limit"] == 0
        assert packet["profile_items"]
        assert packet["graph_rows"] == []
        assert packet["corpus_rows"] == []
    finally:
        store.close()


def test_build_working_memory_packet_preserves_deep_route_depth(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        packet = build_working_memory_packet(
            store,
            query="structured deep request",
            session_id="session:test",
            principal_scope_key="principal:test",
            profile_match_limit=6,
            continuity_recent_limit=4,
            continuity_match_limit=4,
            transcript_match_limit=4,
            transcript_char_budget=800,
            evidence_item_budget=10,
            graph_limit=5,
            corpus_limit=5,
            corpus_char_budget=900,
            record_retrievals=False,
            adaptive_route_signals={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
        )

        assert packet["adaptive_route_plan"]["route_class"] == "deep_mixed"
        assert packet["adaptive_route_plan"]["route_decision"]["escalated_to_tank"] is True
        assert packet["policy"]["graph_limit"] >= 4
        assert packet["policy"]["corpus_limit"] >= 4
        assert packet["policy"]["continuity_match_limit"] >= 4
        assert packet["policy"]["evidence_item_budget"] >= 8
    finally:
        store.close()


def test_tank_shadow_oracle_has_zero_false_negative_deep_route_misses() -> None:
    cases = [
        {
            "case_id": "simple_profile",
            "query_understanding": {"profile_slot_targets": ["identity.name"]},
            "required_evidence_classes": ["profile"],
        },
        {
            "case_id": "temporal_change",
            "query_understanding": {"required_evidence_classes": ["temporal_graph"]},
            "required_evidence_classes": ["temporal_graph"],
        },
        {
            "case_id": "corpus_answer",
            "query_understanding": {"required_evidence_classes": ["corpus"]},
            "required_evidence_classes": ["corpus"],
        },
        {
            "case_id": "broker_disagreement",
            "query_understanding": {"broker_disagreement": True, "required_evidence_classes": ["corpus"]},
            "required_evidence_classes": ["corpus"],
        },
    ]

    report = evaluate_tank_shadow_oracle(cases, current_truth_view=_current_truth_view(1))

    assert report["status"] == "pass"
    assert report["false_negative_tank_miss_count"] == 0
    assert all(row["sufficiency_status"] in {"sufficient", "escalated_to_tank"} for row in report["cases"])


def test_adaptive_route_verifiers_prove_waste_reduction_and_tank_safety() -> None:
    route_report = build_route_report()
    tank_report = build_tank_report()

    assert route_report["status"] == "pass"
    assert route_report["summary"]["simple_reduced_fanout_cases"] >= 2
    assert route_report["summary"]["deep_required_evidence_loss_count"] == 0
    assert route_report["summary"]["north_star_adaptive_not_smaller"] is True
    assert tank_report["status"] == "pass"
    assert tank_report["false_negative_tank_miss_count"] == 0
