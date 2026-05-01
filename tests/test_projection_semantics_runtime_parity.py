from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.verify_projection_semantics_runtime_parity import verify_runtime_parity

ROOT = Path(__file__).resolve().parents[1]


def test_projection_semantics_runtime_parity_report_passes() -> None:
    report = verify_runtime_parity()

    assert report["schema"] == "brainstack.projection_semantics_runtime_parity.v1"
    assert report["status"] == "pass"
    assert report["inspect_verdict"] == "pass"
    assert report["doctor_status"] == "active"
    assert report["conformance_status"] == "pass"
    assert report["selected_event_ids"] == ["truth_a", "truth_b"]
    assert report["unsafe_selected_event_ids"] == []
    assert report["critical_counters"]["packet_authority_critical_dropped"] == 0
    assert report["public_safe"] is True
    assert "private source text" not in str(report)


def test_projection_semantics_runtime_parity_cli_outputs_json(tmp_path) -> None:
    out = tmp_path / "projection_runtime_parity.json"
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/verify_projection_semantics_runtime_parity.py",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert payload == written
    assert payload["status"] == "pass"
    assert payload["public_safe"] is True
