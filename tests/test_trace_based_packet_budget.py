from __future__ import annotations

import random
from pathlib import Path

from brainstack.core.packet_budget import (
    BUDGET_STATUS_APPLIED,
    BUDGET_STATUS_INSUFFICIENT_AUTHORITY,
    PacketBudgetPolicy,
    apply_packet_budget,
    build_budgeted_evidence_trace,
    validate_packet_budget_trace,
)
from brainstack.core.reason_codes import ReasonCode
from brainstack.core.trace import (
    AUTHORITY_RECEIPT_BACKED,
    AUTHORITY_SUPPORT_ONLY,
    DECISION_SELECTED,
    build_evidence_trace,
    make_evidence_candidate,
)
from scripts.run_public_memory_kernel_fixtures import (
    run_fixture_directory,
    run_negative_fixtures,
)

FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def _receipt_candidate(candidate_id: str, token_estimate: int = 8) -> dict[str, object]:
    return make_evidence_candidate(
        candidate_id=candidate_id,
        shelf="profile",
        target_slot="identity.preferred_address_name",
        source_role="user",
        authority=AUTHORITY_RECEIPT_BACKED,
        decision=DECISION_SELECTED,
        reason_code=ReasonCode.SELECTED_RECEIPT_BACKED_FACT.value,
        source_event_id=f"event-{candidate_id}",
        source_span_id=f"span-{candidate_id}",
        proposal_id=f"cap-{candidate_id}",
        admission_id=f"adm-{candidate_id}",
        receipt_id=f"mwr-{candidate_id}",
        truth_eligible=True,
        model_facing_allowed=True,
        answer_evidence_allowed=True,
        raw_value="Alex",
        token_estimate=token_estimate,
    )


def _support_candidate(candidate_id: str, token_estimate: int = 10) -> dict[str, object]:
    return make_evidence_candidate(
        candidate_id=candidate_id,
        shelf="transcript",
        source_role="user",
        authority=AUTHORITY_SUPPORT_ONLY,
        decision=DECISION_SELECTED,
        reason_code=ReasonCode.ONLY_SUPPORTING_CONTEXT.value,
        source_event_id=f"event-{candidate_id}",
        source_span_id=f"span-{candidate_id}",
        truth_eligible=False,
        model_facing_allowed=True,
        answer_evidence_allowed=False,
        raw_value="Support-only context.",
        token_estimate=token_estimate,
    )


def test_packet_budget_preserves_receipt_backed_evidence_under_pressure() -> None:
    candidates = [
        _receipt_candidate("ev_receipt", token_estimate=8),
        _support_candidate("ev_support", token_estimate=12),
    ]

    result = apply_packet_budget(
        candidates,
        PacketBudgetPolicy(max_candidate_tokens=8),
    )

    assert result.status == BUDGET_STATUS_APPLIED
    selected = [item["candidate_id"] for item in result.candidates if item["decision"] == "selected"]
    dropped = {item["candidate_id"]: item["reason_code"] for item in result.candidates if item["decision"] == "dropped"}
    assert selected == ["ev_receipt"]
    assert dropped["ev_support"] == ReasonCode.DROPPED_BUDGET_SUPPORT_ONLY.value
    assert validate_packet_budget_trace({"candidates": result.candidates, "packet_budget": result.to_trace_packet_budget()}) == []


def test_packet_budget_fails_closed_when_authority_minimum_exceeds_cap() -> None:
    candidates = [
        _receipt_candidate("ev_receipt_a", token_estimate=8),
        _receipt_candidate("ev_receipt_b", token_estimate=8),
        _support_candidate("ev_support", token_estimate=4),
    ]

    result = apply_packet_budget(
        candidates,
        PacketBudgetPolicy(max_candidate_tokens=10),
    )

    assert result.status == BUDGET_STATUS_INSUFFICIENT_AUTHORITY
    assert result.fail_closed is True
    selected = [item["candidate_id"] for item in result.candidates if item["decision"] == "selected"]
    assert selected == ["ev_receipt_a", "ev_receipt_b"]
    dropped = {item["candidate_id"]: item["reason_code"] for item in result.candidates if item["decision"] == "dropped"}
    assert dropped["ev_support"] == ReasonCode.BUDGET_INSUFFICIENT_FOR_AUTHORITY_MINIMUM.value


def test_budgeted_trace_keeps_audit_completeness_and_budget_decisions() -> None:
    trace = build_evidence_trace(
        trace_id="trace-budget-unit",
        turn_id="turn-budget-unit",
        query_summary="Budget unit trace.",
        principal_scope_key="principal:public-alex",
        workspace_scope_key="workspace:public-memory",
        candidates=[
            _receipt_candidate("ev_receipt", token_estimate=8),
            _support_candidate("ev_support", token_estimate=9),
        ],
        receipt_coverage={"coverage_status": "complete"},
    )

    budgeted = build_budgeted_evidence_trace(trace=trace, max_candidate_tokens=8)

    assert budgeted["schema"] == "brainstack.evidence_trace.v1"
    assert budgeted["packet_budget"]["status"] == BUDGET_STATUS_APPLIED
    assert budgeted["packet_budget"]["selected_candidate_tokens"] == 8
    assert budgeted["packet_budget"]["dropped_candidate_tokens"] == 9
    assert budgeted["trace_completeness"]["complete_for_audit"] is True
    assert budgeted["packet_budget"]["budget_decisions"]


def test_public_budget_fixtures_pass_contracts() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    by_id = {item["scenario_id"]: item for item in result["scenarios"]}

    assert by_id["budget_support_noise_public_001"]["status"] == "pass"
    assert by_id["budget_duplicate_public_001"]["status"] == "pass"
    assert by_id["budget_authority_minimum_public_001"]["status"] == "pass"
    assert by_id["budget_authority_minimum_public_001"]["trace"]["packet_budget"]["fail_closed"] is True


def test_negative_budget_fixture_rejects_dropped_protected_evidence() -> None:
    result = run_negative_fixtures(FIXTURE_DIR)
    fixture = next(
        item
        for item in result["negative_fixtures"]
        if item["negative_id"] == "budget_protected_dropped"
    )

    assert fixture["status"] == "pass"
    assert "budget_dropped_authority_critical_evidence" in fixture["errors"]


def test_packet_budget_stress_never_drops_protected_evidence() -> None:
    rng = random.Random(196)
    for index in range(500):
        protected_count = rng.randint(1, 4)
        support_count = rng.randint(0, 8)
        protected = [
            _receipt_candidate(f"ev_p_{index}_{inner}", token_estimate=rng.randint(3, 12))
            for inner in range(protected_count)
        ]
        support = [
            _support_candidate(f"ev_s_{index}_{inner}", token_estimate=rng.randint(1, 18))
            for inner in range(support_count)
        ]
        candidates = [*protected, *support]
        rng.shuffle(candidates)
        authority_minimum = sum(int(item["token_estimate"]) for item in protected)
        budget = rng.randint(1, max(1, authority_minimum + 18))

        result = apply_packet_budget(
            candidates,
            PacketBudgetPolicy(max_candidate_tokens=budget),
        )

        selected_ids = {
            item["candidate_id"] for item in result.candidates if item["decision"] == "selected"
        }
        assert {item["candidate_id"] for item in protected}.issubset(selected_ids)
        assert validate_packet_budget_trace(
            {"candidates": result.candidates, "packet_budget": result.to_trace_packet_budget()}
        ) == []
        if authority_minimum > budget:
            assert result.fail_closed is True
            assert result.status == BUDGET_STATUS_INSUFFICIENT_AUTHORITY
        else:
            assert result.selected_candidate_tokens <= budget
