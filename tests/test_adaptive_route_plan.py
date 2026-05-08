from __future__ import annotations

from pathlib import Path
from typing import Any

from brainstack.adaptive_route_plan import (
    ADAPTIVE_ROUTE_PLAN_SCHEMA_VERSION,
    ROUTE_CLASSES,
    ROUTE_OPERATING_STATUS,
    build_adaptive_route_plan,
    evaluate_tank_shadow_oracle,
    route_plan_limit_overrides,
    route_plan_resolver_payload,
    validate_route_plan_public_safety,
)
from brainstack.db import BrainstackStore
from brainstack.control_plane import build_working_memory_packet
from brainstack.retrieval_pipeline.orchestrator import retrieve_executive_context
from brainstack.retrieval_control_plan import retrieval_control_plan_from_adaptive_plan
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
        "operating_status": build_adaptive_route_plan(
            "structured operating status request",
            query_understanding={"required_evidence_classes": ["operating"]},
            current_truth_view=_current_truth_view(0),
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
    operating = build_adaptive_route_plan(
        "structured operating status request",
        query_understanding={"required_evidence_classes": ["operating"]},
        current_truth_view=_current_truth_view(0),
    )
    operating_overrides = route_plan_limit_overrides(operating)
    assert operating["route_class"] == ROUTE_OPERATING_STATUS
    assert operating_overrides["operating_limit"] >= 1
    assert operating_overrides["transcript_limit"] == 0
    assert deep_overrides["graph_limit"] >= 4
    assert deep_overrides["corpus_limit"] >= 4
    assert deep_overrides["continuity_match_limit"] >= 4
    assert deep_overrides["evidence_item_budget"] >= 8


def test_adaptive_route_plan_exposes_route_gated_semantic_retrieval_decision() -> None:
    disabled = build_adaptive_route_plan(
        "structured profile request",
        query_understanding={"profile_slot_targets": ["identity.name"]},
        current_truth_view=_current_truth_view(0),
    )
    enabled = build_adaptive_route_plan(
        "structured deep request",
        query_understanding={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
        current_truth_view=_current_truth_view(0),
    )

    assert disabled["semantic_retrieval"] == {
        "enabled": False,
        "reason": "not_required_by_structured_route_signal",
        "allowed_shelves": [],
        "backend_call_policy": "route_gated",
    }
    assert enabled["semantic_retrieval"]["enabled"] is True
    assert enabled["semantic_retrieval"]["backend_call_policy"] == "route_gated"
    assert set(enabled["semantic_retrieval"]["allowed_shelves"])


def test_build_working_memory_packet_uses_adaptive_route_plan_to_reduce_simple_profile_fanout(tmp_path: Path) -> None:
    store = _open_store(tmp_path, graph_backend="sqlite", corpus_backend="sqlite")
    try:
        store.upsert_profile_item(
            stable_key="identity:name",
            category="identity",
            content="ExampleUser has a structured profile request.",
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


class SemanticSpyStore(BrainstackStore):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.search_semantic_evidence_call_count = 0
        self.search_conversation_semantic_call_count = 0
        self.search_corpus_semantic_call_count = 0
        self.search_semantic_evidence_kwargs: list[dict[str, Any]] = []

    def search_semantic_evidence(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_semantic_evidence_call_count += 1
        self.search_semantic_evidence_kwargs.append(dict(kwargs))
        return []

    def search_conversation_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_conversation_semantic_call_count += 1
        return []

    def search_corpus_semantic(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_corpus_semantic_call_count += 1
        return []

    def search_corpus_semantic_with_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.search_corpus_semantic_call_count += 1
        return {
            "status": "idle",
            "reason": "spy semantic corpus search",
            "rows": [],
            "error_kind": "",
            "fallback_used": False,
            "followup_skipped": 0,
        }


class BackendCallSpyStore(SemanticSpyStore):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.backend_calls: dict[str, int] = {
            "list_profile_items": 0,
            "search_profile": 0,
            "search_continuity": 0,
            "recent_continuity": 0,
            "search_transcript": 0,
            "search_transcript_global": 0,
            "search_operating_records": 0,
            "search_graph": 0,
            "search_corpus": 0,
        }

    def _record(self, name: str) -> None:
        self.backend_calls[name] = self.backend_calls.get(name, 0) + 1

    def list_profile_items(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("list_profile_items")
        return super().list_profile_items(*args, **kwargs)

    def search_profile(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_profile")
        return super().search_profile(*args, **kwargs)

    def search_continuity(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_continuity")
        return super().search_continuity(*args, **kwargs)

    def recent_continuity(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("recent_continuity")
        return super().recent_continuity(*args, **kwargs)

    def search_transcript(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_transcript")
        return super().search_transcript(*args, **kwargs)

    def search_transcript_global(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_transcript_global")
        return super().search_transcript_global(*args, **kwargs)

    def search_operating_records(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_operating_records")
        return super().search_operating_records(*args, **kwargs)

    def search_graph(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_graph")
        return super().search_graph(*args, **kwargs)

    def search_corpus(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self._record("search_corpus")
        return super().search_corpus(*args, **kwargs)


def _policy_from_route_plan(plan: dict[str, Any]) -> dict[str, Any]:
    semantic = plan.get("semantic_retrieval") if isinstance(plan.get("semantic_retrieval"), dict) else {}
    control_plan = retrieval_control_plan_from_adaptive_plan(plan)
    return {
        **route_plan_limit_overrides(plan),
        "show_authoritative_contract": False,
        "evidence_item_budget": route_plan_limit_overrides(plan)["evidence_item_budget"],
        "semantic_evidence_enabled": bool(semantic.get("enabled")),
        "semantic_evidence_reason": str(semantic.get("reason") or "route_gated"),
        "retrieval_control_plan": control_plan.to_public_dict(),
    }


def _retrieve_with_route_plan(store: BackendCallSpyStore, plan: dict[str, Any], *, query: str = "structured route request") -> dict[str, Any]:
    return retrieve_executive_context(
        store,
        query=query,
        session_id="session:test",
        principal_scope_key="principal:test",
        analysis={"profile_slot_targets": (), "task_lookup": None, "operating_lookup": None, "route_payload": None},
        policy=_policy_from_route_plan(plan),
        route_resolver=lambda _query: route_plan_resolver_payload(plan),
    )


def _build_spy_packet(store: SemanticSpyStore, *, signals: dict[str, Any]) -> dict[str, Any]:
    return build_working_memory_packet(
        store,
        query="structured route request",
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
        adaptive_route_signals=signals,
    )


def test_build_working_memory_packet_route_gates_semantic_backend_calls_for_simple_routes(tmp_path: Path) -> None:
    simple_cases = [
        {"memory_intent": "none"},
        {"profile_slot_targets": ["identity.name"]},
        {"route_payload": {"route_class": "current_truth"}},
        {"required_evidence_classes": ["operating"]},
    ]
    for index, signals in enumerate(simple_cases):
        store = SemanticSpyStore(str(tmp_path / f"brainstack-{index}.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            packet = _build_spy_packet(store, signals=signals)

            assert packet["adaptive_route_plan"]["semantic_retrieval"]["enabled"] is False
            assert store.search_semantic_evidence_call_count == 0
            assert store.search_conversation_semantic_call_count == 0
            assert store.search_corpus_semantic_call_count == 0
        finally:
            store.close()


def test_build_working_memory_packet_preserves_semantic_backend_calls_for_deep_routes(tmp_path: Path) -> None:
    store = SemanticSpyStore(str(tmp_path / "brainstack-deep.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        packet = _build_spy_packet(
            store,
            signals={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
        )

        assert packet["adaptive_route_plan"]["semantic_retrieval"]["enabled"] is True
        assert store.search_semantic_evidence_call_count >= 1
    finally:
        store.close()


def test_retrieval_control_plan_scopes_semantic_evidence_store_call_to_allowed_shelves(tmp_path: Path) -> None:
    store = SemanticSpyStore(str(tmp_path / "brainstack-corpus.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        packet = _build_spy_packet(store, signals={"required_evidence_classes": ["corpus"]})

        assert packet["adaptive_route_plan"]["route_class"] == "corpus"
        assert packet["retrieval_control_plan"]["semantic_allowed_shelves"] == ("corpus",)
        assert store.search_semantic_evidence_call_count == 1
        assert store.search_semantic_evidence_kwargs[-1]["shelves"] == ("corpus",)
        assert store.search_conversation_semantic_call_count == 0
        assert store.search_corpus_semantic_call_count >= 1
    finally:
        store.close()


def test_retrieval_control_plan_id_is_shared_by_packet_policy_and_channels(tmp_path: Path) -> None:
    store = SemanticSpyStore(str(tmp_path / "brainstack-plan-id.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        packet = _build_spy_packet(store, signals={"required_evidence_classes": ["corpus"]})

        plan_id = packet["retrieval_control_plan"]["plan_id"]
        assert plan_id
        assert packet["adaptive_route_plan"]["plan_id"] == plan_id
        assert packet["policy"]["adaptive_route_plan"]["plan_id"] == plan_id
        assert packet["policy"]["retrieval_control_plan"]["plan_id"] == plan_id
        assert {channel["plan_id"] for channel in packet["channels"]} == {plan_id}
    finally:
        store.close()


def test_retrieval_control_plan_skips_unbudgeted_shelf_backend_calls_before_packet_budget(tmp_path: Path) -> None:
    cases = [
        {
            "signals": {"memory_intent": "none"},
            "query": "",
            "zero_calls": (
                "list_profile_items",
                "search_profile",
                "search_continuity",
                "recent_continuity",
                "search_transcript",
                "search_transcript_global",
                "search_operating_records",
                "search_graph",
                "search_corpus",
            ),
        },
        {
            "signals": {"profile_slot_targets": ["identity.name"]},
            "zero_calls": (
                "list_profile_items",
                "search_continuity",
                "recent_continuity",
                "search_transcript",
                "search_transcript_global",
                "search_operating_records",
                "search_graph",
                "search_corpus",
            ),
        },
        {
            "signals": {"route_payload": {"route_class": "current_truth"}},
            "zero_calls": (
                "list_profile_items",
                "search_continuity",
                "recent_continuity",
                "search_transcript",
                "search_transcript_global",
                "search_operating_records",
                "search_graph",
                "search_corpus",
            ),
        },
        {
            "signals": {"required_evidence_classes": ["operating"]},
            "zero_calls": (
                "list_profile_items",
                "search_profile",
                "search_continuity",
                "recent_continuity",
                "search_transcript",
                "search_transcript_global",
                "search_graph",
                "search_corpus",
            ),
        },
    ]
    for index, case in enumerate(cases):
        store = BackendCallSpyStore(str(tmp_path / f"budget-{index}.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
        store.open()
        try:
            plan = build_adaptive_route_plan(
                str(case.get("query", "structured route request")),
                query_understanding=case["signals"],
                current_truth_view=_current_truth_view(1),
            )
            result = _retrieve_with_route_plan(store, plan, query=str(case.get("query", "structured route request")))

            assert plan["shelf_budget"]["applied_before_packet_render_budget"] is True
            assert result["channels"]
            assert store.search_semantic_evidence_call_count == 0
            assert store.search_conversation_semantic_call_count == 0
            assert store.search_corpus_semantic_call_count == 0
            for call_name in case["zero_calls"]:
                assert store.backend_calls[call_name] == 0, (plan["route_class"], call_name, store.backend_calls)
        finally:
            store.close()


def test_retrieval_control_plan_keeps_backend_calls_for_deep_supported_routes(tmp_path: Path) -> None:
    store = BackendCallSpyStore(str(tmp_path / "budget-deep.sqlite3"), graph_backend="sqlite", corpus_backend="sqlite")
    store.open()
    try:
        plan = build_adaptive_route_plan(
            "structured deep route request",
            query_understanding={"required_evidence_classes": ["temporal_graph", "corpus", "continuity"]},
            current_truth_view=_current_truth_view(0),
        )
        _retrieve_with_route_plan(store, plan, query="structured deep route request")

        assert plan["route_class"] == "deep_mixed"
        assert plan["shelf_budget"]["backend_call_budget_total"] > 0
        assert store.search_semantic_evidence_call_count >= 1
        assert store.backend_calls["search_graph"] >= 1
        assert store.backend_calls["search_corpus"] >= 1
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
