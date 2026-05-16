from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_enabled_backend_multiprofile_recall_proof_passes_with_sqlite_backends(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_enabled_backend_multiprofile_recall.py",
            "--workspace-dir",
            str(tmp_path / "proof"),
            "--graph-backend",
            "sqlite",
            "--corpus-backend",
            "sqlite",
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema"] == "brainstack.enabled_backend_multiprofile_recall_proof.v1"
    assert payload["status"] == "pass"
    assert len(payload["profiles"]) == 2
    for profile in payload["profiles"]:
        assert profile["required_shelves_missing"] == []
        assert profile["cross_profile_bleed_detected"] is False
        assert profile["selected_counts"]["profile"] >= 1
        assert profile["selected_counts"]["operating"] >= 1
        assert profile["selected_counts"]["graph"] >= 1
        assert profile["selected_counts"]["corpus"] >= 1
