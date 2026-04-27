from __future__ import annotations

from brainstack.product_contracts import assess_workspace_contract, ensure_workspace_fixture


def test_empty_workspace_marks_invalid_fixture(tmp_path) -> None:
    contract = assess_workspace_contract(tmp_path)

    assert contract.fixture_status == "invalid_fixture"


def test_file_capability_available_with_fixture_workspace(tmp_path) -> None:
    contract = ensure_workspace_fixture(tmp_path)

    assert contract.fixture_status == "present"
    assert "README.md" in contract.fixture_files
    assert "docs/PLAN.md" in contract.fixture_files

