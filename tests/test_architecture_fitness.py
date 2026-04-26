from __future__ import annotations

from pathlib import Path

from scripts.brainstack_architecture_fitness import run_checks


def test_architecture_fitness_hard_checks_pass() -> None:
    report = run_checks(Path(__file__).resolve().parents[1])

    assert report.core_import_violations == []
    assert report.generic_module_violations == []
    assert report.hard_failures == []
    assert "storage imports core and DB infrastructure only" in report.advisory_contracts
