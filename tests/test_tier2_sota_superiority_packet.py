from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_tier2_sota_superiority import build_packet


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_tier2_sota_superiority_packet_is_supported_scope_pass(tmp_path: Path) -> None:
    _write(
        tmp_path / "231-RELEASE-CHECKLIST-DEV.json",
        {
            "status": "pass",
            "release_allowed": False,
            "non_git_failures": [],
            "checks": [{"name": "git_hygiene", "status": "fail"}],
        },
    )
    _write(
        tmp_path / "231-PACKET-SOAK-RERUN.json",
        {
            "status": "pass",
            "scenario_count": 100,
            "trace_complete_count": 100,
            "failure_bundle_count": 0,
            "protected_truth_drop_attempts": 0,
            "selected_evidence_fingerprint_mismatch_count": 0,
            "candidate_token_delta_percent": 69.05,
        },
    )
    _write(
        tmp_path / "231-GRAPH-CONFLICT-AUDIT-RERUN.json",
        {
            "status": "pass",
            "issue_count": 0,
            "release_blocked_before_resolution": True,
            "open_conflict_count_after_resolution": 0,
        },
    )
    _write(
        tmp_path / "active-preference-rerun/active_preference_contract_gauntlet_report.json",
        {"metrics": {"failure_count": 0, "private_artifact_leak_count": 0}},
    )
    _write(
        tmp_path / "backend-lifecycle-rerun/backend_lifecycle_gauntlet_report.json",
        {"hidden_backend_disable_count": 0, "silent_degraded_backend_count": 0},
    )

    packet = build_packet(phase_dir=tmp_path)

    assert packet["schema"] == "brainstack.tier2_sota_superiority_packet.v1"
    assert packet["status"] == "pass"
    assert packet["supported_scope_sota_superiority"] is True
    assert packet["tier2_product_supported_prerequisite_met"] is True
    assert packet["tier2_product_release_ready"] is False
    assert packet["blockers"] == ["clean_git_release_parity_not_satisfied"]
    assert all(item["status"] == "pass" for item in packet["donor_invariants"])
    assert all(item["status"] == "pass" for item in packet["baseline_comparison"])
    assert packet["critical_counters"]["tier2_assistant_authored_writes"] == 0
    assert packet["critical_counters"]["tier2_bloat_writes"] == 0
    assert packet["probe"]["current_bounded_candidate_count"] == 8
    assert packet["probe"]["legacy_unbounded_candidate_count"] == 40
    assert packet["probe"]["raw_value_hidden_from_plan"] is True
