from __future__ import annotations

from brainstack.controller_artifact_compaction import compact_controller_artifact


def test_controller_artifact_compacts_large_repeated_fields_with_replay_ref() -> None:
    artifact = {
        "schema": "demo",
        "verdict": "degraded",
        "unresolved_recovery_artifacts": [{"id": idx, "text": "x" * 100} for idx in range(80)],
    }

    result = compact_controller_artifact(
        artifact,
        large_field_chars=1000,
        replay_base_ref="/tmp/run.json",
    )
    compacted = result["compacted_artifact"]["unresolved_recovery_artifacts"]

    assert result["full_replay_required_for_compacted_fields"] is True
    assert compacted["compacted"] is True
    assert compacted["item_count"] == 80
    assert compacted["replay_ref"].startswith("/tmp/run.json#unresolved_recovery_artifacts:")
    assert len(result["compacted_fields"]) == 1

