#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from brainstack.current_truth_view import rebuild_current_truth_view, validate_current_truth_view_public_safety

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
) -> dict[str, Any]:
    graph_kind = memory_kind in {"graph_relation", "graph_state", "temporal_event"}
    hints = {
        "graph_ready": graph_kind if graph_ready is None else graph_ready,
        "budget_ready": True,
        "multihop_ready": graph_kind,
    }
    event: dict[str, Any] = {
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
            "subject_ref": "entity:user:example",
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
            "entity_refs": ["entity:user:example", "entity:language:hu"],
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


def _baseline_events() -> list[dict[str, Any]]:
    return [
        _event(event_id="safe_current", memory_kind="graph_relation", graph_ready=True),
        _event(event_id="expired_prior", memory_kind="graph_relation", graph_ready=True, valid_to="2026-05-03T11:59:30Z"),
        _event(event_id="superseded_prior", superseded_by="safe_current"),
        _event(
            event_id="conflict_visible",
            memory_kind="graph_relation",
            graph_ready=True,
            event_type="conflict_opened",
            truth_eligible=False,
            support_visibility="contradiction_only",
            receipt_id="",
        ),
        _event(event_id="missing_source", source_span_id=""),
        _event(event_id="missing_receipt", receipt_id=""),
        _event(
            event_id="support_only",
            event_type="support_event",
            truth_eligible=False,
            support_visibility="inspect_only",
            receipt_id="",
        ),
        _event(event_id="stale_projection_source", projection_stale=True),
        _event(event_id="malformed_projection", malformed_projection=True),
    ]


def _failure_reasons(view: Mapping[str, Any], *, deterministic_match: bool) -> list[str]:
    counters = view.get("counters") if isinstance(view.get("counters"), Mapping) else {}
    current_ids = {row.get("event_id") for row in view.get("current_truth_rows", []) if isinstance(row, Mapping)}
    reasons: list[str] = []
    if view.get("status") != "pass":
        reasons.append("view_status_not_pass")
    if not deterministic_match:
        reasons.append("deterministic_rebuild_mismatch")
    if counters.get("unsafe_answer_truth_projection_count") != 0:
        reasons.append("unsafe_answer_truth_projection")
    if counters.get("raw_text_leak_count") != 0:
        reasons.append("public_safety_leak")
    if view.get("public_safety", {}).get("public_safe") is not True:
        reasons.append("public_safety_not_pass")
    if current_ids != {"safe_current"}:
        reasons.append("unexpected_current_truth_rows")
    if counters.get("stale_projection_source_count") != 1:
        reasons.append("stale_projection_source_not_visible")
    if counters.get("missing_source_count", 0) < 1:
        reasons.append("missing_source_not_visible")
    if counters.get("missing_receipt_count", 0) < 1:
        reasons.append("missing_receipt_not_visible")
    if counters.get("malformed_projection_count") != 1:
        reasons.append("malformed_projection_not_visible")
    deep_graph = view.get("deep_graph_path") if isinstance(view.get("deep_graph_path"), Mapping) else {}
    if deep_graph.get("available") is not True or deep_graph.get("temporal_or_conflict_path_available") is not True:
        reasons.append("deep_graph_path_not_available")
    if view.get("rebuild", {}).get("freshness_diagnostics_present") is not True:
        reasons.append("freshness_diagnostics_missing")
    return reasons


def build_report(*, fixture: str = "baseline") -> dict[str, Any]:
    events = _baseline_events()
    checked_at = FIXED_REBUILT_AT
    rebuilt_at = FIXED_REBUILT_AT
    cache_max_age_seconds = 300
    if fixture == "stale-cache":
        rebuilt_at = "2026-05-03T11:00:00Z"
        cache_max_age_seconds = 60

    view_1 = rebuild_current_truth_view(
        events,
        rebuilt_at=rebuilt_at,
        checked_at=checked_at,
        cache_max_age_seconds=cache_max_age_seconds,
    )
    view_2 = rebuild_current_truth_view(
        list(reversed(events)),
        rebuilt_at=rebuilt_at,
        checked_at=checked_at,
        cache_max_age_seconds=cache_max_age_seconds,
    )
    deterministic_match = view_1.get("deterministic_snapshot_hash") == view_2.get("deterministic_snapshot_hash")
    if fixture == "mismatch":
        deterministic_match = False

    public_safety_issues = validate_current_truth_view_public_safety(view_1)
    failure_reasons = _failure_reasons(view_1, deterministic_match=deterministic_match)
    status = "pass" if not failure_reasons else "fail"
    return {
        "schema": "brainstack.current_truth_view_verifier.v1",
        "status": status,
        "fixture": fixture,
        "failure_reasons": failure_reasons,
        "deterministic_rebuild_match": deterministic_match,
        "current_truth_view": view_1,
        "public_safety_issues": public_safety_issues,
        "summary": {
            "current_truth_row_count": len(view_1.get("current_truth_rows", [])),
            "non_answerable_row_count": len(view_1.get("non_answerable_rows", [])),
            "issue_count": len(view_1.get("issues", [])),
            "freshness_status": view_1.get("rebuild", {}).get("freshness_status"),
            "unsafe_answer_truth_projection_count": view_1.get("counters", {}).get("unsafe_answer_truth_projection_count"),
            "stale_projection_source_count": view_1.get("counters", {}).get("stale_projection_source_count"),
            "missing_source_count": view_1.get("counters", {}).get("missing_source_count"),
            "missing_receipt_count": view_1.get("counters", {}).get("missing_receipt_count"),
            "malformed_projection_count": view_1.get("counters", {}).get("malformed_projection_count"),
            "deep_graph_path_available": view_1.get("deep_graph_path", {}).get("available"),
            "public_safe": view_1.get("public_safety", {}).get("public_safe"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Brainstack current-truth materialized view contract.")
    parser.add_argument("--out", type=Path, required=True, help="Path to write the public-safe JSON report.")
    parser.add_argument(
        "--fixture",
        choices=("baseline", "stale-cache", "mismatch"),
        default="baseline",
        help="Verifier fixture to run. Non-baseline fixtures intentionally fail.",
    )
    args = parser.parse_args()

    report = build_report(fixture=args.fixture)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
