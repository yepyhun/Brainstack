from __future__ import annotations

from scripts.verify_persistent_bloat_policy import build_report


def test_persistent_bloat_policy_verifier_passes_without_truth_mutation() -> None:
    report = build_report()

    assert report["schema"] == "brainstack.persistent_bloat_policy_verifier.v1"
    assert report["status"] == "pass"
    assert report["public_safe"] is True
    assert report["policy_summary"]["durable_truth"]["action"] == "keep"
    assert report["policy_summary"]["transcript_continuity"]["apply_supported"] is False
    assert report["policy_summary"]["semantic_index"]["apply_supported"] is True
    assert report["unsafe_apply"]["status"] == "rejected"
    assert report["unsafe_apply"]["storage_unchanged"] is True
    assert report["unsafe_apply"]["preservation_contract"]["truth_mutation"] is False
    assert report["semantic_index_apply"]["status"] == "ok"
    assert report["semantic_index_apply"]["changes"][0]["truth_mutation"] is False
