from __future__ import annotations

import json
from pathlib import Path

from scripts.run_memory_kernel_release_checklist import (
    GATE_EVASION_PATTERNS,
    REQUIRED_OPERATION_CLASSES,
    UNBREAKABLE_TARGET,
    _check_hermes_proactive_runtime_parity,
    _check_projection_semantics_runtime_parity,
    _check_release_claim_contract,
    _git_hygiene_from_lists,
    _report,
    CheckResult,
)


def _valid_contract() -> dict[str, object]:
    return {
        "schema": "brainstack.release_claim_contract.v1",
        "stable_release_decision": "allowed",
        "claim_summary": "Tier2 decision gate protects durable memory writes.",
        "unbreakable_target": UNBREAKABLE_TARGET,
        "unbreakable_operation_proof": {
            "status": "pass",
            "operating_space_classes": sorted(REQUIRED_OPERATION_CLASSES),
            "arbitrary_combination_coverage": True,
            "structural_forbidden_state_analysis": True,
            "no_permanent_disable": True,
            "no_regression": True,
            "no_feature_removal": True,
            "no_capability_shutdown": True,
            "no_dumbing_down": True,
            "no_permanent_degraded_mode": True,
            "structurally_impossible_states": [
                "unverified_tier2_proposal_becomes_durable_truth",
                "support_only_event_becomes_answer_truth",
            ],
            "temporary_error_guards": [
                "invalid_contract_blocks_release_until_root_cause_fixed",
            ],
        },
        "gate_evasion": {
            "status": "pass",
            **{pattern: False for pattern in GATE_EVASION_PATTERNS},
        },
        "immutable_principles": {"status": "pass", "violations": []},
        "sota_gate_required": False,
        "evidence": [
            {
                "name": "oracle_and_metamorphic_proof",
                "kind": "unbreakable_operation",
                "status": "pass",
                "summary": "Forbidden durable-write states are structurally blocked.",
            },
            {
                "name": "regression_proof",
                "kind": "regression",
                "status": "pass",
                "summary": "No feature removal, shutdown, or permanent degraded endpoint.",
            },
            {
                "name": "release_note_truthfulness",
                "kind": "release_surface",
                "status": "pass",
                "summary": "Release notes match proven behavior.",
            },
        ],
    }


def _write_contract_and_notes(tmp_path: Path, contract: dict[str, object] | None = None) -> tuple[Path, Path]:
    contract_path = tmp_path / "contract.json"
    notes_path = tmp_path / "notes.md"
    contract_path.write_text(json.dumps(contract or _valid_contract()), encoding="utf-8")
    notes_path.write_text(
        "Tier2 memory-write safety upgrade.\n\n"
        "What changed:\n\n"
        "- Tier2 proposals pass through deterministic decision gate before durable memory writes.\n"
        "- Unverified proposals stay non-durable.\n",
        encoding="utf-8",
    )
    return contract_path, notes_path


def test_projection_semantics_runtime_parity_check_passes(tmp_path: Path) -> None:
    result = _check_projection_semantics_runtime_parity(tmp_path)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["inspect_verdict"] == "pass"
    assert result.summary["doctor_status"] == "active"
    assert result.summary["unsafe_selected_event_ids"] == []
    assert result.summary["packet_authority_critical_dropped"] == 0
    assert result.summary["public_safe"] is True


def test_hermes_proactive_runtime_parity_check_passes(tmp_path: Path) -> None:
    result = _check_hermes_proactive_runtime_parity(tmp_path)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["issue_count"] == 0
    assert result.summary["payload_files_status"] == "present"
    assert result.summary["payload_missing_count"] == 0
    assert result.summary["public_safe"] is True
    assert result.summary["zero_runtime_side_effects"] is True
    assert result.summary["scenario_statuses"] == {
        "idle": "idle",
        "active": "active",
        "paused": "paused",
        "dry_run": "observed",
        "killed": "killed",
        "malformed": "degraded",
    }


def test_git_hygiene_blocks_dirty_source() -> None:
    summary = _git_hygiene_from_lists([" M brainstack/core/example.py"], [])

    assert summary["git_dirty"] is True
    assert summary["dirty_entry_count"] == 1
    assert summary["private_live_untracked_visible"] is False


def test_git_hygiene_blocks_visible_private_live_files() -> None:
    summary = _git_hygiene_from_lists(
        ["?? scripts/run_live_discord_e2e.py"],
        ["scripts/run_live_discord_e2e.py"],
    )

    assert summary["untracked_private_files_count"] == 1
    assert summary["untracked_private_files_policy"] == "blocked_if_visible"
    assert summary["private_live_untracked_visible"] is True


def test_release_report_allows_dev_dirty_without_release_allowed() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["ok"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["ok"], 0, {}),
        CheckResult("public_memory_kernel_corpus", "pass", ["ok"], 0, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "pass"
    assert report["release_allowed"] is False
    assert report["failed_checks"] == ["git_hygiene"]


def test_release_report_fails_non_git_failure_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["ok"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["ok"], 0, {}),
        CheckResult("public_memory_kernel_corpus", "fail", ["bad"], 1, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["public_memory_kernel_corpus"]


def test_release_report_fails_claim_contract_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "fail", ["contract"], 1, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["ok"], 0, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["release_claim_contract"]


def test_release_report_fails_tier2_unbreakable_operation_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "fail", ["tier2"], 2, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["tier2_unbreakable_operation"]


def test_release_report_fails_phase249_ralph_gate_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["tier2"], 0, {}),
        CheckResult("phase249_ralph_gate", "fail", ["ralph"], 2, {}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["phase249_ralph_gate"]


def test_release_claim_contract_blocks_missing_contract(tmp_path: Path) -> None:
    result = _check_release_claim_contract(tmp_path / "missing.json", tmp_path / "missing.md")

    assert result.status == "fail"
    codes = {issue["code"] for issue in result.summary["issues"]}
    assert "missing_release_claim_contract" in codes
    assert "missing_release_notes" in codes


def test_release_claim_contract_blocks_gate_evasion(tmp_path: Path) -> None:
    contract = _valid_contract()
    gate_evasion = dict(contract["gate_evasion"])  # type: ignore[arg-type]
    gate_evasion["scope_shrink"] = True
    contract["gate_evasion"] = gate_evasion
    contract_path, notes_path = _write_contract_and_notes(tmp_path, contract)

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {
        "code": "gate_evasion_pattern_not_rejected",
        "pattern": "scope_shrink",
    } in result.summary["issues"]


def test_release_claim_contract_blocks_immutable_violation(tmp_path: Path) -> None:
    contract = _valid_contract()
    contract["immutable_principles"] = {"status": "fail", "violations": ["temporary_fallback"]}
    contract_path, notes_path = _write_contract_and_notes(tmp_path, contract)

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    codes = {issue["code"] for issue in result.summary["issues"]}
    assert "immutable_principles_status_not_pass" in codes
    assert "immutable_principles_violations_present" in codes


def test_release_claim_contract_blocks_safety_by_disable(tmp_path: Path) -> None:
    contract = _valid_contract()
    proof = dict(contract["unbreakable_operation_proof"])  # type: ignore[arg-type]
    proof["no_capability_shutdown"] = False
    contract["unbreakable_operation_proof"] = proof
    contract_path, notes_path = _write_contract_and_notes(tmp_path, contract)

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {
        "code": "unbreakable_proof_required_flag_not_true",
        "field": "no_capability_shutdown",
    } in result.summary["issues"]


def test_release_claim_contract_blocks_internal_release_note_noise(tmp_path: Path) -> None:
    contract_path, notes_path = _write_contract_and_notes(tmp_path)
    notes_path.write_text("Full pytest: pass.\nDocker rebuild: pass.\n", encoding="utf-8")

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {
        "code": "release_notes_forbidden_pattern",
        "pattern": "internal_qa_noise",
    } in result.summary["issues"]


def test_release_claim_contract_blocks_non_maintainer_attribution(tmp_path: Path) -> None:
    contract_path, notes_path = _write_contract_and_notes(tmp_path)
    notes_path.write_text("Generated by local build helper.\n", encoding="utf-8")

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {
        "code": "release_notes_forbidden_pattern",
        "pattern": "non_maintainer_attribution",
    } in result.summary["issues"]


def test_release_claim_contract_blocks_sota_claim_without_sota_gate(tmp_path: Path) -> None:
    contract_path, notes_path = _write_contract_and_notes(tmp_path)
    notes_path.write_text("SOTA memory-write safety upgrade.\n", encoding="utf-8")

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {"code": "superiority_claim_without_sota_gate"} in result.summary["issues"]


def test_release_claim_contract_blocks_required_sota_gate_even_without_sota_notes(tmp_path: Path) -> None:
    contract = _valid_contract()
    contract["sota_gate_required"] = True
    contract["sota_gate"] = {"status": "not_started"}
    contract_path, notes_path = _write_contract_and_notes(tmp_path, contract)

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "fail"
    assert {"code": "sota_gate_required_but_not_pass"} in result.summary["issues"]


def test_release_claim_contract_valid_contract_passes(tmp_path: Path) -> None:
    contract_path, notes_path = _write_contract_and_notes(tmp_path)

    result = _check_release_claim_contract(contract_path, notes_path)

    assert result.status == "pass"
    assert result.summary["issue_count"] == 0
