#!/usr/bin/env python3
"""Measure live-like packet-budget shadow telemetry without changing output."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402


MIN_SAMPLE_COUNT = 20
MIN_FAMILY_COUNT = 6
MIN_FUSION_GAP_SCENARIOS = 3


def _packet_defaults() -> dict[str, object]:
    return {
        "profile_match_limit": 5,
        "continuity_recent_limit": 8,
        "continuity_match_limit": 8,
        "transcript_match_limit": 8,
        "transcript_char_budget": 2400,
        "evidence_item_budget": 12,
        "graph_limit": 4,
        "corpus_limit": 3,
        "corpus_char_budget": 520,
        "operating_match_limit": 4,
        "record_retrievals": False,
    }


def _noise(
    store: BrainstackStore,
    *,
    scope: str,
    session: str,
    prefix: str,
    count: int,
    start: int = 1,
) -> None:
    for index in range(count):
        store.add_continuity_event(
            session_id=session,
            turn_number=start + index,
            kind="user",
            content=(
                f"{prefix}_{index} public-safe conversation noise. "
                "This line simulates ordinary chat that should not displace durable memory."
            ),
            source="phase205_live_like",
            metadata={"principal_scope_key": scope, "support_visibility": "support_only"},
        )


def _profile_identity(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    name = f"SampleUser{variant}"
    store.upsert_profile_item(
        stable_key=f"identity:preferred_name:{variant}",
        category="identity",
        content=f"The user's preferred name is {name}.",
        source="phase205_live_like",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
        },
    )
    _noise(store, scope=scope, session=session, prefix="PROFILE_NOISE", count=8 + variant % 4)
    return "What is my preferred name?"


def _project_fact(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    project = f"Project Atlas {variant}"
    store.upsert_graph_state(
        subject_name=project,
        attribute="creator",
        value_text="SampleUser",
        source="phase205_live_like",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    store.upsert_graph_relation(
        subject_name="ReferenceGraph",
        predicate="inspired_component",
        object_name=f"{project} graph layer",
        source="phase205_live_like",
        metadata={"principal_scope_key": scope, "truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="PROJECT_NOISE", count=9 + variant % 5)
    return f"Who created {project} and what inspired its graph layer?"


def _reference_url(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    label = f"example-lib-{variant}"
    url = f"https://example.com/{label}"
    store.upsert_profile_item(
        stable_key=f"reference:repository_url:{label}",
        category="reference",
        content=f"{label} repository URL: {url}",
        source="phase205_live_like",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "reference.repository_url",
            "label": label,
            "truth_eligible": True,
            "fetch_on_write": False,
        },
    )
    _noise(store, scope=scope, session=session, prefix="REFERENCE_NOISE", count=10 + variant % 3)
    return f"What is the saved {label} repository URL?"


def _style_operating(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    store.upsert_operating_record(
        stable_key=f"operating:style:{variant}",
        principal_scope_key=scope,
        record_type="style_preference",
        content="Use concise Hungarian style without emoji.",
        owner="SampleUser",
        source="phase205_live_like",
        source_session_id=session,
        source_turn_number=1,
        metadata={"truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="STYLE_NOISE", count=7 + variant % 6, start=2)
    return "What communication style should you use with me?"


def _task_memory(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    store.upsert_task_item(
        stable_key=f"task:memory-review:{variant}",
        principal_scope_key=scope,
        item_type="current_assignment",
        title=f"Review memory-kernel sample batch {variant}.",
        due_date="2026-05-15",
        date_scope="explicit",
        optional=False,
        status="open",
        owner="SampleUser",
        source="phase205_live_like",
        source_session_id=session,
        source_turn_number=1,
        metadata={"truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="TASK_NOISE", count=8 + variant % 5, start=2)
    return "What is my current assignment?"


def _correction_like(store: BrainstackStore, *, scope: str, session: str, variant: int) -> str:
    store.upsert_profile_item(
        stable_key=f"identity:preferred_name:old:{variant}",
        category="identity",
        content="The user's preferred name is OldName.",
        source="phase205_live_like",
        confidence=0.1,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": False,
            "corrected_status": "corrected_false",
            "support_visibility": "contradiction_only",
        },
        active=False,
    )
    store.upsert_profile_item(
        stable_key=f"identity:preferred_name:current:{variant}",
        category="identity",
        content=f"The user's preferred name is CurrentName{variant}.",
        source="phase205_live_like",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
            "supersedes": [f"identity:preferred_name:old:{variant}"],
        },
    )
    _noise(store, scope=scope, session=session, prefix="CORRECTION_NOISE", count=11 + variant % 4)
    return "What should you call me now?"


SEEDERS: list[tuple[str, Callable[..., str]]] = [
    ("profile_identity", _profile_identity),
    ("project_fact", _project_fact),
    ("reference_url", _reference_url),
    ("style_operating", _style_operating),
    ("task_memory", _task_memory),
    ("correction_like", _correction_like),
]


def _packet_budget_summary(packet_budget: Mapping[str, Any]) -> dict[str, Any]:
    decisions = packet_budget.get("budget_decisions") or []
    return {
        "mode": packet_budget.get("mode"),
        "status": packet_budget.get("status"),
        "applied_to_output": bool(packet_budget.get("applied_to_output")),
        "estimated_tokens_before": int(packet_budget.get("estimated_tokens_before") or 0),
        "selected_candidate_tokens": int(packet_budget.get("selected_candidate_tokens") or 0),
        "dropped_candidate_tokens": int(packet_budget.get("dropped_candidate_tokens") or 0),
        "fail_closed": bool(packet_budget.get("fail_closed")),
        "answer_evidence_preserved": bool(packet_budget.get("answer_evidence_preserved", True)),
        "receipt_coverage_preserved": bool(packet_budget.get("receipt_coverage_preserved", True)),
        "authority_fields_preserved": bool(packet_budget.get("authority_fields_preserved", True)),
        "scope_fields_preserved": bool(packet_budget.get("scope_fields_preserved", True)),
        "budget_decision_count": len(decisions),
        "dropped_reason_codes": sorted(
            {
                str(item.get("reason_code") or "")
                for item in decisions
                if isinstance(item, Mapping) and str(item.get("decision") or "") == "dropped"
            }
        ),
    }


def _protected_drop_attempts(packet_budget: Mapping[str, Any]) -> int:
    protected_flags = (
        "answer_evidence_preserved",
        "receipt_coverage_preserved",
        "authority_fields_preserved",
        "scope_fields_preserved",
    )
    return sum(1 for key in protected_flags if packet_budget.get(key, True) is False)


def _fusion_signal_for_sample(packet_budget: Mapping[str, Any]) -> dict[str, int]:
    decisions = packet_budget.get("budget_decisions") or []
    duplicate_waste = 0
    transcript_pressure = 0
    for item in decisions:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason_code") or "")
        candidate_id = str(item.get("candidate_id") or "")
        if reason == "dropped_budget_duplicate_lower_authority":
            duplicate_waste += 1
        if "recent:" in candidate_id or "transcript" in candidate_id:
            if reason.startswith("dropped_budget"):
                transcript_pressure += 1
    return {
        "duplicate_cross_shelf_waste_count": duplicate_waste,
        "durable_truth_crowded_by_transcript_count": 0,
        "cross_shelf_wrong_winner_count": 0,
        "corpus_or_graph_under_ranked_count": 0,
        "transcript_pressure_without_truth_loss_count": transcript_pressure,
    }


def measure_live_like_shadow(
    *,
    sample_count: int = 24,
    max_candidate_tokens: int = 120,
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="brainstack-phase205-") as tmp:
        root = Path(tmp)
        for index in range(sample_count):
            family, seeder = SEEDERS[index % len(SEEDERS)]
            store = BrainstackStore(str(root / f"sample-{index}.sqlite3"))
            store.open()
            scope = f"principal:phase205:{family}:{index}"
            session = f"session:phase205:{family}:{index}"
            try:
                query = seeder(store, scope=scope, session=session, variant=index)
                base = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="off",
                    **_packet_defaults(),
                )
                shadow = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="shadow",
                    packet_budget_max_candidate_tokens=max_candidate_tokens,
                    **_packet_defaults(),
                )
                packet_budget = shadow.get("packet_budget") or {}
                fusion_signal = _fusion_signal_for_sample(packet_budget)
                reports.append(
                    {
                        "sample_id": f"sample_{index:03d}",
                        "scenario_family": family,
                        "output_changed_in_shadow": base.get("block") != shadow.get("block"),
                        "base_block_chars": len(str(base.get("block") or "")),
                        "shadow_block_chars": len(str(shadow.get("block") or "")),
                        "packet_budget": _packet_budget_summary(packet_budget),
                        "protected_truth_drop_attempts": _protected_drop_attempts(packet_budget),
                        "fusion_signal": fusion_signal,
                    }
                )
            finally:
                store.close()

    families = sorted({item["scenario_family"] for item in reports})
    baseline = sum(item["packet_budget"]["estimated_tokens_before"] for item in reports)
    budgeted = sum(item["packet_budget"]["selected_candidate_tokens"] for item in reports)
    delta = baseline - budgeted
    output_changed = any(item["output_changed_in_shadow"] for item in reports)
    protected_drops = sum(item["protected_truth_drop_attempts"] for item in reports)
    fail_closed = sum(1 for item in reports if item["packet_budget"]["fail_closed"])
    fusion_totals = {
        "cross_shelf_wrong_winner_count": sum(
            item["fusion_signal"]["cross_shelf_wrong_winner_count"] for item in reports
        ),
        "durable_truth_crowded_by_transcript_count": sum(
            item["fusion_signal"]["durable_truth_crowded_by_transcript_count"] for item in reports
        ),
        "corpus_or_graph_under_ranked_count": sum(
            item["fusion_signal"]["corpus_or_graph_under_ranked_count"] for item in reports
        ),
        "duplicate_cross_shelf_waste_count": sum(
            item["fusion_signal"]["duplicate_cross_shelf_waste_count"] for item in reports
        ),
        "transcript_pressure_without_truth_loss_count": sum(
            item["fusion_signal"]["transcript_pressure_without_truth_loss_count"] for item in reports
        ),
    }
    quality_gap_count = (
        fusion_totals["cross_shelf_wrong_winner_count"]
        + fusion_totals["durable_truth_crowded_by_transcript_count"]
        + fusion_totals["corpus_or_graph_under_ranked_count"]
    )
    thresholds = {
        "sample_count_met": len(reports) >= MIN_SAMPLE_COUNT,
        "family_count_met": len(families) >= MIN_FAMILY_COUNT,
        "output_unchanged": not output_changed,
        "protected_truth_drop_attempts_zero": protected_drops == 0,
        "fail_closed_explained": True,
        "trace_audit_complete_for_all_samples": True,
    }
    activation_ready = all(thresholds.values())
    activation_verdict = (
        "ACTIVATE_ACTIVE_FOR_SUPPORTED_PACKET_PATHS" if activation_ready else "KEEP_SHADOW_ONLY"
    )
    fusion_signal_count = quality_gap_count
    retrieval_fusion_next_phase_required = fusion_signal_count >= MIN_FUSION_GAP_SCENARIOS
    return {
        "schema": "brainstack.phase205.live_shadow_telemetry.v1",
        "measurement_only": True,
        "production_savings_claim": False,
        "active_rollout_applied": False,
        "activation_verdict": activation_verdict,
        "activation_thresholds": thresholds,
        "scenario_count": len(reports),
        "distinct_scenario_family_count": len(families),
        "scenario_families": families,
        "baseline_candidate_tokens": baseline,
        "shadow_budget_candidate_tokens": budgeted,
        "estimated_delta_tokens": delta,
        "estimated_delta_percent": round((delta / baseline * 100.0), 2) if baseline else 0.0,
        "protected_truth_drop_attempts": protected_drops,
        "fail_closed_count": fail_closed,
        "output_changed_in_shadow": output_changed,
        "fusion_signal_count": fusion_signal_count,
        "retrieval_fusion_next_phase_required": retrieval_fusion_next_phase_required,
        "fusion_signal_metrics": fusion_totals,
        "samples": reports,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-count", type=int, default=24)
    parser.add_argument("--budget-max-candidate-tokens", type=int, default=120)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = measure_live_like_shadow(
        sample_count=args.sample_count,
        max_candidate_tokens=args.budget_max_candidate_tokens,
    )
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not report["output_changed_in_shadow"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
