from __future__ import annotations

from pathlib import Path

from scripts.run_public_memory_kernel_fixtures import run_negative_fixtures


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_negative_fixtures_fail_for_expected_reasons() -> None:
    result = run_negative_fixtures(FIXTURE_DIR)

    assert result["status"] == "pass"
    assert result["negative_count"] >= 4
    for item in result["negative_fixtures"]:
        assert item["status"] == "pass"
        assert any(item["expected_error"] in error for error in item["errors"])
