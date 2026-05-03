from __future__ import annotations

from copy import deepcopy

import pytest

from brainstack.current_truth_view import (
    CURRENT_TRUTH_VIEW_SCHEMA_VERSION,
    CURRENT_TRUTH_VIEW_PROJECTION_VERSION,
    CurrentTruthViewWriteError,
    rebuild_current_truth_view,
    validate_current_truth_view_public_safety,
    write_current_truth_view,
)
from scripts.verify_current_truth_view import build_report


FIXED_REBUILT_AT = "2026-05-03T12:00:00Z"


def _event(
    *,
    event_id: str = "cme_current_1",
    memory_kind: str = "profile",
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "receipt_1",
    source_event_id: str = "evt_current_1",
    source_span_id: str = "span_current_1",
    source_quote_hash: str = "sha256:quote_current_1",
    valid_to: str = "",
    superseded_by: str = "",
    projection_stale: bool = False,
    malformed_projection: bool = False,
    graph_ready: bool | None = None,
    principal_scope_key: str = "principal:a",
    transaction_time: str = "2026-05-03T11:59:00Z",
) -> dict:
    graph_kind = memory_kind in {"graph_relation", "graph_state", "temporal_event"}
    hints = {
        "graph_ready": graph_kind if graph_ready is None else graph_ready,
        "budget_ready": True,
        "multihop_ready": graph_kind,
    }
    event = {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": source_event_id,
            "source_span_id": source_span_id,
            "source_quote_hash": source_quote_hash,
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-05-03T11:58:59Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": principal_scope_key,
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": memory_kind,
            "target_slot": "profile.preferred_language",
            "subject_ref": "entity:user:laura",
            "predicate": "prefers_language",
            "object_ref": "entity:language:hu",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": "profile:preferred_language",
        },
        "authority": {
            "authority_class": "user_explicit",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.99,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": receipt_id,
        },
        "temporal": {
            "valid_from": "2026-05-03T11:58:00Z",
            "valid_to": valid_to,
            "transaction_time": transaction_time,
            "supersedes": [],
            "superseded_by": superseded_by,
        },
        "projection": {
            "entity_refs": ["entity:user:laura", "entity:language:hu"],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": "task_relevant",
            "authority_critical": truth_eligible,
            "projection_hints": hints,
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {},
    }
    if projection_stale:
        event["projection"]["freshness_status"] = "stale"
    if malformed_projection:
        event["projection"]["projection_hints"] = "not-a-mapping"
    return event


def test_current_truth_view_contract_is_rebuildable_public_safe_and_read_only() -> None:
    event = _event()
    event["extensions"] = {"debug.v1": {"raw_text": "private source text", "provider_secret": "secret"}}

    view = rebuild_current_truth_view([event], rebuilt_at=FIXED_REBUILT_AT)

    assert view["schema"] == CURRENT_TRUTH_VIEW_SCHEMA_VERSION
    assert view["status"] == "pass"
    assert view["contract"] == {
        "rebuildable_from_canonical_events": True,
        "second_write_authority": False,
        "durable_truth_writes": False,
        "admission_receipt_override": False,
        "raw_truth_write_api": False,
    }
    assert view["rebuild"]["projection_version"] == CURRENT_TRUTH_VIEW_PROJECTION_VERSION
    assert view["rebuild"]["rebuilt_at"] == FIXED_REBUILT_AT
    assert view["rebuild"]["freshness_status"] == "fresh"
    assert view["source_event_span"]["source_event_count"] == 1
    assert view["receipt_coverage"]["missing_receipt_count"] == 0
    assert len(view["current_truth_rows"]) == 1
    row = view["current_truth_rows"][0]
    assert row["event_id"] == "cme_current_1"
    assert row["stable_fact_id"] == "profile:preferred_language"
    assert row["answerable_current_truth"] is True
    assert row["source_event_id"] == "evt_current_1"
    assert row["source_span_id"] == "span_current_1"
    assert row["source_quote_hash"] == "sha256:quote_current_1"
    assert row["receipt_id"] == "receipt_1"
    assert "private source text" not in str(view)
    assert "secret" not in str(view)
    assert validate_current_truth_view_public_safety(view) == []

    with pytest.raises(CurrentTruthViewWriteError):
        write_current_truth_view({"stable_fact_id": "profile:preferred_language", "raw_value": "Hungarian"})


def test_current_truth_view_excludes_unsafe_rows_from_answer_truth() -> None:
    events = [
        _event(event_id="safe"),
        _event(event_id="expired", valid_to="2026-05-03T11:59:30Z"),
        _event(event_id="superseded", superseded_by="safe"),
        _event(event_id="conflict", event_type="conflict_opened", truth_eligible=False, support_visibility="contradiction_only", receipt_id=""),
        _event(event_id="missing_source", source_span_id=""),
        _event(event_id="missing_receipt", receipt_id=""),
        _event(event_id="support_only", event_type="support_event", truth_eligible=False, support_visibility="inspect_only", receipt_id=""),
        _event(event_id="stale_projection", projection_stale=True),
        _event(event_id="malformed_projection", malformed_projection=True),
    ]

    view = rebuild_current_truth_view(events, rebuilt_at=FIXED_REBUILT_AT)

    assert view["status"] == "pass"
    assert [row["event_id"] for row in view["current_truth_rows"]] == ["safe"]
    blocked_ids = {row["event_id"] for row in view["non_answerable_rows"]}
    assert {
        "expired",
        "superseded",
        "conflict",
        "missing_receipt",
        "support_only",
        "stale_projection",
        "malformed_projection",
    }.issubset(blocked_ids)
    issue_ids = {issue["event_id"] for issue in view["issues"]}
    assert "missing_source" in issue_ids
    assert view["counters"]["prior_count"] == 2
    assert view["counters"]["conflict_count"] == 1
    assert view["counters"]["missing_source_count"] >= 1
    assert view["counters"]["missing_receipt_count"] == 1
    assert view["counters"]["support_only_count"] >= 1
    assert view["counters"]["stale_projection_source_count"] == 1
    assert view["counters"]["malformed_projection_count"] == 1
    assert view["counters"]["unsafe_answer_truth_projection_count"] == 0


def test_current_truth_view_rebuild_is_deterministic_by_snapshot_hash() -> None:
    a = _event(event_id="a", principal_scope_key="principal:a")
    b = _event(event_id="b", principal_scope_key="principal:b")

    view_1 = rebuild_current_truth_view([b, a], rebuilt_at=FIXED_REBUILT_AT)
    view_2 = rebuild_current_truth_view([deepcopy(a), deepcopy(b)], rebuilt_at=FIXED_REBUILT_AT)

    assert view_1["deterministic_snapshot_hash"] == view_2["deterministic_snapshot_hash"]
    assert view_1["current_truth_rows"] == view_2["current_truth_rows"]
    assert view_1["non_answerable_rows"] == view_2["non_answerable_rows"]


def test_current_truth_view_fails_closed_when_cache_is_stale() -> None:
    view = rebuild_current_truth_view(
        [_event()],
        rebuilt_at="2026-05-03T11:00:00Z",
        checked_at=FIXED_REBUILT_AT,
        cache_max_age_seconds=60,
    )

    assert view["status"] == "fail"
    assert view["rebuild"]["freshness_status"] == "stale_cache"
    assert view["rebuild"]["freshness_diagnostics_present"] is True
    assert view["current_truth_rows"] == []
    assert view["non_answerable_rows"][0]["event_id"] == "cme_current_1"
    assert "current_truth_view_cache_stale" in view["non_answerable_rows"][0]["projection_reason_codes"]
    assert view["counters"]["stale_cache_serving_block_count"] == 1


def test_current_truth_view_keeps_deep_graph_path_available_for_temporal_and_conflict_cases() -> None:
    current_graph = _event(event_id="graph_current", memory_kind="graph_relation", graph_ready=True)
    prior_graph = _event(
        event_id="graph_prior",
        memory_kind="graph_relation",
        graph_ready=True,
        valid_to="2026-05-03T11:59:30Z",
    )
    conflict_graph = _event(
        event_id="graph_conflict",
        memory_kind="graph_relation",
        graph_ready=True,
        event_type="conflict_opened",
        truth_eligible=False,
        support_visibility="contradiction_only",
        receipt_id="",
    )

    view = rebuild_current_truth_view([conflict_graph, prior_graph, current_graph], rebuilt_at=FIXED_REBUILT_AT)

    assert view["status"] == "pass"
    assert view["deep_graph_path"]["available"] is True
    assert view["deep_graph_path"]["graph_projection_status"] == "pass"
    assert view["deep_graph_path"]["current_edge_count"] == 1
    assert view["deep_graph_path"]["prior_edge_count"] == 1
    assert view["deep_graph_path"]["inspect_only_edge_count"] == 1
    assert view["deep_graph_path"]["temporal_or_conflict_path_available"] is True
    assert view["deep_graph_path"]["current_truth_view_is_graph_authority"] is False


def test_current_truth_view_verifier_passes_baseline_and_fails_stale_or_mismatch_fixtures() -> None:
    baseline = build_report(fixture="baseline")
    stale = build_report(fixture="stale-cache")
    mismatch = build_report(fixture="mismatch")

    assert baseline["status"] == "pass"
    assert baseline["summary"]["current_truth_row_count"] == 1
    assert baseline["summary"]["unsafe_answer_truth_projection_count"] == 0
    assert baseline["summary"]["deep_graph_path_available"] is True
    assert baseline["summary"]["public_safe"] is True

    assert stale["status"] == "fail"
    assert "view_status_not_pass" in stale["failure_reasons"]
    assert stale["summary"]["freshness_status"] == "stale_cache"

    assert mismatch["status"] == "fail"
    assert "deterministic_rebuild_mismatch" in mismatch["failure_reasons"]
