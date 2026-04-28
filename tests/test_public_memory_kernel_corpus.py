from __future__ import annotations

import json
from pathlib import Path

from scripts.run_public_memory_kernel_fixtures import run_fixture_directory


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_memory_kernel_corpus_passes_contracts() -> None:
    result = run_fixture_directory(FIXTURE_DIR)

    assert result["status"] == "pass"
    assert result["failure_count"] == 0
    assert result["scenario_count"] >= 5


def test_public_scenarios_have_equivalence_records() -> None:
    result = run_fixture_directory(FIXTURE_DIR)
    equivalence = {
        item["public_scenario_id"]: item
        for item in json.loads((FIXTURE_DIR / "equivalence_map.json").read_text())
    }

    for scenario in result["scenarios"]:
        scenario_id = scenario["scenario_id"]
        assert scenario_id in equivalence
        record = equivalence[scenario_id]
        assert record["does_not_contain_private_data"] is True
        assert record["invariant"]
        assert record["forbidden_regression"]
        assert record["required_trace_reason_code"]


def test_public_expected_outputs_are_contract_first() -> None:
    for path in sorted((FIXTURE_DIR / "conversations").glob("*.json")):
        payload = json.loads(path.read_text())
        expected = payload["expected"]

        assert "receipt_coverage" in expected
        assert "selected_slots" in expected
        assert "reset_recall" in expected
        assert "final_answer_text" not in expected


def test_reference_url_fixture_does_not_claim_fetch() -> None:
    payload = json.loads(
        (FIXTURE_DIR / "conversations" / "reference_url_no_fetch_public_001.json").read_text()
    )
    result = run_fixture_directory(FIXTURE_DIR)
    scenario = next(
        item for item in result["scenarios"] if item["scenario_id"] == payload["scenario_id"]
    )

    assert payload["expected"]["must_not_fetch_url"] is True
    assert scenario["reset_recall"]["reference.repository_url:orion-lib"] == (
        "https://example.com/orion-lib"
    )
