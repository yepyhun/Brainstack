from __future__ import annotations

from pathlib import Path

from scripts.brainstack_payload_manifest import build_manifest


def test_payload_manifest_includes_refactored_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(root)
    paths = {entry["path"] for entry in manifest["files"]}

    assert manifest["schema"] == "brainstack.payload_manifest.v1"
    assert manifest["required_refactor_modules_present"] is True
    assert manifest["missing_required_refactor_modules"] == []
    assert "brainstack/storage/store_runtime.py" in paths
    assert "brainstack/provider/runtime.py" in paths
    assert "brainstack/retrieval_pipeline/orchestrator.py" in paths


def test_payload_manifest_uses_relative_non_private_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = build_manifest(root)

    assert manifest["private_path_hits"] == []
    for entry in manifest["files"]:
        assert not str(entry["path"]).startswith("/")
        assert len(entry["sha256"]) == 64
