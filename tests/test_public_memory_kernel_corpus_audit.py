from __future__ import annotations

from pathlib import Path

from scripts.audit_public_memory_kernel_corpus import audit_public_corpus


FIXTURE_DIR = Path("tests/fixtures/public_memory_kernel")


def test_public_memory_kernel_corpus_audit_passes() -> None:
    report = audit_public_corpus(FIXTURE_DIR)

    assert report["status"] == "pass"
    assert report["scenario_count"] == 8
    assert report["negative_count"] >= 5
    assert report["scenario_index_count"] == report["scenario_count"]
    assert report["equivalence_count"] == report["scenario_count"]
    assert report["leak_findings"] == []
    assert report["issues"] == []
