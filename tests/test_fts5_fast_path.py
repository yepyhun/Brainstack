from __future__ import annotations

from scripts.verify_fts5_fast_path import build_report


def test_fts5_fast_path_verifier_passes_all_text_shelves() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.fts5_fast_path_verifier.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["fts_tables"]["missing"] == []
    assert set(report["cases"]) == {
        "profile",
        "continuity",
        "transcript",
        "transcript_global",
        "operating",
        "corpus",
    }
    assert all(case["status"] == "pass" for case in report["cases"].values())
    assert all(count > 0 for count in report["fts_row_counts"].values())
