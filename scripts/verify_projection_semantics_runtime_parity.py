#!/usr/bin/env python3
"""Verify projection semantics through the supported Brainstack Python runtime path."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.projection_inspect import build_projection_doctor_section, build_projection_inspect_report  # noqa: E402

RUNTIME_PARITY_SCHEMA_VERSION = "brainstack.projection_semantics_runtime_parity.v1"


def _event(
    *,
    event_id: str,
    event_type: str = "durable_fact_committed",
    truth_eligible: bool = True,
    support_visibility: str = "answer_evidence",
    receipt_id: str = "1",
    valid_to: str = "",
    authority_critical: bool = True,
    memory_kind: str = "graph_relation",
    target_slot: str = "project.created_by",
    predicate: str = "created_by",
) -> dict[str, Any]:
    return {
        "event": {
            "event_id": event_id,
            "schema_version": "brainstack.canonical_memory_event.v1",
            "event_type": event_type,
            "idempotency_key": f"sha256:{event_id}",
        },
        "source": {
            "source_event_id": f"evt_{event_id}",
            "source_span_id": f"span_{event_id}",
            "source_quote_hash": f"sha256:quote_{event_id}",
            "speaker": "user",
            "assertion_speaker": "user",
            "source_modality": "conversation",
            "observed_at": "2026-04-30T10:00:00Z",
        },
        "scope": {
            "tenant_id": "local",
            "principal_scope_key": "principal:a",
            "workspace_scope_key": "workspace:a",
            "session_id": "session:a",
        },
        "claim": {
            "memory_kind": memory_kind,
            "target_slot": target_slot,
            "subject_ref": f"entity:subject:{event_id}",
            "predicate": predicate,
            "object_ref": f"entity:object:{event_id}",
            "normalized_value_hash": f"sha256:value_{event_id}",
            "stable_fact_id": f"stable:{event_id}",
        },
        "authority": {
            "authority_class": "user_explicit" if truth_eligible else "support_only",
            "truth_eligible": truth_eligible,
            "support_visibility": support_visibility,
            "confidence": 0.99,
            "admission_decision_id": f"adm_{event_id}",
            "receipt_id": receipt_id,
        },
        "temporal": {
            "valid_from": "2026-04-30T10:00:00Z",
            "valid_to": valid_to,
            "transaction_time": "2026-04-30T10:00:01Z",
            "supersedes": [],
            "superseded_by": "",
        },
        "projection": {
            "entity_refs": [f"entity:subject:{event_id}", f"entity:object:{event_id}"],
            "relation_refs": [f"rel:{event_id}"],
            "budget_class": "task_relevant",
            "authority_critical": authority_critical,
            "projection_hints": {"graph_ready": True, "budget_ready": True, "multihop_ready": True},
        },
        "trace": {
            "proposal_id": f"proposal_{event_id}",
            "donor_trace": {"donor": "hindsight", "donor_version": "test"},
            "policy_versions": {"admission": "test", "slot_registry": "test"},
        },
        "extensions": {"debug.v1": {"raw_text": "private source text should never appear"}},
    }


def _brainstack_stats_stale_correction_events() -> list[dict[str, Any]]:
    """Public-safe fixture for old-large vs new-compact diagnostics recall."""

    stable_fact_id = "stable:brainstack_stats_output_shape"
    old_support = _event(
        event_id="brainstack_stats_old_large_support",
        event_type="support_event",
        truth_eligible=False,
        support_visibility="normal",
        receipt_id="",
        authority_critical=False,
        memory_kind="runtime_diagnostic",
        target_slot="brainstack_stats.output_shape",
        predicate="diagnostic_shape",
    )
    old_support["claim"]["stable_fact_id"] = stable_fact_id
    old_support["claim"]["normalized_value_hash"] = "sha256:brainstack_stats_old_large_diagnostic_support"
    old_support["temporal"]["valid_to"] = "2026-05-03T17:57:26Z"
    old_support["trace"]["donor_trace"] = {
        "donor": "hindsight",
        "donor_version": "scoped-continuity-support",
    }

    new_truth = _event(
        event_id="brainstack_stats_new_compact_truth",
        event_type="durable_fact_committed",
        truth_eligible=True,
        support_visibility="answer_evidence",
        receipt_id="20260503_175726_6b58b81c:write:1",
        authority_critical=True,
        memory_kind="runtime_diagnostic",
        target_slot="brainstack_stats.output_shape",
        predicate="diagnostic_shape",
    )
    new_truth["claim"]["stable_fact_id"] = stable_fact_id
    new_truth["claim"]["normalized_value_hash"] = "sha256:brainstack_stats_new_compact_diagnostic_truth"

    return [old_support, new_truth]


def _public_safe(value: Any) -> bool:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True)
    return "private source text" not in payload and '"raw_text"' not in payload and '"raw_private_text"' not in payload


def verify_runtime_parity() -> dict[str, Any]:
    events = [
        _event(event_id="truth_a"),
        _event(event_id="truth_b"),
        _event(
            event_id="support",
            event_type="support_event",
            truth_eligible=False,
            support_visibility="normal",
            receipt_id="",
            authority_critical=False,
        ),
        _event(
            event_id="conflict",
            event_type="conflict_opened",
            truth_eligible=False,
            support_visibility="contradiction_only",
            receipt_id="",
            authority_critical=False,
        ),
        _event(event_id="prior", valid_to="2026-04-30T12:00:00Z"),
        _event(event_id="missing_receipt", event_type="proposal_accepted", receipt_id=""),
        *_brainstack_stats_stale_correction_events(),
    ]
    inspect = build_projection_inspect_report(events, max_packet_tokens=10)
    doctor = build_projection_doctor_section(
        {
            "status": inspect["conformance_status"],
            "surface_status": inspect["surface_status"],
            "critical_counters": inspect["critical_counters"],
            "event_semantics": [],
            "issues": inspect["issues"],
        }
    )
    selected_events = {
        item["event_id"]
        for item in inspect["event_explanations"]
        if item["surface_actions"].get("packet") == "selected"
    }
    unsafe_selected = [
        item["event_id"]
        for item in inspect["event_explanations"]
        if item["answer_decision"] != "answer_safe" and item["surface_actions"].get("packet") == "selected"
    ]
    explanations = {
        item["event_id"]: item
        for item in inspect["event_explanations"]
    }
    stale_old = explanations.get("brainstack_stats_old_large_support", {})
    stale_new = explanations.get("brainstack_stats_new_compact_truth", {})
    stale_fixture = {
        "old_event_id": "brainstack_stats_old_large_support",
        "old_answer_decision": stale_old.get("answer_decision"),
        "old_labels": list(stale_old.get("labels") or []),
        "old_packet_action": dict(stale_old.get("surface_actions") or {}).get("packet"),
        "new_event_id": "brainstack_stats_new_compact_truth",
        "new_answer_decision": stale_new.get("answer_decision"),
        "new_labels": list(stale_new.get("labels") or []),
        "new_packet_action": dict(stale_new.get("surface_actions") or {}).get("packet"),
        "new_receipt_id": "20260503_175726_6b58b81c:write:1",
    }
    counters = dict(inspect.get("critical_counters") or {})
    public_safe = _public_safe(inspect) and _public_safe(doctor)
    status = "pass"
    issues: list[str] = []
    if inspect.get("verdict") != "pass":
        issues.append("inspect_verdict_not_pass")
    if doctor.get("status") != "active":
        issues.append("doctor_status_not_active")
    if unsafe_selected:
        issues.append("unsafe_packet_selected")
    if counters.get("packet_authority_critical_dropped"):
        issues.append("authority_critical_dropped")
    if selected_events != {"truth_a", "truth_b", "brainstack_stats_new_compact_truth"}:
        issues.append("selected_event_set_mismatch")
    if stale_old.get("answer_decision") != "not_answer_safe":
        issues.append("stale_fixture_old_support_answer_safe")
    if dict(stale_old.get("surface_actions") or {}).get("packet") == "selected":
        issues.append("stale_fixture_old_support_selected")
    if stale_new.get("answer_decision") != "answer_safe":
        issues.append("stale_fixture_new_truth_not_answer_safe")
    if dict(stale_new.get("surface_actions") or {}).get("packet") != "selected":
        issues.append("stale_fixture_new_truth_not_selected")
    if not public_safe:
        issues.append("public_safety_failed")
    if issues:
        status = "fail"
    return {
        "schema": RUNTIME_PARITY_SCHEMA_VERSION,
        "status": status,
        "issues": issues,
        "runtime_path": "brainstack.projection_inspect -> projection_conformance -> graphiti/mempalace/multihop/packet_budget",
        "inspect_verdict": inspect.get("verdict"),
        "doctor_status": doctor.get("status"),
        "conformance_status": inspect.get("conformance_status"),
        "surface_status": dict(inspect.get("surface_status") or {}),
        "critical_counters": counters,
        "event_count": len(inspect.get("event_explanations") or []),
        "selected_event_ids": sorted(selected_events),
        "unsafe_selected_event_ids": unsafe_selected,
        "stale_correction_fixture": stale_fixture,
        "public_safe": public_safe,
        "doctor": doctor,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = verify_runtime_parity()
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
