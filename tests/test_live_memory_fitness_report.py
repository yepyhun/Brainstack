from __future__ import annotations

import json

from scripts.verify_live_memory_fitness_report import build_report, classify_memory_fitness


def test_live_memory_fitness_report_is_read_only_public_safe_and_classifies_expected_findings() -> None:
    report = build_report()

    assert report["status"] == "pass"
    assert report["read_only"] is True
    assert report["public_safe"] is True
    assert report["release_blocked"] is False
    assert report["proof"]["read_only_table_counts_unchanged"] is True
    assert report["proof"]["duplicate_strength_classified_not_all_good"] is True
    assert report["proof"]["duplicate_strength_controlled_not_low_hanging"] is True
    assert report["proof"]["healthy_proactive_idle_not_failure"] is True
    assert report["proof"]["kanban_detected_not_write_certified"] is True
    assert report["proof"]["invalid_workspace_is_high"] is True
    codes = {finding["code"] for finding in report["findings"]}
    assert {
        "duplicate_strength_budgeted_review_only",
        "graph_underfed_no_typed_input",
        "proactive_ready_idle",
        "kanban_detected_not_agent_write_certified",
    } <= codes
    assert "duplicate_strength_quality_debt" not in codes
    assert report["summary"]["severity_counts"]["CONTROLLED_QUALITY_SIGNAL"] == 1
    assert "LOW_HANGING_FRUIT" not in report["summary"]["severity_counts"]

    rendered = json.dumps(report, ensure_ascii=False)
    assert "Public fixture duplicate memory fitness preference" not in rendered


def test_live_memory_fitness_blocks_release_only_for_brainstack_high_findings() -> None:
    findings = classify_memory_fitness(
        stats={
            "status": "pass",
            "strict_requested": True,
            "backend_health": {"status": "active"},
            "doctor": {"verdict": "pass"},
            "persistent_bloat": {"issues": []},
        },
        proactive_status={
            "operational_state": "ready_idle",
            "idle_is_failure": False,
            "workstation_integrations": {"kanban": {"available": False, "can_write_board": False}},
        },
        graph_producer={"producer_state": "no_input", "reason_code": "GRAPH_PRODUCER_NO_INPUT"},
        workspace_contract={"fixture_status": "absent"},
        duplicate_strength_control={"status": "pass", "proof": {}},
    )

    workspace = next(item for item in findings if item["code"] == "workspace_contract_invalid")
    assert workspace["severity"] == "HIGH"
    assert workspace["owner"] == "brainstack_installer_or_wizard"


def test_live_memory_fitness_keeps_duplicate_strength_low_hanging_when_control_proof_missing() -> None:
    findings = classify_memory_fitness(
        stats={
            "status": "pass",
            "strict_requested": True,
            "backend_health": {"status": "active"},
            "doctor": {"verdict": "pass"},
            "persistent_bloat": {"issues": ["DUPLICATE_STRENGTH_INFLATION_WARN"]},
        },
        proactive_status={
            "operational_state": "ready_idle",
            "idle_is_failure": False,
            "workstation_integrations": {"kanban": {"available": False, "can_write_board": False}},
        },
        graph_producer={"producer_state": "active", "reason_code": ""},
        workspace_contract={"fixture_status": "present"},
        duplicate_strength_control={"status": "fail", "proof": {}},
    )

    duplicate = next(item for item in findings if item["code"] == "duplicate_strength_quality_debt")
    assert duplicate["severity"] == "LOW_HANGING_FRUIT"
