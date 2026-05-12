from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import run_tier2_sota_gauntlet


def test_donor_fetch_retries_transient_failure(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if len(calls) == 1:
            return subprocess.CompletedProcess(cmd, 128, "", "connection reset")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(run_tier2_sota_gauntlet.subprocess, "run", fake_run)

    fetch, attempts = run_tier2_sota_gauntlet._fetch_donor_with_retry(tmp_path)

    assert fetch.returncode == 0
    assert [attempt["returncode"] for attempt in attempts] == [128, 0]
    assert calls == [["git", "fetch", "origin", "--prune", "--quiet"]] * 2
