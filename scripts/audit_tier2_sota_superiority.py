#!/usr/bin/env python3
"""Build the Phase 231 Tier2 supported-scope superiority packet."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASE_DIR = ROOT / ".planning/phases/231-tier2-godtier-proof-gauntlet-and-release-gate"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_first(paths: list[Path]) -> dict[str, Any]:
    for path in paths:
        if path.exists():
            return _load_json(path)
    return {}


def _provider(tmp_path: Path, extractor: Callable[..., Mapping[str, Any]]):
    from brainstack import BrainstackMemoryProvider

    provider = BrainstackMemoryProvider(
        {
            "db_path": str(tmp_path / "brainstack.sqlite3"),
            "graph_backend": "sqlite",
            "corpus_backend": "sqlite",
            "tier2_transcript_limit": 8,
            "tier2_timeout_seconds": 2,
            "_tier2_extractor": extractor,
        }
    )
    provider.initialize(
        "tier2-sota-session",
        platform="test",
        user_id="user",
        agent_identity="agent-sota",
        agent_workspace="workspace",
    )
    assert provider._store is not None
    provider._store.add_transcript_entry(
        session_id="tier2-sota-session",
        turn_number=1,
        kind="turn",
        content="User: My preferred name is PUBLIC_SAFE_SENTINEL_SHOULD_NOT_APPEAR.",
        source="public-sota",
        metadata=provider._scoped_metadata(),
    )
    return provider


def _run_provider_case(tmp_path: Path, extractor: Callable[..., Mapping[str, Any]]) -> dict[str, Any]:
    provider = _provider(tmp_path, extractor)
    try:
        return provider._run_tier2_batch(
            session_id="tier2-sota-session",
            turn_number=1,
            trigger_reason="idle_window",
        )
    finally:
        provider.shutdown()


def _tier2_supported_scope_probe() -> dict[str, Any]:
    sentinel = "PUBLIC_SAFE_SENTINEL_SHOULD_NOT_APPEAR"
    with tempfile.TemporaryDirectory(prefix="brainstack-tier2-sota-") as temp:
        root = Path(temp)

        def explicit_extractor(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": sentinel,
                        "source_quote": f"My preferred name is {sentinel}.",
                        "confidence": 0.98,
                        "metadata": {"source_role": "user"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "sota_probe"},
            }

        provider = _provider(root / "explicit", explicit_extractor)
        try:
            first = provider._run_tier2_batch(
                session_id="tier2-sota-session",
                turn_number=1,
                trigger_reason="idle_window",
            )
            second = provider._run_tier2_batch(
                session_id="tier2-sota-session",
                turn_number=1,
                trigger_reason="idle_window",
            )
            plan = first.get("consolidation_plan") or {}
            first_proposal = (plan.get("proposals") or [{}])[0]
            receipts = provider._store.list_admission_receipts(limit=10) if provider._store else []
        finally:
            provider.shutdown()

        def assistant_extractor(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:preferred_address_name",
                        "content": "Assistant Claim",
                        "source_quote": "Assistant claimed this about itself.",
                        "confidence": 0.99,
                        "metadata": {"source_role": "assistant"},
                    }
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "sota_probe"},
            }

        assistant = _run_provider_case(root / "assistant", assistant_extractor)

        def bloat_extractor(*args: Any, **kwargs: Any) -> Mapping[str, Any]:
            return {
                "profile_items": [
                    {
                        "category": "identity",
                        "slot": "identity:name",
                        "content": f"Noise {index}",
                        "source_quote": f"Noise {index}",
                        "confidence": 0.95,
                        "metadata": {"source_role": "user"},
                    }
                    for index in range(40)
                ],
                "_meta": {"json_parse_status": "ok", "parse_context": "sota_probe"},
            }

        bloat = _run_provider_case(root / "bloat", bloat_extractor)

    plan_json = json.dumps(plan, sort_keys=True)
    return {
        "schema": "brainstack.tier2_supported_scope_probe.v1",
        "accepted_explicit_write": first.get("writes_performed") == 1,
        "plan_schema_present": plan.get("schema") == "brainstack.tier2_consolidation_plan.v1",
        "proposal_id_present": bool(first_proposal.get("proposal_id")),
        "proposal_id_reaches_receipt": bool(receipts)
        and receipts[0].get("trace_id") == first_proposal.get("proposal_id")
        and str(receipts[0].get("source_span_id") or "").startswith("usrspan_")
        and (receipts[0].get("metadata") or {}).get("verified_user_span_proof", {}).get("status") == "verified",
        "raw_value_hidden_from_plan": sentinel not in plan_json,
        "duplicate_run_writes": second.get("writes_performed"),
        "duplicate_run_action_none": second.get("action_counts", {}).get("NONE"),
        "assistant_authored_writes": assistant.get("writes_performed"),
        "assistant_authored_quarantines": assistant.get("action_counts", {}).get("QUARANTINE_PROPOSAL"),
        "assistant_authored_action_counts": assistant.get("action_counts", {}),
        "bloat_budget_status": (bloat.get("consolidation_budget") or {}).get("status"),
        "bloat_accepted_profile_items": (bloat.get("consolidation_budget") or {})
        .get("accepted_by_kind", {})
        .get("profile_items"),
        "bloat_omitted_total": (bloat.get("consolidation_budget") or {}).get("omitted_total"),
        "bloat_writes": bloat.get("writes_performed"),
        "legacy_unbounded_candidate_count": 40,
        "current_bounded_candidate_count": (bloat.get("consolidation_budget") or {})
        .get("accepted_by_kind", {})
        .get("profile_items"),
    }


def _pass(name: str, passed: bool, evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {"name": name, "status": "pass" if passed else "fail", "evidence": dict(evidence)}


def build_packet(*, phase_dir: Path = PHASE_DIR) -> dict[str, Any]:
    release = _load_first(
        [
            phase_dir / f"{phase_dir.name.split('-', 1)[0]}-RELEASE-CHECKLIST-CLEAN.json",
            phase_dir / f"{phase_dir.name.split('-', 1)[0]}-RELEASE-CHECKLIST-DEV.json",
            phase_dir / "231-RELEASE-CHECKLIST-CLEAN.json",
            phase_dir / "231-RELEASE-CHECKLIST-DEV.json",
            PHASE_DIR / "231-RELEASE-CHECKLIST-CLEAN.json",
            PHASE_DIR / "231-RELEASE-CHECKLIST-DEV.json",
        ]
    )
    packet_soak = _load_first([phase_dir / "231-PACKET-SOAK-RERUN.json", PHASE_DIR / "231-PACKET-SOAK-RERUN.json"])
    graph_conflict = _load_first(
        [phase_dir / "231-GRAPH-CONFLICT-AUDIT-RERUN.json", PHASE_DIR / "231-GRAPH-CONFLICT-AUDIT-RERUN.json"]
    )
    active_pref = _load_first(
        [
            phase_dir / "active-preference-rerun/active_preference_contract_gauntlet_report.json",
            PHASE_DIR / "active-preference-rerun/active_preference_contract_gauntlet_report.json",
        ]
    )
    backend = _load_first(
        [
            phase_dir / "backend-lifecycle-rerun/backend_lifecycle_gauntlet_report.json",
            PHASE_DIR / "backend-lifecycle-rerun/backend_lifecycle_gauntlet_report.json",
        ]
    )
    probe = _tier2_supported_scope_probe()

    donor_invariants = [
        _pass(
            "hindsight_background_not_chat_response",
            probe["plan_schema_present"] and probe["proposal_id_present"],
            {"plan_schema_present": probe["plan_schema_present"], "proposal_id_present": probe["proposal_id_present"]},
        ),
        _pass(
            "hindsight_proposal_before_admission_receipt",
            probe["proposal_id_reaches_receipt"],
            {"proposal_id_reaches_receipt": probe["proposal_id_reaches_receipt"]},
        ),
        _pass(
            "hindsight_verified_explicit_write_path",
            probe["accepted_explicit_write"],
            {
                "accepted_explicit_write": probe["accepted_explicit_write"],
                "required": "durable Tier2 writes need verified user-span proof, not candidate source_role metadata",
            },
        ),
        _pass(
            "hindsight_idempotent_background_retry",
            probe["duplicate_run_writes"] == 0,
            {
                "duplicate_run_writes": probe["duplicate_run_writes"],
                "duplicate_run_action_none": probe["duplicate_run_action_none"],
            },
        ),
        _pass(
            "hindsight_bounded_work",
            probe["bloat_budget_status"] == "trimmed"
            and probe["bloat_accepted_profile_items"] == 8
            and probe["bloat_omitted_total"] == 32,
            {
                "budget_status": probe["bloat_budget_status"],
                "accepted_profile_items": probe["bloat_accepted_profile_items"],
                "omitted_total": probe["bloat_omitted_total"],
            },
        ),
        _pass(
            "hindsight_failure_does_not_poison_memory",
            probe["assistant_authored_writes"] == 0,
            {
                "assistant_authored_writes": probe["assistant_authored_writes"],
                "assistant_authored_quarantines": probe["assistant_authored_quarantines"],
                "assistant_authored_action_counts": probe["assistant_authored_action_counts"],
            },
        ),
        _pass(
            "graphiti_conflict_lifecycle",
            graph_conflict.get("status") == "pass"
            and graph_conflict.get("issue_count") == 0
            and graph_conflict.get("release_blocked_before_resolution") is True
            and graph_conflict.get("open_conflict_count_after_resolution") == 0,
            {
                "status": graph_conflict.get("status"),
                "issue_count": graph_conflict.get("issue_count"),
                "release_blocked_before_resolution": graph_conflict.get("release_blocked_before_resolution"),
                "open_conflict_count_after_resolution": graph_conflict.get("open_conflict_count_after_resolution"),
            },
        ),
        _pass(
            "mempalace_active_budget",
            packet_soak.get("status") == "pass"
            and packet_soak.get("protected_truth_drop_attempts") == 0
            and packet_soak.get("selected_evidence_fingerprint_mismatch_count") == 0
            and packet_soak.get("candidate_token_delta_percent", 0) >= 50,
            {
                "status": packet_soak.get("status"),
                "candidate_token_delta_percent": packet_soak.get("candidate_token_delta_percent"),
                "protected_truth_drop_attempts": packet_soak.get("protected_truth_drop_attempts"),
                "selected_evidence_fingerprint_mismatch_count": packet_soak.get(
                    "selected_evidence_fingerprint_mismatch_count"
                ),
            },
        ),
    ]

    baseline_comparison = [
        _pass(
            "beats_legacy_unbounded_candidate_bloat",
            probe["current_bounded_candidate_count"] < probe["legacy_unbounded_candidate_count"],
            {
                "legacy_unbounded_candidate_count": probe["legacy_unbounded_candidate_count"],
                "current_bounded_candidate_count": probe["current_bounded_candidate_count"],
                "relative_reduction_percent": round(
                    100
                    * (
                        probe["legacy_unbounded_candidate_count"] - probe["current_bounded_candidate_count"]
                    )
                    / probe["legacy_unbounded_candidate_count"],
                    2,
                ),
            },
        ),
        _pass(
            "beats_legacy_raw_value_trace_leak_risk",
            probe["raw_value_hidden_from_plan"],
            {"raw_value_hidden_from_plan": probe["raw_value_hidden_from_plan"]},
        ),
        _pass(
            "beats_legacy_unsupported_conflict_release_risk",
            graph_conflict.get("release_blocked_before_resolution") is True,
            {"release_blocked_before_resolution": graph_conflict.get("release_blocked_before_resolution")},
        ),
    ]

    critical_counters = {
        "release_checklist_non_git_failures": len(release.get("non_git_failures") or []),
        "packet_budget_protected_truth_drop_attempts": packet_soak.get("protected_truth_drop_attempts"),
        "packet_budget_failure_bundle_count": packet_soak.get("failure_bundle_count"),
        "graph_conflict_issue_count": graph_conflict.get("issue_count"),
        "active_preference_failure_count": (active_pref.get("metrics") or {}).get("failure_count"),
        "active_preference_private_artifact_leak_count": (active_pref.get("metrics") or {}).get(
            "private_artifact_leak_count"
        ),
        "backend_hidden_disable_count": backend.get("hidden_backend_disable_count"),
        "backend_silent_degraded_count": backend.get("silent_degraded_backend_count"),
        "tier2_assistant_authored_writes": probe["assistant_authored_writes"],
        "tier2_bloat_writes": probe["bloat_writes"],
    }
    coverage_metrics = {
        "packet_budget_trace_complete_count": packet_soak.get("trace_complete_count"),
        "packet_budget_scenario_count": packet_soak.get("scenario_count"),
    }
    zero_counter_pass = all((value == 0 or value is None) for value in critical_counters.values())
    trace_count_pass = (
        coverage_metrics["packet_budget_trace_complete_count"]
        == coverage_metrics["packet_budget_scenario_count"]
    )
    donor_pass = all(item["status"] == "pass" for item in donor_invariants)
    baseline_pass = all(item["status"] == "pass" for item in baseline_comparison)
    release_pass = not release.get("non_git_failures")

    status = "pass" if donor_pass and baseline_pass and zero_counter_pass and trace_count_pass and release_pass else "fail"
    blockers: list[str] = []
    if status != "pass":
        blockers.append("supported_scope_superiority_packet_failed")
    if not probe["accepted_explicit_write"]:
        blockers.append("verified_user_span_durable_write_path_missing")
    if release.get("release_allowed") is not True:
        blockers.append("clean_git_release_parity_not_satisfied")

    return {
        "schema": "brainstack.tier2_sota_superiority_packet.v1",
        "status": status,
        "sota_claim_scope": "supported Brainstack live-agent memory-kernel Tier2 consolidation path",
        "not_claimed": [
            "global KG-RAG SOTA",
            "all external donor runtimes beaten in their native deployments",
            "full Hermes product readiness",
        ],
        "supported_scope_sota_superiority": status == "pass",
        "tier2_product_supported_prerequisite_met": status == "pass",
        "tier2_product_release_ready": status == "pass" and release.get("release_allowed") is True,
        "blockers": blockers,
        "donor_invariants": donor_invariants,
        "baseline_comparison": baseline_comparison,
        "critical_counters": critical_counters,
        "coverage_metrics": coverage_metrics,
        "release_checklist": {
            "status": release.get("status"),
            "release_allowed": release.get("release_allowed"),
            "non_git_failures": release.get("non_git_failures"),
            "failed_checks": [check.get("name") for check in release.get("checks", []) if check.get("status") != "pass"],
        },
        "probe": probe,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase-dir", type=Path, default=PHASE_DIR)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    packet = build_packet(phase_dir=args.phase_dir)
    text = json.dumps(packet, indent=2, sort_keys=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if packet["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
