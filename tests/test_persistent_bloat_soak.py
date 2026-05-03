from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_persistent_bloat_soak import (
    PRIVATE_SOAK_SENTINEL,
    build_persistent_bloat_soak_report,
)

ROOT = Path(__file__).resolve().parents[1]
SOAK_SCRIPT = ROOT / "scripts" / "run_persistent_bloat_soak.py"


def test_persistent_bloat_soak_warns_without_raw_content(tmp_path: Path) -> None:
    payload = build_persistent_bloat_soak_report(db_path=tmp_path / "soak.sqlite3", iterations=18)

    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert payload["schema"] == "brainstack.persistent_bloat_soak.v1"
    assert payload["status"] == "warn"
    assert payload["public_safe"] is True
    assert PRIVATE_SOAK_SENTINEL not in rendered
    assert payload["seed_counts"]["canonical_events"] > payload["seed_counts"]["iterations"]
    assert payload["report"]["metrics"]["support_only_accumulation"]["transcript_rows"] == 18
    assert payload["report"]["metrics"]["support_only_accumulation"]["continuity_rows"] == 18
    assert payload["report"]["metrics"]["duplicate_strength_inflation"]["canonical_duplicate_truth_groups"] >= 1
    assert "DUPLICATE_STRENGTH_INFLATION_WARN" in payload["report"]["issues"]
    assert "SUPPORT_ONLY_ACCUMULATION_WARN" in payload["report"]["issues"]


def test_persistent_bloat_soak_thresholds_can_fail_deterministically(tmp_path: Path) -> None:
    payload = build_persistent_bloat_soak_report(
        db_path=tmp_path / "soak-fail.sqlite3",
        iterations=12,
        thresholds={
            "support_only_ratio_warn": 0.5,
            "support_only_ratio_fail": 1.0,
            "duplicate_strength_warn": 0.5,
            "duplicate_strength_fail": 1.0,
        },
    )

    assert payload["status"] == "fail"
    assert "SUPPORT_ONLY_ACCUMULATION_FAIL" in payload["report"]["issues"]
    assert "DUPLICATE_STRENGTH_INFLATION_FAIL" in payload["report"]["issues"]
    assert payload["report"]["metric_statuses"]["support_only_accumulation"]["status"] == "fail"
    assert payload["report"]["metric_statuses"]["duplicate_strength_inflation"]["status"] == "fail"


def test_persistent_bloat_soak_report_is_deterministic(tmp_path: Path) -> None:
    first = build_persistent_bloat_soak_report(db_path=tmp_path / "first.sqlite3", iterations=10)
    second = build_persistent_bloat_soak_report(db_path=tmp_path / "second.sqlite3", iterations=10)

    assert first["seed_counts"] == second["seed_counts"]
    assert first["report"] == second["report"]


def test_persistent_bloat_soak_cli_writes_public_safe_artifact(tmp_path: Path) -> None:
    out = tmp_path / "soak-report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SOAK_SCRIPT),
            "--iterations",
            "8",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["schema"] == "brainstack.persistent_bloat_soak.v1"
    assert summary["public_safe"] is True
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert PRIVATE_SOAK_SENTINEL not in rendered
    assert payload["report"]["read_only"] is True
