from __future__ import annotations

import json
from pathlib import Path

from scripts.run_memory_kernel_release_checklist import (
    GATE_EVASION_PATTERNS,
    REQUIRED_OPERATION_CLASSES,
    UNBREAKABLE_TARGET,
    _check_benchmark_transparency,
    _check_packet_budget_active_default,
    _check_adaptive_evidence_kernel,
    _check_adaptive_evidence_performance_completion,
    _check_hermes_proactive_runtime_parity,
    _check_persistent_bloat_rebuild,
    _check_projection_semantics_runtime_parity,
    _check_release_claim_contract,
    _check_tier2_extraction_quality,
    _check_version_metadata_parity,
    _count_python_hermes_coredumps,
    _git_hygiene_from_lists,
    _live_crash_regression_summary,
    _report,
    _version_metadata_parity_summary,
    CheckResult,
)
from scripts.run_persistent_bloat_soak import PRIVATE_SOAK_SENTINEL


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


def test_packet_budget_active_default_release_check_passes(tmp_path: Path) -> None:
    result = _check_packet_budget_active_default(tmp_path)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["active_default"] is True
    assert result.summary["default_off_detected"] is False
    assert result.summary["shadow_only_detected"] is False
    assert result.summary["hidden_fallback_count"] == 0
    assert result.summary["protected_truth_drop_attempts"] == 0
    assert result.summary["public_safe"] is True


def test_release_report_fails_packet_budget_active_default_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["tier2"], 0, {}),
        CheckResult("packet_budget_active_default", "fail", ["active-default"], 1, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["packet_budget_active_default"]


def test_adaptive_evidence_kernel_release_check_passes(tmp_path: Path) -> None:
    result = _check_adaptive_evidence_kernel(tmp_path)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["active_default"] is True
    assert result.summary["protected_truth_drops"] == 0
    assert result.summary["tank_false_negative_misses"] == 0
    assert result.summary["public_safe"] is True


def test_release_report_fails_adaptive_evidence_kernel_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("packet_budget_active_default", "pass", ["active-default"], 0, {}),
        CheckResult("adaptive_evidence_kernel", "fail", ["adaptive-kernel"], 1, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["adaptive_evidence_kernel"]


def test_adaptive_evidence_performance_completion_requires_fresh_hermes_source_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BRAINSTACK_RELEASE_HERMES_SOURCE", raising=False)

    result = _check_adaptive_evidence_performance_completion(tmp_path)

    assert result.status == "fail"
    assert result.summary["fresh_hermes_source_configured"] is False
    assert result.summary["failed"] == ["fresh_hermes_install"]


def test_release_report_fails_adaptive_evidence_performance_completion_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("adaptive_evidence_kernel", "pass", ["adaptive-kernel"], 0, {}),
        CheckResult(
            "adaptive_evidence_performance_completion",
            "fail",
            ["m008"],
            1,
            {"status": "fail"},
        ),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["adaptive_evidence_performance_completion"]


def test_benchmark_transparency_release_check_passes(tmp_path: Path) -> None:
    result = _check_benchmark_transparency(tmp_path)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["schema_issue_count"] == 0
    assert result.summary["variant_count"] == 5
    assert result.summary["off_context_precision"] < result.summary["active_context_precision"]
    assert result.summary["active_context_recall"] == 1.0
    assert result.summary["active_protected_truth_drop_attempts"] == 0


def test_release_report_fails_benchmark_transparency_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("version_metadata_parity", "pass", ["version"], 0, {}),
        CheckResult("benchmark_transparency", "fail", ["benchmark"], 1, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["benchmark_transparency"]


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


def _passing_crash_guard_summary() -> dict[str, object]:
    return _live_crash_regression_summary(
        container_name="hermes-bestie-live",
        container_id="container-id",
        container_state={
            "status": "running",
            "health": "healthy",
            "started_at": "2026-05-03T20:36:07.442503074Z",
            "restart_count": 0,
            "oom_killed": False,
            "exit_code": 0,
        },
        coredumpctl_available=True,
        coredump_count_since_container_start=0,
        coredump_count_after_probe=0,
        log_hit_counts={
            '"exit_code": -11': 0,
            "SIGSEGV": 0,
            "Traceback": 0,
        },
        terminal_smoke_ok=True,
        venv_import_smoke_ok=True,
        chroma_exception_probe_ok=True,
    )


def test_live_crash_regression_guard_summary_passes_clean_runtime() -> None:
    summary = _passing_crash_guard_summary()

    assert summary["status"] == "pass"
    assert summary["issue_count"] == 0
    assert summary["logs_crash_markers_zero"] is True
    assert summary["public_safe"] is True


def test_live_crash_regression_guard_summary_blocks_native_crash_markers() -> None:
    summary = _live_crash_regression_summary(
        container_name="hermes-bestie-live",
        container_id="container-id",
        container_state={
            "status": "running",
            "health": "healthy",
            "started_at": "2026-05-03T20:36:07.442503074Z",
            "restart_count": 0,
            "oom_killed": False,
            "exit_code": 0,
        },
        coredumpctl_available=True,
        coredump_count_since_container_start=1,
        coredump_count_after_probe=1,
        log_hit_counts={'"exit_code": -11': 1, "SIGSEGV": 0},
        terminal_smoke_ok=True,
        venv_import_smoke_ok=True,
        chroma_exception_probe_ok=True,
    )

    assert summary["status"] == "fail"
    codes = {issue["code"] for issue in summary["issues"]}
    assert "live_logs_crash_markers_present" in codes
    assert "python_hermes_coredumps_since_container_start" in codes
    assert "python_hermes_coredumps_after_probe" in codes


def test_live_crash_regression_guard_summary_blocks_smoke_failures() -> None:
    summary = _live_crash_regression_summary(
        container_name="hermes-bestie-live",
        container_id="container-id",
        container_state={
            "status": "running",
            "health": "healthy",
            "started_at": "2026-05-03T20:36:07.442503074Z",
            "restart_count": 0,
            "oom_killed": False,
            "exit_code": 0,
        },
        coredumpctl_available=True,
        coredump_count_since_container_start=0,
        coredump_count_after_probe=0,
        log_hit_counts={'"exit_code": -11': 0, "SIGSEGV": 0},
        terminal_smoke_ok=False,
        venv_import_smoke_ok=False,
        chroma_exception_probe_ok=False,
    )

    assert summary["status"] == "fail"
    codes = {issue["code"] for issue in summary["issues"]}
    assert "terminal_smoke_failed" in codes
    assert "venv_import_smoke_failed" in codes
    assert "chroma_exception_probe_failed" in codes


def test_count_python_hermes_coredumps_only_counts_native_crash_rows() -> None:
    output = "\n".join(
        [
            "TIME PID UID GID SIG COREFILE EXE SIZE",
            "Sun 2026-05-03 21:42:25 CEST 972582 1000 1000 SIGSEGV truncated /usr/bin/python3.13 15.9M",
            "Sun 2026-05-03 21:43:00 CEST 1 0 0 SIGTERM missing /usr/bin/bash -",
            "Sun 2026-05-03 21:44:00 CEST 2 1000 1000 SIGABRT present /opt/hermes/.venv/bin/hermes 1M",
        ]
    )

    assert _count_python_hermes_coredumps(output) == 2


def test_release_report_fails_live_crash_regression_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["tier2"], 0, {}),
        CheckResult("live_crash_regression_guard", "fail", ["crash"], 1, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["live_crash_regression_guard"]


def test_persistent_bloat_rebuild_release_check_passes(tmp_path: Path) -> None:
    result = _check_persistent_bloat_rebuild(tmp_path)
    rendered = json.dumps(result.summary, ensure_ascii=False, sort_keys=True)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["proof_status"] == "pass"
    assert result.summary["public_safe"] is True
    assert result.summary["proof_public_safe"] is True
    assert result.summary["issue_count"] == 0
    assert result.summary["mismatch_count"] == 0
    assert result.summary["persistent_bloat_apply_status"] == "rejected"
    assert result.summary["preservation_contract"]["truth_mutation"] is False
    assert result.summary["preservation_contract"]["raw_history_mutation"] is False
    assert result.summary["semantic_index_truth_mutation_unsafe"] is False
    assert result.summary["critical_counters_zero"] is True
    assert PRIVATE_SOAK_SENTINEL not in rendered


def test_tier2_extraction_quality_release_check_passes(tmp_path: Path) -> None:
    result = _check_tier2_extraction_quality(tmp_path)
    rendered = json.dumps(result.summary, ensure_ascii=False, sort_keys=True)

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["public_safe"] is True
    assert result.summary["case_count"] >= 10
    assert result.summary["metrics_all_one"] is True
    assert result.summary["harmful_counters_zero"] is True
    assert result.summary["bloat_impact"]["status"] == "pass"
    assert result.summary["donor_drift"]["status"] == "pass"
    assert result.summary["resolved_failure_bundle_count"] >= 3
    assert result.summary["unresolved_failure_bundle_count"] == 0
    assert "fixture proof" in rendered


def test_version_metadata_parity_blocks_exact_tag_mismatch(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "brainstack-hermes-plugin"\nversion = "1.0.56"\n',
        encoding="utf-8",
    )

    summary = _version_metadata_parity_summary(pyproject_path=pyproject, exact_tags=["v1.0.57"])

    assert summary["status"] == "fail"
    assert summary["pyproject_version"] == "1.0.56"
    assert summary["exact_release_tag_versions"] == ["1.0.57"]
    assert {"code": "version_metadata_mismatch", "pyproject_version": "1.0.56", "tag_versions": ["1.0.57"]} in summary["issues"]


def test_version_metadata_parity_passes_matching_exact_tag(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "brainstack-hermes-plugin"\nversion = "1.0.57"\n',
        encoding="utf-8",
    )

    result = _check_version_metadata_parity(pyproject_path=pyproject, exact_tags=["v1.0.57"])

    assert result.status == "pass"
    assert result.summary["status"] == "pass"
    assert result.summary["pyproject_version"] == "1.0.57"
    assert result.summary["exact_release_tag_versions"] == ["1.0.57"]


def test_version_metadata_parity_is_explicit_when_head_has_no_release_tag(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "brainstack-hermes-plugin"\nversion = "1.0.57"\n',
        encoding="utf-8",
    )

    summary = _version_metadata_parity_summary(pyproject_path=pyproject, exact_tags=[])

    assert summary["status"] == "pass"
    assert summary["exact_release_tags"] == []
    assert summary["parity_scope"] == "not_tagged_head"


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


def test_release_report_fails_persistent_bloat_rebuild_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["tier2"], 0, {}),
        CheckResult("persistent_bloat_rebuild", "fail", ["bloat"], 1, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["persistent_bloat_rebuild"]


def test_release_report_fails_tier2_extraction_quality_even_in_dev_mode() -> None:
    checks = [
        CheckResult("release_claim_contract", "pass", ["contract"], 0, {}),
        CheckResult("tier2_unbreakable_operation", "pass", ["tier2"], 0, {}),
        CheckResult("tier2_extraction_quality", "fail", ["tier2-extraction"], 2, {"status": "fail"}),
        CheckResult("git_hygiene", "fail", ["git"], 0, {"git_dirty": True}),
    ]

    report = _report(checks, ignore_git_dirty_for_dev=True)

    assert report["status"] == "fail"
    assert report["release_allowed"] is False
    assert report["non_git_failures"] == ["tier2_extraction_quality"]


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
