#!/usr/bin/env python3
"""Run public-safe packet-budget soak across messy memory scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from statistics import quantiles
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from brainstack.control_plane import build_working_memory_packet  # noqa: E402
from brainstack.db import BrainstackStore  # noqa: E402

from scripts.measure_packet_budget_live_shadow_telemetry import (  # noqa: E402
    SEEDERS as PHASE205_SEEDERS,
    _fusion_signal_for_sample,
    _noise,
    _packet_budget_summary,
    _packet_defaults,
    _protected_drop_attempts,
)

MIN_SOAK_SAMPLE_COUNT = 100
MIN_SOAK_FAMILY_COUNT = 10
PRIVATE_LEAK_PATTERNS = (
    re.compile(r"\bTomi\b", re.IGNORECASE),
    re.compile(r"\bLauraTom\b", re.IGNORECASE),
    re.compile(r"\bNevaMind\b", re.IGNORECASE),
    re.compile(r"\bmemU\b", re.IGNORECASE),
    re.compile(r"\bHelyrecs\b", re.IGNORECASE),
    re.compile(r"github\\.com/NevaMind-AI", re.IGNORECASE),
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_fingerprint(payload: Mapping[str, Any]) -> str:
    return _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _metadata(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = candidate.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _candidate_is_protected(candidate: Mapping[str, Any]) -> bool:
    metadata = _metadata(candidate)
    shelf = str(candidate.get("shelf") or "")
    if metadata.get("truth_eligible") is True:
        return True
    if candidate.get("authority_floor_applied") is True:
        return True
    if int(candidate.get("authority_floor") or 0) >= 100:
        return True
    return shelf in {"profile", "task", "operating", "graph"} and metadata.get(
        "support_visibility"
    ) != "support_only"


def _protected_selected_fingerprints(packet: Mapping[str, Any]) -> list[str]:
    fingerprints: list[str] = []
    for candidate in packet.get("fused_candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        if str(candidate.get("selection_status") or "") != "selected":
            continue
        if not _candidate_is_protected(candidate):
            continue
        metadata = _metadata(candidate)
        content = str(candidate.get("content") or candidate.get("value_text") or "")
        fingerprints.append(
            _json_fingerprint(
                {
                    "shelf": candidate.get("shelf"),
                    "key": candidate.get("key"),
                    "stable_key": candidate.get("stable_key"),
                    "category": candidate.get("category"),
                    "target_slot": metadata.get("target_slot"),
                    "record_type": candidate.get("record_type"),
                    "attribute": candidate.get("attribute"),
                    "content_hash": _sha256_text(content),
                }
            )
        )
    return sorted(set(fingerprints))


def _trace_complete(packet_budget: Mapping[str, Any]) -> bool:
    decisions = packet_budget.get("budget_decisions")
    return (
        packet_budget.get("mode") == "active"
        and packet_budget.get("enabled") is True
        and packet_budget.get("applied_to_output") is True
        and isinstance(decisions, list)
        and bool(decisions)
        and packet_budget.get("budget_reason_code_registry_pass", True) is True
        and packet_budget.get("raw_text_in_budget_trace", False) is False
        and _protected_drop_attempts(packet_budget) == 0
        and int(packet_budget.get("estimated_tokens_before") or 0)
        >= int(packet_budget.get("selected_candidate_tokens") or 0)
    )


def _assistant_contamination(
    store: BrainstackStore, *, scope: str, session: str, variant: int
) -> str:
    store.upsert_profile_item(
        stable_key=f"identity:preferred_name:assistant-noise:{variant}",
        category="identity",
        content=f"The user's preferred name is CleanName{variant}.",
        source="phase210_soak",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
        },
    )
    store.add_continuity_event(
        session_id=session,
        turn_number=1,
        kind="assistant",
        content="I am Captain Beetle and I will call you NoiseHandle.",
        source="phase210_soak",
        metadata={
            "principal_scope_key": scope,
            "truth_eligible": False,
            "assistant_claim_type": "assistant_self_claim",
            "support_visibility": "inspect_only",
        },
    )
    _noise(store, scope=scope, session=session, prefix="ASSISTANT_NOISE", count=14, start=2)
    return "What is my preferred name?"


def _support_only_pressure(
    store: BrainstackStore, *, scope: str, session: str, variant: int
) -> str:
    store.upsert_profile_item(
        stable_key=f"identity:support-pressure:{variant}",
        category="identity",
        content=f"The user's preferred name is PriorityName{variant}.",
        source="phase210_soak",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
        },
    )
    _noise(store, scope=scope, session=session, prefix="SUPPORT_PRESSURE", count=28)
    return "What name should you use for me?"


def _reset_like_reference(
    store: BrainstackStore, *, scope: str, session: str, variant: int
) -> str:
    label = f"reset-safe-lib-{variant}"
    store.upsert_profile_item(
        stable_key=f"reference:repository_url:reset:{variant}",
        category="reference",
        content=f"{label} repository URL: https://example.org/{label}",
        source="phase210_soak",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "reference.repository_url",
            "label": label,
            "truth_eligible": True,
            "fetch_on_write": False,
        },
    )
    _noise(
        store,
        scope=scope,
        session=f"{session}:old",
        prefix="RESET_OLD_SESSION_NOISE",
        count=16,
    )
    return f"What is the saved {label} repository URL?"


def _conflict_current_truth(
    store: BrainstackStore, *, scope: str, session: str, variant: int
) -> str:
    old_key = f"identity:conflict:old:{variant}"
    store.upsert_profile_item(
        stable_key=old_key,
        category="identity",
        content="The user's preferred name is WrongOldName.",
        source="phase210_soak",
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
        stable_key=f"identity:conflict:current:{variant}",
        category="identity",
        content=f"The user's preferred name is RightCurrentName{variant}.",
        source="phase210_soak",
        confidence=0.99,
        metadata={
            "principal_scope_key": scope,
            "target_slot": "identity.preferred_address_name",
            "truth_eligible": True,
            "supersedes": [old_key],
        },
    )
    _noise(store, scope=scope, session=session, prefix="CONFLICT_NOISE", count=18)
    return "What should you call me now?"


def _long_noisy_transcript(
    store: BrainstackStore, *, scope: str, session: str, variant: int
) -> str:
    store.upsert_operating_record(
        stable_key=f"operating:long-noise-style:{variant}",
        principal_scope_key=scope,
        record_type="style_preference",
        content="Use direct concise answers and do not add decorative persona prefixes.",
        owner="SampleUser",
        source="phase210_soak",
        source_session_id=session,
        source_turn_number=1,
        metadata={"truth_eligible": True},
    )
    _noise(store, scope=scope, session=session, prefix="LONG_TRANSCRIPT_NOISE", count=36, start=2)
    return "What communication style should you use?"


SOAK_SEEDERS: list[tuple[str, Callable[..., str]]] = [
    *PHASE205_SEEDERS,
    ("assistant_contamination", _assistant_contamination),
    ("support_only_pressure", _support_only_pressure),
    ("reset_like_reference", _reset_like_reference),
    ("conflict_current_truth", _conflict_current_truth),
    ("long_noisy_transcript", _long_noisy_transcript),
]


def _failure(sample_id: str, family: str, reason_code: str, owner: str) -> dict[str, str]:
    return {
        "failure_id": f"phase210_{sample_id}_{reason_code.lower()}",
        "scenario_id": sample_id,
        "scenario_family": family,
        "owner": owner,
        "reason_code": reason_code,
        "repairability": "REPAIRABLE_AUTOMATIC",
        "recommended_playbook": "PACKET_BUDGET_TRACE_OR_SELECTION_FIX",
    }


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) < 2:
        return values[0]
    return quantiles(values, n=20, method="inclusive")[18]


def _scan_report_for_private_leaks(report: Mapping[str, Any]) -> list[str]:
    text = json.dumps(report, sort_keys=True)
    findings: list[str] = []
    for pattern in PRIVATE_LEAK_PATTERNS:
        if pattern.search(text):
            findings.append(pattern.pattern)
    return findings


def run_packet_budget_soak(
    *,
    sample_count: int = MIN_SOAK_SAMPLE_COUNT,
    max_candidate_tokens: int = 120,
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    active_elapsed: list[float] = []
    off_elapsed: list[float] = []

    with tempfile.TemporaryDirectory(prefix="brainstack-phase210-soak-") as tmp:
        root = Path(tmp)
        for index in range(sample_count):
            family, seeder = SOAK_SEEDERS[index % len(SOAK_SEEDERS)]
            sample_id = f"sample_{index:03d}"
            store = BrainstackStore(str(root / f"{sample_id}.sqlite3"))
            store.open()
            scope = f"principal:phase210:{family}:{index}"
            session = f"session:phase210:{family}:{index}"
            try:
                query = seeder(store, scope=scope, session=session, variant=index)
                start = time.perf_counter()
                off = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="off",
                    **_packet_defaults(),
                )
                off_elapsed.append((time.perf_counter() - start) * 1000.0)

                start = time.perf_counter()
                active = build_working_memory_packet(
                    store,
                    query=query,
                    session_id=session,
                    principal_scope_key=scope,
                    packet_budget_mode="active",
                    packet_budget_max_candidate_tokens=max_candidate_tokens,
                    **_packet_defaults(),
                )
                active_elapsed.append((time.perf_counter() - start) * 1000.0)
            finally:
                store.close()

            active_budget = active.get("packet_budget") or {}
            off_fingerprints = _protected_selected_fingerprints(off)
            active_fingerprints = _protected_selected_fingerprints(active)
            protected_drops = _protected_drop_attempts(active_budget)
            trace_complete = _trace_complete(active_budget)
            fingerprint_match = off_fingerprints == active_fingerprints
            active_applied = active_budget.get("applied_to_output") is True
            fusion_signal = _fusion_signal_for_sample(active_budget)

            if not active_applied:
                failures.append(
                    _failure(sample_id, family, "ACTIVE_BUDGET_NOT_APPLIED", "packet_budget")
                )
            if protected_drops:
                failures.append(
                    _failure(sample_id, family, "PROTECTED_TRUTH_DROP", "packet_budget")
                )
            if not trace_complete:
                failures.append(
                    _failure(sample_id, family, "INCOMPLETE_PACKET_BUDGET_TRACE", "evidence_trace")
                )
            if not fingerprint_match:
                failures.append(
                    _failure(sample_id, family, "SELECTED_EVIDENCE_FINGERPRINT_CHANGED", "retrieval")
                )

            samples.append(
                {
                    "sample_id": sample_id,
                    "scenario_family": family,
                    "active_applied_to_output": active_applied,
                    "protected_truth_drop_attempts": protected_drops,
                    "trace_complete": trace_complete,
                    "selected_evidence_fingerprint_match": fingerprint_match,
                    "selected_evidence_fingerprint_count": len(active_fingerprints),
                    "block_changed_from_unbudgeted": off.get("block") != active.get("block"),
                    "packet_budget": _packet_budget_summary(active_budget),
                    "fusion_signal": fusion_signal,
                }
            )

    families = sorted({sample["scenario_family"] for sample in samples})
    baseline_tokens = sum(
        int(sample["packet_budget"]["estimated_tokens_before"] or 0) for sample in samples
    )
    selected_tokens = sum(
        int(sample["packet_budget"]["selected_candidate_tokens"] or 0) for sample in samples
    )
    delta_percent = round(
        ((baseline_tokens - selected_tokens) / baseline_tokens * 100.0), 2
    ) if baseline_tokens else 0.0
    selected_mismatches = sum(
        1 for sample in samples if not sample["selected_evidence_fingerprint_match"]
    )
    protected_drops_total = sum(sample["protected_truth_drop_attempts"] for sample in samples)
    trace_complete_count = sum(1 for sample in samples if sample["trace_complete"])
    fusion_quality_signal_count = sum(
        int(sample["fusion_signal"]["cross_shelf_wrong_winner_count"])
        + int(sample["fusion_signal"]["durable_truth_crowded_by_transcript_count"])
        + int(sample["fusion_signal"]["corpus_or_graph_under_ranked_count"])
        for sample in samples
    )
    latency_overhead_values = [
        max(0.0, active - off) for active, off in zip(active_elapsed, off_elapsed)
    ]

    report: dict[str, Any] = {
        "schema": "brainstack.phase210.packet_budget_soak.v1",
        "status": "pending",
        "scenario_count": len(samples),
        "scenario_family_count": len(families),
        "scenario_families": families,
        "protected_truth_drop_attempts": protected_drops_total,
        "selected_evidence_changed_count": selected_mismatches,
        "selected_evidence_fingerprint_mismatch_count": selected_mismatches,
        "trace_complete_count": trace_complete_count,
        "candidate_token_delta_percent": delta_percent,
        "baseline_candidate_tokens": baseline_tokens,
        "active_budget_candidate_tokens": selected_tokens,
        "packet_build_latency_overhead_ms_p95": round(_p95(latency_overhead_values), 3),
        "retrieval_fusion_signal_count": fusion_quality_signal_count,
        "retrieval_fusion_next_phase_required": fusion_quality_signal_count >= 3,
        "failure_bundle_count": len(failures),
        "failure_bundles": failures,
        "samples": samples,
    }
    leak_findings = _scan_report_for_private_leaks(report)
    report["soak_artifact_leak_findings"] = len(leak_findings)
    report["leak_findings"] = leak_findings

    thresholds = {
        "sample_count_met": report["scenario_count"] >= MIN_SOAK_SAMPLE_COUNT,
        "family_count_met": report["scenario_family_count"] >= MIN_SOAK_FAMILY_COUNT,
        "protected_truth_drop_attempts_zero": protected_drops_total == 0,
        "selected_evidence_fingerprint_mismatch_zero": selected_mismatches == 0,
        "trace_complete_for_all_samples": trace_complete_count == len(samples),
        "soak_artifact_leak_findings_zero": not leak_findings,
        "failure_bundle_count_zero": not failures,
        "candidate_token_delta_positive": delta_percent > 0,
        "retrieval_fusion_stays_deferred": fusion_quality_signal_count < 3,
    }
    report["thresholds"] = thresholds
    report["status"] = "pass" if all(thresholds.values()) else "fail"
    return report


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-count", type=int, default=MIN_SOAK_SAMPLE_COUNT)
    parser.add_argument("--budget-max-candidate-tokens", type=int, default=120)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    report = run_packet_budget_soak(
        sample_count=args.sample_count,
        max_candidate_tokens=args.budget_max_candidate_tokens,
    )
    if args.out:
        _write_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
